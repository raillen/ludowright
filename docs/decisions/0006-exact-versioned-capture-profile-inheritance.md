# ADR 0006: Exact Versioned Capture-Profile Inheritance

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contract:** `CAPTURE_PROFILES.md`

## Context

Visual-reference requirements repeat across many assets.

Characters may share front, side, rear, component-isolation, neutral-pose, background, and lighting rules. A humanoid profile may then add clothing and hand views, while one project may replace the background or output dimensions.

Copying complete profiles creates drift. Unversioned inheritance creates a different problem: updating a base profile silently changes every derived profile and therefore changes generation output without changing the child contract.

The project also needs deterministic ordering so generated files, technical sheets, tests, and future schemas remain reproducible.

## Decision

Capture profiles use immutable revisions and exact parent references.

A parent reference contains:

- `CaptureProfileId`;
- `ProfileVersion`.

A child resolves only against that exact profile revision.

## Resolution rules

- parents must be resolved before use;
- a child cannot change the inherited asset family;
- subtype may specialize or replace the inherited subtype;
- explicitly provided scalar settings replace inherited settings;
- collection items are matched by typed ID;
- a child item with an existing ID replaces the parent item in its original position;
- new child items are appended in child order;
- the resolved result is validated as a complete root profile.

The initial model does not remove inherited items. A child may replace one with the same ID and mark it optional.

## Why exact versions

Exact versions ensure that:

- a parent update does not silently alter an existing child;
- request fingerprints remain explainable;
- generated references can name the effective profile revision;
- migrations can identify affected profiles;
- reproducible packages can include the correct parent graph.

Using only the parent ID would make profile resolution depend on whichever revision happens to be current.

## Technical-sheet outputs

Profiles explicitly distinguish:

- individual output files;
- assembled technical sheets.

A sheet must request at least one of these forms and may require both. This supports workflows where every view, garment, accessory, state, or modular piece must remain individually usable while a consolidated sheet is produced for review.

## Consequences

### Positive

- shared requirements are reusable without silent drift;
- child overrides are deterministic;
- profile resolution produces stable ordering;
- family-level rules remain protected;
- jobs can fingerprint resolved profiles;
- individual images and assembled sheets are both first-class requirements.

### Negative

- callers must resolve inheritance before execution;
- parent updates require deliberate child revision updates;
- profile graphs and resolved fingerprints must be packaged later;
- removing an inherited requirement is not supported in the initial contract.

## Alternatives considered

### Copy complete profiles

Rejected because repeated requirements would diverge and become expensive to audit.

### Inherit the latest parent revision

Rejected because output could change without a child revision or migration.

### Merge collections by position

Rejected because ordering edits would replace the wrong requirements.

### Unordered set merging

Rejected because file names, job outputs, and technical-sheet slots need deterministic order.

### Allow child family changes

Rejected because a character profile silently becoming a prop profile would invalidate assumptions throughout visual production.

## Security and reliability

- profile values contain no provider credentials;
- inheritance cannot fetch remote profiles;
- exact references prevent dependency confusion between revisions;
- bounded dimensions, angles, focal lengths, and collection types prevent malformed resource requests;
- provider adapters must still enforce execution budgets and content safeguards.

## Compatibility

No persisted capture-profile schema exists yet.

After JSON Schema publication, changes to merge order, parent matching, scalar override semantics, requirement kinds, or sheet output rules require compatibility fixtures and migrations.

## Follow-up

- JSON Schema publication;
- resolved-profile fingerprints;
- profile catalogs by asset family;
- deterministic sheet assembly;
- project override files;
- capture-profile audit and migration tooling.
