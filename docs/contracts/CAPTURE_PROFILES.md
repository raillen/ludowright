# Capture Profiles

## Purpose

Capture profiles define how LudoWright must produce consistent visual references for an asset family.

A profile can specify:

- camera projection and framing;
- background treatment;
- lighting and shadows;
- output dimensions and quality rules;
- required views;
- isolated component, variant, and state captures;
- separate output files;
- deterministic assembled technical sheets;
- exact inheritance from another profile revision.

Profiles describe production requirements. They do not execute providers or store image binaries.

## Identity and revisions

Each profile has:

- `CaptureProfileId` — stable lineage identity;
- `ProfileVersion` — immutable revision;
- `DisplayName` — human-facing name;
- asset family and optional subtype.

A reference to a parent profile always contains both ID and version. Resolving against a different parent revision is invalid.

## Camera

`CameraSpec` supports:

| Projection | Focal length |
|---|---|
| `orthographic` | Forbidden |
| `isometric` | Forbidden |
| `perspective` | Required, 10–300 mm |

Framing margin is an integer from 0% to 50%.

Isometric is a semantic production projection. Provider adapters decide the exact camera implementation while preserving the profile's deterministic intent.

## Background

Background modes are:

- `transparent`;
- `solid`;
- `neutral`;
- `environment`.

A solid background requires a canonical uppercase `#RRGGBB` color. Other modes cannot define a color.

## Lighting

Lighting modes are:

- `flat`;
- `studio`;
- `natural`;
- `dramatic`;
- `unlit`;
- `custom`.

Shadow modes are:

- `none`;
- `contact`;
- `soft`;
- `full`.

Custom lighting requires a descriptive display label. Other modes cannot carry a custom label.

## Output validation

`CaptureValidation` defines:

- pixel dimensions from 64 to 16,384 pixels per axis;
- full-subject visibility;
- consistent scale;
- neutral-pose requirement;
- occlusion policy.

A profile cannot simultaneously require the full subject and allow occlusion.

Additional provider-specific quality metrics belong to adapters or future evaluation contracts.

## Views

Every resolved profile has at least one `CaptureView`.

A view includes:

- `CaptureViewId`;
- display name;
- azimuth from 0° to 359°;
- elevation from −90° to 90°;
- visual reference role;
- required or optional status.

Examples:

```text
front: azimuth 0, elevation 0
side: azimuth 90, elevation 0
rear: azimuth 180, elevation 0
top: azimuth 0, elevation 90
```

## Component, variant, and state requirements

`CaptureRequirement` unifies three typed requirement kinds:

| Kind | Required ID type | Example |
|---|---|---|
| `component` | `ComponentId` | `base-body`, `shirt`, `backpack` |
| `variant` | `VariantId` | `winter`, `festival` |
| `state` | `AssetStateId` | `open`, `closed`, `damaged` |

The ID type must match the declared kind.

This allows a character profile to require the body, clothing, and accessories as separate references while also describing variants and functional states.

## Technical sheets

A `CaptureSheet` defines:

- typed sheet ID and name;
- layout;
- ordered unique view IDs;
- subject modes;
- whether individual files are required;
- whether an assembled sheet is required;
- whether the sheet itself is required.

Layouts are:

- `grid`;
- `turnaround`;
- `exploded`;
- `contact-sheet`.

Subject modes are:

- complete asset;
- components;
- variants;
- states.

A sheet must request at least one output form:

- separate files;
- assembled sheet;
- both.

A subject mode for components, variants, or states requires at least one matching capture requirement in the resolved profile.

Sheets can reference only views present in the resolved profile.

## Root profiles

A root profile has no parent and must define:

- asset family;
- camera;
- background;
- lighting;
- validation rules;
- at least one view.

Its requirement collections are immutable tuples with unique IDs.

## Child profiles

A child profile contains an exact `CaptureProfileRef`.

It may omit inherited scalar values and collections.

Resolution rules:

1. the parent must already be resolved;
2. parent ID and version must match exactly;
3. the child cannot change the parent's asset family;
4. child subtype replaces or specializes the inherited subtype;
5. child camera, background, lighting, and validation replace inherited values when provided;
6. collection items with the same ID replace inherited items in place;
7. new collection items are appended in child order;
8. the resolved result has no parent pointer and passes all root-profile validation.

This produces deterministic ordering for views, requirements, and sheets.

## Optional inherited requirements

The initial inheritance model does not delete inherited requirements.

A child can replace an inherited view or requirement with the same ID and mark it optional. Complete removal may be introduced later only with explicit schema and compatibility rules.

## Relationship to visual jobs

A `VisualJob` stores the `ProfileVersion` used by the request. Future schemas will also bind the profile ID and resolved profile fingerprint.

Changing a resolved capture profile changes the request specification and therefore creates a new visual job rather than a retry of the previous job.

## Boundaries

Capture profiles do not define:

- prompts or provider payloads;
- image file paths;
- execution timestamps;
- approval authority;
- asset completion status;
- sheet-rendering implementation;
- schema serialization.

Those concerns belong to visual jobs, storage adapters, approvals, deterministic sheet assembly, and the forthcoming JSON Schema publication.
