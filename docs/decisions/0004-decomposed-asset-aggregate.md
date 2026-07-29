# ADR 0004: Decomposed asset aggregate with shared production status

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision owners:** Raillen Santos
- **Related issue or RFC:** Implementation Plan PR 8
- **Affected contracts:** assets, components, variants, states, ownership, production status, future registries and visual jobs

## Context

A useful asset record must describe more than a name and category. Character modeling may require a body, clothing, hair, props, variants, and functional states. Vehicles, buildings, vegetation, UI, audio, and effects need different decompositions but still share production concepts.

A flat checklist would lose hierarchy and completion rules. A highly specialized class per asset type would duplicate status, ownership, and validation while making project-specific categories difficult to add.

## Decision drivers

- support human and non-human assets;
- distinguish components, variants, and states;
- make completion depend on explicit required work;
- keep classification extensible without uncontrolled free text;
- preserve immutable and testable transitions;
- allow ownership at aggregate and child level;
- remain independent of capture profiles, storage, and engine integrations.

## Decision

LudoWright will model each asset as an immutable aggregate containing:

- typed `AssetId` and display name;
- stable `AssetFamily` plus optional open `AssetSubtype` slug;
- `AssetPriority`;
- shared `AssetStatus`;
- optional `AssetOwner`;
- immutable component, variant, and state tuples.

The domain adds typed IDs for:

- variants;
- asset states;
- owners.

Components may form an acyclic parent hierarchy inside one asset. Variants and states remain flat in this initial contract.

Assets and decomposed items share the same adjacent production-status vocabulary. Required child items block aggregate completion until completed. Optional items remain planned without blocking completion.

Ownership identifies responsibility only. Approval authority remains in the policy and application layers.

## Consequences

### Positive

- character clothing and props can be planned separately from the base body;
- the same aggregate supports buildings, creatures, vehicles, plants, UI, audio, and effects;
- required work produces deterministic completion blockers;
- optional scope remains visible without preventing milestone completion;
- component cycles and missing parents fail before persistence;
- extensible subtypes avoid frequent core enum changes;
- shared statuses simplify reporting and later ODS export.

### Negative and trade-offs

- one shared status vocabulary may not express every studio-specific workflow;
- variants and states do not initially support nested hierarchies;
- the aggregate does not yet model cross-asset dependencies or blockers;
- child status changes require replacing the aggregate in future application services;
- ownership does not encode allocation percentage, capacity, or permissions;
- completion readiness depends only on required child statuses, not approvals or external dependencies yet.

### Risks

- users may confuse variants with states;
- very large modular assets may create oversized aggregates;
- subtype slugs may diverge without a later taxonomy registry;
- a completed child might later become stale through reference or dependency invalidation;
- future workflow packs may require mapped custom stages rather than extending the core enum.

## Compatibility and migration

No persisted asset schema exists yet.

After schema publication, changes to families, statuses, transition maps, required-item semantics, ownership shape, or hierarchy rules require compatibility analysis and migrations.

Adding `VariantId`, `AssetStateId`, and `OwnerId` extends the typed-identifier architecture from ADR 0001 without changing its grammar.

## Security and privacy

Owner labels and IDs must not contain credentials, personal contact details, or private service identifiers.

Component hierarchy validation prevents cycles that could otherwise cause unbounded traversal. Future storage adapters must still enforce input-size limits and safe parsing.

Asset completion is not approval. Application policy must require approvals where appropriate before packaging or release.

## Validation

- unit tests for classification, ownership, decomposition, hierarchy, uniqueness, and completion;
- property tests for the complete status-transition matrix;
- immutability tests;
- cycle and missing-parent tests;
- strict typing, coverage, documentation, dependency audit, and secret scanning.

## Follow-up work

- model references, visual jobs, generation receipts, and visual reviews;
- connect capture profiles to asset classification and decomposition;
- publish JSON Schemas and fixtures;
- add asset dependencies and stale propagation;
- implement registry repositories and ODS export;
- expose asset planning and status commands through CLI and Codex.

## References

- `docs/contracts/ASSET_DOMAIN.md`
- `docs/contracts/IDENTIFIERS_AND_VERSIONS.md`
- `docs/plans/IMPLEMENTATION_PLAN.md`
