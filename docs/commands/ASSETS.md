# Asset Registry and Discovery CLI

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
```

The create and update inputs are individual `asset` contracts. Import inputs
are `asset-registry` contracts and merge only new IDs into the canonical YAML
registry. Export produces the same batch contract in the requested format.

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
