# Explicit Migration Framework

## Purpose

LudoWright evolves persisted schemas without silently reinterpreting or destroying project data.

The migration framework provides:

- deterministic migration discovery;
- contiguous version plans;
- disposable dry-run simulation;
- consistent SQLite backups;
- persisted rollback receipts;
- transactional application;
- post-migration integrity validation;
- explicit rollback guarded by exact database digests;
- fail-closed behavior for missing or unknown versions.

The implementation lives in:

```text
src/ludowright/infrastructure/migrations.py
src/ludowright/contracts/migrations.py
```

The first production migration upgrades the rebuildable state database from schema v1 to v2.

## Architectural position

```text
versioned database
        ↓ inspect
migration catalog
        ↓ plan
consistent disposable copy ── dry run
        ↓ apply after approval
backup + prepared receipt
        ↓
transactional migration
        ↓
validation + completed receipt
```

Migration is an explicit operation. Opening `StateStore` does not silently upgrade an older database.

## Migration catalog

`MigrationCatalog` contains validated `MigrationStep` entries.

Each step defines:

- canonical migration ID;
- source version;
- target version;
- human-readable description;
- deterministic SQLite operation.

A step must advance exactly one version:

```text
vN → vN+1
```

The catalog rejects:

- duplicate migration IDs;
- more than one step from the same source version;
- non-positive versions;
- steps that skip or reverse versions;
- empty descriptions;
- missing apply functions.

## Discovery and planning

`plan()` inspects `PRAGMA user_version` and discovers the exact contiguous path to the target version.

Examples:

```text
v1 → v2       one step
v1 → v3       v1→v2 followed by v2→v3
v2 → v2       no-op
v3 → v2       rejected downgrade
v1 → v3       rejected when v2→v3 is missing
```

Plans contain ordered immutable steps and stable migration IDs.

Planning never changes the database.

## Current state schema migration

The initial production step is:

```text
state-v1-to-v2-migration-history
```

It creates the strict `migration_history` table and advances `PRAGMA user_version` from 1 to 2.

The table records:

- migration ID;
- run ID;
- source and target versions;
- canonical UTC application timestamp;
- LudoWright tool version.

Fresh state databases are created directly at v2. Existing v1 databases require the explicit migration manager.

## Dry run

`dry_run()`:

1. acquires the migration project lock;
2. inspects and plans the current database;
3. creates a consistent disposable SQLite copy;
4. applies the entire migration plan to the copy;
5. validates target version, required tables, and `PRAGMA quick_check`;
6. calculates the simulated database digest;
7. removes the temporary database and sidecars.

Dry run does not create a persistent backup or rollback receipt and does not modify the source database.

A successful dry run proves that the registered steps can migrate the observed database revision under the current runtime. It does not guarantee that a later real run cannot be interrupted by hardware or operating-system failure.

## Backup layout

A real migration creates one canonical run directory:

```text
.ludowright/backups/migrations/<run-id>/
├── state-before.sqlite3
└── rollback.json
```

A later rollback also creates:

```text
state-before-rollback.sqlite3
```

The run ID includes a UTC timestamp and random suffix and remains a canonical repository slug.

## Consistent SQLite backup

Backups use SQLite's backup API rather than copying a live database file directly.

This produces a consistent snapshot even when the source uses WAL. The backup is synchronized to disk before migration proceeds.

The receipt records SHA-256 for the backup snapshot. The hash identifies exact backup bytes and is verified before rollback.

## Rollback receipt

`rollback.json` uses the published `migration-receipt` contract.

It contains:

- run ID and status;
- database and backup repository paths;
- source and target versions;
- ordered migration IDs;
- start, completion, and optional rollback timestamps;
- logical database digest before migration;
- backup digest;
- logical database digest after migration;
- pre-rollback safety-copy digest;
- bounded failure text when execution fails.

Receipt states are:

| State | Meaning |
|---|---|
| `prepared` | Backup and initial metadata are durable; migration has not completed |
| `completed` | Database reached and validated the target version |
| `failed` | Transaction failed; backup remains available for investigation |
| `rolled-back` | A completed run was explicitly restored to its source snapshot |

State-specific fields are validated. A prepared receipt cannot claim an after digest, and a completed receipt must contain completion metadata.

