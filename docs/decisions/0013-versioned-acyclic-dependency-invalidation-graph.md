# ADR 0013 — Versioned Acyclic Dependency and Invalidation Graph

- Status: Accepted
- Date: 2026-07-29
- Decision owners: LudoWright maintainers

## Context

LudoWright produces many derived artifacts from changing canonical inputs: documents, capture profiles, visual jobs, references, technical sheets, workbooks, packages, and releases.

Without an explicit dependency model, a change can leave downstream outputs apparently valid even when their assumptions are obsolete. Prompt memory, timestamps, and directory conventions are not sufficient because they cannot provide deterministic impact analysis, resumable refresh, or auditable explanations.

The graph must support both strict invalidation and softer review requirements. It must also remain portable across the CLI, Codex workflows, JSON files, SQLite indexes, tests, and future packaging checks.

## Decision

Adopt one canonical, versioned, directed acyclic dependency graph stored at:

```text
.ludowright/dependency-graph.json
```

Each node has a typed kind and slug ID, a positive content revision, a derived freshness state, and persisted invalidation causes.

Each edge points from a source input to a dependent target and records:

- typed relation;
- invalidation mode;
- exact source revision observed by the target.

Invalidation modes are:

- `stale`;
- `review`;
- `none`.

Publishing a newer source revision leaves the source fresh and propagates impact through edges that observed an older revision. Explicit invalidation marks the source itself and propagates downstream.

Every propagated cause stores the root, reason, resulting state, and complete path. Stronger impact wins over weaker impact. Equal-strength paths are selected deterministically by length and lexical order.

Refreshing a node requires all propagating inputs to be fresh, advances the node revision, records current incoming source revisions, clears its causes, and invalidates downstream dependents of the refreshed output.

All directed cycles are rejected, including cycles containing non-propagating edges.

The graph document is canonical. SQLite may index it but must remain rebuildable. Significant graph changes will later be coordinated with event-log records by the application layer.

## Rationale

### Typed keys instead of raw paths

Entity kind plus canonical ID survives file movement and prevents collisions between different domains. Paths remain persistence details rather than graph identity.

### Observed revisions instead of timestamps

A dependent must state which source revision it used. Timestamps are vulnerable to clock differences, copying, and ambiguous ordering.

### Persisted causes instead of recomputation only

Persisted paths make stale state explainable after restart and allow humans or agents to answer why an artifact is blocked without reconstructing historical prompt context.

### Explicit review state

Not every upstream change invalidates an output completely. A separate `review-required` state avoids treating all dependencies as equally destructive while still preventing silent acceptance.

### Acyclic graph

A DAG enables deterministic topological planning, bounded propagation, stable explanations, and future rebuild scheduling. Allowing cycles would require fixed-point semantics and make refresh ordering ambiguous.

### Canonical JSON plus derived indexes

Dependency declarations and invalidation state are important project data. Keeping them only in SQLite would make manual inspection, version control, migration, and cross-tool portability weaker.

## Consequences

### Positive

- Propagating edges require fresh sources, preventing new dependents from starting from already invalid inputs.
- Root publication and derived refresh are separate operations, so consumed input revisions cannot be bypassed.
- One edge per ordered node pair keeps invalidation policy unambiguous.
- Iterative cycle validation supports deep valid DAGs without Python recursion limits.
- Changes produce explicit downstream impact.
- Every stale or review-required node can explain its root cause and path.
- Refresh cannot falsely declare an output fresh while required inputs remain blocked.
- Cycles fail during validation rather than during production planning.
- JSON Schema supports editors and external tools.
- Optimistic concurrency prevents silent overwrite of graph changes.
- SQLite indexes and ODS reports can be regenerated from the canonical graph.

### Negative

- Application operations must maintain graph edges and node revisions deliberately.
- Persisted causes increase graph size.
- Large graphs require careful query indexing later.
- Removing edges may require first reconciling stale paths.
- The application layer will need recovery policy for partial cross-resource operations.

### Neutral

- This decision does not automatically discover dependencies.
- This decision does not automatically regenerate stale outputs.
- This decision does not define CLI commands yet.
- This decision does not authenticate graph authors.

## Alternatives considered

### Timestamps and file modification times

Rejected because they do not identify the exact source revision used and are unstable across copies, archives, and version-control operations.

### SQLite-only graph

Rejected because dependency declarations are important canonical project data and should remain reviewable, portable, and version-controlled.

### Recompute all impacts without persisting causes

Rejected because restart-time explanations would depend on reconstructing historical operations and could choose different paths after graph edits.

### Allow cycles and iterate to a fixed point

Rejected because refresh order and impact explanations become ambiguous, while legitimate dependency workflows can be modeled as a DAG.

### One boolean stale flag

Rejected because review-required relationships are materially different from invalid outputs and because a boolean cannot explain multiple causes.

## Compatibility

The initial persisted contract is `dependency-graph` schema version 1.

Incompatible changes to node identity, edge direction, revision meaning, invalidation severity, path selection, refresh rules, or cycle policy require a new schema version and migration.

New node kinds or relation values require contract review because enums are published and unknown values fail closed.

## Validation

The decision is enforced by:

- immutable domain types;
- exact revision checks;
- duplicate and endpoint validation;
- directed-cycle detection;
- deterministic propagation tests;
- refresh-blocking tests;
- contract round trips;
- compatibility fixtures;
- canonical repository conflict tests;
- checked-in JSON Schema drift checks;
- strict documentation builds.
