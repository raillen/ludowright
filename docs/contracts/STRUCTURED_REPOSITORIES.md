# Structured JSON and YAML Repositories

## Purpose

LudoWright stores human-editable project data in JSON and YAML while preserving one deterministic and auditable interpretation.

The structured repository layer provides:

- bounded UTF-8 reads;
- safe JSON and YAML parsing;
- validation through the published Pydantic contracts;
- canonical serialization;
- exact SHA-256 document identities;
- atomic writes through `ProjectFilesystem`;
- advisory locks for concurrent writers;
- optimistic conflict detection;
- detection of manually formatted but semantically valid files.

The canonical implementation lives in:

```text
src/ludowright/infrastructure/structured.py
```

## Architectural position

```text
Domain invariants
        ↑
Pydantic contract model
        ↑
Structured repository
        ↑
Safe project filesystem
        ↑
Project root
```

The repository does not duplicate business rules. Parsed data is accepted only after the registered contract model accepts it and its domain validators run.

## Supported formats

The initial implementation provides:

- `JsonDocumentRepository` for `.json` files;
- `YamlDocumentRepository` for `.yaml` files.

The `.yml` extension is deliberately not canonical. Restricting each format to one extension avoids duplicate naming conventions and simplifies discovery, tooling, migrations, and packaging.

## Contract type

Every repository is bound to one `ContractModel` subclass.

Example:

```python
repository = JsonDocumentRepository(
    filesystem,
    RepositoryPath(".ludowright/project.json"),
    ProjectContract,
)
```

A repository rejects values belonging to another contract type.

## Bounded reads

The default document limit is 2,000,000 bytes.

Each repository may define a smaller or larger positive limit according to the expected document type. The limit is enforced by `ProjectFilesystem` before parsing and again if a file grows during reading.

Large binary files, images, databases, event logs, and generated archives do not belong in these repositories.

## UTF-8 policy

Structured files must use UTF-8 without a byte-order mark.

The repository rejects:

- invalid UTF-8;
- UTF-8 BOM prefixes;
- arbitrary alternative encodings.

Canonical output always uses UTF-8 and ends with one newline.

## Strict JSON parsing

JSON parsing rejects:

- duplicate object keys;
- `NaN`;
- positive or negative infinity;
- malformed syntax;
- excessive nesting or value counts;
- values that cannot be represented by the canonical JSON-compatible data model.

Duplicate keys are rejected before Pydantic validation. A parser must never silently choose the first or last duplicate value.

## Strict YAML parsing

YAML uses a customized `SafeLoader`.

It rejects:

- aliases and references;
- merge keys;
- duplicate mapping keys;
- non-string mapping keys;
- multiple YAML documents in one file;
- empty documents;
- unsafe or unknown object tags;
- values that become non-JSON-native Python objects;
- excessive nesting or value counts.

This means YAML timestamps such as an unquoted `2026-07-29` are rejected when the loader converts them to date objects. Authors should quote values intended to remain strings.

Aliases are disabled even though they can be convenient. They complicate provenance, allow expansion attacks, and make canonical identity less obvious.

## JSON-compatible value boundary

After parsing, documents may contain only:

- objects with string keys;
- arrays;
- strings;
- booleans;
- integers;
- finite floating-point values;
- null.

The repository rejects sets, tuples, byte strings, timestamps, Python objects, and non-finite numbers.

The initial safety limits are:

- 100 nesting levels;
- 100,000 values.

These limits protect normal configuration documents without pretending to provide a complete resource-isolation sandbox.

## Canonical JSON

Canonical JSON uses:

- contract `model_dump(mode="json", exclude_none=True)`;
- sorted object keys;
- two-space indentation;
- native Unicode characters;
- finite numbers only;
- one trailing newline.

Example:

```json
{
  "id": "locadora-2000",
  "kind": "project",
  "name": "Locadora 2000",
  "schema_version": 1
}
```

The exact field set depends on the bound contract model.

## Canonical YAML

Canonical YAML uses:

- the same JSON-compatible contract dump;
- safe dumping only;
- sorted keys;
- block style;
- two-space indentation;
- Unicode output;
- no emitted aliases;
- one trailing newline.

