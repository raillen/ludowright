# Project Audit CLI

Run a deterministic, read-only readiness audit from the project marker:

```bash
ludowright audit ./my-game
ludowright audit ./my-game --dry-run
ludowright audit ./my-game --check
ludowright --json audit ./my-game --check
```

Human output uses Rich and shows the project, overall state, category table,
stable finding codes, and remediation context. JSON output uses the published
`cli-response` envelope. The `data` object is the complete `project-audit`
report, including source evidence, findings, warnings, the schema version, and
the deterministic source digest.

`--check` exits with code `1` when the report is `needs-review` or `blocked`.
Without `--check`, an audit that successfully inspected the project exits `0`
even when the report contains findings. Expected input, corruption, and
concurrency failures use the existing CLI semantic codes and exit codes:

| Condition | Error code | Exit |
|---|---|---:|
| Project changes while reading | `conflict` | 5 |
| Invalid or unsafe persisted project state | `corrupt-state` | 6 |
| Other audit input failure | `invalid-input` | 4 |

The command never overwrites existing artifacts and does not modify the event
log, dependency graph, approvals, references, sheets, package files, or
SQLite state. A source mutation during the audit invalidates the whole report
and must be retried after the writer finishes.
