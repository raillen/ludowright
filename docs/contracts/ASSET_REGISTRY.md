# Asset Registry Contract

## Purpose

The asset registry is the canonical project-local collection of asset
aggregates. Its v1 document is stored at:

```text
assets/registry.yaml
```

The file is a strict `asset-registry` contract containing a monotonic registry
revision and a deterministic list of published `asset` contracts. The asset
aggregate remains the source of domain invariants; the registry only owns
collection identity and persistence order.

## Shape and versioning

The published machine-readable contract is
`schemas/v1/asset-registry.schema.json` and has this shape:

```yaml
schema_version: 1
kind: asset-registry
version: 1
assets: []
```

`version` starts at `1` when the first asset is created or imported and
increments only when the canonical registry changes. Assets are serialized in
ascending ID order. Duplicate IDs are rejected.

The registry uses the existing v1 `asset` contract for every item. Each asset
must also satisfy the packaged data-driven taxonomy, including its family
prefix and declared subtype policy.

## Operations

The application service in `src/ludowright/application/asset_registry.py`
coordinates the YAML repository, the project event log, and the rebuildable
SQLite index. Mutating operations use the `asset-registry` project lock and
optimistic document snapshots.

- create and import refuse duplicate IDs;
- update replaces one asset but never changes its ID or bypasses a domain
  status transition;
- archive changes status to terminal `archived` and never deletes data;
- list, inspect, and validate are read-only;
- export writes a new JSON or YAML batch file and refuses an existing target;
- dry-run planning does not create directories, locks, SQLite files, events,
  or canonical documents.

Each successful canonical mutation appends a namespaced asset event and updates
the `asset-registry/registry` derived entity at the current SQLite schema
version. A failure after one resource is written restores the prior YAML and
event bytes and restores the derived index where possible. If restoration
fails, the original failure remains the cause of a `corrupt-state` error.

The `assets decompose` workflow reuses the registry replacement boundary for
the asset aggregate and records `asset.decomposed`. Its cross-asset
prerequisites remain in the canonical dependency graph rather than being
embedded in this YAML collection. Graph-first persistence is coordinated by
the application service and restored after a later registry failure when the
safe optimistic byte check succeeds. See
[`ASSET_DECOMPOSITION.md`](ASSET_DECOMPOSITION.md).

## Compatibility and migration

This PR introduces the first persisted registry shape as v1. Existing `asset`
v1 documents remain valid and unchanged. A future incompatible registry shape
requires a new schema version, retained fixtures, an explicit migration or
dual-read policy, and an ADR. The registry revision is not an event-log
sequence and must not be used as one.

ODS output is implemented as a derived projection in PR35; it never changes
the registry contract or writes back to the YAML document. The read-only
completeness audit is implemented by PR36 as a separate application service
and report. It does not change registry persistence or turn decomposition
recommendations into executable capture profiles.

Document candidate discovery is defined separately in
[`ASSET_DISCOVERY.md`](ASSET_DISCOVERY.md). Confirmed candidates reuse this
registry's batch mutation and event/state rollback boundary; discovery does not
change the registry contract shape.
