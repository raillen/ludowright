# ADR 0009: Canonical Structured Document Repositories

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `STRUCTURED_REPOSITORIES.md`, `PROJECT_FILESYSTEM.md`, `JSON_SCHEMAS.md`

## Context

LudoWright needs human-editable JSON and YAML files for project manifests, decisions, assets, visual specifications, capture profiles, and later workflow state.

Using `json.load()` or `yaml.safe_load()` directly throughout the application would create inconsistent behavior:

- different byte limits;
- duplicate-key ambiguity;
- inconsistent Unicode handling;
- unsafe or surprising YAML features;
- inconsistent field validation;
- nondeterministic formatting;
- silent lost updates;
- direct writes that bypass atomic replacement and symlink protection;
- no stable document identity for provenance and conflict detection.

The project already has strict Pydantic contract models and a safe repository-relative filesystem boundary. Structured persistence should compose those layers rather than create another source of truth.

## Decision

LudoWright introduces generic JSON and YAML document repositories bound to one `ContractModel` type and one `RepositoryPath`.

The repository:

1. performs bounded reads through `ProjectFilesystem`;
2. decodes UTF-8 without BOM;
3. parses through strict format-specific loaders;
4. restricts values to a JSON-compatible tree;
5. validates through the bound Pydantic contract;
6. calculates SHA-256 over the exact bytes read;
7. reports whether the file is already canonical;
8. writes deterministic canonical bytes atomically;
9. coordinates writers through a stable per-path lock;
10. supports optimistic concurrency through expected digests.

## JSON decision

JSON parsing rejects duplicate keys and non-finite numbers.

Canonical JSON uses sorted keys, two-space indentation, native Unicode, omitted null fields according to the contract dump, and one trailing newline.

## YAML decision

YAML uses a customized `SafeLoader` and rejects:

- aliases;
- merge keys;
- duplicate keys;
- non-string keys;
- multiple documents;
- unsafe tags;
- empty documents;
- non-JSON-native constructed values.

Canonical YAML uses safe block-style dumping, sorted keys, two-space indentation, Unicode, no aliases, and one trailing newline.

YAML comments and manual key order are not preserved after canonical save.

## Why aliases are rejected

Aliases complicate exact document identity and can produce expansion attacks. They also make a local section depend on content defined elsewhere in the same file, weakening straightforward review.

Reusable project concepts belong in explicit IDs and versioned cross-document references, not YAML graph mechanics.

## Snapshot identity

A loaded document produces a snapshot containing the validated value and the SHA-256 digest of the exact source bytes.

The digest is byte identity rather than semantic identity. Formatting-only changes therefore participate in conflict detection.

This is intentional: an external editor changed the persisted revision even when the resulting model remains equal.

## Concurrency decision

Each repository derives a deterministic lock name from the repository path.

`create()`, `save()`, and `replace()` hold the lock while checking current state and performing the atomic write.

`replace()` requires a snapshot from the same path and format and compares its digest with current bytes.

The repository does not hide conflicts through automatic merging.

## Resource limits

The initial defaults are:

- 2,000,000 bytes per document;
- 100 nesting levels;
- 100,000 values.

Individual repositories may use stricter byte limits.

Changing limits can alter which persisted documents are accepted and therefore requires compatibility analysis.

## File extensions

Canonical extensions are:

- `.json`;
- `.yaml`.

`.yml` is not accepted. One extension per format reduces ambiguity in templates, migrations, package manifests, and external tooling.

## Consequences

### Positive

- one validation path for JSON, YAML, schemas, and domain invariants;
- deterministic diffs and package contents;
- explicit handling of noncanonical human edits;
- lost-update protection;
- safe YAML without object execution or aliases;
- reusable repository infrastructure for all current contracts;
- exact document fingerprints for provenance and future event records.

### Negative

- comments and manual YAML formatting are lost on save;
- aliases and merge keys cannot be used;
- strict duplicate detection rejects files accepted by permissive parsers;
- byte identity can report conflicts after formatting-only edits;
- PyYAML becomes a runtime dependency;
- cross-document transactions still require a higher-level service.

## Alternatives considered

### JSON only

Rejected because YAML is useful for longer human-edited specifications and configuration. The safe repository keeps YAML as a surface without allowing it to redefine domain behavior.

### YAML as the canonical internal model

Rejected because YAML has a larger and more surprising data model. The canonical validated tree remains JSON-compatible.

### Preserve comments with a round-trip YAML library

Deferred. Comment preservation adds complexity, parser-specific node models, and mutation semantics. It may be reconsidered for dedicated authoring tools, but canonical generated project data remains deterministic.

### Last writer wins

Rejected because it silently destroys concurrent changes. Unconditional save remains available only as an explicit caller decision.

### Semantic hashes

Rejected for concurrency identity. A semantic hash would ignore external formatting and comment edits. Exact-byte SHA-256 is simpler and accurately identifies the persisted revision.

## Compatibility

Canonical serialization, loader restrictions, digest meaning, file extensions, and conflict behavior are infrastructure contracts.

Incompatible changes require:

- retained fixtures for the old behavior;
- migration or dual-read handling;
- documentation;
- an ADR or RFC according to impact;
- tests demonstrating preservation or intentional conversion.

## Security

- parsing is bounded by bytes, depth, and value count;
- YAML object tags cannot execute;
- aliases and merge keys are denied;
- duplicate keys cannot conceal values;
- non-finite numbers are denied;
- filesystem containment and symlink protection remain enforced;
- atomic writes prevent partial document replacement;
- locks and digest checks reduce concurrent overwrite risk.

This does not replace authorization, approval policy, signature verification, migration safety, or archive validation.
