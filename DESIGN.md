# Design and review

User: site maintainers reviewing a launch, migration or crawl-policy change.
Workflow: retain old policy → review concrete before/after expectations → edit policy →
run contract → fix unexpected changes → use the same command as a CI gate.

The project validates a closed JSON schema, loads bounded UTF-8 policies, calls Protego's
public matcher twice per case, evaluates both decisions and emits a deterministic report.
Policy syntax and URL matching remain the dependency's responsibility. No matcher internals
are copied or accessed. Inputs are hashed before decoding, binding evidence to exact bytes.

Review gates include strict JSON booleans, duplicate detection, finite nonempty cases,
route/origin validation, Unicode scalar validation and explicit oversize rejection.
Tests prove intended and accidental changes, equal-specificity Allow behavior, group
merging, wildcards, encoded paths, optional BOM, no network, stable output and unchanged files.

The parser is BSD-3-Clause, compatible with this project's MIT code. Its original license
is preserved in THIRD_PARTY_NOTICES.md and its installed wheel; it has no transitive runtime
dependencies. Pinning provides reproducibility but requires intentional maintenance when
security or semantics change. The CLI uses only the three public matching interfaces:
`Protego.parse`, `Protego.can_fetch`, and package-version metadata.

Volume bounds are not a CPU sandbox. Protego and Python must be kept maintained; CI has
a job timeout. Reports omit routes by default, but hashes and user-chosen case IDs are
not anonymization. Finite fixtures do not prove a policy correct for unlisted routes.
