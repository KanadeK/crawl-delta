import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, check_files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gate a reviewed robots.txt policy transition")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--include-locations",
        action="store_true",
        help="Include potentially private routes and agents in JSON",
    )
    args = parser.parse_args(argv)
    try:
        result = check_files(
            args.before, args.after, args.contract, include_locations=args.include_locations
        )
    except InputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
    else:
        for case in result["results"]:
            status = "PASS" if case["passed"] else "FAIL"
            print(
                f"{status} {case['id']}: {case['transition']}; "
                f"expected {case['expected']}, observed {case['observed']}"
            )
        print(f"Contract: {result['summary']['passed']}/{result['summary']['cases']} passed")
    return 0 if result["passed"] else 1
