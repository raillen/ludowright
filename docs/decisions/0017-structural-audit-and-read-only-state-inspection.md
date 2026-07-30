# ADR 0017: Read-only structural audit and SQLite inspection

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `STRUCTURAL_AUDIT.md`, `STATE_STORE.md`, `CLI.md`

## Context

Project initialization and later application workflows write several canonical
components: a manifest, an event log, a dependency graph, and a derived SQLite
state store. A process interruption or an external edit can leave those
components inconsistent even when each individual file still exists.

The first lifecycle audit must be safe to run during diagnosis. Constructing a
normal `StateStore` may initialize a missing database or enable WAL, which is a
write-side effect and cannot be used by a read-only verification command.

## Decision

Add `ludowright audit PATH` as a read-only structural verification command.

The application service checks canonical paths through `ProjectFilesystem`,
reuses the existing structured repositories, replays the event log, validates
the dependency graph, and compares state-store source digests and event
checkpoints. It returns deterministic findings and non-automatic repair
guidance through the existing CLI envelope.

`StateStore(read_only=True)` is a strict inspection mode:

- it never creates parent directories or a database;
- it rejects missing databases and active WAL files;
- it opens SQLite with an immutable read-only URI;
- it validates the current supported schema and strict tables;
- it refuses every mutating public operation;
- it preserves the existing state-store version and migration rules.

Approved-file mutations are detected when a derived `indexed_entity` record is
marked `approved` and its exact source digest no longer matches. The audit
reports the mutation and recommends a new revision or explicit restoration.

Verification findings use the existing `checks-failed` category and exit code
`1`; a missing project root retains `project-not-found` and exit code `3`.

## Alternatives considered

### Open the normal state store

Rejected because initialization and WAL configuration can mutate a project
during an operation explicitly documented as read-only.

### Query SQLite directly in the application service

Rejected because it would duplicate state-store path, schema, row, and
consistency rules outside the infrastructure boundary.

### Repair during audit

Rejected because corruption and approved-file changes require evidence
preservation, explicit migration or recovery policy, and a separate command.

### Treat findings as successful output

Rejected because automation needs a stable non-zero verification result while
still receiving the full structured report.

## Consequences

The audit can be run safely by humans, CI, and Codex without hidden state or
automatic data loss. Active writers must be quiesced before SQLite inspection,
and repairs remain future bounded commands. The `StateStore` API gains one
explicit read-only mode that is now part of its compatibility surface.
