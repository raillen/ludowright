# ADR 0002: Immutable project aggregate with separate stage and lifecycle

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision owners:** Raillen Santos
- **Related issue or RFC:** Implementation Plan PR 6
- **Affected contracts:** project identity, targets, engine, dimensions, stage, lifecycle, future project events and manifests

## Context

A game project needs both a production position and an operational state. Treating these as one status creates ambiguous values: a project may be in production but paused, released but still active, or cancelled during concept.

Mutable objects would also make future event logging, auditing, retries, and deterministic Codex workflows harder because state could change without an explicit transition record.

## Decision drivers

- clear project status semantics;
- explicit invalid transitions;
- deterministic and testable behavior;
- compatibility with future append-only events;
- support for paused, cancelled, completed, and archived projects at meaningful stages;
- independence from persistence and serialization frameworks.

## Decision

LudoWright will represent the project as an immutable aggregate.

The aggregate separates:

- `ProjectStage` for production progression;
- `ProjectLifecycle` for operational activity.

Production stages form an adjacent, reversible sequence:

```text
concept ↔ pre-production ↔ production ↔ validation ↔ released ↔ post-release
```

Lifecycle values are:

```text
active | on-hold | cancelled | completed | archived
```

Rules:

1. stage transitions occur only while active;
2. stage transitions move one adjacent step;
3. completion requires released or post-release;
4. archived is terminal;
5. cancellation and completion may be explicitly reactivated before archival;
6. no-op transitions are idempotent;
7. every valid transition returns a new aggregate;
8. invariants are enforced both at construction and transition boundaries;
9. persistence and event history remain separate adapters and models.

## Consequences

### Positive

- stage and lifecycle answer different questions without overloading one field;
- transitions are pure and easy to test;
- future event records can describe before and after states exactly;
- invalid state combinations fail early;
- Codex can plan a transition before changing persisted data.

### Negative and trade-offs

- workflows must perform several adjacent transitions rather than skipping directly;
- reactivation is explicit even when a completed game returns to active maintenance;
- the initial stage vocabulary is intentionally broad and may not match every studio's milestone names;
- custom milestone tracking requires a later production-planning layer.

## Compatibility and migration

No persisted project schema exists yet.

Future changes to stage values, lifecycle values, transition rules, target families, or serialization require compatibility analysis and migration support after schema publication.

## Security and privacy

The aggregate stores no credentials or private service configuration. Engine versions and platform labels prohibit control characters.

Immutability does not replace authorization. Future commands must still require explicit approval for destructive lifecycle changes such as cancellation or archival.

## Validation

- unit tests for every invariant;
- property tests over the complete stage transition matrix;
- immutability tests;
- strict typing and repository quality gates;
- public contract documentation.

## Follow-up work

- publish project schemas;
- persist transitions through the event log;
- add CLI confirmation and dry-run behavior;
- derive project readiness and recommended next actions;
- connect lifecycle changes to decisions and approvals.

## References

- `docs/contracts/PROJECT_DOMAIN.md`
- `docs/contracts/IDENTIFIERS_AND_VERSIONS.md`
- `docs/plans/IMPLEMENTATION_PLAN.md`
