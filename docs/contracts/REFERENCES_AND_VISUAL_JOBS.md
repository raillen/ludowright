# References and Visual Jobs

## Purpose

LudoWright treats visual production as a traceable pipeline rather than a folder of loosely related images.

The domain separates four records:

1. **visual reference** — one exact revision of an image or visual artifact;
2. **visual job** — an immutable generation specification;
3. **generation receipt** — the terminal result of one execution attempt;
4. **visual review** — a human outcome for outputs from one specific receipt.

This separation preserves provenance, supports retries without rewriting history, and prevents approvals from silently moving to changed content.

## Reference targets

A reference always targets an `AssetId`.

It may additionally select one decomposed item:

- `ComponentId`;
- `VariantId`;
- `AssetStateId`.

Selecting more than one decomposed item is invalid. A reference for a shirt component is therefore distinct from a reference for a winter variant or a damaged state.

## Reference roles

The initial roles are:

| Role | Purpose |
|---|---|
| `identity` | Stable identity or canonical appearance |
| `silhouette` | Outer shape and readability |
| `proportion` | Relative dimensions and scale |
| `construction` | Parts, joins, layers, or modeling information |
| `material` | Surface and material behavior |
| `color` | Palette and color relationships |
| `style` | Rendering and art-direction language |
| `context` | Environment or usage context |
| `negative` | Explicit example of what must not be reproduced |
| `output` | Generated production output |
| `other` | Project-specific role not covered above |

Roles describe production purpose. They do not imply approval.

## Provenance origins

Every reference includes a `SubjectRevision`, such as a SHA-256 fingerprint, Git revision, or immutable version tag.

### External

External references require a credential-free absolute HTTPS URI.

The URI contract rejects:

- HTTP;
- embedded usernames or passwords;
- relative paths;
- fragments;
- values longer than 2,048 characters.

An external reference may also record creator and license labels. Secrets, private tokens, and signed credentials must never be stored in the URI.

### Generated

Generated references require both:

- the `JobId` that specified the work;
- the `ReceiptId` for the exact attempt that produced the output.

Generated provenance cannot use an external source URI as a substitute for this lineage.

### Captured

Captured references require a creator label. This origin covers photography, scanning, screenshots, or other direct capture performed for the project.

### Derived

Derived references require one or more unique parent `ReferenceId` values. A reference cannot derive from itself.

Examples include:

- cropped details;
- annotated turnarounds;
- composite mood boards;
- cleaned silhouettes;
- deterministic sheet assemblies.

## Reference lifecycle

```text
candidate → approved → revoked → candidate
          → approved → superseded
          → rejected
          → archived
```

Additional terminal archival paths are allowed for rejected, revoked, approved, and superseded records.

An approved reference requires an `ApprovalId`. The approval record must refer to the same immutable content revision.

When content changes, the correct process is:

1. create a new reference revision;
2. request a new approval;
3. supersede the old reference when the replacement is accepted.

Reusing the old approval is invalid.

## Immutable visual jobs

A `VisualJob` is an immutable request specification containing:

- typed job ID and display name;
- reference target;
- capture-profile revision;
- request fingerprint;
- unique input reference IDs;
- one role for every expected output;
- expected output count;
- optional superseded job ID.

A job can be executed multiple times without changing the job itself.

The provider-neutral `compiled-prompt` output is produced before execution by
the prompt compiler. It is not yet a field in the v1 `VisualJob` contract;
future planning and execution slices will bind that immutable output to a job
and its request fingerprint.

Changing prompts, references, profile revision, output count, target, or another request input creates a **new job**, normally with a new request fingerprint and an explicit superseding relationship.

## Retries versus superseding jobs

A retry means:

- the job specification is unchanged;
- the request fingerprint is unchanged;
- the previous attempt did not succeed;
- a new receipt is appended.

A superseding job means the specification changed.

This distinction prevents failed provider calls from being mixed with intentional changes to art direction or production requirements.

## Generation receipts

A `GenerationReceipt` records one terminal attempt.

Required fields include:

- `ReceiptId`;
- `JobId`;
- attempt number;
- provider and model labels;
- request fingerprint;
- terminal status.

Statuses are:

- `succeeded`;
- `failed`;
- `cancelled`.

A successful receipt:

- contains generated `ReferenceId` outputs;
- contains no failure note;
- produces exactly the output count declared by the job.

A failed receipt:

- contains a review note describing the failure;
- contains no generated outputs.

A cancelled receipt contains no outputs. It may optionally omit a failure note because cancellation is not necessarily an execution error.

## Generation series

`GenerationSeries` binds a visual job to its append-only receipt history.

Rules:

- attempts begin at `1` and are contiguous;
- receipt IDs are unique;
- all receipts use the job ID and request fingerprint;
- attempts after the first name the immediately previous receipt in `retry_of`;
- a successful attempt is terminal and cannot be retried;
- successful output count matches the job specification.

Operational timestamps, actor identity, latency, costs, and provider payloads belong to future event-log and adapter contracts.

## Visual reviews

A `VisualReview` evaluates one or more exact output references from a named receipt.

Outcomes are:

| Outcome | Requirements |
|---|---|
| `accepted` | Requires an `ApprovalId` |
| `changes-requested` | Requires an explanatory note |
| `rejected` | Requires an explanatory note |

The generation series validates that:

- the receipt belongs to the job;
- the receipt succeeded;
- every reviewed reference was produced by that receipt.

A review may supersede an earlier review, but cannot supersede itself.

## Approval boundary

Visual review and approval are related but distinct:

- review says whether generated outputs satisfy the visual criteria;
- approval provides the formal revision-bound authorization record;
- reference status projects the accepted approval onto the catalog entry.

Reviewer identity, permissions, separation of duties, and agent restrictions belong to the future policy/application layer.

## Persistence boundary

These domain objects do not define:

- repository-relative file paths;
- image binary storage;
- provider API payloads;
- timestamps;
- monetary cost;
- database indexes;
- serialization format.

Those concerns will be added by schemas, repositories, the event log, and provider adapters without weakening the domain invariants above.
