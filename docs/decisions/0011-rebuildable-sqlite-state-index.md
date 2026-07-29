# ADR 0011: Rebuildable SQLite State Index

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `STATE_STORE.md`, `EVENT_LOG.md`, `STRUCTURED_REPOSITORIES.md`, `PROJECT_FILESYSTEM.md`

## Context

LudoWright needs fast indexed access to workflow progress, canonical entity metadata, and the event revision already incorporated into derived state.

Human-editable JSON and YAML files remain the canonical source for product data where practical. The append-only event log records significant operations and ordering. Neither surface is optimized for repeated queries such as:

- list active workflows by status;
- resume one guided operation;
- find indexed entities by type;
- determine whether an entity source changed after indexing;
- determine whether the local index is behind or divergent from the event log.

Making SQLite the only source of product truth would conflict with the documented architecture, reduce inspectability, and couple migrations to every domain change. Avoiding SQLite entirely would force repeated full-file scans and ad hoc caches.

## Decision

LudoWright introduces a local SQLite database at:

```text
.ludowright/state.sqlite3
```

The database is a **rebuildable derived index**.

It stores:

- resumable workflow progress;
- indexed canonical entity paths, revisions, statuses, and exact source digests;
- one checkpoint for the event-log revision incorporated into the index.

It does not replace canonical project files or the append-only event log.

## Authority decision

SQLite is authoritative only for transient operational state that has no separate canonical representation, such as the cursor of an unfinished workflow.

Important decisions, approvals, asset definitions, reference states, generation metadata, and project facts must continue to exist in their canonical contracts and event history.

Deleting the database may remove local progress and indexes. It must never delete or rewrite canonical files or events.

## SQLite configuration

Every connection enables:

- foreign keys;
- WAL journal mode;
- full synchronous durability;
- in-memory temporary storage;
- disabled trusted schema;
- a configured busy timeout.

WAL supports concurrent readers and serialized local writers. Full synchronous mode favors durable project metadata over maximum write throughput.

## Schema decision

The initial database schema uses:

```text
PRAGMA user_version = 1
```

The version contains three strict tables:

- `workflow_progress`;
- `indexed_entity`;
- `event_checkpoint`.

Unknown non-zero schema versions are rejected. Migration is not guessed or performed automatically; the next bounded PR introduces the migration framework.

## Transaction decision

Every public store method opens a fresh connection and a short explicit transaction.

Reads use a read transaction and query-only mode. Writes use `BEGIN IMMEDIATE` so writer contention is resolved before application work proceeds.

Successful operations commit. Exceptions roll back. Connections are closed after each operation.

The API does not expose arbitrary SQL or long-lived public connections.

## Workflow progress decision

One row per workflow stores:

- canonical workflow ID and type;
- canonical status and optional step;
- canonical JSON context;
- optional source event sequence;
- canonical UTC timestamp.

Workflow context is deeply immutable at the Python boundary.

Product decisions must not be hidden only inside workflow context.

## Entity-index decision

One row per `(entity_type, entity_id)` stores:

- canonical repository-relative source path;
- SHA-256 of exact source bytes;
- positive source revision;
- status;
- canonical UTC timestamp.

Exact-byte digests intentionally report formatting-only file edits as changes. The index identifies the source revision actually observed, not merely a semantically equivalent model.

## Event-checkpoint decision

The singleton event checkpoint stores:

- terminal indexed sequence;
- terminal indexed event hash;
- digest of the complete event-log bytes;
- canonical UTC timestamp.

Consistency checks distinguish:

- fully synchronized;
- no checkpoint for a non-empty log;
- safely behind a still-matching history;
- divergent from replay history or exact log bytes.

A behind index can normally be replayed forward. A divergent index should be investigated or discarded before rebuilding.

## Consistency decision

The state store compares indexed source digests with current canonical files and reports:

- in sync;
- changed;
- missing;
- unsafe path;
- unreadable source.

It never automatically updates either side.

The overall report is consistent only when the event checkpoint and every indexed source match.

## Rebuild decision

The database may be removed and recreated.

A future application rebuild operation will:

1. initialize an empty supported schema;
2. inspect canonical files;
3. replay the event log;
4. recreate indexes and workflow state that can be derived safely;
5. write the terminal event checkpoint;
6. run consistency validation.

This infrastructure PR initializes an empty replacement and verifies that canonical sources and events remain untouched.

## Filesystem and sidecar decision

SQLite manages the database and its `-journal`, `-shm`, and `-wal` sidecars directly. They are not written through atomic whole-file replacement.

Before and after operations, LudoWright rejects symlink and non-regular database or sidecar paths.

There remains a local filesystem time-of-check/time-of-use boundary against a hostile process able to replace files concurrently. Project-directory ownership and operating-system permissions remain part of the trust model.

## Consequences

### Positive

- fast indexed queries without replacing human-readable canonical files;
- resumable workflows;
- explicit event replay checkpoints;
- exact source-revision consistency checks;
- concurrent local reads and serialized writes;
- database corruption can be isolated from canonical product data;
- the next migration framework has a clear versioned target.

### Negative

- canonical files, event history, and SQLite are not yet one cross-resource transaction;
- crashes can leave the index behind after a canonical write or event append;
- workflow-only progress can be lost if the database is deleted;
- WAL creates sidecar files outside the atomic filesystem adapter;
- exact-byte digests can mark formatting-only changes as stale;
- rebuild application services are not implemented in this PR;
- SQLite table layout becomes a versioned compatibility surface.

## Alternatives considered

### SQLite as the sole source of truth

Rejected because it reduces inspectability, portability, and compatibility with the documented canonical-file architecture.

### No database

Rejected because repeated full scans would become increasingly expensive and every workflow would invent its own cache.

### Long-lived shared connection

Rejected because it encourages long transactions, thread coupling, and hidden connection state. Fresh short transactions are easier to reason about and recover.

### DELETE journal mode

Rejected in favor of WAL for concurrent readers and local writer serialization.

### Automatic schema upgrade

Rejected until migrations have dry-run, backup, rollback metadata, and tests. Unknown versions fail closed.

### Semantic source hashes

Rejected for index identity. Exact bytes accurately identify the persisted revision observed by the index.

## Compatibility

The following are persisted contracts:

- database path;
- schema version;
- tables, columns, keys, constraints, and indexes;
- timestamp and context serialization;
- WAL and transaction policy;
- workflow and entity key grammar;
- checkpoint semantics;
- consistency-state meanings.

Incompatible changes require the migration framework, fixtures, dry-run behavior, backup and rollback metadata, documentation, and tests.

## Security

- database and sidecars reject symlinks and non-regular files;
- parameters are bound rather than interpolated into SQL data statements;
- arbitrary application SQL is not exposed;
- strict tables and Python validation both enforce contracts;
- short transactions reduce lock and crash exposure;
- canonical files are read through the bounded safe filesystem;
- corruption is reported without rewriting canonical data;
- unknown schema versions fail closed.

The store does not provide authorization, encryption at rest, digital signatures, remote synchronization, or protection from a hostile process with full project-directory write access.
