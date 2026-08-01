# System Overview

## Architectural goal

LudoWright must provide a guided Codex experience without placing state, business rules, or validation exclusively inside prompts. The system therefore separates deterministic product behavior from agent orchestration.

## System layers

```text
User
  ↓
Codex adapter: skill, agents, hooks, ImageGen execution
  ↓
Application layer: commands, use cases, workflows, event handling
  ↓
Domain core: entities, policies, state machines, dependencies, validation
  ↓
Infrastructure: filesystem, SQLite, YAML/JSON, ODS, images, Git, packaging
```

Dependency direction points inward. Domain code must not import CLI, Codex, filesystem, database, ODS, Pillow, or Git implementations.

## Major modules

### Core domain

Owns:

- projects and lifecycle stages;
- decisions and approvals;
- documents and canonical-source relationships;
- assets, components, variants, states, and dependencies;
- visual bibles, generic capture profiles, specialized humanoid/wearable, creature/animal, environment/hard-surface, and visual-specialty profiles, and deterministic visual-job plans;
- prompt templates and compiled prompt hashes;
- visual jobs, generations, references, and receipts;
- audits, issues, milestones, packages, and releases;
- IDs, versions, status transitions, and validation policies.

### Application

Coordinates domain behavior through explicit use cases:

- initialize project;
- answer guided intake;
- generate or refresh documents;
- discover and decompose assets;
- plan visual jobs through the pure profile-aware `VisualJobPlanner`;
- compile provider-neutral prompts from visual bibles and approved references;
- record a generation result;
- approve, reject, or supersede a reference;
- assemble sheets;
- run audits;
- build a release package.

The global `audit` use case is read-only and composes existing product,
document, asset, visual, sheet, and package repositories. It records no new
canonical state; its v1 report is a deterministic readiness projection that
the later release verifier can consume.

Application code depends on ports, not concrete infrastructure.

### CLI

Provides stable human-readable and JSON interfaces. Commands must be scriptable, have predictable exit codes, and support non-interactive operation. Destructive and migration commands require dry-run support.

### Codex adapter

Provides:

- `$ludowright` skill;
- guided conversation policy;
- specialized agents;
- job-to-ImageGen execution;
- review checkpoints;
- resumable next-action suggestions;
- deterministic agent eval fixtures.

The PR44 installer lives in `integrations/codex/skill_installer.py` and ships
the versioned data from `integrations/codex/skills/ludowright/`. The PR45
orchestration policy and pure next-action planner live in
`integrations/codex/orchestration.py`; they consume read-only observations and
delegate all mutations to canonical application/CLI boundaries. The PR46
provider boundary lives in `integrations/codex/imagegen.py`; it records one
deterministic operation and validated output per view. PR47 persists receipts
and candidate references. The PR48 review workflow lives in
`src/ludowright/application/visual_review.py` and projects human approval,
reference status, dependency invalidation, and event history through canonical
repositories. PR49 adds the versioned specialist catalog and pure route
selection in `integrations/codex/agents.py`; PR50 adds the offline conformance
suite in `tests/test_codex_agent_evals.py` and
`tests/fixtures/codex-agent-evals.json`. Neither executes a phase or mutates
project state. A typed MCP-like adapter may
be added only if CLI boundaries prove insufficient.

### Infrastructure

Implements:

- local project filesystem;
- SQLite state and query index;
- YAML/JSON serialization;
- JSON Lines event log;
- ODS export;
- image normalization and composition;
- checksums and provenance;
- Git metadata;
- ZIP packaging;
- atomic writes, locks, backups, and migrations.

The filesystem also exposes a restricted case-sensitive child-file boundary for
external integration formats such as `SKILL.md`. It reuses root containment,
symlink rejection, atomic replacement, and lock ownership; it does not relax
the lowercase `RepositoryPath` grammar.

## Canonical state model

Human-editable structured files remain the canonical product data where practical. SQLite provides indexed state, workflow progress, and query support. The event log records significant changes. Derived artifacts include:

- rendered Markdown sections;
- ODS workbooks;
- technical sheets;
- reports;
- package indexes;
- ZIP releases.

Derived outputs must contain or reference their source version and generation metadata.

## Source-of-truth rules

