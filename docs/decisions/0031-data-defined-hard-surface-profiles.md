# ADR 0031: Data-Defined Environment and Hard-Surface Profiles

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers

## Context

The generic capture-profile model already owns camera, views, requirements,
validation, and technical-sheet invariants. Props, vehicles, buildings,
modular kits, and interiors need additional construction components,
relationship guidance, and explicit operational states. A second capture
implementation would duplicate those rules and make future visual-job
planning inconsistent.

Construction relationships also need a stable, reviewable representation for
technical references. Free-form relationship text would not provide enough
structure for deterministic validation or future planning.

## Decision

Publish `hard-surface-profile` v1 with these rules:

1. profiles are versioned JSON data under package resources, not Python
   constants;
2. each profile embeds a resolved `capture-profile` without generic sheets;
3. the closed profile catalog contains `prop`, `vehicle`, `building`,
   `modular-kit`, and `interior`, each with an exact asset-family/subtype
   mapping;
4. components and states mirror generic capture requirements exactly;
5. construction views map existing capture views to bounded roles and require
   a whole-asset view;
6. connection-matrix rows are directed, typed, unique, non-self-referential,
   and limited to known components;
7. outputs reuse the existing capture-sheet contract and are projected into
   the generic profile in data order;
8. loading is local, immutable, deterministic, provider-neutral, and
   side-effect free.

The domain owns these invariants, Pydantic contracts publish them, and the
application loader owns package-resource access and error translation. No
project persistence, event-log write, graph mutation, SQLite migration, job
creation, or provider execution is part of this slice.

## Alternatives considered

### Duplicate a hard-surface-specific capture-profile model

Rejected because camera, view, validation, requirement, and sheet invariants
would drift from the generic contract.

### Accept arbitrary construction kinds and relationship strings

Rejected for v1 because downstream planning could not rely on stable family,
component, view, state, or connection semantics. The closed catalog can be
expanded deliberately.

### Reuse the project dependency graph for the connection matrix

Rejected because the matrix is capture guidance between construction
components, while the dependency graph records project artifact invalidation.
Conflating them would introduce persistence and lifecycle coupling before
profile-aware job planning exists.

### Persist package profiles in each project immediately

Rejected because project-local profile selection and migrations are separate
roadmap concerns. Package data can be validated and tested first without
changing persisted project formats.

## Consequences

### Positive

- five useful construction profiles are available without provider coupling;
- family/subtype mismatches, invalid components, views, states, and matrix
  rows fail closed;
- manifests remain reviewable and extensible as data;
- generic capture-profile and sheet validation remains authoritative;
- deterministic derivation is testable without filesystem writes or network
  access.

### Negative

- the construction vocabulary and connection kinds are intentionally narrow;
- profiles are not yet selectable from a project-local catalog or visual-job
  planner;
- the matrix describes capture relationships but does not create graph edges;
- variant semantics and provider execution remain unsupported.

## Compatibility

This decision adds the v1 `hard-surface-profile` contract, schema, fixture,
and five package manifests. Existing project, asset, capture-profile,
visual-reference, visual-job, event-log, dependency-graph, and SQLite formats
remain unchanged; no migration is required. Changing the closed catalog,
family/subtype mapping, requirement mapping, matrix semantics, or output
projection rules requires a new schema revision or an explicitly compatible
decision with regression tests.
