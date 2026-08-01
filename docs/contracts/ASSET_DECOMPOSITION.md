# Asset Decomposition Contract

## Purpose

PR34 turns the immutable v1 asset aggregate into an explicit, reviewable
decomposition workflow. Components, variants, and states remain part of the
asset contract. Asset-to-asset relationships are persisted only in the
canonical dependency graph.

The workflow is local-first and deterministic. It does not create executable
capture profiles or image jobs; it derives a versioned recommendation report
from packaged data for later visual-foundation work.

## Published contracts

The source models live in
`src/ludowright/contracts/asset_decomposition.py` and are published as:

- `asset-decomposition.schema.json` — complete replacement input for one asset;
- `asset-decomposition-report.schema.json` — inspection, planning, success, or
  guided-correction result.

Both contracts are v1 and use the standard `schema_version` and `kind` fields.
Input collections and dependency IDs must be sorted and unique. Component
hierarchy remains validated by the existing asset domain contract.

## Command

Inspect an existing aggregate without changing the repository:

```bash
ludowright assets decompose PROJECT ASSET_ID
```

Apply a complete decomposition replacement:

```bash
ludowright assets decompose PROJECT ASSET_ID \
  --input imports/maya-decomposition.json
```

Plan the same operation without writing files:

```bash
ludowright --json assets decompose PROJECT ASSET_ID \
  --input imports/maya-decomposition.json --dry-run
```

Input paths are repository-relative `.json` or `.yaml` documents. Absolute
paths, traversal, unsafe symlinks, unknown asset IDs, self-dependencies, and
missing prerequisite assets are rejected by the existing filesystem and
contract boundaries.

## Persistence workflow

For a successful mutation the application service:

1. locks the project decomposition operation;
2. validates the complete input and derives the replacement asset contract;
3. plans the dependency graph revision and `requires` edges;
4. writes the graph atomically;
5. replaces the asset through the registry's existing event-log and SQLite
   rollback boundary;
6. records `asset.decomposed` with dependency and recommendation provenance.

If the registry step fails, the graph is restored only when its bytes still
match the bytes written by this operation. An unsafe restoration raises a
rollback error and preserves the original failure as its cause. No success
marker is emitted before both canonical resources are valid.

The registry replacement also checks that the asset read during planning is
still the current asset before writing. A concurrent registry update therefore
fails closed and triggers graph restoration instead of silently clobbering the
other update.

The graph direction is prerequisite asset → decomposed asset. Components,
variants, and states are not promoted to independent graph nodes in this
slice. Repeating an identical decomposition is a safe no-op and does not add
another event or change canonical bytes.

## Recommendations and corrections

Recommendation rules are versioned data in
`src/ludowright/decomposition_data/recommendations.json`. Exact family/subtype
rules take precedence over family defaults. The report filters recommended
subject modes to the subjects actually present and lists required item IDs.
The profile ID and version are advisory keys only; executable profile catalogs
remain part of the visual-foundation roadmap.

Validation errors return actionable correction records. Human output renders
the same report used by JSON mode, while JSON mode wraps it in the published
`cli-response` envelope. Expected invalid input uses the existing
`invalid-input` semantic code and validation exit code.

## Compatibility

The existing `asset` v1 and `asset-registry` v1 contracts remain unchanged.
The decomposition document and report are new v1 contracts, with fixtures and
manifest checksums published alongside the source models. No migration is
needed for existing projects. Future changes to persisted decomposition
meaning require a new schema version and an explicit migration policy.
