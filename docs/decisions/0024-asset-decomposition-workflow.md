# ADR 0024: Deterministic Asset Decomposition Workflow

## Status

Accepted

## Context

The asset aggregate already supports components, variants, and states, while
the registry and dependency graph have separate canonical persistence rules.
The next workflow must connect those contracts without creating a second graph,
duplicating registry rollback, or pretending that capture-profile execution is
already available.

## Decision

Implement one application service and one `assets decompose` command with these
boundaries:

- component, variant, and state data stays inside the existing `asset` v1
  aggregate;
- explicit asset-to-asset prerequisites are stored as `requires` edges in the
  canonical dependency graph, from prerequisite to dependent;
- registry persistence reuses the existing event-log, SQLite, locking, and
  rollback implementation;
- graph persistence occurs before registry persistence and is restored after a
  later registry failure when optimistic byte checks permit safe restoration;
- packaged recommendation rules are data, and their profile IDs/versions are
  advisory until the visual-foundation profile catalog exists;
- inspection is read-only, dry-run is side-effect free, and identical
  replacements are idempotent;
- invalid input produces structured guided corrections through the existing CLI
  response envelope.

## Rationale

Keeping the aggregate shape unchanged avoids a parallel decomposition format.
Keeping cross-asset relationships in the graph preserves one authority for
revision-aware invalidation. Reusing the registry mutation path keeps event and
state-store behavior consistent with existing asset commands. A derived
recommendation report gives users useful next actions without inventing an
executable visual pipeline prematurely.

## Consequences

The workflow can safely create the first dependency edges and report capture
scope, but it does not yet generate capture profiles, visual jobs, or separate
component files. Components are not independently addressable graph nodes in
this slice. A future change that promotes them to graph entities must define
identity, revision, migration, and rollback semantics explicitly.

The two new v1 JSON contracts are published with fixtures and manifest
checksums. Existing v1 asset and registry documents remain compatible without
migration.

## Rejected alternatives

- Storing dependencies inside the asset registry would duplicate the graph's
  invalidation authority.
- Creating a Python recommendation table would make profile guidance harder to
  version, audit, and extend as data.
- Treating recommendations as executable capture profiles would couple PR34 to
  the later visual-foundation implementation.
