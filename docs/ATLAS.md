# LudoWright Documentation Atlas

This is the main navigation map for humans and agents. Each subject should have one canonical source.

## Project entry points

- [Repository README](https://github.com/raillen/ludowright/blob/main/README.md) — project overview, status, setup, and primary links.
- [Project Start](https://github.com/raillen/ludowright/blob/main/PROJECT_START.md) — orientation for contributors and agents.
- [Agent Guide](https://github.com/raillen/ludowright/blob/main/AGENTS.md) — concise operational rules for Codex and other repository agents.

## Product

- [`product/PRODUCT_VISION.md`](product/PRODUCT_VISION.md) — mission, users, value, principles, boundaries, and success measures.
- [`product/ROADMAP.md`](product/ROADMAP.md) — planned capabilities from the 0.x series through the long-term Studio direction.

## Architecture

- [`architecture/SYSTEM_OVERVIEW.md`](architecture/SYSTEM_OVERVIEW.md) — system boundaries, layers, modules, state, and integration model.
- `architecture/COMPONENTS.md` — planned detailed component responsibilities.
- `architecture/DATA_MODEL.md` — planned canonical entities and relationships.
- `architecture/DEPENDENCY_GRAPH.md` — planned impact graph and invalidation model.

## Contracts

- [`contracts/IDENTIFIERS_AND_VERSIONS.md`](contracts/IDENTIFIERS_AND_VERSIONS.md) — display names, slugs, typed entity IDs, and schema/template/profile revisions.
- [`contracts/PROJECT_DOMAIN.md`](contracts/PROJECT_DOMAIN.md) — project identity, dimensions, targets, engine, production stage, lifecycle, and transition invariants.
- [`contracts/DECISIONS_AND_APPROVALS.md`](contracts/DECISIONS_AND_APPROVALS.md) — decision states, revision-bound approval states, immutable logical histories, and superseding relationships.
- [`contracts/ASSET_DOMAIN.md`](contracts/ASSET_DOMAIN.md) — asset families, subtypes, ownership, decomposition, hierarchy, priority, status, and completion rules.
- [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md) — visual provenance, revision-bound references, immutable generation jobs, attempt receipts, retries, and reviews.

Planned canonical contracts:

- project manifest;
- capture profile;
- CLI JSON output;
- release manifest.

## Codex integration

Planned documents:

- skill installation and invocation;
- agent roles and routing;
- ImageGen job execution;
- approval checkpoints;
- recovery and retry behavior;
- evals for agent compliance.

## Visual production

The visual reference and job foundation is defined in [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md).

Planned detailed documents:

- visual bible schema;
- asset-family taxonomy;
- capture-profile design;
- segmented character references;
- garments and props;
- creatures, vehicles, architecture, foliage, UI, VFX, and modular kits;
- deterministic technical-sheet assembly;
- provenance and licensing operations.

## Implementation

- [`plans/IMPLEMENTATION_PLAN.md`](plans/IMPLEMENTATION_PLAN.md) — ordered PR program for the first stable release.

Future bounded changes should receive their own plan under `plans/`.

## Quality

- [`quality/ENGINEERING_QUALITY.md`](quality/ENGINEERING_QUALITY.md) — pre-commit, unified quality commands, coverage, property tests, dependency audits, secret scanning, CI, and failure policy.

Planned detailed documents:

- schema and CLI contract testing;
- snapshot testing;
- agent evals;
- release verification;
- performance budgets.

## Security

- [Security Policy](https://github.com/raillen/ludowright/blob/main/SECURITY.md) — vulnerability reporting and current security requirements.

Planned detailed documents:

- threat model;
- local file safety;
- archive extraction and packaging safety;
- template and plugin trust;
- secret handling;
- visual-content safeguards.

External-reference URI and credential rules are canonical in [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md).

## Governance and operations

- [Contributing](https://github.com/raillen/ludowright/blob/main/CONTRIBUTING.md) — development, testing, compatibility, and pull-request workflow.
- [Governance](https://github.com/raillen/ludowright/blob/main/GOVERNANCE.md) — roles, decisions, ADR/RFC thresholds, releases, and maintainership.
- [`governance/RFC_TEMPLATE.md`](governance/RFC_TEMPLATE.md) — required structure for cross-cutting proposals.
- [Code of Conduct](https://github.com/raillen/ludowright/blob/main/CODE_OF_CONDUCT.md) — community behavior and enforcement.
- [Support](https://github.com/raillen/ludowright/blob/main/SUPPORT.md) — support channels and required diagnostic information.
- [Pull Request Template](https://github.com/raillen/ludowright/blob/main/.github/PULL_REQUEST_TEMPLATE.md) — required PR review checklist.
- [Issue Templates](https://github.com/raillen/ludowright/tree/main/.github/ISSUE_TEMPLATE) — structured bug and feature intake.
- [`operations/DOCUMENTATION_SITE.md`](operations/DOCUMENTATION_SITE.md) — local preview, strict validation, and Pages publication.

Planned operational documents:

- compatibility policy;
- versioning and deprecation;
- migration policy;
- release process;
- extension governance.

## Decisions

- [`decisions/0005-immutable-visual-jobs-and-receipts.md`](decisions/0005-immutable-visual-jobs-and-receipts.md) — accepted immutable visual jobs, append-only attempt receipts, retry semantics, and output-bound reviews.
- [`decisions/0004-decomposed-asset-aggregate.md`](decisions/0004-decomposed-asset-aggregate.md) — accepted decomposed asset aggregate, shared production status, ownership, and completion model.
- [`decisions/0003-revision-bound-approvals.md`](decisions/0003-revision-bound-approvals.md) — accepted revision-bound approvals, immutable logical histories, and superseding relationships.
- [`decisions/0002-immutable-project-aggregate.md`](decisions/0002-immutable-project-aggregate.md) — accepted immutable project aggregate and separate stage/lifecycle model.
- [`decisions/0001-typed-identifiers-and-revision-versions.md`](decisions/0001-typed-identifiers-and-revision-versions.md) — accepted identifier, display-name, slug, and contract-revision architecture.
- [`decisions/0000-template.md`](decisions/0000-template.md) — canonical Architecture Decision Record template.

Accepted Architecture Decision Records follow the naming pattern:

```text
NNNN-short-decision-title.md
```

An ADR is required when a decision changes architecture, public contracts, persistence, compatibility, security boundaries, or extension points.
