"""Exercise the installed CLI on reviewed and accidental crawl transitions."""

import subprocess
import sys
from pathlib import Path


def main():
    directory = Path(__file__).resolve().parent
    for filename, code in (("after.txt", 0), ("broken.txt", 1)):
        print(f"Checking {filename}; expected exit {code}", flush=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "crawl_delta",
                "--before",
                str(directory / "before.txt"),
                "--after",
                str(directory / filename),
                "--contract",
                str(directory / "contract.json"),
            ],
            check=False,
        )
        if result.returncode != code:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
