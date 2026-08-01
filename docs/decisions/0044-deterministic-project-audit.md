# ADR 0044: Deterministic Read-Only Global Project Audit

## Status

Accepted

## Context

The package manifest and builder verify individual release inputs, but a user
also needs one machine-readable view of readiness across product state,
documentation, assets, visual provenance, approvals, technical sheets, and
package outputs. That view must not become a second source of truth or repair
project state implicitly.

## Decision

Implement `ludowright audit PROJECT` as a read-only application use case. It
produces the versioned `project-audit` contract with eight fixed categories,
source evidence, stable finding codes, deterministic ordering, and explicit
`ready`, `needs-review`, and `blocked` states.

The audit reuses the existing event-log, dependency-graph, structured-document,
package-scanner, package-archive, and asset-audit boundaries. SQLite is opened
through an immutable read-only URI after checking the current schema and
rejecting an already active WAL. The audit performs an inventory and source
recheck before returning; a change is reported as a concurrency conflict.

`--check` is a presentation policy: it maps a non-ready report to the existing
`checks-failed` envelope and exit code without changing the report itself.

## Consequences

- Release verification can consume one stable report without duplicating
  product or persistence rules.
- Missing and warning-level work remains visible without being confused with
  corruption.
- The report is safe to run in CI and local-first workflows because it does
  not create locks, sidecars, or derived files.
- Release signatures, archive policy, and automatic repair remain separate
  follow-up stages.
