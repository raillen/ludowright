# Structural Audit Contract

## Purpose

`ludowright audit PATH` is a read-only verification command for the local
project boundary. It checks the minimum canonical state needed to trust a
project after interruption, manual edits, migration, or a long period away.

The audit does not repair files, initialize missing components, migrate
SQLite, truncate an event log, or rewrite an approved artifact.

## Checked components

The first audit covers these canonical paths:

| Component | Path | Expected version |
|---|---|---:|
| manifest | `.ludowright/project.json` | 1 |
| event log | `.ludowright/events.jsonl` | 1 |
| dependency graph | `.ludowright/dependency-graph.json` | 1 |
| state store | `.ludowright/state.sqlite3` | 2 |

Each path is resolved through `ProjectFilesystem`. Missing files, symlinks,
non-regular entries, and paths that cannot be safely read become findings.

The event log is replayed with its existing hash-chain and incomplete-tail
rules. The graph and manifest are loaded through their published structured
repositories. SQLite is opened through `StateStore(read_only=True)` and is
never initialized or migrated by the audit. A live WAL is reported as an
unavailable read-only snapshot; writers must stop before repeating the audit.

## Approved-file mutation detection

The current infrastructure identifies an approved source through an
`indexed_entity` row whose status is `approved`. Its exact digest is compared
with the current source file. A changed, missing, or unsafe approved source
produces a dedicated finding rather than silently accepting the mutation.

Future approval and reference repositories may add richer provenance, but they
must preserve this exact-byte comparison rule and must not weaken the audit.

## Finding contract

Findings are deterministic and sorted by component, path, and code. Each
finding contains:

- `code`: stable machine-readable diagnostic;
- `severity`: `error` or `warning`;
- `component`: canonical component name;
- `path`: canonical repository-relative path when applicable;
- `detail`: human-readable explanation;
- `repair_code`: stable non-automatic repair guidance identifier.

Initial codes include:

- `manifest-missing`, `manifest-corrupt`, `manifest-version-mismatch`;
- `event-log-missing`, `event-log-corrupt`, `event-log-incomplete-tail`;
- `dependency-graph-missing`, `dependency-graph-corrupt`,
  `dependency-graph-version-mismatch`;
- `state-store-missing`, `state-store-corrupt`,
  `state-store-version-mismatch`;
- `state-index-empty-index`, `state-index-behind`,
  `state-index-diverged`;
- `canonical-source-changed`, `canonical-source-missing`,
  `canonical-source-invalid-path`, `canonical-source-unreadable`;
- `approved-file-mutated`, `approved-file-missing`,
  `approved-file-unsafe-path`.

Repair guidance describes a future or manual operation. It is advice, not an
automatic command execution contract.

## CLI behavior

Human mode uses Rich:

```bash
ludowright audit ./my-game
```

JSON mode uses the published `cli-response` envelope:

```bash
ludowright --json audit ./my-game
```

The command returns exit code `0` with `ok: true` only when no finding exists.
Verification findings return `checks-failed` and exit code `1`, while retaining
the complete audit data in the response. A missing project root uses the
existing `project-not-found` / exit `3` contract.

The result data includes the absolute discovered project directory, optional
project identity, `read_only: true`, component states, observed and expected
versions, findings, and deterministic repair guidance.

## Compatibility and security

The audit adds no persisted file format and no new JSON Schema version. Its
result is command data inside the existing CLI envelope. Adding or removing
finding codes is a public CLI compatibility change and requires tests and
documentation.

The audit is intentionally fail-closed around symlinks, malformed structured
documents, invalid event history, unsupported state versions, active SQLite
WAL snapshots, and approved-source digest changes.
