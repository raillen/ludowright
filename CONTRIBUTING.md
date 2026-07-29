# Contributing to LudoWright

Thank you for helping improve LudoWright.

LudoWright is currently pre-alpha. Product boundaries, schemas, CLI contracts, project layouts, and extension points may change while the foundation is being established.

## Start here

Before changing the repository, read:

1. `PROJECT_START.md`
2. `docs/ATLAS.md`
3. `AGENTS.md`
4. the canonical document for the area you intend to change
5. relevant ADRs and implementation plans

## Ways to contribute

Useful contributions include:

- bug reports with reproducible steps;
- documentation corrections;
- tests and fixtures;
- CLI usability improvements;
- schemas and validation rules;
- capture profiles;
- asset-family definitions;
- Codex workflow improvements;
- security and privacy reviews.

Large features should begin with an issue or RFC before implementation.

## Development setup

Requirements:

- Python 3.12 or newer;
- `uv`;
- Git.

```bash
uv sync --extra dev --extra docs
uv run pre-commit install
uv run ludowright --version
uv run ludowright status
```

## Required checks

Run the complete quality gate before opening a pull request:

```bash
uv run ludowright quality check
```

Before a release-related change is considered complete, run:

```bash
uv run ludowright quality release
```

The quality gate covers pre-commit hooks, tests with branch coverage, generated-schema drift, strict documentation validation, dependency auditing, and secret scanning. See `docs/quality/ENGINEERING_QUALITY.md`.

## Branches and commits

- Create a short-lived branch from `main`.
- Use descriptive names such as `feature/project-manifest` or `fix/version-option`.
- Keep commits focused and understandable.
- Do not include unrelated generated files, local state, secrets, or personal data.

## Pull requests

A pull request should:

- solve one coherent problem;
- explain what changed and why;
- include tests for behavior changes;
- update documentation in the same PR;
- identify compatibility, migration, security, and data-loss risks;
- add an ADR when changing architecture or stable contracts;
- keep generated outputs reproducible;
- pass all required checks.

Prefer squash merging unless preserving individual commits is important to understanding a migration.

## Documentation rules

- Each subject has one canonical source.
- `docs/ATLAS.md` is the navigation entry point.
- Architecture documents describe the current design.
- ADRs preserve decisions and rationale.
- Plans describe bounded implementation work.
- Avoid duplicating complete specifications across files.

## Tests

Use the smallest suitable level:

- unit tests for domain rules;
- property tests for invariants across many valid inputs;
- contract tests for schemas, manifests, and machine-readable CLI output;
- snapshot tests for generated documents and sheets;
- integration tests for storage and filesystem boundaries;
- end-to-end tests for complete project workflows;
- agent evals for Codex behavior.

Tests that require real ImageGen calls must be optional. Normal CI should use deterministic fakes and fixtures.

## Generated JSON Schemas

Published schemas live under `schemas/vN/` and are generated from `src/ludowright/contracts/`.

After changing a contract model, run:

```bash
uv run python -m ludowright.contracts publish
uv run python -m ludowright.contracts check
```

Do not edit generated schema JSON manually.

A schema-related change must include, as applicable:

- the domain and Pydantic contract change;
- regenerated schema files;
- an updated checksum manifest;
- canonical fixture changes or additions;
- compatibility analysis;
- migration guidance for incompatible changes;
- documentation and ADR updates.

Never delete an old fixture merely because a new model rejects it. Either preserve compatibility or introduce a new schema version with an explicit migration path.

## Generated and visual artifacts

Every generated artifact must preserve provenance when applicable:

- source specification;
- prompt or template version;
- reference identifiers and checksums;
- output checksum;
- generation job;
- approval state.

Technical sheets must be assembled from approved images rather than regenerated as a new image.

## Backward compatibility

Do not silently change persisted project data.

Changes to schemas, manifests, state storage, templates, capture profiles, or public CLI JSON require:

- an explicit version change when incompatible;
- migration or compatibility handling;
- contract tests and retained fixtures;
- regenerated publication artifacts;
- documentation;
- changelog entry.

## Reporting security problems

Do not open public issues for vulnerabilities. Follow `SECURITY.md`.

## License

By submitting a contribution, you agree that it may be distributed under the repository's Apache License 2.0.