## Prepared receipt ordering

For a real apply, LudoWright persists the backup and a `prepared` receipt before changing the source database.

This ordering ensures that an interrupted operation leaves discoverable rollback information.

After successful validation, the same receipt is atomically replaced with `completed` metadata.

When the transaction fails, it is atomically replaced with `failed` metadata. SQLite rollback preserves the source version.

## Transactional apply

All migration steps for one plan execute inside one `BEGIN IMMEDIATE` transaction.

For each step, the manager:

1. verifies the observed `user_version`;
2. executes the registered operation;
3. advances `user_version`;
4. records migration history when the table exists.

Any exception rolls back the full plan.

After commit, the manager validates:

- exact target version;
- SQLite `quick_check`;
- required target tables;
- a consistent logical database digest.

## Logical database digests

A live WAL-backed SQLite database is not represented by one stable file alone. Therefore before/after consistency uses a temporary consistent SQLite backup and hashes that snapshot.

Consequences:

- the before digest equals the persisted backup digest for the initial snapshot;
- the after digest identifies a normalized consistent post-migration snapshot;
- rollback compares the current logical database snapshot with the recorded after digest;
- arbitrary newer writes block rollback.

The digest is integrity metadata, not a digital signature.

## Explicit rollback

`rollback(run_id)` is allowed only when:

- the receipt exists and is `completed`;
- the current logical database digest equals the recorded after digest;
- the backup exists as a regular non-symlink file;
- the backup SHA-256 matches the receipt;
- the restored database reports the source version;
- the restored logical digest matches the before digest.

Before replacement, the manager creates `state-before-rollback.sqlite3`. If restoration fails, it attempts to restore this safety copy.

Rollback updates the receipt to `rolled-back` and records the pre-rollback digest and timestamp.

Rollback refuses to destroy writes made after migration. There is no force option in the initial framework.

## Database replacement

Restore creates a consistent temporary SQLite copy from the backup, synchronizes it, removes existing SQLite sidecars under the migration lock, and atomically replaces the main database file.

The containing directory is synchronized where supported.

## Migration lock

All planning operations that create copies, dry runs, apply, and rollback use:

```text
sqlite-state-migration
```

The lock covers source-version reinspection, backup, migration, validation, and receipt updates.

Two concurrent callers cannot assign competing migration plans. After the first caller completes, the second reinspects the database and normally returns a no-op plan.

## Temporary files

Disposable SQLite copies live under:

```text
.ludowright/tmp/migrations/
```

The manager removes the database and any journal, shared-memory, or WAL sidecars after use.

Symlink or non-regular temporary paths fail closed.

## Error model

| Error | Meaning |
|---|---|
| `MigrationError` | Base migration configuration or persistence failure |
| `MigrationPlanError` | Missing, ambiguous, reverse, or invalid migration path |
| `MigrationExecutionError` | Backup, transaction, or target validation failed |
| `MigrationRollbackError` | Receipt or current database prevents safe rollback |
| `UnsupportedStateSchemaError` | `StateStore` requires an explicit supported migration |

Receipts retain bounded failure text but are not a replacement for complete local logs or diagnostics.

## Compatibility policy

The following are persisted migration contracts:

- migration IDs and version edges;
- catalog ordering and gap behavior;
- backup directory structure;
- receipt schema and states;
- timestamp, digest, and path representation;
- transaction and rollback rules;
- logical digest interpretation;
- state schema version and migration history table;
- dry-run semantics.

A released migration ID must never be reused for different behavior.

Changing an applied migration requires a new forward migration, not editing historical meaning.

## Security boundaries

The framework:

- rejects missing, symlink, and non-regular database or backup paths;
- uses parameterized migration-history writes;
- does not accept arbitrary migration SQL from project files;
- validates exact source version before every step;
- backs up before source mutation;
- blocks rollback after newer writes;
- fails closed on unknown versions;
- retains rollback metadata outside the migrated database.

It does not provide:

- authorization;
- encrypted backups;
- digital signatures;
- remote backup replication;
- protection from a hostile process with full project-directory write access;
- automatic canonical-file migrations yet;
- a CLI command yet.

CLI exposure arrives in the later CLI phase after the application boundary and stable exit codes are implemented.
