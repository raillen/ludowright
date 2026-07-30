# Asset Domain Contract

## Purpose

The asset aggregate is the canonical production record for anything a game project must create, acquire, configure, or validate.

It supports visual and non-visual work, including:

- characters and creatures;
- architecture, environments, terrain, and vegetation;
- props and vehicles;
- materials and textures;
- animation, UI, VFX, and audio;
- project-specific families through an extensible subtype.

Capture views, prompts, references, generation receipts, file paths, budgets, dependencies, and engine import settings belong to later contracts.

## Classification

An `AssetClassification` combines:

- one stable `AssetFamily` enum;
- an optional extensible `AssetSubtype` slug.

Initial families:

```text
character | creature | environment | architecture | prop
vehicle | vegetation | terrain | material | texture
animation | ui | vfx | audio | other
```

Subtypes remain open and repository-safe:

```text
humanoid
quadruped
modular-building
handheld-tool
large-tree
interface-icon
```

The `other` family requires a subtype. Other families may use a subtype when more precision is useful.

A subtype is classification data, not a second asset ID. The initial canonical
subtype catalog and family naming prefixes live in
[`ASSET_TAXONOMY.md`](ASSET_TAXONOMY.md).

## Priority

`AssetPriority` represents relative production importance:

```text
critical | high | normal | low | backlog
```

Priority is independent from status. A critical asset may still be planned, and a backlog asset may already be completed.

## Ownership

`AssetOwner` identifies the responsible production owner through:

- `OwnerId`;
- human label;
- `OwnerKind`.

Owner kinds:

```text
person | team | role | automation
```

Ownership indicates responsibility, not authorization. It does not grant approval rights and does not replace the decision and approval policy layer.

Assets, components, variants, and states may each identify an owner. A child owner can differ from the aggregate owner.

## Decomposition

An asset may contain immutable tuples of:

- components;
- variants;
- states.

Every item has its own typed ID, display name, production status, required flag, and optional owner.

### Components

An `AssetComponent` is a separately producible part of the same asset.

Examples:

```text
base-body
hair
shirt
backpack
left-hand
vehicle-wheel
building-door
```

Components may reference a parent component, creating an acyclic hierarchy.

Rules:

- component IDs are unique inside the asset;
- a component cannot parent itself;
- the parent must exist in the same asset;
- cycles are rejected;
- ordering in the tuple is presentation order, not dependency order.

### Variants

An `AssetVariant` is an alternative expression of the asset.

Examples:

```text
summer-outfit
winter-palette
young-tree
premium-storefront
```

A variant answers **which alternative version?**

### States

An `AssetState` is a functional or visual condition of the same asset.

Examples:

```text
open
closed
damaged
sleeping
powered-off
```

A state answers **what condition is the asset in?**

Variants and states are deliberately separate. A seasonal palette is not the same concept as an opened container or damaged vehicle.

## Required and optional items

Every decomposed item has a boolean `required` flag.

Required items block aggregate completion until their status is `completed`. Optional items remain visible in the production plan but do not prevent completion.

This supports scopes such as:

- body and standard clothing required;
- festival hat optional;
- closed and open states required;
- damaged state optional for the first milestone.

Changing a required flag after schema publication will affect readiness and derived production reports, so it must remain traceable through canonical data and the future event log.

## Production status

Assets and decomposed items share one progress vocabulary:

```text
planned ↔ specified ↔ ready ↔ in-production ↔ in-review ↔ completed
   └──────────────→ cancelled ↔ planned
completed → archived
cancelled → archived
```

The exact transitions are:

- planned → specified or cancelled;
- specified → planned, ready, or cancelled;
- ready → specified, in-production, or cancelled;
- in-production → ready, in-review, or cancelled;
- in-review → in-production, completed, or cancelled;
- completed → in-review or archived;
- cancelled → planned or archived;
- archived is terminal.

Transitions are adjacent and explicit. No-op transitions are idempotent.

An aggregate may enter `completed` only when all required components, variants, and states are completed.

A completed aggregate may return to `in-review`. This supports corrections and post-review discoveries without rewriting history. It must return through review before becoming completed again.

## Immutability

All asset values are immutable dataclasses.

```python
specified = asset.transition_status(AssetStatus.SPECIFIED)
```

The original asset remains unchanged.

Decomposition collections are tuples. Mutable lists and invalid element types are rejected at the domain boundary.

## Typed identifiers

The asset domain adds:

- `VariantId`;
- `AssetStateId`;
- `OwnerId`.

These follow the universal slug grammar but remain distinct runtime types. A component, variant, state, and owner may share the same slug text without comparing equal.

## Boundaries

This contract does not yet define:

- asset-to-asset dependencies;
- blockers or risk records;
- estimates and budgets;
- capture profiles;
- references and generation jobs;
- review approvals;
- filesystem paths;
- engine import settings;
- ODS rows;
- persisted YAML or JSON shapes.

Those capabilities will reference the asset aggregate rather than expanding it into an all-purpose production object. Registry persistence and
project-specific taxonomy extensions remain later asset-registry work.
