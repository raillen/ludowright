# ADR 0037: Durable ImageGen Generation Receipts

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `REFERENCES_AND_VISUAL_JOBS.md`, `IMAGEGEN_EXECUTION.md`, `PROJECT_FILESYSTEM.md`, `STRUCTURED_REPOSITORIES.md`

## Context

PR46 persisted an immutable `imagegen-operation` and validated PNG outputs, but
that manifest could not prove which provider attempt completed, identify exact
output bytes, preserve failure history, or provide generated-reference
provenance. Retrying a failed operation also needs durable contiguous attempt
metadata.

## Decision

1. Keep `GenerationReceiptContract` as the published receipt contract and add
   optional v1 adapter fields for operation and prompt fingerprints, tool
   metadata, UTC timestamps, and per-output validation facts. Existing v1
   documents remain valid; newly recorded receipts populate the richer fields.
2. Persist receipts as canonical JSON under
   `.ludowright/generation-receipts/<job-id>/<receipt-id>.json` through
   `JsonDocumentRepository`.
3. Persist one candidate `VisualReferenceContract` per successful output under
   `.ludowright/visual-references/`. Each generated reference points to the
   exact job and receipt and uses the output SHA-256 as its content revision.
4. Run operation creation, provider calls, PNG writes, candidate-reference
   writes, and successful-receipt creation under the existing
   `imagegen-execution` lock. A failed attempt rolls back operation artifacts
   first and then keeps a failed receipt without outputs.
5. Derive receipt and reference IDs from the operation revision, attempt, and
   output checksum. Provider labels default to `unspecified` when the host does
   not provide them. Raw provider payloads and credentials are never stored.
6. Do not add an event-log projection or SQLite migration in this slice. The
   canonical receipt and reference files are sufficient; indexing and review
   projections remain later workflows.

## Alternatives considered

### Treat the operation manifest as the receipt

Rejected because it has no terminal status, retry lineage, output checksum,
provider metadata, or durable failed-attempt record.

### Store receipts only in SQLite or the event log

Rejected because canonical structured records must remain available for local
inspection and recovery without requiring a rebuild or query index.

### Write generated references before provider completion

Rejected because a failed or partial attempt must not leave candidate records
that point to absent output bytes.

## Consequences

### Positive

- successful outputs are traceable to exact job, receipt, path, and bytes;
- failed attempts remain auditable after output rollback;
- retries preserve contiguous history without mutating prior receipts;
- the core remains provider-neutral and local-first;
- existing v1 receipt documents do not need migration.

### Negative

- receipt and reference files are not yet indexed in SQLite or projected into
  the event log;
- generated references remain candidates until the review workflow runs;
- wall-clock timestamps are operational metadata and are not deterministic,
  although formatting and IDs are deterministic.

## Compatibility and migration

The published `generation-receipt` schema remains version 1. New fields are
additive and optional for compatibility with existing fixtures and projects.
No database migration is required. New receipt files are created only for
ImageGen executions after this slice; old operation manifests are not rewritten.
