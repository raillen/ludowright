# ADR 0021 — Data-driven asset taxonomy

- Status: accepted
- Date: 2026-07-30
- Decision owners: LudoWright maintainers

## Context

The asset domain already defines stable families and an extensible subtype
slug, but it had no canonical catalog. Without one, subtype names and family
prefixes could drift across registry commands, capture profiles, visual jobs,
and Codex workflows.

## Decision

Publish a strict `asset-taxonomy` contract and ship its initial catalog as
versioned JSON package data. The catalog covers every current `AssetFamily`,
declares sorted subtype records, and defines one unique prefix per family.

The application exposes a read-only loader and validation object. It composes
the existing generic slug and typed-ID rules with data-defined subtype and
prefix rules. It does not mutate the asset aggregate, persist taxonomy
overrides, or introduce asset registry commands.

## Consequences

- subtype and naming policy changes are reviewable data changes;
- future registry and visual workflows can share one catalog;
- asset IDs remain repository-safe while gaining family context;
- adding a subtype does not require changing the generic identifier layer;
- a new stable family still requires a domain enum and taxonomy revision;
- project-specific taxonomy persistence remains deferred to asset-registry stages.

## Compatibility

The existing `asset` v1 contract is unchanged. The new `asset-taxonomy` v1
contract has a fixture and generated schema. A semantic taxonomy change that
changes accepted subtype or naming values requires a reviewed catalog revision
and impact analysis for future persisted registries.
