# Rebuildable SQLite State Store

## Purpose

LudoWright uses SQLite for indexed state and resumable workflow progress while keeping human-editable structured files and the append-only event log as independent canonical inputs.

The state store provides:

- fast workflow lookup;
- indexed canonical-entity metadata;
- exact source-file digests;
- event-log replay checkpoints;
- consistency reports;
- short explicit transactions;
- concurrent local writers through SQLite WAL;
- a database that may be deleted and rebuilt without deleting canonical project data.
- a read-only inspection mode for status and audit commands.

The implementation lives in:

```text
src/ludowright/infrastructure/state_store.py
```

The default database is:

```text
.ludowright/state.sqlite3
```

## Authority model

The database is **derived state**.

It is authoritative only for transient information that has no separate canonical representation, such as the current cursor of a resumable workflow. It is not authoritative for product facts already stored in:

- project JSON or YAML;
- decision and approval records;
- asset specifications;
- reference and generation records;
- capture profiles;
- the project event log.

Deleting the database may remove cached indexes and local workflow progress. It must not delete or rewrite canonical files or events.

## Architectural position

```text
canonical files ───────┐
                       ├─ consistency checks → SQLite derived index
append-only event log ─┘
                                   ↑
                         application workflows
```

The upcoming application layer will coordinate canonical writes, event append, and index updates. This infrastructure PR does not claim a cross-resource atomic transaction.

## Database path and safety

The default path is a canonical `RepositoryPath` ending in `.sqlite3`.

Before opening SQLite, LudoWright:

- creates the canonical parent directory through `ProjectFilesystem`;
- rejects symlink or non-regular database files;
- rejects symlink or non-regular `-journal`, `-shm`, and `-wal` sidecars;
- verifies the files again after operations.

SQLite creates and manages the database and sidecars directly. They are not written through `ProjectFilesystem.write_bytes()` because SQLite supplies its own transactional page and journal protocol.

There remains an ordinary local filesystem time-of-check/time-of-use boundary against a hostile process able to replace files concurrently. The project lock, directory ownership, and operating-system permissions remain part of the trust boundary.

## SQLite configuration

Every connection enables:

```text
foreign_keys = ON
journal_mode = WAL
synchronous = FULL
temp_store = MEMORY
trusted_schema = OFF
busy_timeout = configured value
```

The default busy timeout is 5,000 milliseconds.

WAL allows concurrent readers and serialized writers. `synchronous=FULL` favors durability over maximum write throughput for project metadata.

## Read-only inspection

`StateStore(read_only=True)` is reserved for commands that cannot mutate the project,
such as `ludowright status`. The mode:

- does not create the database or its parent directories;
- requires the existing database at the current version with a WAL header;
- rejects an active `-wal` sidecar because an immutable SQLite URI cannot safely
  incorporate it;
- opens with `immutable=1&mode=ro` and validates the schema and `quick_check`;
- rejects all write methods.

A concurrent writer must finish before inspection. A command that needs to handle an
active WAL must implement an explicit wait or recovery policy; the current status
command fails closed and preserves the original project state.

## Schema version

The current database uses:

```text
PRAGMA user_version = 2
```

Fresh databases are created at v2. Existing v1 databases require the explicit migration framework documented in [`MIGRATIONS.md`](MIGRATIONS.md).

A new empty database is initialized as version 2. A v1 database is rejected until the explicit v1→v2 migration is applied. Other non-zero versions are rejected with `UnsupportedStateSchemaError`.

Schema migration is explicit and backed up. The state store must not guess how to upgrade an unknown version.

## Tables

### `workflow_progress`

Stores one current progress record per workflow ID:

- workflow ID;
- workflow type;
- status;
- optional current step;
- canonical JSON context;
- optional source event sequence;
- canonical UTC update timestamp.

Workflow values use canonical slug grammar. Context uses the same immutable JSON-compatible value model as event payloads.

### `indexed_entity`

Stores one derived index record per entity type and ID:

- entity type;
- entity ID;
- canonical repository-relative source path;
- SHA-256 digest of exact source bytes;
- positive source revision;
- status;
- canonical UTC update timestamp.

The source digest identifies the exact indexed file revision. Formatting-only changes therefore appear as changed until the index is refreshed intentionally.

### `migration_history`

Stores one immutable row per applied state-schema migration:

- migration ID;
- run ID;
- source and target versions;
- canonical UTC timestamp;
- LudoWright tool version.

The external rollback receipt remains authoritative for backup restoration because rolling back to v1 removes this v2-only table.

### `event_checkpoint`

Stores one singleton checkpoint:

- last indexed event sequence;
- last indexed event hash;
- exact complete event-log digest;
- canonical UTC update timestamp.

Sequence zero requires a null event hash. A positive sequence requires a hash.

## Strict tables

All tables use SQLite `STRICT` mode. The entity index also uses `WITHOUT ROWID` because its natural composite key is the row identity.

Database constraints complement Python validation. They do not replace it.

