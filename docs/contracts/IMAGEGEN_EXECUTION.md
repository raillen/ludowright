# ImageGen Job Execution

## Scope

PR46 defines the provider boundary that executes one validated `VisualJob` and
its matching `CompiledPrompt`. The caller is responsible for selecting the job
from a `VisualJobPlan` whose state is `ready`; this adapter does not duplicate
planner readiness rules.

The execution boundary is implemented by
`integrations/codex/imagegen.py`. Its published operation record is the v1
`imagegen-operation` contract at
`schemas/v1/imagegen-operation.schema.json`.

This slice creates the terminal generation receipt and candidate generated
references described below. It does not create approvals, event-log entries, or
SQLite state. Approval and review remain later slices.

## Preparation

`ImageGenExecutor.prepare()` accepts:

- an immutable `VisualJob`;
- a provider-neutral `CompiledPrompt` for the exact same target;
- a validated project-relative output directory.

The compiled prompt must contain exactly the job's input reference IDs. The
operation records the job request revision, profile revision, prompt hash, full
positive and negative prompts, sorted input IDs, target, output directory, and
one output for every job role.

Preparation is deterministic. The output path for index `n` and role `role` is:

```text
<output-directory>/<n zero-padded to two digits>-<role>.png
```

The operation ID and content revision are SHA-256 values derived from the
canonical operation payload. A prepared operation also fixes its manifest at
`<output-directory>/operation.json`.

## Provider boundary

The Codex integration owns the small `ImageGenProvider` protocol:

```python
generate(request: ImageGenRequest) -> bytes
```

The provider receives the complete immutable operation and one output contract.
It is called exactly once per output, so one image always represents one
technical view. The provider is injected by the host; the core does not import
a network SDK or choose a provider, model, credentials, or retry policy.

Returned bytes must be a bounded, structurally valid non-animated PNG. The
validator checks the PNG signature, chunk order, CRCs, dimensions, `IDAT`, and
`IEND`, and rejects APNG animation chunks. Provider payloads are written through
the shared atomic `ProjectFilesystem` boundary.

## Transaction and conflicts

Execution acquires the project lock `imagegen-execution`. It then:

1. creates only missing output directories after validating every path segment;
2. refuses an existing operation manifest or output;
3. writes the operation manifest atomically before the first provider call;
4. calls the provider and writes each validated PNG atomically;
5. validates and persists one candidate reference per output;
6. persists a successful generation receipt only after every output and
   reference exists;
7. returns `executed` only after the receipt is durable.

Any conflict is fail-closed and never overwrites an existing file. A provider,
validation, or write failure removes the manifest, outputs created by this
attempt, and empty directories created by this attempt, then persists a failed
receipt without output references. If cleanup itself fails, the original error
remains the cause of `ImageGenRollbackError`. If the terminal receipt cannot be
persisted, the original execution failure remains the cause of
`ImageGenReceiptError`.

The operation is therefore create-only and retry-safe: a completed target must
be explicitly handled as a conflict rather than silently regenerated. A failed
attempt can be retried after its rolled-back operation is absent; the next
receipt uses the contiguous attempt number and points to the previous receipt
with `retry_of`.

## Dry-run and compatibility

`dry_run=True` returns the same deterministic operation with state `planned` and
does not acquire a lock, call the provider, create directories, or write files.

The operation manifest is the only new persisted artifact in PR46. It uses
schema version 1 and is registered in the generated schema manifest and the v1
compatibility fixtures. It intentionally has no output checksums, provider
metadata, timestamps, receipt ID, or generated-reference IDs; PR47 adds those
responsibilities without changing the immutable job or prompt contracts.

## Generation receipts

Receipts are persisted as canonical JSON under:

```text
.ludowright/generation-receipts/<job-id>/<receipt-id>.json
```

The additive v1 receipt fields include operation and prompt fingerprints,
provider/model/tool labels, canonical UTC timestamps, deterministic generated
reference IDs, output paths, byte sizes, SHA-256 checksums, dimensions, and the
bounded non-animated PNG validation result.

Candidate generated-reference contracts are persisted under:

```text
.ludowright/visual-references/<reference-id>.json
```

They point to the exact job and receipt and remain in `candidate` status. A
receipt is not approval. If provider metadata is unavailable, the adapter uses
`unspecified` labels. Dry-run creates neither images, references, nor receipts.
