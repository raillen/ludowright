# LudoWright Documentation Atlas

This is the main navigation map for humans and agents. Each subject should have one canonical source.

## Project entry points

- [`../README.md`](../README.md) — project overview, status, setup, and primary links.
- [`../PROJECT_START.md`](../PROJECT_START.md) — orientation for contributors and agents.
- [`../AGENTS.md`](../AGENTS.md) — concise operational rules for Codex and other repository agents.

## Product

- [`product/PRODUCT_VISION.md`](product/PRODUCT_VISION.md) — mission, users, value, principles, boundaries, and success measures.
- [`product/ROADMAP.md`](product/ROADMAP.md) — planned capabilities from the 0.x series through the long-term Studio direction.

## Architecture

- [`architecture/SYSTEM_OVERVIEW.md`](architecture/SYSTEM_OVERVIEW.md) — system boundaries, layers, modules, state, and integration model.
- `architecture/COMPONENTS.md` — planned detailed component responsibilities.
- `architecture/DATA_MODEL.md` — planned canonical entities and relationships.
- `architecture/DEPENDENCY_GRAPH.md` — planned impact graph and invalidation model.

## Contracts

Planned canonical contracts:

- project manifest;
- asset specification;
- visual-generation job;
- generation receipt;
- approval record;
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

Planned documents:

- visual bible schema;
- asset-family taxonomy;
- capture-profile design;
- segmented character references;
- garments and props;
- creatures, vehicles, architecture, foliage, UI, VFX, and modular kits;
- deterministic technical-sheet assembly;
- provenance and licensing.

## Implementation

- [`plans/IMPLEMENTATION_PLAN.md`](plans/IMPLEMENTATION_PLAN.md) — ordered PR program for the first stable release.

Future bounded changes should receive their own plan under `plans/`.

## Quality

Planned documents:

- test strategy;
- schema and CLI contract testing;
- snapshot testing;
- agent evals;
- release verification;
- performance budgets.

## Security

- [`../SECURITY.md`](../SECURITY.md) — vulnerability reporting and current security requirements.

Planned detailed documents:

- threat model;
- local file safety;
- archive extraction and packaging safety;
- template and plugin trust;
- secret handling;
- external-reference provenance;
- visual-content safeguards.

## Governance and operations

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — development, testing, compatibility, and pull-request workflow.
- [`../GOVERNANCE.md`](../GOVERNANCE.md) — roles, decisions, ADR/RFC thresholds, releases, and maintainership.
- [`governance/RFC_TEMPLATE.md`](governance/RFC_TEMPLATE.md) — required structure for cross-cutting proposals.
- [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) — community behavior and enforcement.
- [`../SUPPORT.md`](../SUPPORT.md) — support channels and required diagnostic information.
- [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) — required PR review checklist.
- [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) — structured bug and feature intake.

Planned operational documents:

- compatibility policy;
- versioning and deprecation;
- migration policy;
- release process;
- extension governance.

## Decisions

- [`decisions/0000-template.md`](decisions/0000-template.md) — canonical Architecture Decision Record template.

Accepted Architecture Decision Records will follow the naming pattern:

```text
NNNN-short-decision-title.md
```

An ADR is required when a decision changes architecture, public contracts, persistence, compatibility, security boundaries, or extension points.
