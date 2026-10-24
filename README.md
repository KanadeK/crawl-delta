# crawl-delta

[![CI](https://github.com/KanadeK/crawl-delta/actions/workflows/ci.yml/badge.svg)](https://github.com/KanadeK/crawl-delta/actions/workflows/ci.yml)

Gate a robots.txt change against a **reviewed before → after contract**, entirely offline.
Catch an accidental launch-wide block or newly exposed crawl route before deploying.
Python 3.11+, one pinned runtime dependency: [Protego](https://github.com/scrapy/protego).

[中文说明](README.zh-CN.md) · [Design](DESIGN.md) · [Dependency notices](THIRD_PARTY_NOTICES.md)

## Why a transition contract?

A plain text diff cannot tell you whether a specific crawler can still reach a page.
A single-policy expected-result test also does not record which old behavior was reviewed.
This tool checks both decisions and labels observed transitions `opened`, `blocked` or
`unchanged`. The report binds both policy files and the contract with SHA-256 hashes.

The matcher is Protego 0.7.0, whose public API supports RFC 9309 parsing and matching.
This project supplies contract validation, transition evaluation, evidence and a CI gate;
it does not reimplement the matcher or fetch robots.txt.

## Installation and first run

```sh
git clone https://github.com/KanadeK/crawl-delta.git
cd crawl-delta
python -m venv .venv
```

Install using the virtual environment's Python:

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe examples/demo.py
```

```sh
# macOS/Linux
.venv/bin/python -m pip install .
.venv/bin/python examples/demo.py
```

The demo invokes the installed CLI on real files: a reviewed launch change must pass,
then an accidental `Disallow: /` must fail. It needs no network after dependencies are installed.
For direct use, activate the venv or use its `crawl-delta` executable:

```sh
crawl-delta --before examples/before.txt --after examples/after.txt --contract examples/contract.json
crawl-delta --before examples/before.txt --after examples/after.txt --contract examples/contract.json --format json
```

Release wheels are also available from [Releases](https://github.com/KanadeK/crawl-delta/releases).
This project is not published to PyPI. Dependency installation requires PyPI or a local wheel cache.

## Contract format

```json
{
  "version": 1,
  "origin": "https://example.test",
  "cases": [
    {"id": "launch", "agent": "ExampleBot", "path": "/launch/product", "before": false, "after": true},
    {"id": "private", "agent": "ExampleBot", "path": "/private/account", "before": false, "after": false}
  ]
}
```

`origin` supplies URL parsing context only; no request is made. `path` is one concrete
route, optionally with a query, rather than a case-generation pattern. Unicode and valid
percent encoding are accepted. `agent` is a product token or printable User-Agent value.
Expectations must be JSON booleans. Unknown keys, duplicate JSON members, repeated IDs,
repeated agent/path pairs, malformed origins and empty test suites fail as input errors.

Review expected behavior before editing the contract. Copying observed output into
expectations without review defeats the gate. A failure of the **before** expectation
also fails the contract, even when the new policy matches its expectation.

## Reports, privacy and exits

JSON results contain case IDs, expected/observed booleans, transitions, summary counts,
the exact parser version and three input hashes. Identical inputs produce identical output
with that parser version. File names, origin, agents and route strings are omitted by default.
`--include-locations` explicitly includes agents and routes in JSON for local debugging.
Case IDs and hashes can still reveal information; select neutral IDs and review reports.

* `0`: every before and after expectation passed.
* `1`: at least one expectation failed.
* `2`: invalid or unreadable input; no passing report is produced.

No input is changed, no report file is written automatically, and there is no telemetry.
Redirect stdout yourself if a persisted report is needed. HTTP credentials and network
fetching are deliberately outside this command's workflow.

## Limits

Policies: strict UTF-8 (optional BOM), at most 512 KiB each and 8,192 characters per line.
Contract: at most 2 MiB, 5,000 cases, routes at most 8,192 characters. Oversized inputs
are rejected, never silently truncated. These bound input volume, not worst-case CPU
time in a third-party matcher; use a CI job timeout for untrusted policy files.

Only the supplied finite cases are proven. No complete URL-space equivalence, crawl
prediction, ranking guarantee, syntax certification, sitemap validation or rate-limit
extension checks are claimed. RFC-compatible tolerant parsing may ignore unknown or
malformed directives; this is not a strict robots syntax linter. Obvious HTML input is rejected.
Empty robots.txt is valid and allows access, so include blocked-route cases in the contract.
HTTP status, redirect and cache rules for fetching robots.txt are out of scope.

Robots rules are advisory crawler instructions and do not enforce access control.
See [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) and
[Google's site migration checklist](https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes).

## Alternatives

[robots-txt-tester](https://github.com/cgrantnz/robots-txt-tester) already offers URL
expectations and JUnit output. Use it for that workflow. Google Search Console and
browser testers help inspect deployed sites. crawl-delta adds a reviewed **pair of
decisions**, explicit exposure/blocking transitions and location-minimized hash-bound
reports in a Python CLI. It uses Protego under BSD-3-Clause; dependency authors retain
their original copyrights. No competitor implementation was copied.

## Development and cleanup

```sh
python -m pip install -e . ruff==0.17.2 build==1.6.1
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
python -m pip uninstall crawl-delta
```

Run development commands in an activated venv. Remove the venv to also remove its
dependency installation. Delete your redirected reports and clone when no longer needed.
Original project code is MIT licensed; third-party notices are included separately.
