# LudoWright

> **Plan it. Visualize it. Produce it.**

LudoWright is a local-first, repository-native framework for planning, documenting, visualizing, validating, and packaging game projects through Codex.

## What it will connect

```text
idea → guided intake → modular documentation → asset registry
→ visual bible → segmented ImageGen jobs → human approval
→ technical sheets → audit → reproducible package
```

## Current status

LudoWright is in the **pre-alpha beta-preparation phase**.

The repository currently establishes:

- the product vision and long-term roadmap;
- the layered Python and Codex architecture;
- documentation and contribution governance;
- the initial package and CLI;
- project initialization from the versioned `minimal` template, including the
  manifest, event log, dependency graph, and current SQLite state store;
- tests and continuous integration.
- deterministic document templates and an ATLAS index with canonical-source and
  link-integrity checks.
- incremental document refresh with source hashes, stale planning, manual
  preservation, and rollback.
- deterministic documentation audits for required topics, duplicate sources,
  explicit contradiction rules, and stale references.
- a versioned data-driven asset taxonomy with subtype catalogs and naming policy.
- a versioned YAML asset registry with safe CRUD, validation, batch import/export,
  event auditing, and derived SQLite indexing.
- deterministic Markdown asset discovery with explicit candidate confirmation,
  duplicate handling, and source provenance.
- deterministic asset decomposition with versioned contracts, prerequisite graph
  edges, guided corrections, dry-run planning, and advisory capture-profile
  recommendations.
- deterministic derived ODS asset workbooks with six versioned views, dry-run,
  source/output hashes, and create-only atomic writes.
- deterministic read-only asset audits for orphan graph nodes, incomplete
  specifications, invalid dependencies, missing capture profiles, and
  incomplete production ownership metadata.
- a strict v1 visual bible contract for shared shape, proportion, palette,
  material, camera, lighting, detail, budget, and prompt constraints.
- a provider-neutral deterministic prompt compiler with approved-reference
  resolution and canonical prompt hashes.
- the initial data-defined humanoid/wearable profile with a neutral body base,
  per-view requirements, isolated categories, and assembled outputs.
- initial data-defined creature/animal profiles for quadrupeds, birds, fish,
  insects, and fantasy creatures with anatomy-specific views, components,
  states, and outputs.
- initial data-defined environment/hard-surface profiles for props, vehicles,
  buildings, modular kits, and interiors with construction components,
  connection matrices, states, views, and outputs.
- initial data-defined visual-specialty profiles for trees, plants, UI,
  particle and shader effects, locomotion, and motion sets.
- a versioned project-local `$ludowright` Codex skill with safe install,
  update, verification, removal, checksums, and rollback.

The Codex orchestration policy now enforces status-first inspection, durable
decisions, validations, approval checkpoints, and safe resume planning. The
ImageGen adapter executes a selected ready job through an injected provider,
records a deterministic operation manifest, validates one PNG per view, and
rolls back partial failures. Generation receipts, review workflows, technical
sheets, global audits, package manifests, reproducible package builds, local
release verification, and deterministic example inputs are implemented. The
supported checkout installation path, first-project tutorial,
character/custom-profile workflow, and troubleshooting guide cover Linux,
Windows, macOS, `ludowright init`, dry-run, profile contracts, deterministic
planning, project-local skill setup, conservative failure recovery, and safe
checkout/skill updates; uninstall and beta readiness remain the next bounded
work.
The pure deterministic visual-job planner does not execute providers or persist
project-local plans.

## Start here

- [Installation](getting-started/INSTALLATION.md) — supported local setup for Linux, Windows, and macOS.
- [First project](getting-started/FIRST_PROJECT.md) — create and verify a minimal project.
- [Character workflow](getting-started/CHARACTER_WORKFLOW.md) — custom profiles, humanoid profiles, planning, and approval boundaries.
- [Troubleshooting](getting-started/TROUBLESHOOTING.md) — conservative recovery for installation, init, Codex skill, and quality-gate failures.
- [Updating](getting-started/UPDATING.md) — safe checkout, environment, and project-local skill updates.
- [Documentation Atlas](ATLAS.md) — canonical navigation map.
- [Product Vision](product/PRODUCT_VISION.md) — mission, users, principles, and boundaries.
- [Roadmap](product/ROADMAP.md) — planned releases and long-term direction.
- [System Overview](architecture/SYSTEM_OVERVIEW.md) — architecture and dependency rules.
- [Implementation Plan](plans/IMPLEMENTATION_PLAN.md) — ordered pull requests to the first stable release.

## Repository policies

The following policies live at the repository root because GitHub discovers them there:

- [Contributing](https://github.com/raillen/ludowright/blob/main/CONTRIBUTING.md)
- [Security](https://github.com/raillen/ludowright/blob/main/SECURITY.md)
- [Support](https://github.com/raillen/ludowright/blob/main/SUPPORT.md)
- [Governance](https://github.com/raillen/ludowright/blob/main/GOVERNANCE.md)
- [Code of Conduct](https://github.com/raillen/ludowright/blob/main/CODE_OF_CONDUCT.md)

## Development setup

```bash
git clone https://github.com/raillen/ludowright.git
cd ludowright
uv sync --extra dev --extra docs
uv run ludowright --version
uv run mkdocs serve
```

See [Documentation Site Operations](operations/DOCUMENTATION_SITE.md) for strict builds and publication details.
