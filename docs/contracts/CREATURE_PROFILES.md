# Creature and Animal Profiles

## Purpose

The `creature-profile` contract is the first data-defined specialization for
animals and non-humanoid creatures. It describes anatomy, isolated components,
functional states, anatomy-specific views, and technical-sheet outputs while
reusing the generic `capture-profile` contract.

Profiles are immutable package data. Loading a profile is local, deterministic,
provider-neutral, and side-effect free. The profile describes required visual
artifacts; it does not create project files, image binaries, visual jobs, or
approval records.

## Initial catalog

Version 1 publishes these profile IDs under
`src/ludowright/profile_data/creature/`:

| Profile ID | Anatomy family |
|---|---|
| `quadruped` | four-limb animals with a body, head, limbs, and optional tail |
| `bird` | birds with body, head, wings, tail, and optional beak detail |
| `fish` | fish with body, head, fins, tail, and optional gill detail |
| `insect` | segmented insects with legs, antennae, and optional wings |
| `fantasy-creature` | bounded unusual anatomy with optional tail, horns, or shell |

The catalog is intentionally closed for v1. Adding an anatomy family requires
a contract revision or an explicitly compatible catalog change with tests and
documentation.

## Contract shape

Each profile contains:

- a resolved v1 `capture-profile` with `family: creature` and a subtype equal
  to the anatomy kind;
- one `anatomy` record with a closed kind and bounded NFC guidance text;
- `anatomy_views`, mapping existing capture views to roles such as
  `whole-body`, `limb`, `wing`, `fin`, `tail`, `antennae`, `silhouette`, or
  `underside`;
- `components`, which must match the generic component requirements exactly;
- `states`, which must match the generic state requirements exactly;
- `outputs`, which reuse the generic capture-sheet contract.

Every profile requires exactly one required `body` component, at least one
whole-body anatomy view, at least one state, and at least one assembled output.
Only component and state requirements are supported by this specialization;
variant requirements are rejected until a later profile contract defines their
semantics.

Guidance is bounded to 1,000 Unicode NFC characters and rejects control
characters. IDs, names, views, requirements, and output references are checked
by the existing domain and capture-profile invariants.

## Loading and compatibility

`load_creature_profile()` reads a versioned JSON manifest from package data,
rejects invalid slugs, duplicate keys, UTF-8 BOMs, invalid UTF-8, schema errors,
and domain violations, then returns an immutable domain profile. The
`CreatureProfile.to_capture_profile()` projection adds the specialized output
sheets to a validated generic capture profile in deterministic order.

The `creature-profile` v1 schema and compatibility fixture are published with
the other contracts. This PR changes no project-local persisted format, event
log, dependency graph, SQLite state store, migration, provider adapter, or
visual-job format; no migration is required.

## Future expansion

Project-local profile selection, profile-aware job planning, richer pose and
variant semantics, reference provenance, and provider execution remain later
roadmap work. New profile data should preserve the generic capture-profile
boundary and keep template-specific behavior in data rather than Python.
