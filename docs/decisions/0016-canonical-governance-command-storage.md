# ADR 0016: Canonical governance command storage and audit coordination

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `DECISIONS_AND_APPROVALS.md`, `STRUCTURED_REPOSITORIES.md`, `EVENT_LOG.md`, `DEPENDENCY_GRAPH.md`, `CLI.md`

## Context

The domain already defines immutable decision and approval histories, but the
first command layer needs a repository convention and a safe way to coordinate
multiple canonical resources. Without one convention, list and inspect commands
would need to discover arbitrary files, while a mutation could update a JSON
history without updating its dependency node or audit trail.

The project filesystem and structured repositories provide atomic single-file
writes and per-document locks. They do not provide a transaction spanning a
governance document, the dependency graph, and the event log.

## Decision

LudoWright stores governance records at:

```text
decisions/<decision-id>.json
approvals/<approval-id>.json
```

The paths are built only from typed canonical IDs and `RepositoryPath`. Listing
rejects symbolic links and unsafe JSON names. `record` and `request` are
create-only; existing records are never silently replaced.

The application service coordinates a mutation under the project lock
`governance-write`:

1. validate external input through the published Pydantic contract and domain;
2. create or replace the immutable JSON history atomically;
3. add or advance the corresponding `decision` or `approval` dependency node;
4. append a namespaced event to the hash-chained event log;
5. restore the changed document and graph when a later step fails and restoration
   is still safe.

Repeated domain transitions are no-ops and do not append audit events. A
supersession always references a separately recorded replacement aggregate.

The SQLite state store remains derived. It is not a second governance source of
truth and this command layer does not duplicate decision or approval histories in
database tables.

## Consequences

### Positive

- paths are deterministic, portable, and reviewable in Git;
- domain history and persisted contracts use the same validation rules;
- graph nodes expose governance revisions to future invalidation workflows;
- event records preserve operational audit evidence;
- create-only commands protect existing records;
- the project lock serializes LudoWright governance writers;
- partial failures attempt an explicit rollback instead of leaving a new record
  without its graph or audit event.

### Trade-offs

- the coordination protocol is not a cross-resource transaction;
- an unrecoverable filesystem or process failure can still require structural
  audit and explicit repair guidance;
- event IDs and timestamps are operational metadata and are not deterministic
  content identities;
- SQLite indexes must remain rebuildable from canonical files and events.

## Compatibility and migration

This decision introduces the `decisions/` and `approvals/` repository conventions
but does not change the published `decision` or `approval` schema version. Future
path or storage changes require migration or dual-read behavior, fixtures, and an
ADR. Existing domain contracts remain schema version 1.

## Security

All paths pass through the repository-relative filesystem boundary. Traversal,
absolute paths, unsafe names, symlink ancestors, symlink targets, and non-regular
governance files are rejected. Human labels remain structured data and are never
used as filenames. Approval records bind a typed subject to an immutable
fingerprint; an approval state does not itself grant authorization.

## Validation

- repository round trips and create conflicts;
- deterministic listing and complete history inspection;
- valid and invalid domain transitions;
- graph revision and event-chain updates;
- rollback after an event failure;
- symlink rejection;
- Rich output, JSON envelopes, and semantic errors;
- full quality gate and schema publication checks.
