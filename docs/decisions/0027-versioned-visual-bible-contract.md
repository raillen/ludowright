# ADR 0027: Versioned Visual Bible Contract

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contract:** `contracts/VISUAL_BIBLE.md`

## Context

The visual foundation needs one canonical place for shared art direction before
capture profiles, prompt compilation, and visual jobs are planned. Without a
versioned contract, shape language, palette, materials, camera, and negative
constraints would remain prose in prompts and could change without a traceable
revision.

The repository already has strict domain values for camera, lighting, colors,
identifiers, and revision versions. The new contract must reuse those rules and
remain independent of ImageGen, provider payloads, image files, and CLI
workflow state.

## Decision

Publish a strict `visual-bible` v1 contract with:

- a stable `VisualBibleId`, `ProjectId`, and monotonic `VisualBibleVersion`;
- structured shape descriptors, proportion rules, palette colors, materials,
  detail levels, and provider-neutral workload limits;
- shared positive and negative constraints;
- the existing camera and lighting contract shapes;
- immutable ordered collections with unique scoped IDs;
- Pydantic serialization backed by domain validation and a checked-in JSON
  Schema, manifest checksum, and compatibility fixture.

The v1 deliberately stores guidance text rather than pretending that generated
images encode exact geometry. Prompt compilation, executable profiles, and
provider-specific budgets remain separate contracts.

## Alternatives considered

### Free-form prompt document

Rejected because important visual decisions would be hard to validate,
compare, hash, or consume deterministically.

### Provider-specific visual configuration

Rejected because it would make the core depend on one generation provider and
would mix direction with execution payloads.

### One large capture-profile document

Rejected because visual direction is project-level while capture profiles are
family- and asset-oriented. Profiles will consume the bible through a later
versioned relationship.

## Consequences

### Positive

- visual direction is reviewable outside chat history;
- invalid colors, duplicate entries, missing defaults, and contradictory
  constraint lists fail at the contract boundary;
- schema fixtures and checksums make compatibility visible;
- camera and lighting semantics remain aligned with capture profiles;
- future prompt and job layers have a stable source contract.

### Negative

- the v1 guidance fields do not encode exact geometry or provider cost;
- changing required visual semantics requires a schema compatibility decision;
- the project does not yet persist or edit visual bibles through a CLI.

## Compatibility

This PR adds a new v1 contract and does not alter existing persisted formats,
SQLite schema versions, event types, or migrations. Existing projects remain
valid. Future incompatible changes must publish a new schema version and retain
the v1 fixture.
