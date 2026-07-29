# ADR 0012: Explicit Backed-Up Schema Migrations

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `MIGRATIONS.md`, `STATE_STORE.md`, `JSON_SCHEMAS.md`, `PROJECT_FILESYSTEM.md`

## Context

LudoWright now has persisted JSON Schemas, canonical JSON and YAML documents, a hash-chained event log, and a versioned SQLite state index.

Persisted formats will evolve. A naive strategy such as automatically running unversioned SQL when the database opens would create unacceptable risks:

- users cannot inspect what will change;
- failed upgrades may lack a usable backup;
- rollback may overwrite work created after migration;
- migration behavior can drift after release;
- unknown versions can be misinterpreted;
- the database may become authoritative merely because it was upgraded silently;
- support cannot determine which steps ran.

The state store currently has schema v1. The migration framework must be tested on a real production transition rather than only hypothetical examples.

## Decision

LudoWright introduces an explicit migration catalog and manager.

Opening `StateStore` never performs an implicit upgrade. A database with an older supported version raises a migration-required error until the caller explicitly plans, dry-runs, and applies the upgrade.

The first migration advances the state database from v1 to v2 by adding a strict migration-history table.

## Planning decision

Migration steps are immutable registered code with stable canonical IDs.

Each step advances exactly one integer schema version. Discovery must find one unique contiguous path from source to target.

Downgrades, gaps, duplicate IDs, and branching source versions are rejected.

Released migration IDs are permanent historical identifiers. Their meaning must not be edited after release.

## Dry-run decision

Dry run uses SQLite's backup API to create a disposable consistent database copy, applies the complete plan, validates the target, calculates a digest, and deletes the copy.

It does not mutate the source or create a persistent backup receipt.

Dry run is required as a supported operation because planning alone cannot detect schema-specific SQL failures.

## Backup decision

A real migration creates a consistent SQLite backup and a prepared rollback receipt before opening the source transaction.

The backup lives outside the database being migrated. This preserves recovery metadata even when the source database becomes unreadable.

Backups are synchronized to disk before migration proceeds.

## Receipt decision

Rollback metadata uses a strict published `migration-receipt` JSON contract.

The receipt transitions through:

```text
prepared → completed → rolled-back
         ↘ failed
```

The receipt records exact paths, versions, ordered migration IDs, UTC timestamps, logical database digests, backup digest, optional failure text, and pre-rollback safety-copy digest.

Receipt state determines which fields are required or forbidden.

## Transaction decision

All steps in one plan execute inside a single `BEGIN IMMEDIATE` transaction.

Every step verifies the current `user_version`, applies its operation, advances the version, and records history when the target schema supports it.

Any exception rolls back the complete plan.

Post-commit validation checks the target version, SQLite integrity, required schema objects, and a consistent logical digest.

## Logical digest decision

The digest of a live WAL-backed SQLite database cannot safely be defined as the bytes of only the main file.

Migration consistency therefore hashes a consistent SQLite backup snapshot.

Rollback is allowed only when a fresh logical digest of the current database equals the recorded post-migration digest.

This prevents rollback from silently destroying newer workflow or index writes.

## Rollback decision

Rollback is explicit and receipt-driven.

Before restoration, the manager creates a consistent safety copy of the current database. The original migration backup is verified by SHA-256. Restoration is validated against the source version and before digest.

If restoration fails, the manager attempts to replace the database from the pre-rollback safety copy.

No force rollback option is provided initially.

## State schema v2 decision

Fresh databases use schema v2 and contain:

```text
migration_history
```

The table records migration ID, run ID, source and target versions, UTC timestamp, and LudoWright tool version.

Migrating a v1 database creates the table transactionally and records the v1→v2 step.

The external receipt remains the primary rollback artifact because it survives restoration to v1, where the history table does not exist.

## Consequences

### Positive

- users and agents can inspect changes before applying them;
- dry run exercises actual SQL on observed data;
- every real migration has a durable consistent backup;
- receipts remain available outside a damaged database;
- migration steps are uniquely discoverable and auditable;
- failed plans roll back transactionally;
- rollback cannot overwrite newer state silently;
- the framework is validated by a real v1→v2 transition;
- JSON Schema tooling can validate rollback metadata.

### Negative

- state schema v1 users must perform an explicit operation before reopening the new `StateStore`;
- migration code and historical steps become permanent compatibility obligations;
- backup and dry-run copies require additional disk space;
- whole-database SQLite backup cost grows with database size;
- the framework currently targets SQLite state only;
- CLI exposure is deferred;
- receipts contain local filesystem paths and must be handled as project-operational metadata.

## Alternatives considered

### Automatic migration during `StateStore` initialization

Rejected because it removes the opportunity for dry run, approval, backup review, and deliberate failure handling.

### SQL files discovered from the project directory

Rejected because project-controlled SQL would create a code-execution boundary and weaken migration authenticity. Migration operations are registered trusted application code.

### One transaction per migration step

Rejected for the initial local state schema. A complete plan should either reach the target version or leave the source unchanged.

### Copy the live database file directly

Rejected because WAL may contain committed pages absent from the main file. The SQLite backup API produces a consistent snapshot.

### Allow forced rollback

Rejected initially because overwriting post-migration writes is destructive. A future disaster-recovery tool may add an explicit force workflow with an additional backup and stronger confirmation.

### Store rollback metadata only inside SQLite

Rejected because restoring v1 removes v2-only tables and corruption may make the database unreadable.

## Compatibility

Migration IDs, version edges, receipts, backup layout, digest interpretation, and rollback rules are persisted contracts.

Historical migration code must remain capable of upgrading supported old fixtures. Behavior changes require a new migration step or a documented correction process, never silent mutation of released history.

The migration receipt joins the v1 JSON Schema publication without changing the interpretation of existing v1 contracts.

## Security

- migration code is trusted packaged code, not project input;
- database, backup, temporary, and sidecar paths reject symlinks and non-regular files;
- source version is rechecked under the migration lock;
- backup is durable before source mutation;
- transaction failures roll back;
- rollback requires exact current and backup digests;
- unknown versions fail closed;
- receipts are strict, bounded, and atomically written.

The framework does not authenticate migration authors, encrypt backups, provide remote attestation, or defend against an attacker with unrestricted write access to the complete project directory and runtime.
