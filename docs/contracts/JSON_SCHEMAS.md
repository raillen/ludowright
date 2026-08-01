# JSON Schema Publication

## Purpose

LudoWright publishes machine-readable JSON Schemas for the canonical persisted contracts.

The schemas allow:

- editors and IDEs to validate project files;
- CLI and API adapters to reject malformed payloads;
- migrations to identify the source contract revision;
- fixtures to preserve backward compatibility;
- external tools to integrate without importing Python;
- generated files to remain reviewable and reproducible.

## Current publication

The first publication lives under:

```text
schemas/v1/
```

It uses JSON Schema Draft 2020-12 and contains:

| Contract | Published file |
|---|---|
| Project | `project.schema.json` |
| Decision | `decision.schema.json` |
| Approval | `approval.schema.json` |
| Asset | `asset.schema.json` |
| Asset registry | `asset-registry.schema.json` |
| Asset discovery candidate | `asset-discovery-candidate.schema.json` |
| Asset discovery issue | `asset-discovery-issue.schema.json` |
| Asset discovery report | `asset-discovery-report.schema.json` |
| Asset decomposition | `asset-decomposition.schema.json` |
| Asset decomposition report | `asset-decomposition-report.schema.json` |
| Asset workbook template | `asset-workbook-template.schema.json` |
| Asset workbook export report | `asset-workbook-export-report.schema.json` |
| Asset audit report | `asset-audit.schema.json` |
| Visual reference | `visual-reference.schema.json` |
| Visual job | `visual-job.schema.json` |
| Generation receipt | `generation-receipt.schema.json` |
| Visual review | `visual-review.schema.json` |
| Capture profile | `capture-profile.schema.json` |
| Humanoid profile | `humanoid-profile.schema.json` |
| Creature profile | `creature-profile.schema.json` |
| Visual bible | `visual-bible.schema.json` |
| Prompt template | `prompt-template.schema.json` |
| Compiled prompt | `compiled-prompt.schema.json` |
| Migration receipt | `migration-receipt.schema.json` |
| Dependency graph | `dependency-graph.schema.json` |
| Document template | `document-template.schema.json` |
| ATLAS metadata | `atlas-metadata.schema.json` |
| ATLAS report | `atlas-report.schema.json` |
| CLI response | `cli-response.schema.json` |
| Interview questionnaire | `interview-questionnaire.schema.json` |
| Interview session | `interview-session.schema.json` |
| Interview interaction | `interview-interaction.schema.json` |

Every top-level contract contains:

```json
{
  "schema_version": 1,
  "kind": "contract-name"
}
```

`schema_version` identifies the persisted contract generation. `kind` prevents a valid document for one contract from being interpreted as another contract.

## Source of truth

The source of truth is the Pydantic contract layer under:

```text
src/ludowright/contracts/
```

The generated JSON files are checked into the repository for review and external consumption, but they must never be edited manually.

Contract models convert into the canonical domain aggregates. This reuses the same invariants for:

- Python application code;
- JSON and future YAML adapters;
- generated JSON Schemas;
- compatibility fixtures.

The contract layer handles serialization shapes. The domain remains independent from Pydantic.

## Publishing schemas

Generate the complete publication with:

```bash
uv run python -m ludowright.contracts publish
```

The command:

1. generates all registered schemas;
2. writes canonical sorted UTF-8 JSON;
3. removes stale JSON files from the version directory;
4. generates `manifest.json` with SHA-256 checksums.

The operation is deterministic. Repeating it without source changes must produce no diff.

## Checking drift

Verify that checked-in schemas match the source models:

```bash
uv run python -m ludowright.contracts check
```

The command reports:

- `missing:<file>`;
- `modified:<file>`;
- `stale:<file>`.

Schema drift is part of:

```bash
uv run ludowright quality check
```

A pull request cannot intentionally change contract code while leaving the published schemas outdated.

## Manifest

`schemas/v1/manifest.json` records:

- schema publication version;
- JSON Schema draft;
- ordered contract names;
- file names;
- stable schema IDs;
- SHA-256 checksums.

The manifest supports packaging, cache validation, release verification, and downstream integrity checks.

Checksums cover the canonical text of each generated schema. They do not sign or authenticate a release. Cryptographic release signing belongs to the future packaging and release process.

## Schema IDs

Version 1 schemas use IDs under:

```text
https://schemas.ludowright.dev/v1/
```

These are stable identifiers, not a promise that network retrieval is currently available. Tools should resolve checked-in or packaged schemas locally unless a future release explicitly provides an online schema registry.

## Strictness

Top-level and nested contract objects reject unknown fields through `additionalProperties: false`.

This is intentional:

- misspelled fields do not disappear silently;
- unsupported extensions cannot masquerade as canonical data;
- migrations can reason about known shapes;
- agents receive immediate validation errors.

Future extension points must be introduced explicitly through a versioned field or extension contract.

## Compatibility fixtures

Canonical fixtures live under:

```text
tests/fixtures/contracts/v1/
```

There is at least one valid fixture for every published schema.

The test suite verifies that fixtures:

- remain valid under their registered contract model;
- convert through the domain invariants;
- round-trip through canonical JSON-compatible serialization;
- reject unknown fields;
- retain the expected `schema_version` and `kind`.

These fixtures are the minimum compatibility baseline. Future fixtures should cover important optional fields, terminal states, and migration boundaries.

## Versioning policy

A new schema version is required when a persisted shape or interpretation changes incompatibly, including:

- adding a required field without a default or migration;
- removing or renaming a field;
- narrowing an accepted value;
- changing enum meaning;
- changing identifier semantics;
- changing inheritance or transition rules that affect persisted interpretation;
- changing whether unknown fields are accepted;
- changing deterministic serialization.

Compatible additions may remain in the same version only when old documents remain valid and semantics do not change. The change still requires fixtures, tests, documentation, and a regenerated manifest.

## Creating a new schema version

A future `v2` publication must:

1. preserve `schemas/v1/`;
2. add a separate registry or versioned model set;
3. publish to `schemas/v2/`;
4. provide migration or compatibility guidance;
5. retain v1 fixtures;
6. add v2 fixtures;
7. test supported cross-version behavior;
8. document deprecation and support windows.

Never overwrite v1 files with incompatible v2 meanings.

## Review checklist

A pull request changing a persisted contract must include:

- contract-model changes;
- domain-invariant analysis;
- regenerated schemas;
- updated manifest;
- fixture changes or additions;
- compatibility assessment;
- migration plan when required;
- documentation updates;
- ADR or RFC when architecture or compatibility policy changes.

## Security considerations

- schemas reject unknown fields but do not replace application authorization;
- URI and path safety remain domain and adapter responsibilities;
- schemas must not contain credentials, private URLs, or production secrets;
- schema validation does not prove that referenced files exist or are trusted;
- resource limits for parsing and validation belong to adapters;
- untrusted documents must still be parsed with bounded, non-executing loaders.

## Boundaries

This publication does not yet define:

- YAML formatting conventions;
- repository-relative paths;
- event-log records;
- SQLite tables;
- migration execution;
- CLI JSON envelopes;
- package manifests;
- online schema hosting.

Those are introduced in later implementation phases while consuming these canonical contracts.
