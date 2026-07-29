# Dependency and Invalidation Graph

## Purpose

LudoWright records explicit dependencies between canonical inputs and derived outputs so that changes never silently leave apparently valid artifacts behind.

The graph provides:

- typed node identities;
- typed dependency relations;
- exact observed source revisions;
- deterministic stale and review propagation;
- persisted impact explanations;
- directed-cycle rejection;
- safe refresh rules;
- canonical JSON persistence with optimistic concurrency.

The implementation lives in:

```text
src/ludowright/domain/dependencies.py
src/ludowright/contracts/dependencies.py
src/ludowright/infrastructure/dependency_graph.py
```

The default canonical file is:

```text
.ludowright/dependency-graph.json
```

## Authority model

The graph file is canonical for:

- declared dependency nodes;
- declared directed edges;
- the source revision observed by each dependent;
- persisted freshness state;
- persisted invalidation causes and paths.

SQLite may later index this graph for queries, but it must remain rebuildable from the JSON document. Chat messages and agent reasoning are never dependency records.

Application services remain responsible for updating the graph in the same logical workflow as canonical document writes and event-log records. This PR does not claim a cross-resource atomic transaction.

## Direction

Every edge points from an input source to a dependent target:

```text
source input ── relation / policy ──▶ dependent target
```

Examples:

```text
character body ── requires ──▶ garment fit reference
approved front view ── assembled-from ──▶ technical sheet
visual bible ── derives-from ──▶ capture profile
visual job ── generated-from ──▶ generation receipt
```

Changing the source may affect the target. The reverse is not implied.

## Graph revision

The graph document has a positive monotonic `revision`.

Each structural or freshness-changing operation advances it exactly once:

- add or remove a node;
- connect or disconnect an edge;
- publish a newer node revision;
- invalidate a node;
- refresh a node.

The graph revision identifies the dependency document itself. It is independent from each node's content revision.

## Node keys

`DependencyKey` combines:

- a stable `DependencyNodeKind`;
- a canonical slug ID.

Its human-facing token is:

```text
<kind>:<id>
```

Example:

```text
component:maya-body
reference:maya-front
technical-sheet:maya-model-sheet
```

Supported initial kinds include projects, decisions, approvals, documents, assets, components, variants, asset states, references, capture profiles, visual jobs, generation receipts, visual reviews, technical sheets, workbooks, packages, releases, and an explicit `other` category.

The kind is part of identity. `asset:maya` and `document:maya` are different nodes.

## Nodes

A `DependencyNode` stores:

- typed key;
- positive monotonic content revision;
- freshness state;
- zero or more persisted invalidation causes.

Freshness states are:

| State | Meaning |
|---|---|
| `fresh` | No persisted dependency invalidation blocks current use |
| `review-required` | The item may remain usable but requires explicit human or workflow review |
| `stale` | The item is no longer current relative to one or more dependencies |

Freshness is derived from invalidation causes. A node with no causes must be `fresh`. A node with any stale cause must be `stale`.

## Edges

A `DependencyEdge` stores:

- source key;
- target key;
- relation;
- invalidation mode;
- observed source revision.

Initial relations are:

- `requires`;
- `derives-from`;
- `references`;
- `generated-from`;
- `assembled-from`;
- `approved-by`;
- `packages`;
- `supersedes`;
- `other`.

Relations explain meaning. Invalidation mode controls propagation.

## Observed source revision

When an edge is created or its target is refreshed, it records the source node's current revision.

Example:

```text
body revision: 4
edge observed_source_revision: 4
```

If the body advances to revision 5, the edge is outdated and its target is invalidated according to the edge policy.

An edge cannot claim to have observed a revision newer than its source node.

## Invalidation modes

| Mode | Effect when the source changes |
|---|---|
| `stale` | Target becomes stale |
| `review` | Target requires review |
| `none` | Relationship remains queryable but does not propagate invalidation |

Propagation is conservative. When a path already carries a stronger state, a later softer edge does not weaken it.

Severity order is:

```text
fresh < review-required < stale
```

## Publishing a revision

