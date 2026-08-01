# ADR 0029: Data-Defined Humanoid and Wearable Profiles

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contract:** `contracts/HUMANOID_PROFILES.md`

## Context

The generic capture-profile model already defines camera, views, component
requirements, validation, and technical-sheet semantics. Humanoid production
needs additional structure for a neutral body base and common wearable
categories, but duplicating those generic rules would create two sources of
truth and make later visual-job planning inconsistent.

The product also requires body-base representation constraints to remain
explicit and reviewable. An unbounded free-text instruction would allow unsafe
or ambiguous representations to reappear in profile data or prompts.

## Decision

Publish `humanoid-profile` v1 with these rules:

1. package profiles are versioned JSON data, not Python constants;
2. each profile embeds the existing `capture-profile` contract without sheets;
3. the profile declares one required body-base component and categorized
   wearable components for hair, garments, footwear, accessories, props, and
   details;
4. outputs reuse the existing capture-sheet contract and are deterministically
   added to the generic profile by the application/domain boundary;
5. neutral representation is a closed enum of neutral bodysuit, fitted neutral
   clothing, or technical mannequin, with bounded guidance;
6. profile loading is local, immutable, provider-neutral, and side-effect free.

## Alternatives considered

### Duplicate a humanoid-specific capture-profile model

Rejected because camera, view, validation, requirement, and sheet invariants
would drift from the existing generic contract.

### Store only free-form category guidance

Rejected because category identity, requiredness, and component linkage would
not be machine-validatable or deterministic.

### Allow arbitrary body representation text

Rejected because representation safety belongs in a closed policy contract, not
only in prompts or agent instructions.

## Consequences

### Positive

- the minimal profile can be reviewed and extended without Python changes;
- existing capture-profile and sheet validation remains authoritative;
- body-base policy is explicit and provider-neutral;
- profile derivation is deterministic and testable without filesystem or
  network side effects;
- later foliage, UI, and VFX profiles can use the same data-driven boundary
  without inheriting humanoid categories; creature and hard-surface profiles
  now use that boundary in dedicated contracts.

### Negative

- package profiles are not yet selectable from a project-local persisted
  catalog or visual-job planner;
- the initial category vocabulary is intentionally narrow;
- profile outputs describe required artifacts but do not execute or approve
  images.

## Compatibility

This decision adds the v1 `humanoid-profile` contract and package data only.
Existing persisted project, asset, capture-profile, visual-reference,
visual-job, event-log, dependency-graph, and SQLite formats remain unchanged;
no migration is required. Changing the closed neutral-policy enum, component
mapping semantics, or output derivation rules requires a new schema revision
and an explicit compatibility review.
