# ADR 0026 — Deterministic Asset Audit

- Status: accepted
- Date: 2026-08-01
- Decision owners: LudoWright maintainers
- Related contracts: `ASSET_AUDIT.md`, `ASSET_REGISTRY.md`, `DEPENDENCY_GRAPH.md`, `CAPTURE_PROFILES.md`

## Context

The asset registry and dependency graph are now canonical, but a valid
individual asset contract does not show whether the project is ready for
production. The project also has a capture-profile contract and advisory
decomposition recommendations without a persisted executable profile catalog.
An audit must expose those gaps without treating recommendations as profiles,
creating a second source of truth, or mutating the repository while checking
it.

## Decision

Implement one read-only `AssetAuditService` and the `assets audit` command. It
reads the existing registry and graph repositories, records their exact source
digest and revisions, and emits the versioned `asset-audit` report through the
shared CLI envelope.

The first report uses these rules:

- graph asset nodes absent from the registry are orphan errors;
- asset-to-asset edges must use `requires`, and asset endpoints must exist in
  the registry; violations are errors;
- active assets without component, variant, or state records have a missing
  production specification warning;
- active assets report a missing capture-profile warning until an executable
  project-local profile catalog exists; advisory recommendation keys do not
  satisfy this check;
- active assets and required child items without an owner have incomplete
  production metadata warnings;
- archived and cancelled assets are excluded from completeness warnings;
- `--check` returns `checks-failed` only for error-severity findings.

The audit performs a second source read before returning. A changed source
fails with `conflict`; malformed source documents remain `corrupt-state`.
Audits do not create locks, SQLite files, event entries, or derived artifacts.

## Consequences

- audit output is reproducible from canonical project files;
- warnings distinguish roadmap gaps from corrupt or inconsistent asset state;
- the existing registry, graph, event log, and SQLite boundaries are reused;
- future profile persistence can replace the warning rule without changing the
  asset aggregate;
- the audit intentionally does not validate visual images, references, jobs,
  approvals, or package readiness.

## Compatibility

The `asset-audit` contract and schema are new v1 artifacts. Existing persisted
contracts and the current SQLite schema v2 are unchanged; no migration is
needed. Changes to finding codes, severity, or completeness semantics require
fixtures, documentation, and a compatibility review.
