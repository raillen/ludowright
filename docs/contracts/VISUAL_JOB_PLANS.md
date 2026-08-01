# Visual Job Plans

## Purpose

The visual-job planner turns explicit assets, resolved capture profiles, approved
references, and an optional dependency graph into a deterministic, provider-
neutral plan. It decides what work is required and whether that work is ready;
it does not execute image generation or persist project state.

The published boundary is the `visual-job-plan` v1 contract at
`schemas/v1/visual-job-plan.schema.json`. The domain rules live in
`src/ludowright/domain/visual_planning.py` and the orchestration lives in
`src/ludowright/application/visual_planning.py`.

## Inputs and job derivation

`VisualJobPlanner.plan()` accepts one or more `VisualPlanTarget` values. Each
target contains an `Asset`, an already resolved `CaptureProfile`, and explicit
reference IDs. Profile inheritance must be resolved before planning; project-
local profile catalog persistence is outside this slice.

For every required `CaptureSheet`, the planner derives one immutable
`VisualJob` for each required subject target:

- `asset` captures the complete asset;
- `components` captures required profile components that exist in the asset;
- `variants` captures required profile variants that exist in the asset;
- `states` captures required profile states that exist in the asset.

The special component ID `subject` denotes the complete asset. Optional sheets
and optional requirements do not create jobs. Each job contains one output role
per capture view, a request revision derived from a canonical SHA-256 payload,
and a stable ID derived from that same payload. The planner is therefore safe to
run repeatedly without generating duplicate identity values.

Missing or inactive assets/items, missing required sheets, invalid reference
selection, and excessive outputs produce stable blocker codes rather than
partially valid jobs.

## References and readiness

Only explicitly selected references are considered. A reference must exist,
have `approved` status, and target the exact planned asset/item to become a job
input. Reference IDs are sorted before hashing and serialization.

The plan is `ready` only when it has no blockers. Otherwise it is `blocked` and
the contract retains every deterministic blocker with a semantic code, subject,
and diagnostic message. Blockers include stale dependencies, missing
prerequisite jobs, reference problems, missing required items, and visual-bible
budget violations.

## Dependency ordering

The planner consumes the existing `DependencyGraph`; it never mutates or
persists it. Incoming asset-to-asset `requires` edges order every source-asset
job before every target-asset job. A required prerequisite omitted from the plan
is a blocker. Non-fresh graph nodes reachable through propagating edges also
block readiness.

Component parent relationships are projected into the transient visual-job
ordering graph, so parent component jobs precede child component jobs when both
are planned. The existing graph's deterministic topological-order operation is
reused for the final order.

## Batches and estimates

Jobs are grouped into `VisualJobBatch` values by exact capture-profile ID and
version. Batch IDs are deterministic and batch membership is create-only from
the planner's perspective.

The workload estimate is provider-neutral:

- one output equals one cost unit;
- one output costs at least one workload unit;
- larger capture dimensions multiply workload by the ceiling of pixel area over
  1,048,576 pixels;
- visual-bible limits can block plans before execution.

These units are planning signals, not provider prices or time guarantees.

## Persistence and execution

The planner itself has no project files, event-log records, SQLite writes,
locks, image outputs, provider calls, or CLI command. The ImageGen execution
adapter consumes a job selected from a `ready` plan and must preserve its
immutable job ID and request revision. It binds the job to a matching compiled
prompt and records that binding in the separate `imagegen-operation` contract.
Any persisted plan must use the published contract and the existing atomic
repository, event-log, and state-store boundaries.

The plan does not select profiles from a project catalog, compile prompts,
execute ImageGen, create receipts, or approve references. Prompt compilation
and ImageGen operation execution are separate stages; receipts and approvals
remain later roadmap stages.
