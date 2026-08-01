# Asset Workbook Contract

## Purpose

The asset workbook is a derived, local-first ODS projection of the canonical
asset registry and dependency graph. It is not a second source of truth and it
does not write back to either canonical document.

The v1 report contract is published as
`schemas/v1/asset-workbook-export-report.schema.json`. The workbook template
is versioned data in `src/ludowright/workbook_data/asset-registry.json` and
defines these sheets, in this exact order:

1. `Overview` — one row per asset, counts, priority, and graph freshness;
2. `Components` — components, variants, and states in one decomposition view;
3. `References` — reference availability and graph freshness;
4. `Status` — aggregate and production-item readiness;
5. `Priority` — stable priority ranking;
6. `Dependencies` — canonical graph edges and observed revisions.

Visual-reference metadata is not persisted by the current asset contracts.
The `References` view therefore reports `not-available` fields until a later
reference contract supplies those details. The limitation is emitted as a
stable warning in every report.

## Command

```bash
ludowright assets export-ods PROJECT exports/assets.ods
ludowright assets export-ods PROJECT exports/assets.ods --dry-run
ludowright --json assets export-ods PROJECT exports/assets.ods --dry-run
```

The path is repository-relative, must end in `.ods`, and is validated by the
shared filesystem boundary. Human output uses Rich. JSON output uses the
published `cli-response` envelope and includes the report's template, source
revisions, sheet counts, hashes, warnings, and final state.

## Determinism and compatibility

The application sorts all source rows and uses a versioned data template.
ODFPy output is canonicalized as a bounded ZIP with a fixed timestamp, stable
entry order, fixed permissions, and an uncompressed `mimetype` entry. The
result is validated before it is reported or written.

The report records the exact source digest, registry version, dependency-graph
revision, template ID/version, and output SHA-256. The current SQLite state
store remains the version already published by the project; ODS export does
not introduce a migration or an alternate persistence path.

## Dry-run, idempotency, and failure behavior

`--dry-run` renders and validates the planned workbook in memory. It creates no
output directory, workbook, lock, event, or SQLite state. A normal export is
create-only: an existing regular file, directory, or symlink target is a
conflict or unsafe path and is never overwritten silently.

Normal exports lock the decomposition and registry read boundaries before
rendering, then use a separate workbook lock for atomic create. Writes use the
existing atomic filesystem adapter. If rendering or writing fails, temporary
files are removed by that adapter and no success marker is emitted. The
output is a derived artifact, so there is no canonical rollback to perform.

Concurrent exports to the same target have one winner and one semantic
`conflict`; the winner's ODS package is validated before the command returns.

No migration is needed for existing projects. Future incompatible workbook
templates or report shapes require a new template/schema version and an
explicit compatibility decision.
