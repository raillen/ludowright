# Project Audit Contract

`ludowright audit PROJECT` is the read-only readiness boundary between project
state and release verification. It inspects the current product chain:

```text
product → documents → assets → references → jobs → approvals → sheets → package
```

The command does not repair, migrate, regenerate, approve, or package files.
It validates each available canonical or derived source and returns a v1
`project-audit` report with:

- the discovered `ProjectId` and project name;
- the schema version and deterministic source digest;
- current, missing, or invalid source evidence;
- per-category item counts, state, and error/warning counts;
- sorted findings with stable codes, paths, related IDs, and remediation;
- deterministic recommended actions.

## States and severity

`ready` means that the inspected chain has no findings. `needs-review` means
that the report contains warnings. `blocked` means that at least one error
prevents a readiness claim. `valid` is true only for `ready`.

The audit checks the current state-store schema (`PRAGMA user_version = 2`),
replays the event log, validates the dependency graph, and opens SQLite using
an immutable read-only connection. An active SQLite WAL is treated as an
unsafe concurrent state and produces a blocking product finding. No state
store sidecar is created by an audit.

## Determinism and concurrency

Files, findings, categories, actions, and source evidence are sorted by their
published contracts. The audit records SHA-256 digests and checks the file
inventory and every observed source again before publishing the report. A
change during the audit is a `conflict`, not a partially trusted report.

The report's `dry_run` field records the caller's explicit mode. Both modes
are read-only today; `--dry-run` is retained as an explicit automation and
future-compatibility signal.

The persisted contract and schema are:

```text
src/ludowright/contracts/project_audit.py
schemas/v1/project-audit.schema.json
tests/fixtures/contracts/v1/project-audit.json
```
