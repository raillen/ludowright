# ADR 0022 — Versioned Asset Registry Persistence

- Status: accepted
- Date: 2026-07-30
- Decision owners: LudoWright maintainers
- Related contracts: `ASSET_DOMAIN.md`, `ASSET_TAXONOMY.md`, `ASSET_REGISTRY.md`, `STRUCTURED_REPOSITORIES.md`

## Context

The asset domain and taxonomy define valid individual aggregates, but a
project still needs one inspectable collection for planning and automation.
The registry must remain human-editable, deterministic, safe under local
concurrency, and compatible with the existing event log and derived SQLite
store.

## Decision

Persist the canonical collection as a v1 `asset-registry` YAML document at
`assets/registry.yaml`. The document contains a monotonic collection revision
and a sorted tuple of existing v1 `asset` contracts. Individual IDs are unique.

The application service owns the operation boundary. It validates each asset
against both the published contract/domain rules and the packaged taxonomy,
holds the shared `asset-registry` lock, uses structured repository snapshots
for conflict detection, and writes through the existing atomic filesystem
adapter.

Successful mutations append `asset.*` events and update one derived SQLite
index entity. Since the current infrastructure does not provide a cross-file
transaction, the service captures prior bytes and derived metadata and rolls
back in reverse order when a later step fails. It never deletes an asset for
archive; archive is the domain terminal status.

Batch import merges only new IDs. Export is a derived, create-only artifact and
may use JSON or YAML. Paths remain repository-relative and symlinks are
rejected by the existing filesystem boundary.

## Consequences

- the registry is easy to review and diff in Git;
- the existing asset contract remains reusable without a parallel asset shape;
- collection revisions and event sequences are distinct and auditable;
- a failed multi-resource write can be restored without hiding the original
  failure;
- cross-asset dependencies, discovery, decomposition, ODS, and audits remain
  separate follow-up slices;
- large registries will eventually need measured indexing or segmentation,
  but the bounded structured-repository limit applies now.

## Compatibility

This is the first persisted `asset-registry` contract, published in
`schemas/v1/` with a fixture. Future incompatible shape or interpretation
changes require a new schema version and explicit migration policy. The
existing `asset` v1 contract and the current SQLite schema v2 are unchanged.
