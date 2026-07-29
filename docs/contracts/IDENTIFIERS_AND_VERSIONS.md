# Identifiers, Names, and Revision Versions

## Purpose

LudoWright needs stable values that remain safe across:

- YAML and JSON files;
- SQLite indexes;
- repository-relative paths;
- generated document links;
- Codex commands;
- ImageGen jobs and receipts;
- ODS exports;
- package manifests;
- Windows, Linux, and macOS.

Human-facing names and machine-facing identifiers therefore use different contracts.

## Display names

`DisplayName` stores a human-readable Unicode name.

Requirements:

- 1 to 120 characters;
- no surrounding whitespace;
- canonical Unicode NFC normalization;
- no control or invisible format characters.

Display names may contain spaces, accents, punctuation, and non-English text.

Examples:

```text
Última Ficha — Edição Brasileira
Maya's Backpack
Árvore do Cerrado
```

A display name is **never** used directly as a filesystem path.

## Canonical slugs

A canonical slug:

- uses lowercase ASCII letters and digits;
- separates segments with one hyphen;
- contains no spaces, underscores, repeated hyphens, path separators, or punctuation;
- is between 1 and 80 characters;
- excludes reserved cross-platform device names such as `con`, `nul`, `com1`, and `lpt1`.

Grammar:

```text
[a-z0-9]+(?:-[a-z0-9]+)*
```

Valid examples:

```text
locadora-2000
chr-maya
prop-backpack
ref-maya-identity
job-chr-maya-front-v1
```

Invalid examples:

```text
Locadora-2000
contains_underscore
two--hyphens
../outside
con
```

## Explicit slug conversion

`slugify()` converts a display value into a slug explicitly.

```python
from ludowright.domain import slugify

slugify("Última Ficha: Edição 2000!")
# "ultima-ficha-edicao-2000"
```

Conversion is deterministic and idempotent, but transliteration may cause collisions. For example, two different Unicode names can produce the same ASCII slug.

The caller must resolve collisions through project context or an explicit suffix. LudoWright must not silently rename an existing canonical entity.

Reserved names receive the suffix `-item` during explicit conversion:

```text
CON → con-item
```

## Typed identifiers

The initial identifier types are:

| Type | Entity |
|---|---|
| `ProjectId` | Game project |
| `AssetId` | Planned or produced asset |
| `ComponentId` | Component belonging to an asset |
| `ReferenceId` | External, candidate, approved, rejected, or archived reference |
| `JobId` | Workflow or generation job |
| `DecisionId` | Recorded decision |
| `PackageId` | Reproducible project or production package |

Each type uses the same slug grammar but remains a distinct runtime value object.

```python
from ludowright.domain import AssetId, ProjectId

ProjectId("shared") != AssetId("shared")
```

This prevents accidental comparison or substitution across entity classes.

The string representation remains the canonical serialized value:

```python
str(ProjectId("locadora-2000"))
# "locadora-2000"
```

Pydantic and JSON Schema adapters will be introduced with the published schema contracts. The domain objects do not depend on storage or serialization frameworks.

## Identifier prefixes

The base grammar does not require a global prefix. Individual schemas or taxonomies may require contextual prefixes such as:

```text
chr-
prop-
env-
ref-
job-
```

Prefix rules belong to the canonical schema or taxonomy that understands the entity context. The generic identifier layer only guarantees repository-safe syntax.

## Revision versions

Persisted schemas, deterministic templates, and capture or production profiles use positive monotonic integer revisions:

| Type | Example serialized value | Human tag |
|---|---:|---|
| `SchemaVersion` | `1` | `v1` |
| `TemplateVersion` | `3` | `v3` |
| `ProfileVersion` | `12` | `v12` |

Accepted parser inputs:

```text
1
"1"
"v1"
```

Canonical structured serialization uses the integer value. File names and human-facing labels may use the `vN` tag.

Rejected forms include:

```text
0
-1
"01"
"v01"
"1.0"
"V1"
```

## Why revision integers instead of SemVer

An individual schema, template, or profile revision is an ordered contract generation, not an independently released software product.

Compatibility is determined by explicit migration and compatibility rules, not inferred from a minor or patch digit.

LudoWright package releases continue to use Semantic Versioning. A package release may support several contract revisions simultaneously.

## Revision changes

Increment a revision when a persisted or generated contract changes in a way that can affect interpretation or deterministic output, including:

- adding a required field;
- removing or renaming a field;
- changing field meaning;
- changing validation;
- changing a deterministic template output;
- changing capture-profile requirements;
- changing inheritance behavior.

A revision change requires, according to impact:

- migration or compatibility handling;
- contract fixtures;
- tests;
- documentation;
- changelog entry;
- invalidation of affected derived outputs.

## Limits

Revision values range from `1` to `2,147,483,647`.

The limit keeps representations portable across common databases and tools. Reaching it would indicate a broken versioning process rather than a practical capacity problem.
