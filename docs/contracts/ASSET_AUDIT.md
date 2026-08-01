# Asset Audit Contract

## Purpose

`assets audit` is a deterministic, read-only review of the canonical asset
registry and dependency graph. It identifies production gaps without creating
an alternate asset database or changing project state.

The published v1 report is `asset-audit`, stored in
`schemas/v1/asset-audit.schema.json`. The report includes the registry and
graph revisions, the current SQLite schema version, an exact source digest,
and sorted findings.

## Findings

The initial audit covers five bounded categories:

- `orphan-asset-node` — an asset node exists in the dependency graph without a
  matching registry asset;
- `missing-specification` — an active asset has no components, variants, or
  states in its production specification;
- `invalid-dependency` — an asset dependency references an unknown registry
  asset or an asset-to-asset edge uses a relation other than `requires`;
- `missing-capture-profile` — the project has no executable persisted
  capture-profile catalog. Packaged profiles such as the v1 humanoid profile
  are reusable definitions but do not count as a project-local catalog;
  decomposition recommendations also do not count as executable profiles;
- `incomplete-production-metadata` — an active asset or required production
  item has no owner.

Archived and cancelled assets are excluded from completeness warnings. Graph
orphans and invalid dependencies remain blocking findings. Missing
specifications, capture profiles, and ownership are warnings because the
visual-foundation/profile catalog and team assignment workflows are not yet
persisted by the current project format.

The report is `valid` when it has no error-severity findings. A report with
warnings is still useful and remains valid; `--check` fails only when blocking
findings exist. An empty project produces an `empty` report with no findings.

## Command and safety

```bash
ludowright assets audit PROJECT
ludowright assets audit PROJECT --dry-run
ludowright assets audit PROJECT --check
ludowright --json assets audit PROJECT --check
```

The command reads only `assets/registry.yaml` and
`.ludowright/dependency-graph.json` through their existing repositories. It
does not create locks, SQLite state, event-log entries, or output files. A
second source read detects a concurrent canonical change and fails with the
shared `conflict` error. Malformed persisted documents remain `corrupt-state`
errors and are not converted into audit findings.

Human output uses Rich. JSON output uses the published `cli-response` envelope;
when `--check` fails, the complete `asset-audit` report remains in `data`.

## Compatibility

This slice adds the `asset-audit` v1 report and fixture. It does not change the
asset, registry, dependency-graph, event-log, or SQLite schemas, so no
migration is required. Changing finding meaning, severity, or source
interpretation requires a new report revision or an explicit compatibility
decision.
