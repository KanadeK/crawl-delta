import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawl_delta.cli import main
from crawl_delta.core import (
    CONTRACT_LIMIT,
    POLICY_LIMIT,
    InputError,
    check_files,
    evaluate,
    parse_contract,
    parse_policy,
    read_bounded,
)


def case(key="sample", path="/public", before=True, after=True, agent="ExampleBot"):
    return {"id": key, "path": path, "before": before, "after": after, "agent": agent}


def contract(cases=None):
    return {"version": 1, "origin": "https://example.test", "cases": cases or [case()]}


def encode(value):
    return json.dumps(value).encode()


class BehaviorTests(unittest.TestCase):
    def test_reviewed_opening_and_retained_block(self):
        c = contract(
            [case("open", "/launch", False, True), case("private", "/private/a", False, False)]
        )
        before = b"User-agent: *\nDisallow: /launch\nDisallow: /private/"
        after = b"User-agent: *\nDisallow: /private/"
        result = evaluate(before, after, encode(c))
        self.assertTrue(result["passed"])
        self.assertEqual(
            result["summary"],
            {"cases": 2, "passed": 2, "failed": 0, "opened": 1, "blocked": 0, "unchanged": 1},
        )
        self.assertEqual(result["sha256"]["before"], hashlib.sha256(before).hexdigest())

    def test_unexpected_new_block_fails(self):
        result = evaluate(b"", b"User-agent: *\nDisallow: /", encode(contract()))
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"][0]["transition"], "blocked")

    def test_unexpected_opening_fails(self):
        c = contract([case(before=False, after=False)])
        result = evaluate(b"User-agent: *\nDisallow: /", b"", encode(c))
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"][0]["transition"], "opened")

    def test_before_expectation_is_also_checked(self):
        result = evaluate(b"", b"", encode(contract([case(before=False, after=True)])))
        self.assertFalse(result["passed"])

    def test_wildcard_end_anchor_and_longest_allow(self):
        policy = b"User-agent: *\nDisallow: /*.pdf$\nAllow: /public/paper.pdf"
        c = contract(
            [
                case("blocked", "/paper.pdf", False, False),
                case("query", "/paper.pdf?download=1", True, True),
                case("allowed", "/public/paper.pdf", True, True),
            ]
        )
        self.assertTrue(evaluate(policy, policy, encode(c))["passed"])

    def test_equal_specificity_prefers_allow(self):
        policy = b"User-agent: *\nDisallow: /a\nAllow: /a"
        self.assertTrue(evaluate(policy, policy, encode(contract([case(path="/a")])))["passed"])

    def test_specific_group_and_group_merging(self):
        policy = (
            b"User-agent: *\nDisallow: /\n\nUser-agent: ExampleBot\nAllow: /one\n"
            b"\nUser-agent: examplebot\nDisallow: /two"
        )
        c = contract(
            [
                case("one", "/one"),
                case("two", "/two", False, False),
                case("other", "/one", False, False, "OtherBot"),
            ]
        )
        self.assertTrue(evaluate(policy, policy, encode(c))["passed"])

    def test_percent_encoding_and_unicode(self):
        policy = "User-agent: *\nDisallow: /café\nDisallow: /a/b".encode()
        c = contract(
            [
                case("encoded", "/caf%C3%A9", False, False),
                case("unicode", "/café", False, False),
                case("reserved", "/a%2Fb", True, True),
            ]
        )
        self.assertTrue(evaluate(policy, policy, encode(c))["passed"])

    def test_paths_are_case_sensitive(self):
        policy = b"User-agent: *\nDisallow: /Private"
        c = contract([case("upper", "/Private", False, False), case("lower", "/private")])
        self.assertTrue(evaluate(policy, policy, encode(c))["passed"])

    def test_empty_policy_allows_cases(self):
        self.assertTrue(evaluate(b"", b"", encode(contract()))["passed"])

    def test_bom_and_crlf(self):
        policy = b"\xef\xbb\xbfUser-agent: *\r\nDisallow: /secret\r\n"
        c = contract([case(path="/secret", before=False, after=False)])
        self.assertTrue(evaluate(policy, policy, b"\xef\xbb\xbf" + encode(c))["passed"])

    def test_offline_deterministic_report(self):
        with patch("socket.socket", side_effect=AssertionError("Network attempted")):
            first = evaluate(b"", b"", encode(contract()))
            second = evaluate(b"", b"", encode(contract()))
        self.assertEqual(first, second)

    def test_default_report_omits_locations(self):
        c = contract([case("case-1", "/private-person?token=example-secret", agent="PrivateBot")])
        output = json.dumps(evaluate(b"", b"", encode(c)))
        for private in ("private-person", "example-secret", "PrivateBot", "example.test"):
            self.assertNotIn(private, output)
        detailed = evaluate(b"", b"", encode(c), include_locations=True)
        self.assertEqual(detailed["results"][0]["path"], c["cases"][0]["path"])


