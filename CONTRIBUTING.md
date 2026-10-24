# Contributing

Start with an issue describing the user problem and a minimal synthetic reproduction.
Please keep private files, tokens and identifying production data out of examples.
Run `python -m unittest discover -s tests -v`, `ruff check .` and `ruff format --check .`.
Tests must exercise observable behavior and failure paths. Documentation must state limits.
This initial release uses maintainer-authored commits. Automatic dependency commits,
automatic PR merges, and workflow write permissions are disabled.
Third-party code must retain its license and attribution; never present it as original work.
