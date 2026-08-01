# Asset Registry, Discovery, Decomposition, and Workbook CLI

## Canonical commands

Asset input and batch paths are project-relative and must use `.json` or
`.yaml`. The project is discovered from the supplied directory or a path below
it.

```bash
ludowright assets create PROJECT --input imports/asset.json
ludowright assets update PROJECT prop-arcade-cabinet --input imports/asset.json
ludowright assets list PROJECT
ludowright assets inspect PROJECT prop-arcade-cabinet
ludowright assets archive PROJECT prop-arcade-cabinet
ludowright assets validate PROJECT
ludowright assets import PROJECT imports/assets.json
ludowright assets export PROJECT exports/assets.json
ludowright assets discover PROJECT
ludowright assets discover PROJECT --source .ludowright/documents/brief.md
ludowright assets discover PROJECT --confirm candidate-<sha256>
ludowright assets decompose PROJECT chr-maya
ludowright assets decompose PROJECT chr-maya --input imports/maya-decomposition.json
ludowright assets export-ods PROJECT exports/assets.ods
ludowright assets export-ods PROJECT exports/assets.ods --dry-run
```

The create and update inputs are individual `asset` contracts. Import inputs
are `asset-registry` contracts and merge only new IDs into the canonical YAML
registry. Export produces the same batch contract in the requested format.

## ODS workbook export

`assets export-ods` creates a derived ODS workbook from the canonical YAML
registry and dependency graph. It produces the six versioned views documented
in [`ASSET_WORKBOOK.md`](../contracts/ASSET_WORKBOOK.md). The workbook is
create-only: an existing output is a `conflict`, and paths are subject to the
same traversal and symlink checks as every other project-relative write.

The command is non-interactive and supports both output surfaces:

```bash
ludowright assets export-ods PROJECT exports/assets.ods
ludowright --json assets export-ods PROJECT exports/assets.ods --dry-run
```

Dry-run validates the complete in-memory workbook and reports its planned
hashes and row counts without creating directories, locks, or files. Normal
exports lock the source read boundaries, validate the ODS package, and create
the output atomically. A partial failure does not leave a workbook that looks
valid. Repeating the command for the same output intentionally returns a
conflict; choose a new output path for a new derived snapshot.

## Decomposition

`assets decompose` inspects or replaces the components, variants, states, and
asset-to-asset prerequisites of one existing asset:

```bash
ludowright assets decompose PROJECT chr-maya
ludowright --json assets decompose PROJECT chr-maya \
  --input imports/maya-decomposition.json --dry-run
```

Without `--input`, the command is read-only and reports the current aggregate,
dependency-graph revision, and a recommendation derived from packaged
versioned data. With input, the path must be a safe project-relative `.json` or
`.yaml` decomposition contract. The operation validates the complete
replacement, plans `requires` edges in the canonical dependency graph, and
reuses the registry's event-log and SQLite rollback boundary.

Recommendations expose a profile ID and version for later visual-foundation
work; they do not execute or create capture profiles in this slice. Invalid
dependencies and malformed hierarchies produce guided correction records.
Repeating the same replacement is a safe no-op. A failed registry write
restores the graph when an optimistic byte check confirms that no concurrent
writer changed it.

## JSON and dry-run output

Use the shared CLI envelope for automation:

```bash
ludowright --json assets list PROJECT
ludowright assets import PROJECT imports/assets.json --dry-run --json
```

The response data identifies the operation, registry path and revision,
selected or affected assets, validity, dry-run status, and the current SQLite
state-store schema version. Human mode uses Rich tables; JSON mode never emits
ANSI styling.

## Idempotency and failures

The registry is create-only with respect to IDs. Repeating create or importing
an existing ID returns `conflict` and leaves the YAML, event log, and state
index unchanged. Repeating archive on an already archived asset is a safe
no-op. Update and archive use the domain transition rules.

All writes are repository-relative, symlink-safe, atomic, and locked. Existing
files are never overwritten silently. If a later event-log or SQLite step
fails, the service rolls back the registry and event bytes; an unrecoverable
rollback is reported as `corrupt-state` with the original failure preserved.

`--dry-run` validates all input and reports the planned registry revision
without changing any project file.

## Document discovery

`assets discover` scans explicit candidate declarations in
`.ludowright/documents/**/*.md`:

```markdown
<!-- ludowright:asset-candidate family="character" subtype="humanoid" --> Maya
```

It ignores declarations inside fenced code blocks and does not interpret free
text. The first scan is read-only and returns deterministic candidate IDs with
source evidence. Confirm candidates explicitly and non-interactively by
repeating `--confirm`:

```bash
ludowright --json assets discover PROJECT
ludowright assets discover PROJECT --confirm candidate-<sha256> --dry-run
ludowright assets discover PROJECT --confirm candidate-<sha256>
```

Duplicate suggested IDs are reported as `ambiguous`; an ID already present in
the registry is `rejected`. Neither can be confirmed. A successful confirmation
creates the selected assets through the registry batch operation and appends
`asset.discovered` with source path and line provenance. See
[`ASSET_DISCOVERY.md`](../contracts/ASSET_DISCOVERY.md) for the contract and
marker grammar.

The decomposition contract and report are defined in
[`ASSET_DECOMPOSITION.md`](../contracts/ASSET_DECOMPOSITION.md).
The workbook report and versioned template are defined in
[`ASSET_WORKBOOK.md`](../contracts/ASSET_WORKBOOK.md).