`publish_revision(key, revision)` requires a strictly newer node revision.

The operation:

1. publishes the root node as the new fresh canonical revision;
2. finds outgoing edges that observed an older source revision;
3. propagates impact transitively;
4. persists one cause per root and reason on each affected node;
5. returns the new graph and deterministic impact records.

The changed input itself remains fresh. Its dependents become stale or review-required.

## Explicit invalidation

`invalidate(key, reason)` is used when the node itself is unusable, for example:

- reference rejected;
- approval revoked;
- source removed;
- manual invalidation.

The root receives an invalidation cause with a one-node path, and downstream impacts propagate from it.

Reasons are extensible canonical slugs. Stable built-ins include:

- `source-changed`;
- `source-removed`;
- `source-rejected`;
- `approval-revoked`;
- `manual-invalidation`.

## Impact explanation

Every cause records:

- root node;
- affected node;
- reason;
- resulting freshness state;
- complete directed path from root to affected node.

Example:

```text
component:maya-body
→ component:maya-jacket
→ technical-sheet:maya-model-sheet
```

When more than one path reaches the same node for one root and reason:

1. the stronger freshness impact wins;
2. for equal strength, the shorter path wins;
3. for equal length, lexical node-token order provides a deterministic tie-break.

Different roots and reasons remain separately explainable.

## Refresh

`refresh(key, revision)` represents rebuilding or reconciling a node from current dependencies.

Refresh requires:

- a strictly newer node revision;
- every propagating incoming dependency to be fresh.

A successful refresh:

1. clears the node's prior invalidation causes;
2. records the current revision of every incoming source edge;
3. marks the node fresh;
4. propagates the refreshed node's new revision to its own dependents.

A node cannot be declared fresh while one of its required inputs remains stale or review-required.

## Cycles

The dependency graph is a directed acyclic graph.

The domain rejects:

- self-dependencies;
- direct cycles;
- indirect cycles;
- cycles involving non-propagating edges.

Rejecting all cycles keeps topological planning, stale propagation, impact explanations, and future rebuild ordering deterministic.

Lineage or cross-reference relationships that naturally require a bidirectional view must be represented as separate query metadata rather than cyclic dependency edges.

## Structural mutation

Node and edge identities are unique.

A connected node cannot be removed. Callers must explicitly disconnect every edge first. This prevents accidental loss of dependency meaning.

Disconnecting an edge that is still referenced by a persisted invalidation path is rejected by graph validation. The affected node must first be refreshed or otherwise reconciled.

## Canonical serialization

The published `dependency-graph` contract uses schema version 1 and contains:

```text
revision
nodes[]
edges[]
```

Collections serialize in deterministic order. Unknown fields are rejected. The checked-in JSON Schema is:

```text
schemas/v1/dependency-graph.schema.json
```

A compatibility fixture lives at:

```text
tests/fixtures/contracts/v1/dependency-graph.json
```

## Repository behavior

`DependencyGraphRepository` wraps the canonical JSON repository and provides domain values.

It supports:

- optional load;
- create-only writes;
- canonical save;
- optimistic replacement from an exact prior digest;
- deterministic canonical bytes.

Writes reuse the audited project filesystem, per-document lock, atomic replacement, bounded parsing, strict contract validation, and exact-byte conflict detection.

## Resource limits

Initial limits are:

- 100,000 nodes per graph;
- 500,000 edges per graph;
- 256 persisted invalidation causes per node;
- 1,024 nodes per persisted impact path;
- 32 MiB for the canonical graph document.

These are safety ceilings, not performance targets. Normal projects should remain far smaller.

## Security and failure policy

The graph:

- accepts only canonical typed keys;
- rejects unknown fields and malformed revisions;
- rejects missing endpoints and duplicate identities;
- rejects cycles before persistence;
- never regenerates or deletes outputs automatically;
- marks impacts explicitly instead of hiding changes;
- uses bounded canonical JSON persistence;
- fails on optimistic concurrency conflicts.

The graph does not authenticate authors or replace access controls. Project-directory permissions remain part of the local trust boundary.
