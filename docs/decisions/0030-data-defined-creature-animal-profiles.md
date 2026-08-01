# ADR 0030: Data-Defined Creature and Animal Profiles

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers

## Context

The generic capture-profile model already owns camera, views, requirements,
validation, and technical-sheet invariants. Animal and creature production
needs additional anatomy-specific guidance, isolated components, and explicit
functional states. A second capture-profile implementation would duplicate
those rules and make future visual-job planning inconsistent.

The initial catalog must remain small and auditable. Unbounded free-text
anatomy categories would make profile compatibility and downstream planning
ambiguous.

## Decision

Publish `creature-profile` v1 with these rules:

1. profiles are versioned JSON data under package resources, not Python
   constants;
2. each profile embeds a resolved `capture-profile` without generic sheets;
3. the profile family is `creature`, and its subtype must equal one closed
   anatomy kind: `quadruped`, `bird`, `fish`, `insect`, or `fantasy-creature`;
4. components and states mirror generic capture requirements exactly;
5. anatomy views map existing capture views to bounded anatomy roles and require
   a whole-body view;
6. outputs reuse the existing capture-sheet contract and are projected into the
   generic profile in data order;
7. profile loading is local, immutable, deterministic, provider-neutral, and
   side-effect free.

The domain enforces these rules and Pydantic contracts publish them. The
application loader owns package-resource access and error translation. No
project persistence, event-log write, graph mutation, SQLite migration, job
creation, or provider execution is part of this slice.

## Alternatives considered

### Duplicate a creature-specific capture-profile model

Rejected because camera, view, validation, requirement, and sheet invariants
would drift from the generic contract.

### Accept arbitrary anatomy strings

Rejected for v1 because downstream planning could not rely on stable component,
view, and state semantics. The closed catalog can be expanded deliberately.

### Persist package profiles in each project immediately

Rejected because project-local profile selection and migration are separate
roadmap concerns. Package data can be validated and tested first without
changing persisted project formats.

## Consequences

### Positive

- five useful initial creature families are available without provider coupling;
- domain validation prevents mismatched anatomy, components, states, and views;
- profile manifests are reviewable and extensible as data;
- existing capture-profile and sheet validation remains authoritative;
- deterministic derivation is testable without filesystem writes or network
  access.

### Negative

- the anatomy vocabulary and state model are intentionally narrow;
- profiles are not yet selectable from a project-local catalog;
- outputs describe artifacts but do not execute or approve images;
- variant semantics remain unsupported for creature profiles.

## Compatibility

This decision adds the v1 `creature-profile` contract, schema, fixture, and
package manifests. Existing project, asset, capture-profile, visual-reference,
visual-job, event-log, dependency-graph, and SQLite formats remain unchanged;
no migration is required. Changing the closed anatomy vocabulary, requirement
mapping, or output projection rules requires a new schema revision or an
explicitly compatible decision with regression tests.
