# Humanoid and Wearable Profiles

## Purpose

The `humanoid-profile` v1 contract specializes the existing generic capture
profile for humanoid references. It makes the neutral body base, per-view
capture requirements, wearable categories, and assembled outputs explicit
without creating a second capture-profile model.

Profiles describe production requirements. They do not create image files,
choose a provider, persist project-local state, or claim that generated views
are exact geometric blueprints.

## Published contract

The source model is
`src/ludowright/contracts/humanoid_profiles.py`; the published contract is
`schemas/v1/humanoid-profile.schema.json` with a compatibility fixture at
`tests/fixtures/contracts/v1/humanoid-profile.json`.

The top-level shape contains:

- `capture_profile` — the existing v1 capture profile, including camera,
  background, lighting, validation, views, and component requirements;
- `neutral_representation` — one approved body-base mode and bounded guidance;
- `body_base` — the required `ComponentId` for the neutral body;
- `wearables` — categorized component IDs for hair, garments, footwear,
  accessories, props, and details;
- `outputs` — existing capture-sheet definitions for separate files and/or
  deterministic assembled sheets.

The nested `capture_profile.sheets` collection must be empty. The specialized
`outputs` collection is the only source for sheets, and the application derives
the generic resolved `CaptureProfile` from it. This prevents two competing
definitions of the same output.

## Neutral representation policy

The v1 policy allows only:

- `neutral-bodysuit`;
- `fitted-neutral-clothing`;
- `technical-mannequin`.

The policy is explicit data rather than hidden prompt prose. The default
minimal profile uses a neutral bodysuit and states that references support
modeling decisions but are not exact CAD or geometric projections. The policy
does not require a universal underside view; profiles can request useful
details such as soles, feet, attachment points, or underside components when
the asset needs them.

## Versioned package data

The first catalog entry is:

```text
src/ludowright/profile_data/humanoid/minimal/manifest.json
```

It is loaded with:

```python
from ludowright.application import load_humanoid_profile

profile = load_humanoid_profile("minimal")
capture_profile = profile.to_capture_profile()
```

The catalog is versioned package data. Loading the same entry twice yields the
same immutable domain value, and category, requirement, view, and output order
is preserved. Profile data is not yet a project-local persisted catalog; that
integration belongs to a later lifecycle slice.

## Boundaries and compatibility

This slice does not add a CLI command, visual-job planner, provider adapter,
image execution, approval workflow, SQLite table, event type, or migration.
Existing capture-profile, visual-reference, visual-job, event-log, dependency
graph, and state-store formats remain compatible. A future incompatible change
to profile categories, neutral modes, or output semantics requires a new
schema revision and a compatibility decision.

The profile is validated at both the Pydantic boundary and the domain boundary.
The body base and wearable IDs must exactly match component requirements,
required flags must agree, every output view must exist, and at least one
assembled output is required.
