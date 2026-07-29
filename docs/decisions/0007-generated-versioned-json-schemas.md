# ADR 0007: Generated and Versioned JSON Schemas

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contract:** `JSON_SCHEMAS.md`

## Context

LudoWright needs stable persisted contracts that can be consumed by Python, editors, CLI tools, Codex workflows, future APIs, YAML adapters, SQLite repositories, and external integrations.

Maintaining domain classes and hand-written JSON Schemas separately would create duplicate rules and predictable drift:

- a field could be required in one representation and optional in another;
- enum values could diverge;
- nested validation could be omitted;
- unknown-field behavior could differ;
- documentation could describe a shape no longer accepted by the application;
- migration tooling could target the wrong contract.

Generated schemas alone are not enough if they are produced only during release and are not reviewed. Downstream tools also need stable files in the repository rather than requiring Python execution.

## Decision

LudoWright uses a three-layer contract architecture:

1. immutable domain objects define business invariants;
2. strict Pydantic contract models define serialization shapes and convert to domain objects;
3. JSON Schemas are generated deterministically from the registered Pydantic models.

Generated schemas are checked into versioned directories and verified for drift in the normal quality gate.

## Publication layout

Version 1 is published under:

```text
schemas/v1/
```

Every top-level contract includes:

- `schema_version` as a constant positive revision;
- `kind` as a constant contract discriminator;
- `additionalProperties: false` through strict model configuration.

The publication includes a deterministic checksum manifest.

## Source-of-truth rule

Files under `schemas/vN/` are generated artifacts. They are reviewable and distributable but are not edited manually.

A contract change begins in the domain and Pydantic model, then regenerates the publication.

If the generated diff is unexpected, the source model is corrected. The generated file is never patched to hide the mismatch.

## Compatibility fixtures

Each published contract version maintains canonical fixtures.

Fixtures are validated through the registered Pydantic contract and domain conversion, then round-tripped through JSON-compatible serialization.

Old fixtures remain in the repository when a new schema version is introduced. They define the minimum supported compatibility baseline and provide migration test inputs.

## Drift enforcement

The publication command renders canonical sorted JSON with a final newline and SHA-256 manifest.

The check command compares generated content against the checked-in publication and reports missing, modified, or stale files.

This check runs inside `ludowright quality check`.

## Consequences

### Positive

- domain and serialization invariants remain connected;
- schema diffs are visible in pull requests;
- external tools can consume files without importing Python;
- unknown fields are rejected consistently;
- fixture compatibility is continuously tested;
- release packaging can verify schema checksums;
- migrations can target explicit contract versions.

### Negative

- schema changes produce generated-file diffs;
- contributors must regenerate publication after model edits;
- Pydantic becomes part of the contract adapter layer;
- generated schemas may include verbose `$defs` structures;
- cross-document relationships still require application-level validation.

## Alternatives considered

### Hand-written JSON Schemas

Rejected because validation rules would be duplicated and likely drift from Python behavior.

### Runtime-only schema generation

Rejected because pull requests, external tools, packages, and offline editors need stable reviewed files.

### Make Pydantic models the domain

Rejected because the core domain should remain independent from serialization and persistence frameworks.

### Permit unknown fields for forward compatibility

Rejected for canonical contracts because misspellings and unsupported extensions would silently enter persisted state. Explicit versioned extension points can be added later.

### One schema file containing all contracts

Rejected because independent files are easier to distribute, reference, compare, and version operationally. Shared definitions may be introduced later if they improve interoperability without weakening deterministic publication.

## Versioning

Incompatible shape or semantic changes require a new `schemas/vN/` directory.

Existing version directories are immutable except for corrections that preserve the documented interpretation and pass compatibility review.

A new version requires:

- new publication files;
- retained previous publication;
- new fixtures;
- retained previous fixtures;
- migration or compatibility guidance;
- tests for supported cross-version behavior.

## Security considerations

- strict schemas reject unknown data but do not provide authorization;
- generated schemas cannot contain secrets or private operational URLs;
- validation adapters must enforce resource limits for untrusted documents;
- schemas do not establish trust in referenced files or remote resources;
- online retrieval of schema IDs is not required for validation;
- release signing is separate from checksum integrity.

## Follow-up

- YAML and JSON repository adapters;
- migration framework;
- CLI validation commands;
- package inclusion and release verification;
- editor integration examples;
- optional online schema registry;
- cross-document consistency validation.