Comments and hand-selected key order are not retained in canonical output. YAML remains a human-editable input format, but the validated data model is canonical—not presentation trivia.

## Snapshots

`load()` returns `StructuredDocumentSnapshot` containing:

- repository path;
- document format;
- validated contract value;
- SHA-256 digest of the exact bytes read;
- byte length;
- whether the bytes already match canonical serialization.

A valid document may have `canonical=False` when it contains comments, different whitespace, alternate key order, or another safe representation.

Re-saving the validated value produces canonical bytes.

## Document identity

The snapshot digest identifies the exact persisted bytes, not merely semantic equality.

Consequences:

- a comment change in YAML changes the digest;
- whitespace changes in JSON change the digest;
- canonical JSON and YAML for the same contract have different digests;
- re-saving canonical bytes without a model change preserves the digest.

The digest supports conflict detection and provenance. It is not a digital signature and does not authenticate an author.

## Atomic saves

All writes use `ProjectFilesystem.write_bytes()`.

The repository therefore inherits:

- repository-relative containment;
- symlink rejection;
- sibling temporary files;
- payload synchronization;
- atomic `os.replace()`;
- parent-directory synchronization where supported;
- temporary-file cleanup after failure.

## Per-document locks

Every repository derives a stable lock name from the SHA-256 digest of its repository path.

The lock is held across:

1. reading the current digest;
2. checking conflicts;
3. writing the replacement.

Different files use different locks. The same canonical path always resolves to the same lock name.

Locks coordinate LudoWright processes only. External editors may still modify files directly, which is why digest comparison remains necessary.

## Creating documents

`create()` succeeds only when the target does not exist.

If another writer created the document first, it raises `StructuredDocumentConflictError` and preserves the existing file.

## Saving documents

`save()` always writes canonical bytes.

Without `expected_digest`, it performs an unconditional atomic replacement under the document lock.

With `expected_digest`, the repository compares the current exact digest before writing. A missing or changed file raises `StructuredDocumentConflictError`.

Use unconditional saves only when the caller intentionally owns the latest state or is generating a new derived artifact.

## Replacing snapshots

`replace(snapshot, value)` uses the snapshot digest as the expected current revision.

The snapshot must belong to the same path and format. A JSON snapshot cannot replace a YAML repository, and a snapshot from another file cannot be reused.

This is the preferred update flow:

```text
load snapshot
→ calculate new immutable contract
→ replace snapshot
```

## Error model

| Error | Meaning |
|---|---|
| `StructuredDocumentError` | Base structured persistence failure |
| `StructuredDocumentFormatError` | Encoding, BOM, or extension is not canonical |
| `StructuredDocumentParseError` | JSON/YAML input is invalid, unsafe, or outside resource limits |
| `StructuredDocumentConflictError` | Existing bytes do not match the expected document revision |
| `ValidationError` | Parsed data violates the bound Pydantic contract |

Filesystem and lock exceptions remain visible when they accurately describe the underlying failure.

## Compatibility policy

Canonical serialization is a persisted contract.

Changes to any of the following require compatibility analysis and usually an ADR:

- file extensions;
- key ordering;
- indentation;
- omitted-field behavior;
- Unicode policy;
- YAML loader behavior;
- alias or merge handling;
- digest interpretation;
- size or structure limits;
- lock-name derivation;
- conflict semantics.

An incompatible change requires migration or dual-read handling. Existing files must not silently acquire a new interpretation.

## Security boundaries

This layer does not decide:

- user authorization;
- whether an approved artifact may be superseded;
- whether referenced files exist or are trusted;
- migration policy;
- cross-document transactions;
- event-log integrity;
- SQLite consistency;
- archive extraction safety;
- release signing.

Those concerns belong to higher application services or later infrastructure adapters.

## Required tests

Structured repository changes should test, as applicable:

- JSON and YAML round trips;
- deterministic serialization;
- noncanonical input detection;
- duplicate keys;
- YAML aliases and merge keys;
- unsafe tags;
- multiple documents;
- non-string keys;
- invalid UTF-8 and BOMs;
- read limits;
- Pydantic validation failures;
- create conflicts;
- stale digest conflicts;
- file preservation after failure;
- lock coordination.
