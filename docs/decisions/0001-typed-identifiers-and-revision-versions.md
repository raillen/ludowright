# ADR 0001: Typed identifiers and monotonic contract revisions

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision owners:** Raillen Santos
- **Related issue or RFC:** Implementation Plan PR 5
- **Affected contracts:** identifiers, display names, schemas, templates, profiles, future manifests and CLI JSON

## Context

LudoWright will persist and exchange entity references across Markdown, YAML, JSON, SQLite, ODS, generated images, package manifests, Codex workflows, and multiple operating systems.

Using unrestricted strings for every identifier would allow:

- accidental substitution between project, asset, job, and reference IDs;
- path separators or platform-reserved names;
- inconsistent casing and punctuation;
- silent Unicode normalization differences;
- unstable file names;
- ambiguity between human names and machine keys.

Schemas, templates, and capture profiles also need explicit versions. Semantic Versioning is appropriate for the LudoWright package, but it overstates what minor and patch digits mean for individual persisted contracts.

## Decision drivers

- deterministic serialization;
- cross-platform path safety;
- clear separation between human names and machine keys;
- runtime protection against mixing entity classes;
- simple migrations and compatibility checks;
- independence of the domain layer from Pydantic, SQLite, and filesystem adapters;
- readable values in repository files and Codex conversations.

## Options considered

### Plain strings everywhere

Simple initially, but provides no runtime type separation and allows invalid or unsafe values to propagate into storage and paths.

### UUIDs for all entities

Globally unique and easy to generate, but difficult for humans to read, review, type, and discuss. UUIDs also do not solve the need for stable semantic slugs in repository-native workflows.

UUIDs may still be used later for correlation or event IDs where semantic readability is not required.

### Prefixed strings enforced globally

Values such as `prj-*`, `ast-*`, and `job-*` improve readability but force generic domain code to understand taxonomy-specific naming. Asset prefixes such as `chr-*` and `prop-*` belong to asset-family rules, not the universal identifier grammar.

### Typed slug value objects and integer contract revisions

Provides readable serialization, cross-platform validation, runtime entity separation, and simple ordered revisions without coupling the domain to storage frameworks.

## Decision

LudoWright will:

1. represent human-facing names with a dedicated Unicode `DisplayName` value object;
2. represent canonical entity IDs with typed immutable value objects;
3. use lowercase ASCII kebab-case as the universal ID grammar;
4. reject platform-reserved device names;
5. require explicit `slugify()` conversion rather than silently rewriting IDs;
6. keep taxonomy-specific prefixes outside the generic identifier layer;
7. serialize identifiers as their canonical string value;
8. version schemas, templates, and profiles with separate positive integer revision types;
9. serialize structured revision values as integers and expose `vN` for human-facing tags;
10. keep package releases on Semantic Versioning independently of contract revisions.

Initial typed IDs are:

- `ProjectId`;
- `AssetId`;
- `ComponentId`;
- `ReferenceId`;
- `JobId`;
- `DecisionId`;
- `PackageId`.

Initial revision types are:

- `SchemaVersion`;
- `TemplateVersion`;
- `ProfileVersion`.

## Consequences

### Positive

- entity IDs cannot compare equal across different identifier classes;
- invalid path-like values fail at construction;
- serialized values remain readable and diff-friendly;
- names can remain internationalized without becoming unsafe paths;
- revision ordering is simple and explicit;
- future adapters can add Pydantic and JSON Schema support around stable domain values.

### Negative and trade-offs

- typed values require explicit conversion at serialization boundaries;
- ASCII transliteration can produce collisions;
- globally unique IDs are not guaranteed without project context;
- taxonomy-specific prefix enforcement requires an additional validation layer;
- integer revisions do not communicate compatibility without accompanying policy.

### Risks

- callers may bypass value objects and keep using raw strings;
- future schemas may accidentally serialize wrapper objects rather than primitive values;
- IDs may be mistaken for paths despite the documented separation;
- collision handling may become inconsistent if not centralized with repository storage.

## Compatibility and migration

This is the first identifier and contract-version decision, so no existing project data requires migration.

Future changes to:

- slug grammar;
- reserved names;
- maximum lengths;
- identifier serialization;
- revision representation;
- typed identifier set;

must include compatibility analysis and, when persisted data exists, a migration strategy.

## Security and privacy

The grammar rejects path separators, dot traversal, control characters, and common reserved device names.

Display names are explicitly not paths. Filesystem adapters must still validate repository-relative paths independently and must not assume that a valid ID alone makes a complete path safe.

Identifiers must not embed credentials, personal data, or confidential project information.

## Validation

The decision is validated through:

- unit tests for accepted and rejected values;
- property tests for deterministic and idempotent slug conversion;
- property tests for revision parsing and tag round trips;
- strict typing;
- coverage and repository quality gates.

## Rollout and rollback

The value objects are introduced before persisted project schemas. Future domain models will adopt them directly.

Rollback would remove the new domain module before public schema publication. After schemas are published, replacement requires a migration ADR.

## Follow-up work

- use typed IDs in the project domain model;
- use typed IDs in asset, decision, approval, reference, and job models;
- publish Pydantic and JSON Schema adapters;
- define taxonomy-specific asset naming policies;
- define filesystem-safe repository paths independently of IDs.

## References

- `docs/contracts/IDENTIFIERS_AND_VERSIONS.md`
- `docs/plans/IMPLEMENTATION_PLAN.md`