class ValidationTests(unittest.TestCase):
    def test_json_errors(self):
        for raw in (
            b"{}",
            b"[]",
            b"{",
            b"\xff",
            b'{"version":1,"version":1}',
            b'{"x": NaN}',
            b"[" * 2000,
        ):
            with self.subTest(raw=raw[:30]), self.assertRaises(InputError):
                parse_contract(raw)

    def test_unknown_fields_and_wrong_version(self):
        for value in (0, True, "1", 2):
            c = contract()
            c["version"] = value
            with self.assertRaises(InputError):
                parse_contract(encode(c))
        c = contract()
        c["extra"] = True
        with self.assertRaises(InputError):
            parse_contract(encode(c))

    def test_origin_validation(self):
        for origin in (
            "file:///tmp",
            "https://u:p@example.test",
            "https://example.test/a",
            "https://example.test?",
            "https://example.test#",
            "https://example.test:0",
            "https://example.test:invalid",
            "https://example.test\\@elsewhere",
            "https://example.test/\n",
        ):
            c = contract()
            c["origin"] = origin
            with self.subTest(origin=origin), self.assertRaises(InputError):
                parse_contract(encode(c))

    def test_path_validation(self):
        for path in (
            "relative",
            "//elsewhere",
            "/x#fragment",
            "/x y",
            "/x\n",
            "/bad%xy",
            "/bad%",
            "/\\host",
            "/\ud800",
        ):
            with self.subTest(path=repr(path)), self.assertRaises(InputError):
                parse_contract(encode(contract([case(path=path)])))

    def test_boolean_expectations_are_strict(self):
        for value in (0, 1, None, "true", []):
            c = contract()
            c["cases"][0]["before"] = value
            with self.assertRaises(InputError):
                parse_contract(encode(c))

    def test_agent_id_and_case_fields(self):
        for field, value in (
            ("agent", ""),
            ("agent", "\n"),
            ("agent", "x" * 257),
            ("id", "bad name"),
            ("id", "\x1b[31m"),
            ("path", 1),
        ):
            c = contract()
            c["cases"][0][field] = value
            with self.assertRaises(InputError):
                parse_contract(encode(c))
        c = contract()
        c["cases"][0]["expected"] = True
        with self.assertRaises(InputError):
            parse_contract(encode(c))

    def test_duplicate_cases(self):
        for duplicate_id in (True, False):
            first = case()
            second = copy.deepcopy(first)
            if not duplicate_id:
                second["id"] = "different"
                second["agent"] = "EXAMPLEBOT"
            with self.assertRaises(InputError):
                parse_contract(encode(contract([first, second])))

    def test_empty_case_list(self):
        c = contract()
        c["cases"] = []
        with self.assertRaises(InputError):
            parse_contract(encode(c))

    def test_byte_and_case_limits(self):
        with self.assertRaises(InputError):
            parse_contract(b" " * (CONTRACT_LIMIT + 1))
        with self.assertRaises(InputError):
            parse_policy(b"x" * (POLICY_LIMIT + 1))
        c = contract()
        c["cases"] = [case(str(n), f"/{n}") for n in range(5001)]
        with self.assertRaises(InputError):
            parse_contract(encode(c))

    def test_bad_policies(self):
        for raw in (b"\xff", b"\0", b"<html>not robots</html>", b"#" + b"x" * 8192):
            with self.assertRaises(InputError):
                parse_policy(raw)

    def test_file_errors(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "missing"
            with self.assertRaises(InputError):
                read_bounded(path, 1)
            path.write_bytes(b"xx")
            with self.assertRaises(InputError):
                read_bounded(path, 1)

    def test_cli_and_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            before, after, plan = (root / n for n in ("before", "after", "contract"))
            before.write_bytes(b"")
            after.write_bytes(b"")
            plan.write_bytes(encode(contract()))
            original = {p: p.read_bytes() for p in (before, after, plan)}
            self.assertTrue(check_files(before, after, plan)["passed"])
            for filename, expected in ((after, 0), (root / "missing", 2)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    code = main(
                        [
                            "--before",
                            str(before),
                            "--after",
                            str(filename),
                            "--contract",
                            str(plan),
                            "--format",
                            "json",
                        ]
                    )
                self.assertEqual(code, expected)
                if expected == 0:
                    self.assertTrue(json.loads(out.getvalue())["passed"])
            self.assertEqual(original, {p: p.read_bytes() for p in original})
            after.write_bytes(b"User-agent: *\nDisallow: /")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["--before", str(before), "--after", str(after), "--contract", str(plan)]),
                    1,
                )


if __name__ == "__main__":
    unittest.main()
