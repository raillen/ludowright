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

LudoWright is in the **pre-alpha foundation phase**. The current branch establishes the product vision, long-term roadmap, architecture, documentation system, Python package, CLI smoke command, tests, and CI. Project management, asset planning, and ImageGen workflows are not implemented yet.

## Development setup

Requirements:

- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/raillen/ludowright.git
cd ludowright
uv sync --extra dev
uv run ludowright --version
uv run ludowright status
```

Run the baseline checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## Documentation

Start with:

- [`PROJECT_START.md`](PROJECT_START.md)
- [`docs/ATLAS.md`](docs/ATLAS.md)
- [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)
- [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)
- [`docs/architecture/SYSTEM_OVERVIEW.md`](docs/architecture/SYSTEM_OVERVIEW.md)
- [`docs/plans/IMPLEMENTATION_PLAN.md`](docs/plans/IMPLEMENTATION_PLAN.md)

## License

Licensed under the [Apache License 2.0](LICENSE).
