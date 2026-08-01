# LudoWright

> **Plan it. Visualize it. Produce it.**

LudoWright is a local-first, repository-native framework for planning, documenting, visualizing, validating, and packaging game projects through Codex.

## Why it exists

Game projects often spread their design decisions, asset lists, visual references, prompts, approvals, and production notes across chats, spreadsheets, folders, and outdated documents. LudoWright turns those materials into a structured, traceable project that can be resumed and audited without depending on conversation history.

## Planned workflow

```text
idea → guided intake → modular documentation → asset registry
→ visual bible → segmented ImageGen jobs → human approval
→ technical sheets → audit → reproducible package
```

## Core principles

- the repository is the source of truth;
- deterministic Python code owns schemas, paths, versions, validation, and packaging;
- Codex provides the guided workflow, not the only copy of project state;
- each technical asset view is generated as an individual image;
- garments, props, and other components are planned and generated separately;
- technical sheets are assembled from approved references rather than regenerated;
- all generated outputs keep provenance, prompt, reference, version, and checksum data;
- human approval is required for canonical references and major decisions.

## Current status

LudoWright is in the **pre-alpha beta-preparation phase**. Product vision, long-term roadmap, layered architecture, documentation navigation, the initial Python package, project initialization, CLI workflows, tests, CI, asset planning, the v1 visual bible schema, a provider-neutral deterministic prompt compiler, the initial data-defined humanoid/wearable, creature/animal, environment/hard-surface, and visual-specialty profiles, the pure deterministic visual-job planner, the versioned project-local `$ludowright` skill installer, its status-first orchestration policy, provider-bound ImageGen operation execution, generation receipts, review workflows, technical sheets, audits, specialist routing, package generation, local release verification, and deterministic example inputs are established. The supported installation, first-project, character/custom-profile, troubleshooting, update, and uninstall guides are now available; clean-room installation and public-beta readiness remain bounded follow-up slices.

See the ordered implementation program in [`docs/plans/IMPLEMENTATION_PLAN.md`](docs/plans/IMPLEMENTATION_PLAN.md).

Start with the [installation guide](docs/getting-started/INSTALLATION.md) and
then follow the [first-project tutorial](docs/getting-started/FIRST_PROJECT.md).

## Development setup

Requirements:

- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/raillen/ludowright.git
cd ludowright
uv sync --extra dev --extra docs
uv run ludowright --version
uv run ludowright status
```

Install the local hooks once:

```bash
uv run pre-commit install
```

Run the complete pull-request quality gate:

```bash
uv run ludowright quality check
```

Run the release gate, including package build verification:

```bash
uv run ludowright quality release
```

Both commands support `--dry-run` and `--json`.

## Documentation

The documentation site is configured for:

```text
https://raillen.github.io/ludowright/
```

Preview it locally with:

```bash
uv run mkdocs serve
```

Start with:

- [`PROJECT_START.md`](PROJECT_START.md)
- [`docs/ATLAS.md`](docs/ATLAS.md)
- [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)
- [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)
- [`docs/architecture/SYSTEM_OVERVIEW.md`](docs/architecture/SYSTEM_OVERVIEW.md)
- [`docs/plans/IMPLEMENTATION_PLAN.md`](docs/plans/IMPLEMENTATION_PLAN.md)
- [`docs/quality/ENGINEERING_QUALITY.md`](docs/quality/ENGINEERING_QUALITY.md)
- [`docs/operations/DOCUMENTATION_SITE.md`](docs/operations/DOCUMENTATION_SITE.md)

## Contributing and support

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development workflow and pull-request requirements;
- [`SUPPORT.md`](SUPPORT.md) — where and how to request help;
- [`SECURITY.md`](SECURITY.md) — private vulnerability-reporting policy;
- [`GOVERNANCE.md`](GOVERNANCE.md) — roles and decision process;
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — community behavior and enforcement.

## License

Licensed under the [Apache License 2.0](LICENSE).
