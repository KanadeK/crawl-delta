"""Finite before/after crawl policy contracts. No network access."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from protego import Protego

POLICY_LIMIT = 512 * 1024
CONTRACT_LIMIT = 2 * 1024 * 1024
CASE_LIMIT = 5000


class InputError(ValueError):
    """Invalid input, without echoing private values."""


def read_bounded(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as exc:
        raise InputError("Input file cannot be read") from exc
    if len(data) > limit:
        raise InputError("Input exceeds its documented byte limit")
    return data


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("Duplicate JSON member")
        result[key] = value
    return result


def invalid_constant(_):
    raise InputError("Non-finite JSON number")


def parse_contract(raw: bytes) -> dict:
    if len(raw) > CONTRACT_LIMIT:
        raise InputError("Contract exceeds byte limit")
    try:
        contract = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=strict_object,
            parse_constant=invalid_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError("Contract must be strict UTF-8 JSON with unique members") from exc
    if not isinstance(contract, dict) or set(contract) != {"version", "origin", "cases"}:
        raise InputError("Contract requires exactly version, origin and cases")
    if type(contract["version"]) is not int or contract["version"] != 1:
        raise InputError("Unsupported contract version")
    origin = contract["origin"]
    if (
        not isinstance(origin, str)
        or len(origin) > 2048
        or any(ord(c) <= 32 or ord(c) >= 127 for c in origin)
    ):
        raise InputError("Origin must be an ASCII HTTP(S) origin")
    try:
        parsed = urlsplit(origin)
        port = parsed.port
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or "?" in origin
            or "#" in origin
            or "\\" in parsed.netloc
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError
    except ValueError as exc:
        raise InputError("Origin must have no credentials, route, query or fragment") from exc
    contract["origin"] = origin.rstrip("/")
    cases = contract["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= CASE_LIMIT:
        raise InputError("Contract requires between 1 and 5000 cases")
    ids, pairs = set(), set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "agent", "path", "before", "after"}:
            raise InputError("Case requires exactly id, agent, path, before and after")
        key, agent, path = case["id"], case["agent"], case["path"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", key):
            raise InputError(
                "Case id must use 1–128 ASCII letters, digits, dots, dashes or underscores"
            )
        if key in ids:
            raise InputError("Duplicate case id")
        ids.add(key)
        if (
            not isinstance(agent, str)
            or not 1 <= len(agent) <= 256
            or not agent.strip()
            or any(ord(c) < 32 or ord(c) >= 127 for c in agent)
        ):
            raise InputError(
                "Agent must be a nonempty printable ASCII string, at most 256 characters"
            )
        if (
            not isinstance(path, str)
            or not 1 <= len(path) <= 8192
            or not path.startswith("/")
            or path.startswith("//")
            or "#" in path
            or "\\" in path
            or any(ord(c) <= 32 or ord(c) == 127 for c in path)
            or re.search(r"%(?![0-9a-fA-F]{2})", path)
        ):
            raise InputError(
                "Case path must be an absolute route/query without fragment or controls"
            )
        try:
            path.encode("utf-8")
        except UnicodeError as exc:
            raise InputError("Case path contains an invalid Unicode scalar") from exc
        pair = (agent.lower(), path)
        if pair in pairs:
            raise InputError("Duplicate agent/path case")
        pairs.add(pair)
        if type(case["before"]) is not bool or type(case["after"]) is not bool:
            raise InputError("before and after expectations must be JSON booleans")
    return contract


def parse_policy(raw: bytes):
    if len(raw) > POLICY_LIMIT:
        raise InputError("Policy exceeds 512 KiB; it will not be silently truncated")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise InputError("Policy must be UTF-8") from exc
    if "\0" in text or any(len(line) > 8192 for line in text.splitlines()):
        raise InputError("Policy contains a NUL or line longer than 8192 characters")
    if text.lstrip().startswith("<"):
        raise InputError("Policy looks like HTML rather than robots.txt")
    return Protego.parse(text)


def transition(before: bool, after: bool) -> str:
    if before == after:
        return "unchanged"
    return "opened" if after else "blocked"


def evaluate(before: bytes, after: bytes, raw_contract: bytes, *, include_locations=False) -> dict:
    contract = parse_contract(raw_contract)
    old, new = parse_policy(before), parse_policy(after)
    results = []
    summary = {
        "cases": len(contract["cases"]),
        "passed": 0,
        "failed": 0,
        "opened": 0,
        "blocked": 0,
        "unchanged": 0,
    }
    for case in contract["cases"]:
        url = contract["origin"] + case["path"]
        old_allowed = old.can_fetch(url, case["agent"])
        new_allowed = new.can_fetch(url, case["agent"])
        observed = transition(old_allowed, new_allowed)
        passed = old_allowed == case["before"] and new_allowed == case["after"]
        summary["passed" if passed else "failed"] += 1
        summary[observed] += 1
        result = {
            "id": case["id"],
            "passed": passed,
            "expected": {"before": case["before"], "after": case["after"]},
            "observed": {"before": old_allowed, "after": new_allowed},
            "transition": observed,
        }
        if include_locations:
            result.update({"agent": case["agent"], "path": case["path"]})
        results.append(result)
    return {
        "schema_version": 1,
        "tool_version": "0.1.0",
        "parser": "protego",
        "parser_version": version("protego"),
        "passed": summary["failed"] == 0,
        "sha256": {
            label: hashlib.sha256(data).hexdigest()
            for label, data in (("before", before), ("after", after), ("contract", raw_contract))
        },
        "summary": summary,
        "results": results,
    }


def check_files(before: Path, after: Path, contract: Path, *, include_locations=False) -> dict:
    return evaluate(
        read_bounded(before, POLICY_LIMIT),
        read_bounded(after, POLICY_LIMIT),
        read_bounded(contract, CONTRACT_LIMIT),
        include_locations=include_locations,
    )
