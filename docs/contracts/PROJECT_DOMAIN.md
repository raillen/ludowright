# Project Domain Contract

## Purpose

The project aggregate records the smallest set of canonical facts needed to identify a game project and reason about its current production and operational state.

It intentionally excludes persisted storage, event history, decisions, assets, interviews, and generated documents. Those layers will reference this contract rather than duplicate it.

## Project identity

`ProjectIdentity` contains:

- `ProjectId` — stable machine-facing identifier;
- `DisplayName` — canonical human-facing name;
- optional `codename` — internal or pre-announcement name.

Changing a display name does not imply changing the project ID.

## Dimensions

`ProjectDimension` records the primary spatial representation:

- `2d`;
- `2.5d`;
- `3d`;
- `mixed`.

This is a production-planning fact, not a claim about a specific engine renderer.

## Platform targets

Each `ProjectTarget` contains:

- a stable `PlatformFamily`;
- an optional human label for generation, device, storefront, or deployment detail.

Families are deliberately broad:

- Windows;
- Linux;
- macOS;
- web;
- Android;
- iOS;
- PlayStation;
- Xbox;
- Nintendo;
- Steam Deck;
- XR;
- other.

An `other` target requires a label. A project requires at least one target.

Broad families avoid changing the domain every time hardware generations or storefront names change. A label may preserve specificity such as `PlayStation 5` or `Experimental Arcade Cabinet`.

## Engine selection

`EngineSpec` contains:

- a display name;
- an optional version string.

The project may omit an engine while it remains undecided or engine-independent.

The version is descriptive rather than parsed as SemVer because engines use different release schemes. It must be trimmed, free of control characters, and no longer than 64 characters.

## Production stages

`ProjectStage` describes where the project is in production:

```text
concept ↔ pre-production ↔ production ↔ validation ↔ released ↔ post-release
```

Transitions move one adjacent step at a time. This makes rollback explicit and prevents a single command from silently skipping required phases.

Stage changes are allowed only while the lifecycle is `active`.

## Lifecycle states

`ProjectLifecycle` describes whether work is operationally proceeding:

- `active`;
- `on-hold`;
- `cancelled`;
- `completed`;
- `archived`.

This is separate from production stage. For example, a project can be:

- in production and on hold;
- released and active;
- post-release and completed;
- cancelled during concept;
- archived at any stage.

`archived` is terminal. A cancelled or completed project may be explicitly reactivated before archival.

A project can be marked completed only in `released` or `post-release`.

## Immutability

The aggregate is immutable.

```python
updated = project.transition_stage(ProjectStage.PRE_PRODUCTION)
```

The method returns a new instance. The original object remains unchanged.

This supports future append-only events, reproducible state transitions, undo planning, and deterministic tests.

## Transition policy

No-op transitions return the same instance, making repeated commands idempotent.

Invalid transitions raise `InvalidProjectTransitionError` rather than silently coercing state.

Direct construction also enforces invariants, so persistence adapters cannot create a completed concept-stage project merely by bypassing transition methods.

## Serialization

The domain contract is adapted at the published Pydantic and JSON Schema boundaries. YAML serialization, migrations, and storage adapters remain separate infrastructure concerns.

Serialized enums will use their lowercase string values. Typed IDs serialize to their canonical string values. Exact published schema shapes will become stable in the JSON Schema publication phase.

The published `ProjectContract` also accepts optional template provenance:

- `template.id` — canonical template ID;
- `template.version` — positive template revision.

Initialization writes this metadata when a template is selected. Existing v1 manifests without the optional field remain valid.
