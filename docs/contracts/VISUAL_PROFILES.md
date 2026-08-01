# Foliage, UI, VFX, and Animation Profiles

## Purpose

The `visual-profile` v1 contract specializes the generic capture profile for
trees, plants, interface assets, visual effects, and animation references. It
keeps the vocabulary for components, variants, states, views, and outputs
explicit while reusing the existing capture, camera, lighting, validation, and
technical-sheet semantics.

Profiles are immutable package data. Loading one is local, deterministic,
provider-neutral, and side-effect free. A profile describes visual artifacts;
it does not create project files, visual jobs, image binaries, approvals, or
provider requests.

## Initial catalog

The closed v1 catalog is stored under `src/ludowright/profile_data/visual/`:

| Profile ID | Scope | Capture family | Capture subtype |
|---|---|---|---|
| `tree` | trees | `vegetation` | `large-tree` |
| `plant` | plants | `vegetation` | `plant` |
| `interface-icon` | interface icons | `ui` | `interface-icon` |
| `menu` | menus and panels | `ui` | `menu` |
| `particle-effect` | particle effects | `vfx` | `particle-effect` |
| `shader-effect` | shader and surface effects | `vfx` | `shader-effect` |
| `locomotion` | locomotion references | `animation` | `locomotion` |
| `motion-set` | reusable motion sets | `animation` | `motion-set` |

The profile ID is also the closed `profile_kind` value. New kinds or taxonomy
families require an explicit catalog and contract review.

## Contract shape

Each profile contains:

- `capture_profile` — a resolved v1 generic capture profile with no nested
  sheets;
- `profile_kind` — one of the eight initial visual-specialty kinds;
- `guidance` — bounded profile-level production guidance;
- `views` — roles and bounded guidance mapped to generic capture views;
- `components` — independently inspectable visual parts, with exactly one
  required `subject` component;
- `variants` — optional visual alternatives such as season, theme, or style;
- `states` — required conditions such as default, impact, loop, or contact;
- `outputs` — existing capture-sheet definitions for separate files and/or
  deterministic assembled sheets.

The specialized components, variants, and states must mirror the generic
capture requirements exactly, including IDs, names, requirement kinds, and
required flags. Profiles require at least one state and exactly one
`whole-subject` view. Every output references known views and at least one
assembled output is required.

Animation profiles use states and views to describe pose or motion phases;
they do not encode a runtime animation graph. VFX profiles describe visual
effect concepts and states; they do not execute shaders or particle systems.

## Loading package data

The application boundary loads the versioned manifests:

```python
from ludowright.application import load_visual_profile

profile = load_visual_profile("particle-effect")
capture_profile = profile.to_capture_profile()
```

The loader rejects noncanonical IDs, missing resources, duplicate JSON keys,
UTF-8 BOMs, invalid UTF-8, contract errors, and domain violations. Package
data is not a project-local persisted catalog; project selection remains a later
roadmap slice. Profile-aware visual-job planning is implemented by the generic
deterministic planner and is documented in
[`VISUAL_JOB_PLANS.md`](VISUAL_JOB_PLANS.md).

## Published contract and compatibility

The source model is `src/ludowright/contracts/visual_profiles.py`. The
published schema is `schemas/v1/visual-profile.schema.json`, with a valid
fixture at `tests/fixtures/contracts/v1/visual-profile.json`.

This slice adds no CLI command, project manifest field, event type, dependency
graph mutation, SQLite table, migration, provider adapter, visual job, or
image execution. Existing project, asset, capture-profile, visual-reference,
visual-job, event-log, dependency-graph, and state-store formats remain
compatible; no migration is required.
