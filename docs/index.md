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

LudoWright is in the **pre-alpha documentation phase**.

The repository currently establishes:

- the product vision and long-term roadmap;
- the layered Python and Codex architecture;
- documentation and contribution governance;
- the initial package and CLI;
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

Executable capture profiles, ImageGen execution, review workflows, technical
sheets, audits, and package generation remain planned work.

## Start here

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
