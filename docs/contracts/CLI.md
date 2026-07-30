# Command-Line Interface Contract

## Purpose

The LudoWright CLI serves both humans and automation. Human output uses Rich for readable tables, emphasis, and status labels. Machine output uses one stable JSON envelope across commands.

The foundation provides:

- Typer command routing;
- Rich human-readable output;
- global and command-local JSON mode;
- a published JSON response schema;
- stable command error categories;
- stable process exit codes;
- version output;
- non-mutating runtime diagnostics;
- reusable error mapping for future project commands.

The implementation lives in:

```text
src/ludowright/cli/app.py
src/ludowright/cli/runtime.py
src/ludowright/cli/diagnostics.py
src/ludowright/cli/quality.py
src/ludowright/contracts/cli.py
```

Governance commands reuse this contract:

```bash
ludowright decision record PATH --id camera-choice --title "Isometric camera"
ludowright --json decision list PATH
ludowright approval request PATH --id front-review \
  --subject-kind reference --subject-id maya-front --revision sha256:abc123
```

The command-specific `data` contains canonical relative paths, typed IDs,
current status, history length, and the event sequence for mutations. Decision
and approval records are stored in `decisions/` and `approvals/`; their published
contract schemas remain version 1. See [`commands/GOVERNANCE.md`](../commands/GOVERNANCE.md)
for the complete command surface.

## Human and machine surfaces

Human mode is the default:

```text
ludowright status
ludowright diagnostics
ludowright quality check --dry-run
```

Machine mode may be selected globally before a subcommand:

```text
ludowright --json status
ludowright --json diagnostics
```

or locally after a command:

```text
ludowright status --json
ludowright diagnostics --json
ludowright quality check --json
```

Global settings are inherited by nested command groups.

## JSON envelope

Every successfully parsed command in JSON mode emits one compact JSON object to standard output:

```json
{
  "schema_version": 1,
  "kind": "cli-response",
  "command": "status",
  "ok": true,
  "data": {
    "status": "foundation",
    "version": "0.1.0.dev0"
  },
  "error": null,
  "meta": {
    "ludowright_version": "0.1.0.dev0",
    "output": "json"
  }
}
```

The checked-in schema is:

```text
schemas/v1/cli-response.schema.json
```

A compatibility fixture lives at:

```text
tests/fixtures/contracts/v1/cli-response.json
```

## Envelope fields

| Field | Meaning |
|---|---|
| `schema_version` | Version of the response envelope contract |
| `kind` | Always `cli-response` |
| `command` | Canonical parsed command name, such as `quality check` |
| `ok` | Whether the command completed successfully |
| `data` | Command-specific JSON-compatible result, including partial failure results when useful |
| `error` | Stable error object or `null` |
| `meta` | LudoWright version and output format |

A successful response requires `error: null`. A failed response requires an error object. Failed commands may retain structured `data`, such as the complete list of quality-check results.

## Canonical JSON

JSON responses are:

- UTF-8;
- compact, without presentation whitespace;
- key-sorted;
- terminated by the CLI output stream newline;
- free of ANSI styling;
- validated for JSON-compatible values;
- limited to 64 nesting levels and 100,000 values per `data` or `details` object;
- rejected when they contain non-finite numbers or unsupported Python values.

Deterministic output helps tests, shell integrations, Codex tools, caching, and future compatibility checks.

## Error object

A JSON failure contains:

```json
{
  "code": "checks-failed",
  "message": "One or more quality checks failed.",
  "details": {
    "failed_checks": ["tests"]
  }
}
```

Initial stable error codes are:

| Code | Meaning |
|---|---|
| `checks-failed` | One or more requested verification checks failed |
| `invalid-input` | A parsed value violates a canonical domain contract |
| `project-not-found` | A command requires a project but none can be discovered |
| `conflict` | Optimistic concurrency or another explicit state conflict occurred |
| `corrupt-state` | Persisted project state cannot be safely parsed or replayed |
| `blocked` | A known prerequisite prevents the requested operation |
| `internal-error` | Reserved for controlled top-level handling of unexpected defects |

Error codes are stable API values. Human messages may become clearer without changing the code.

## Process exit codes

Parsed commands use these stable exit codes:

| Exit code | Name | Meaning |
|---:|---|---|
| `0` | success | Command completed successfully |
| `1` | checks failed | Verification ran but one or more checks failed |
| `2` | usage | Typer or Click rejected command syntax or options |
| `3` | not found | Required project or resource was not found |
| `4` | validation | Parsed input violates a canonical contract |
| `5` | conflict | State changed concurrently or conflicts with the request |
| `6` | corrupt state | Persisted state is invalid or unsafe to continue with |
| `7` | blocked | A known workflow prerequisite blocks progress |
| `70` | internal | Reserved unexpected internal software failure |

Shell integrations must use the process code for broad control flow and the JSON error code for precise behavior.

Parser-level usage errors are produced by Typer and Click before a command callback runs. They use exit code 2 and human usage text. The JSON envelope applies after successful command parsing.

## Expected exception mapping

The shared runtime maps known failures without hiding unexpected programming defects:

- project root discovery failure → `project-not-found`, exit 3;
- structured-document conflict → `conflict`, exit 5;
- corrupt event log, state store, or structured document → `corrupt-state`, exit 6;
- domain validation error → `invalid-input`, exit 4;
- explicit `CliFailure` → its declared code and exit code.

Unrecognized exceptions are re-raised during command execution. They must not be silently converted into a successful or generic result.

## Quality gates

Quality commands retain complete check results in `data`.

Successful dry run:

```text
command: quality check
ok: true
exit: 0
```

Failed executed gate:

```text
command: quality check
ok: false
error.code: checks-failed
exit: 1
```

This separates a valid verification result from input, project, corruption, or internal failures.

## Version

Human version output remains intentionally minimal:

```text
ludowright --version
```

prints only the installed version.

Machine version output uses:

```text
ludowright --json --version
```

and returns the standard envelope with `command: version`.

## Diagnostics

`ludowright diagnostics` reports:

- installed LudoWright version;
- Python implementation, version, and executable;
- operating-system system, release, and machine;
- whether the nearest LudoWright project marker can be discovered;
- discovered project root when present.

Diagnostics are read-only. Being outside a project is a successful diagnostic state, not an error.

Paths and platform information may be sensitive when copied into public bug reports. Users should review diagnostic output before sharing it.

## Color policy

Human output may use Rich styling. `--no-color` disables ANSI color output:

```text
ludowright --no-color diagnostics
```

JSON output never contains Rich markup or ANSI sequences.

## Compatibility policy

The CLI JSON envelope is a published contract.

A new schema version is required for incompatible changes such as:

- removing or renaming envelope fields;
- changing success/error exclusivity;
- changing the meaning of `ok`;
- changing error object shape;
- narrowing command-data JSON compatibility;
- changing canonical serialization semantics.

Adding a new error code or new command-specific `data` field requires tests and documentation but does not necessarily require a new envelope version.

Exit-code meanings must remain stable. A command may begin using an existing more precise code when its behavior is documented and covered by contract tests.

## Security and failure policy

The CLI contract:

- never puts Rich markup inside JSON;
- rejects non-JSON values and non-finite numbers;
- bounds response data and error detail complexity;
- does not expose tracebacks for expected failures;
- does not swallow unexpected exceptions inside command callbacks;
- keeps diagnostics read-only;
- avoids treating missing optional project context as corruption;
- preserves command failure data for auditing.

Future commands must use the shared runtime rather than inventing command-specific JSON envelopes or exit-code conventions.
