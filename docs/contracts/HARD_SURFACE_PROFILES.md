# Environment and Hard-Surface Profiles

## Purpose

The `hard-surface-profile` v1 contract specializes the generic capture profile
for props, vehicles, buildings, modular kits, and interiors. It describes
construction components, connection relationships, useful views, operational
states, and technical-sheet outputs without creating a second capture-profile
model.

Profiles are immutable package data. Loading one is local, deterministic,
provider-neutral, and side-effect free. A profile describes required visual
artifacts; it does not create project files, image binaries, visual jobs, or
approval records.

## Initial catalog

The closed v1 catalog is stored under
`src/ludowright/profile_data/hard-surface/`:

| Profile ID | Capture family | Capture subtype |
|---|---|---|
| `prop` | `prop` | none |
| `vehicle` | `vehicle` | `vehicle` |
| `building` | `architecture` | `building` |
| `modular-kit` | `environment` | `modular-environment` |
| `interior` | `environment` | `interior` |

The profile ID is also the closed `profile_kind` value. Adding a new kind or
changing the family/subtype mapping requires a contract revision or an
explicitly compatible catalog change with tests and documentation.

## Contract shape

Each profile contains:

- `capture_profile` — a resolved v1 generic capture profile with camera,
  background, lighting, validation, views, and component/state requirements;
- `profile_kind` — one of the five closed construction kinds;
- `construction_views` — roles and bounded guidance mapped to existing capture
  views, including at least one `whole-asset` view;
- `components` — separately producible construction parts, including exactly
  one required `root` component;
- `connection_matrix` — directed relationships between known components;
- `states` — construction, operational, or damage states mirrored exactly by
  generic state requirements;
- `outputs` — existing capture-sheet definitions for separate files and/or
  deterministic assembled sheets.

The nested `capture_profile.sheets` collection must be empty. The specialized
`outputs` collection is the only source of sheets, and
`HardSurfaceProfile.to_capture_profile()` projects those outputs into a
validated generic profile in data order.

Only component and state requirements are supported by this specialization.
Variant requirements remain outside the v1 hard-surface contract until their
semantics are defined explicitly.

## Connection matrix

Each matrix row has:

- `source_component_id` and `target_component_id`, both existing component
  IDs;
- a closed `kind`: `attachment`, `hinge`, `socket`, `edge`, `floor`, `wall`,
  `mount`, or `clearance`;
- bounded NFC guidance text;
- a `required` flag describing whether the relationship is required for the
  construction profile.

Rows are directed, cannot contain self-loops, and are unique by source,
target, and kind. The matrix is descriptive production guidance; it does not
mutate the project dependency graph and does not claim that every component
must be physically simulated.

## Versioned package data and loading

The five manifests are loaded with the application boundary:

```python
from ludowright.application import load_hard_surface_profile

profile = load_hard_surface_profile("vehicle")
capture_profile = profile.to_capture_profile()
```

The loader rejects noncanonical IDs, missing resources, duplicate JSON keys,
UTF-8 BOMs, invalid UTF-8, contract errors, and domain violations. Package
data is not yet a project-local persisted catalog; project selection and
profile-aware job planning belong to later roadmap slices.

## Published contract and compatibility

The source model is
`src/ludowright/contracts/hard_surface_profiles.py`. The generated schema is
`schemas/v1/hard-surface-profile.schema.json`, with a compatibility fixture at
`tests/fixtures/contracts/v1/hard-surface-profile.json`.

This slice adds no CLI command, project manifest field, event type, dependency
graph mutation, SQLite table, migration, provider adapter, visual job, or
image execution. Existing project, asset, capture-profile, visual-reference,
visual-job, event-log, dependency-graph, and state-store formats remain
compatible; no migration is required.

The visual-specialty profile contract uses the same generic capture boundary
for foliage, UI, VFX, and animation references while defining its own
data-defined vocabulary and invariants.