## Transaction policy

Every public read or write operation opens a fresh connection and one short transaction.

Reads use:

```text
BEGIN
PRAGMA query_only = ON
```

Writes acquire the shared `sqlite-state-store-write` project lock and then use:

```text
BEGIN IMMEDIATE
```

Migration apply and rollback operations acquire the same lock across backup, schema mutation, digest calculation, and database replacement. This prevents a StateStore write from falling between the rollback snapshot and the migrated state.

Successful operations commit. Any exception rolls back. Connections are always closed.

The store does not expose arbitrary SQL or a long-lived public connection. This prevents callers from bypassing validation, retaining transactions across user interaction, or coupling application logic to table layout.

## Workflow progress

`WorkflowProgress` is immutable and contains:

- canonical workflow ID and type;
- canonical status;
- optional canonical step;
- deeply immutable JSON object context;
- optional positive source event sequence;
- timezone-aware update time normalized to UTC.

Saving uses an upsert by workflow ID. Listing is stable by workflow ID. Deletion is explicit and reports whether a row existed.

Workflow progress is derived operational state. Application services must record important product decisions in canonical documents and events rather than hiding them only inside workflow context.

## Indexed entities

`IndexedEntity` binds an entity key to one exact canonical source revision.

Saving uses an upsert by `(entity_type, entity_id)`. Listing is stable by type and ID and may be filtered by entity type.

The index may contain projects, decisions, approvals, assets, references, jobs, profiles, packages, or future canonical entities. It does not parse or mutate their source documents.

## Event checkpoints

`record_event_checkpoint()` accepts a fully validated `EventLogSnapshot`.

It stores:

- terminal sequence;
- terminal event hash;
- exact log digest.

The checkpoint should be updated in the same application operation that updates the index derived from those events. Until a cross-resource transaction coordinator exists, a crash may leave the index behind; the consistency report makes that state explicit.

## Event consistency states

`check_consistency()` reports one of:

| State | Meaning |
|---|---|
| `in-sync` | Checkpoint matches the complete current event log |
| `empty-index` | Events exist but no checkpoint has been recorded |
| `behind` | Checkpoint history still matches, but later events exist |
| `diverged` | Checkpoint is ahead or its event hash/log digest does not match |

A behind index can normally be replayed forward. A divergent index should be discarded or investigated before rebuilding.

## Canonical source consistency

Each indexed entity is compared with its current source file.

Possible states:

| State | Meaning |
|---|---|
| `in-sync` | Exact current SHA-256 matches the indexed digest |
| `changed` | File exists but exact bytes differ |
| `missing` | Source file no longer exists |
| `invalid-path` | Source path became unsafe, commonly through a symlink |
| `unreadable` | Path exists but is not a readable regular file or exceeds limits |

The default source read limit is 16 MiB per indexed document.

The report never rewrites either the source or the database automatically.

## Overall consistency

`StateConsistencyReport.is_consistent` is true only when:

- the event checkpoint is `in-sync`; and
- every indexed source is `in-sync`.

An empty event log with no checkpoint is considered synchronized.

## Rebuild behavior

Because the database is derived, a supported repair is:

1. stop active writers;
2. preserve the database as diagnostic evidence when needed;
3. remove the database and SQLite sidecars;
4. initialize a new state store;
5. replay canonical files and the event log through application rebuild services;
6. record a new checkpoint;
7. run consistency checks.

The infrastructure currently initializes an empty replacement but does not yet implement the application rebuild workflow.

## Corruption handling

Initialization validates:

- supported `user_version`;
- expected tables;
- SQLite `quick_check`.

Malformed rows are converted into `StateStoreCorruptionError` rather than returned as partially trusted values.

A corrupt database should not cause canonical files or the event log to be rewritten.

## Error model

| Error | Meaning |
|---|---|
| `StateStoreError` | Base configuration or persistence contract failure |
| `UnsupportedStateSchemaError` | Database requires an explicit migration |
| `StateStoreCorruptionError` | Database, schema, row, or SQLite operation is invalid |
| `UnsafeProjectPathError` | Database, sidecar, or canonical source path is unsafe |

SQLite lock timeouts and other database failures are surfaced as state-store operation failures.

## Compatibility policy

The following are persisted contracts:

- database path and sidecar policy;
- schema version;
- table names, columns, keys, constraints, and indexes;
- timestamp and JSON serialization;
- workflow and entity key grammar;
- checkpoint semantics;
- consistency-state meanings;
- WAL and transaction policy.

Incompatible changes require the migration framework planned for the next PR, including dry run, backup, rollback metadata, fixtures, and tests.

## Boundaries

This state store does not yet provide:

- canonical-file migrations;
- automatic event replay into domain-specific tables;
- a dependency graph;
- full-text search;
- cross-resource atomic commits;
- remote synchronization;
- multi-user authorization;
- automatic repair;
- canonical product-data storage.

Those concerns belong to later bounded PRs.
