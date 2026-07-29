# ADR 0005: Immutable Visual Jobs and Attempt Receipts

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `REFERENCES_AND_VISUAL_JOBS.md`

## Context

Visual production must support external references, generated images, direct captures, derived sheets, retries, failed provider calls, human review, approval, and replacement.

A single mutable generation record creates several ambiguities:

- whether a retry used the original request or a changed prompt;
- which provider attempt produced a particular image;
- whether an approval still applies after content changes;
- whether a failed response overwrote earlier diagnostic information;
- which exact outputs a human reviewed;
- whether a later job replaces or merely retries an earlier one.

The project also needs to operate across Codex, ChatGPT, ImageGen, future providers, local scripts, and deterministic document assembly without coupling the core domain to one API.

## Decision

LudoWright separates visual production into immutable records.

### Visual references

A visual reference identifies one exact content revision and records:

- target asset or one decomposed item;
- production role;
- origin;
- provenance lineage;
- revision-bound approval projection;
- replacement state.

External references use credential-free HTTPS provenance. Generated references point to both the immutable job and the exact attempt receipt.

### Visual jobs

A visual job is an immutable generation specification.

It records the target, capture-profile revision, request fingerprint, input references, output roles, output count, and optional superseded job.

Changing any request-defining input creates a new job instead of editing the existing job.

### Generation receipts

Every terminal attempt creates a new immutable receipt.

Receipts record provider/model identity, attempt number, request fingerprint, status, outputs or failure note, and retry lineage.

Receipts form a contiguous append-only series. Successful attempts are terminal for that series.

### Visual reviews

A visual review evaluates exact output references from one successful receipt.

Accepted reviews require a formal approval record. Changes-requested and rejected reviews require explanatory notes.

## Retry rule

A retry is allowed only when:

- the job is unchanged;
- the request fingerprint is unchanged;
- the previous attempt did not succeed;
- the new receipt names the immediately previous receipt.

A changed request creates a superseding job, not a retry.

## Approval rule

Approval remains bound to the immutable content revision.

Reference catalog status may project an accepted approval, but cannot manufacture approval independently. When the image changes, the old approval does not transfer.

## Consequences

### Positive

- retries cannot silently change prompts or profile requirements;
- every generated reference has attempt-level provenance;
- failed and cancelled attempts remain auditable;
- reviews cannot accidentally point to outputs from another receipt;
- changed jobs and retried jobs have different semantics;
- provider adapters remain replaceable;
- future cost, latency, and event data can attach without changing the domain model.

### Negative

- more records are created than in a mutable job model;
- callers must calculate request and content fingerprints;
- application services must coordinate jobs, receipts, references, reviews, and approvals;
- storage adapters must preserve append-only ordering and uniqueness.

## Alternatives considered

### Mutable job with current status

Rejected because retries, specification edits, and provider outcomes would overwrite history or require an ad hoc audit structure.

### One job per provider attempt

Rejected because it loses the distinction between retrying an unchanged request and intentionally changing the specification.

### Approval field directly on image files

Rejected because file replacement could leave stale approval metadata attached to changed content.

### Provider-specific generation models in the domain

Rejected because provider request/response formats are adapter concerns and would make the domain unstable.

## Security considerations

- external source URIs reject credentials and non-HTTPS schemes;
- request fingerprints and content revisions must not contain secrets;
- provider payloads and tokens are not stored in domain objects;
- approval does not imply reviewer authorization;
- future adapters must redact provider errors before storing review notes;
- file paths and binary content remain outside this domain contract.

## Compatibility

No persisted reference, visual-job, receipt, or visual-review schema exists yet.

After JSON Schema publication, changes to provenance origins, statuses, retry rules, output-count rules, or review outcomes require compatibility analysis, fixtures, and migrations.

## Follow-up

- capture-profile model;
- generated JSON Schemas and fixtures;
- repository adapters;
- append-only event log;
- provider execution adapters;
- approval policy and reviewer authorization;
- cost and performance telemetry.