- A decision record is canonical for rationale and status.
- Structured asset specifications are canonical for asset data.
- The visual bible and capture profiles are canonical for visual-generation requirements.
- Specialized package profiles reuse those capture semantics and remain canonical
  data definitions until a later project-local profile catalog is introduced.
- Approved individual references are canonical visual inputs.
- Contact sheets and spreadsheets are derived.
- Chat messages are never canonical.

## Project lifecycle

Initial lifecycle:

```text
new
→ intake_in_progress
→ requirements_ready
→ documentation_ready
→ assets_planned
→ visual_plan_ready
→ generation_in_progress
→ review_in_progress
→ package_ready
→ released
```

The lifecycle is not strictly linear. Changes may invalidate later stages and return the project to an earlier readiness state without deleting historical outputs.

## Invalidation model

Every generated or derived item records dependencies. When an input changes, LudoWright marks dependents stale instead of silently regenerating or deleting them.

Examples:

- changing camera perspective invalidates relevant capture profiles, environment references, and some UI decisions;
- changing a character body proportion invalidates clothing-fit references and consolidated sheets;
- rejecting an approved reference invalidates jobs and sheets that depended on it;
- changing an asset ID requires an explicit migration.

## Visual-generation architecture

The core creates a structured visual-job plan and immutable jobs. Codex executes
jobs selected from ready plans through the provider-neutral ImageGen boundary;
generation receipts record the terminal result and exact output provenance. A visual job
identifies:

- asset and component;
- operation and required view;
- approved reference inputs;
- compiled prompt and constraints;
- expected output path and format;
- validation checks;
- approval requirements.

Each technical view is generated separately. Clothing, hair, accessories, and props are independent components. Consolidated technical sheets are composed deterministically from approved files.

The PR51 `images normalize` workflow is the first derived-image boundary: it
applies bounded EXIF orientation, dimensions, padding, transparent/neutral
backgrounds, thumbnails, and alignment guides, then records an
`image-normalization` report. It does not approve or replace the source
reference. The PR52 `sheets assemble` workflow consumes explicit requests,
approved references, and exact normalized PNG checksums. Its data-defined
template selects deterministic layouts, and the application writes a PNG plus
`technical-sheet` report through the shared lock and atomic filesystem boundary.
It remains a derived workflow and does not mutate approval, event-log, graph, or
SQLite state.

Package manifest generation is implemented by
`src/ludowright/infrastructure/package_manifest.py` and
`src/ludowright/application/package_manifest.py`; the `package manifest`
command lives in `src/ludowright/cli/packages.py`. It inventories regular
project files with deterministic SHA-256 checksums, validates known structured
sources through existing repositories, records visual provenance and license
labels, and explicitly excludes transient paths and rebuildable SQLite state.
It uses the project lock and atomic filesystem writer only for a real output;
dry-run is read-only. The `package build` command in the same CLI module uses
`src/ludowright/application/package_builder.py` and the deterministic
`PackageArchiveBuilder` infrastructure adapter to validate the manifest's
source checksums, create a fixed-metadata ZIP, and write a v1 package index in
a create-only release directory. The `audit` command validates the complete
chain without writing project files or SQLite sidecars. The `release verify`
use case consumes that report and the existing package artifacts, validates the
final ZIP without extracting it, and prepares a create-only checksum manifest;
it does not sign or publish the release.

## Persistence and file safety

- writes should be atomic;
- destructive migrations create backups;
- approved files are immutable by default;
- replacements create new versions and superseding relationships;
- paths are repository-relative and normalized;
- package builders reject traversal and external paths;
- checksums detect unexpected modifications.

## Extension boundary

The initial codebase is modular but not a plugin platform. Public extension APIs arrive only after core schemas and workflows stabilize. Future plugins may add templates, capture profiles, validators, generators, and exporters without replacing domain invariants.

## Initial technology choices

- Python 3.12+;
- `uv` for development and installation workflows;
- Typer and Rich for CLI;
- Pydantic and JSON Schema for contracts;
- Jinja2 for templates;
- SQLite and YAML/JSON for persistence;
- Pillow for image processing;
- ODFPy for ODS export;
- pytest, Hypothesis, Ruff, mypy, and pre-commit for quality;
- MkDocs Material for public documentation.

Each material choice should receive an ADR before it becomes difficult to reverse.
