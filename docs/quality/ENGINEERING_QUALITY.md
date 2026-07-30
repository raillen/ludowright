# Engineering Quality Baseline

## Purpose

LudoWright treats tests, documentation, security checks, generated-contract integrity, and package verification as one reproducible quality system.

The same commands must work for:

- contributors on local machines;
- Codex operating in the repository;
- pull-request CI;
- scheduled security checks;
- release verification.

## Install the complete development environment

```bash
uv sync --extra dev --extra docs
```

## Fast local checks

Install the repository hooks once:

```bash
uv run pre-commit install
```

Run every configured hook against tracked files:

```bash
uv run pre-commit run --all-files
```

The hooks verify:

- Ruff lint rules;
- Ruff formatting;
- strict mypy typing;
- likely committed secrets.

Hooks use check-only behavior. They do not silently reformat or rewrite files.

## Unified quality command

Run the pull-request gate with:

```bash
uv run ludowright quality check
```

The command executes, in order:

1. all pre-commit hooks;
2. the pytest suite with coverage;
3. generated JSON Schema drift verification;
4. ATLAS canonical-source, link, and orphan validation;
5. the deterministic documentation audit;
6. the strict documentation build;
7. the Python dependency audit.

Inspect the planned commands without executing them:

```bash
uv run ludowright quality check --dry-run
```

Use stable machine-readable output:

```bash
uv run ludowright quality check --dry-run --json
```

## JSON Schema integrity

Published contracts under `schemas/v1/` are generated from the registry in `src/ludowright/contracts/`.

Regenerate them with:

```bash
uv run python -m ludowright.contracts publish
```

Check them without modifying files:

```bash
uv run python -m ludowright.contracts check
```

The check fails for:

- a missing generated schema;
- a generated schema whose checked-in content differs from the canonical model;
- a stale JSON file that is no longer registered;
- a missing or changed checksum manifest.

Do not edit generated schemas manually. Fix the contract source and regenerate the complete publication.

Canonical fixtures under `tests/fixtures/contracts/v1/` must remain valid for the supported v1 contracts. Incompatible changes require a new schema version and migration or compatibility guidance.

## Release gate

Before publishing a release, run:

```bash
uv run ludowright quality release
```

This runs the normal quality checks and then verifies that source and wheel distributions build with `uv build`.

## Coverage policy

Coverage uses branch measurement and fails below **80%**.

The threshold is an initial floor, not a target. New code should normally include enough focused tests to avoid lowering total coverage. Raising the threshold is preferred over weakening exclusions.

Coverage cannot prove correctness. Contract, property, integration, end-to-end, snapshot, security, and agent-eval tests remain necessary according to risk.

## Property testing

Hypothesis is available for rules that should hold across many valid inputs.

Good candidates include:

- identifier and slug normalization;
- schema round trips;
- migration invariants;
- graph properties;
- deterministic ordering;
- path normalization;
- manifest stability;
- package reproducibility.

Property tests should state an invariant rather than generate arbitrary data without a meaningful claim.

## Dependency auditing

`pip-audit` checks installed Python dependencies for known vulnerabilities.

The normal quality gate runs it on pull requests. The security workflow also runs it on a weekly schedule so newly disclosed vulnerabilities can be detected without waiting for code changes.

A vulnerability must not be ignored silently. Any temporary exception requires:

- the advisory identifier;
- affected package and version;
- exposure analysis;
- compensating controls;
- owner;
- expiry or review date;
- linked issue or ADR when the risk is substantial.

## Secret scanning

`detect-secrets` checks tracked text files through pre-commit and the scheduled security workflow.

Never commit real credentials merely to test detection. Use clearly fake values and avoid strings that resemble active provider tokens.

A detected value may be allowlisted only when it is demonstrably non-secret and the reason is reviewable.

Generated schemas, fixtures, source URIs, and contract examples must not contain credentials or private operational URLs.

## Continuous integration

### CI workflow

Every pull request and push to `main` installs development and documentation dependencies, then runs:

```bash
uv run ludowright quality check
```

### Documentation workflow

Documentation changes also run the strict MkDocs build and publish from `main` through GitHub Pages.

### Security workflow

The security workflow runs:

- on relevant changes to `main`;
- manually;
- weekly.

It audits dependencies and scans tracked files for likely secrets.

## Failure policy

Quality failures are blocking.

Do not bypass a check by:

- deleting or weakening a test without explaining the changed requirement;
- lowering coverage merely to pass CI;
- disabling a lint or type rule globally for one local problem;
- editing a generated schema instead of its source contract;
- removing an old compatibility fixture to hide an incompatible change;
- suppressing a vulnerability without risk analysis;
- marking a suspected credential as safe without verification;
- removing provenance or approval checks from generated artifacts.

Fix the underlying issue or document a narrow, time-bounded exception.
