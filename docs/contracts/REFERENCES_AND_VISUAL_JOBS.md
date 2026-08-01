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
the prompt compiler. It is not a field in the v1 `VisualJob` contract. The
ImageGen adapter binds that immutable output to a job and its request
fingerprint through the separate `imagegen-operation` integration contract.

Changing prompts, references, profile revision, output count, target, or another request input creates a **new job**, normally with a new request fingerprint and an explicit superseding relationship.

## Deterministic visual-job planning

The pure `VisualJobPlanner` derives required immutable jobs from explicit assets,
resolved capture profiles, selected references, and an optional dependency graph.
It creates one job per required capture sheet and required asset, component,
variant, or state target. Optional sheets and requirements are not planned.

Planning is published as the `visual-job-plan` v1 contract. A plan contains
sorted jobs, deterministic dependency order, profile-revision batches,
provider-neutral workload estimates, and stable blocker codes. It is `ready` only
when required inputs, exact approved references, dependencies, and visual-bible
budget limits are satisfied; otherwise it is `blocked` with diagnostics.

The planner consumes the dependency graph without mutating it, and does not
write project files, event-log entries, SQLite state, prompts, receipts, or image
outputs. Profile selection, provider execution, and persistence remain separate
application stages. See the canonical [Visual Job Plans contract](VISUAL_JOB_PLANS.md)
and [ADR 0033](../decisions/0033-deterministic-visual-job-planner.md).

## ImageGen operation execution

The Codex integration consumes a job selected from a `ready` visual-job plan
and its matching compiled prompt. It creates a deterministic
`imagegen-operation` record, records the full prompt and sorted input IDs, and
sends exactly one provider request per output role. Each request must return one
valid, non-animated PNG for one technical view. Existing operation or output
paths are conflicts; they are never overwritten.

The operation manifest is written atomically before provider calls. A provider,
validation, or write failure rolls back the manifest, outputs, and empty
directories created by that attempt. This is an execution artifact, not yet a
`GenerationReceipt`: checksums, provider metadata, timestamps, output
references, and durable failure history remain the next slice. See the
[ImageGen execution contract](IMAGEGEN_EXECUTION.md) and
[ADR 0036](../decisions/0036-imagegen-job-execution.md).

## Review workflow

The `ludowright review` command applies one published `visual-review` contract
to the exact outputs of a successful receipt. It writes canonical review files
under `.ludowright/visual-reviews/`, approvals under `.ludowright/approvals/`,
updates generated references, persists dependency invalidation, and appends a
hash-chained event only after the required records are ready.

The supported outcome mapping is:

| Review outcome | Reference projection | Dependency effect |
|---|---|---|
| `accepted` | creates or completes a revision-bound approval and marks the reference `approved` | clears a prior review-required cause when fresh inputs permit refresh |
| `changes-requested` | keeps the reference `candidate` | marks the reference and downstream review consumers `review-required` |
| `rejected` | marks the reference `rejected` | marks the reference and downstream consumers `stale` |
| `accepted` with `supersedes` | approves the replacement and marks the old approved reference/approval `superseded` | records a non-propagating supersession edge and stale impact for the old reference |

The word “correct” in workflow discussions means `changes-requested` in the
published contract. Because v1 stores one singular `approval_id`, an accepted
review conservatively names exactly one output. Corrective and rejected
reviews may name multiple outputs.

New reviews require distinct reviewer and producer identities. An accepted
review requires a human reviewer; an agent cannot approve its own output or
the output of the same stable actor ID. The actor fields are additive and
optional in the v1 schema for compatibility with old documents, but the new
application command requires both fields.

The command is local-first and non-interactive. `--dry-run` validates the
receipt, references, approval policy, and graph plan without creating files or
events. Repeating the exact same review is idempotent; reusing a review ID with
different content is a conflict. Existing canonical records are never silently
overwritten. A project lock, atomic structured repositories, optimistic graph
digests, and rollback of files written by the current operation protect against
concurrent or partial execution. No SQLite migration is required: the JSON
records, dependency graph, and event log remain canonical, while the current
state store version remains a rebuildable derived index.

See the [Review CLI command](../commands/REVIEWS.md) and
[ADR 0038](../decisions/0038-visual-review-workflow.md).

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

The provider adapter also records, for each successful output:

- its repository-relative PNG path and deterministic reference ID;
- the exact byte count and SHA-256 checksum;
- the validated PNG dimensions, format, and non-animated result.

Receipts may additionally record the operation ID, compiled prompt hash,
provider tool label, and canonical UTC start/completion timestamps. These
fields are adapter metadata and do not change the immutable job request.

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

The current ImageGen adapter persists receipts and candidate generated
references as canonical JSON files under `.ludowright/generation-receipts/`
and `.ludowright/visual-references/`. Operational actor identity, latency,
costs, raw provider payloads, and event-log projection remain future concerns.

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

The domain objects do not define:

- repository-relative file paths;
- image binary storage;
- provider API payloads;
- adapter timestamps and provider metadata;
- monetary cost;
- database indexes;
- serialization format.

The receipt repository and provider adapter add those concerns without
weakening the domain invariants above. Generated reference records remain
candidates until the review and approval workflow accepts them.
