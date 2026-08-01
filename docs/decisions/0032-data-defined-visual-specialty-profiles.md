# ADR 0032: Data-Defined Visual Specialty Profiles

- Status: accepted
- Date: 2026-08-01
- Decision owners: LudoWright maintainers

## Context

The generic capture profile and the first specialized humanoid, creature, and
hard-surface profiles establish reusable camera, view, requirement, and sheet
semantics. Trees, plants, UI, VFX, and animation references need additional
vocabulary for components, visual variants, states, and production views, but
they do not yet need project persistence or provider execution.

The roadmap calls for a small, reviewable catalog before visual-job planning.
The catalog must remain data-defined, deterministic, and compatible with the
existing taxonomy and capture-profile contracts.

## Decision

Add one versioned `visual-profile` v1 contract with eight closed package-data
profiles:

- `tree` and `plant` for vegetation;
- `interface-icon` and `menu` for UI;
- `particle-effect` and `shader-effect` for VFX;
- `locomotion` and `motion-set` for animation references.

Each manifest declares its exact asset family/subtype mapping, bounded
guidance, typed components, optional variants, required states, typed views,
and capture-sheet outputs. The generic capture requirements are the canonical
execution boundary and must mirror the specialized declarations exactly.
Every profile has one required `subject` component, one `whole-subject` view,
at least one state, and an assembled output. The domain derives a generic
capture profile from the specialized output definitions without mutating
project state.

## Alternatives considered

### Four independent contracts

Separate foliage, UI, VFX, and animation contracts would duplicate the same
capture, requirement, view, and output semantics and make future cross-domain
catalogs harder to validate. One specialization with a closed kind keeps the
shared boundary explicit.

### Untyped strings and free-form requirements

Arbitrary component, state, and view strings would defer errors to visual-job
planning and make taxonomy drift easy. Typed enums and mirrored generic
requirements fail closed at load time.

### Project-local persistence in this slice

Persisting profile selections now would broaden the change into project
manifests, event-log events, SQLite indexes, migrations, and CLI behavior.
Those concerns belong to a later profile-aware planning slice.

## Consequences

The catalog is intentionally small and can expand through new data manifests,
tests, and documentation. Loading remains local, deterministic, and
side-effect free. No existing persisted project format, event log, dependency
graph, SQLite schema, provider boundary, or migration changes.
