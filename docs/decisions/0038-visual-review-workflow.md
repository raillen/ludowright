# ADR 0038: Canonical Visual Review Workflow

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `REFERENCES_AND_VISUAL_JOBS.md`, `DECISIONS_AND_APPROVALS.md`, `DEPENDENCY_GRAPH.md`, `EVENT_LOG.md`, `CLI.md`

## Context

PR47 makes generated outputs and their provenance durable, but a candidate
reference still needs an explicit review boundary. The workflow must preserve
the exact receipt and content revision, separate generation from approval, and
make corrections or rejection visible to dependency consumers. It must also
remain safe when a CLI process fails after writing one of several canonical
records.

## Decision

1. Introduce `ludowright review INPUT.json [PROJECT]` as the application entry
   point for the published `visual-review` contract. The contract outcome
   `changes-requested` is the canonical representation of “correct”.
2. Persist reviews at `.ludowright/visual-reviews/<review-id>.json`, approvals
   at `.ludowright/approvals/<approval-id>.json`, and update generated
   references in `.ludowright/visual-references/` through the shared structured
   repositories.
3. Accepted reviews create or complete one revision-bound approval and project
   that approval onto exactly one reference. This single-output rule is a
   conservative v1 choice because the contract has one singular `approval_id`.
   Corrective and rejected reviews may name multiple references.
4. Require stable reviewer and producer identities for new operations. IDs must
   differ, and only a human reviewer may accept generated output. Actor fields
   are additive in v1 so old review documents remain readable.
5. Update the canonical dependency graph in the same workflow. Rejection
   propagates `stale`, correction propagates `review-required`, and accepted
   supersession records a replacement edge while invalidating the old approved
   reference. Graph persistence remains JSON-canonical and SQLite remains a
   rebuildable derived index; no migration is introduced.
6. Hold the visual-review project lock, use atomic writes and optimistic graph
   replacement, append the event last, and restore only files written by the
   current operation when a later step fails. Exact retries are idempotent;
   different content for an existing review ID is a conflict.

## Alternatives considered

### Store review state only in the event log

Rejected because review and approval contracts must remain directly inspectable,
validated, and independently recoverable by local tooling.

### Let agents approve generated output

Rejected because the approval checkpoint is a product safety boundary. Agents
may produce and propose outputs, but an accepted generated reference requires a
distinct human reviewer.

### Overwrite an accepted reference during correction

Rejected because a correction is a new immutable review and, when accepted, a
new reference/approval revision. The previous history remains auditable.

## Consequences

### Positive

- review outcomes are durable and scriptable in human and JSON CLI modes;
- approved references remain bound to immutable content revisions;
- rejection and correction impacts are explainable through the dependency graph;
- failures do not leave an apparently complete review record;
- existing v1 review documents remain readable.

### Negative

- accepted v1 reviews cannot batch multiple outputs;
- SQLite does not immediately index review records in this slice;
- cross-file rollback is guarded by optimistic checks and is not a filesystem
  transaction across arbitrary external changes.

## Compatibility and migration

The `visual-review` schema remains version 1 with additive optional actor
fields. The command requires those fields for new operations and fails closed
when they are absent. No SQLite schema migration is required; the current
state-store version remains compatible and can be rebuilt from canonical
sources. Existing candidate generated references are not rewritten until an
explicit review is applied.
