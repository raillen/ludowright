# ADR 0033: Deterministic Visual-Job Planner

- Status: accepted
- Date: 2026-08-01
- Decision owners: LudoWright maintainers

## Context

The repository now contains versioned visual-bible and capture-profile
contracts, specialized data-defined profiles, immutable visual jobs, approved
references, and an acyclic dependency graph. The next bounded capability must
derive the work required by a profile without making provider, persistence, or
Codex concerns part of the core contract.

## Decision

Implement one pure application service, `VisualJobPlanner`, over explicit
canonical inputs:

- assets;
- resolved capture profiles;
- selected references;
- an optional existing dependency graph;
- an optional visual-bible budget.

The planner derives one immutable job per required capture sheet and required
subject target, hashes a canonical payload for the job identity and request
revision, orders jobs through the existing deterministic graph mechanics, groups
jobs by exact profile revision, and returns a v1 `visual-job-plan` contract.

Plans are `ready` only without blockers. Missing required items, inactive
inputs, invalid approved-reference selection, stale prerequisites, omitted
required dependency jobs, output limits, and visual-bible budget violations are
represented as stable blocker codes.

The planner consumes but does not mutate or persist the dependency graph. It
does not select project-local profiles, compile prompts, call a provider, write
the event log, update SQLite, create receipts, or expose a CLI command.

## Alternatives considered

### Persist plans immediately

Rejected for this slice. Persistence would couple job derivation to event-log,
SQLite, locking, rollback, and migration concerns before the plan contract and
execution boundary are stable.

### Let each profile implement its own planner

Rejected. It would duplicate required-item, reference, batching, ordering, and
workload rules across profile families. Profiles remain data; the generic
planner owns shared semantics.

### Embed provider cost and scheduling policy

Rejected. Provider prices, latency, quotas, and concurrency are external and
unstable. The v1 planner exposes only deterministic provider-neutral units.

## Consequences

The visual pipeline has a reproducible planning boundary that can be tested and
reviewed without network access or image generation. Future execution, receipt,
review, and project-persistence stages can consume the stable plan while
preserving immutable jobs. A later project-local profile catalog and CLI must
adapt into this service rather than reimplement its rules.
