# Asset taxonomy contract

The asset taxonomy is the versioned data catalog for stable asset families,
initial subtypes, and family-specific asset ID prefixes. Domain invariants
remain in `src/ludowright/domain/assets.py`; the catalog is shipped as data at
`src/ludowright/taxonomy_data/asset-taxonomy.json`.

The published contract is `asset-taxonomy` under `schemas/v1/`. It contains one
definition for every stable `AssetFamily`, sorted subtype definitions with
labels and descriptions, and one unique naming prefix for every family.

## Initial families

The catalog covers `animation`, `architecture`, `audio`, `character`,
`creature`, `environment`, `material`, `other`, `prop`, `terrain`, `texture`,
`ui`, `vegetation`, `vehicle`, and `vfx`.

Subtypes are extension data rather than new Python enum members. A future
taxonomy revision can add subtype records without changing the generic
identifier grammar. The `other` family includes `custom` as the explicit
project-defined extension point and still requires a subtype at the domain
boundary.

## Naming policy

The initial asset ID format is:

```text
{family-prefix}-{canonical-slug}
```

Examples are `chr-maya`, `prop-arcade-cabinet`, and `env-town-square`.
`load_asset_taxonomy()` composes generic slug validation with the declared
subtype catalog and family prefix. It does not replace `AssetId` or
`AssetSubtype` validation and does not persist or rename assets.

## Compatibility and scope

This slice adds a v1 catalog contract and packaged data; it does not change the
persisted `asset` contract, add registry commands, or persist project-specific
taxonomy overrides. Registry repositories and user-facing asset commands are
the scope of the following asset-registry PRs.

Loading is local-first, performs no network access, and computes a SHA-256
source digest for provenance.
