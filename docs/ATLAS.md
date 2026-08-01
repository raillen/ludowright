# LudoWright Documentation Atlas

This is the main navigation map for humans and agents. Each subject should have one canonical source.

## Project entry points

- [Repository README](https://github.com/raillen/ludowright/blob/main/README.md) — project overview, status, setup, and primary links.
- [Project Start](https://github.com/raillen/ludowright/blob/main/PROJECT_START.md) — orientation for contributors and agents.
- [Agent Guide](https://github.com/raillen/ludowright/blob/main/AGENTS.md) — concise operational rules for Codex and other repository agents.
- `atlas.json` — versioned canonical-source metadata consumed by the ATLAS generator.

## Getting started

- [`getting-started/INSTALLATION.md`](getting-started/INSTALLATION.md) — supported checkout installation for Linux, Windows, and macOS.
- [`getting-started/FIRST_PROJECT.md`](getting-started/FIRST_PROJECT.md) — deterministic first-project flow with `init`, dry-run, and project-local skill installation.
- [`getting-started/CHARACTER_WORKFLOW.md`](getting-started/CHARACTER_WORKFLOW.md) — character workflow, custom capture profile, humanoid package profile, planning, and approval boundaries.
- [`getting-started/TROUBLESHOOTING.md`](getting-started/TROUBLESHOOTING.md) — conservative diagnosis and recovery for checkout installation, project initialization, Codex skill, and quality-gate failures.
- [`getting-started/UPDATING.md`](getting-started/UPDATING.md) — safe checkout, environment, and project-local skill update flow.
- [`getting-started/UNINSTALLING.md`](getting-started/UNINSTALLING.md) — safe removal and reinstallation of the project-local Codex skill.

## Product

- [`product/PRODUCT_VISION.md`](product/PRODUCT_VISION.md) — mission, users, value, principles, boundaries, and success measures.
- [`product/PRODUCT_DOCUMENT_SET.md`](product/PRODUCT_DOCUMENT_SET.md) — initial product-document catalog, entrypoints, contexts, and derived-output boundaries.
- [`product/ROADMAP.md`](product/ROADMAP.md) — planned capabilities from the 0.x series through the long-term Studio direction.

## Architecture

- [`architecture/SYSTEM_OVERVIEW.md`](architecture/SYSTEM_OVERVIEW.md) — system boundaries, layers, modules, state, and integration model.
- [`architecture/ARCHITECTURE_DOCUMENT_SET.md`](architecture/ARCHITECTURE_DOCUMENT_SET.md) — versioned architecture and implementation template entrypoints and their canonical sources.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — canonical dependency direction, revision tracking, stale propagation, impact explanation, refresh, and cycle policy.
- `architecture/COMPONENTS.md` — planned detailed component responsibilities.
- `architecture/DATA_MODEL.md` — planned canonical entities and relationships.

## Contracts

- [`contracts/IDENTIFIERS_AND_VERSIONS.md`](contracts/IDENTIFIERS_AND_VERSIONS.md) — display names, slugs, typed entity IDs, and schema/template/profile revisions.
- [`contracts/PROJECT_DOMAIN.md`](contracts/PROJECT_DOMAIN.md) — project identity, dimensions, targets, engine, production stage, lifecycle, and transition invariants.
- [`contracts/DECISIONS_AND_APPROVALS.md`](contracts/DECISIONS_AND_APPROVALS.md) — decision states, revision-bound approval states, immutable logical histories, and superseding relationships.
- [`contracts/ASSET_DOMAIN.md`](contracts/ASSET_DOMAIN.md) — asset families, subtypes, ownership, decomposition, hierarchy, priority, status, and completion rules.
- [`contracts/ASSET_TAXONOMY.md`](contracts/ASSET_TAXONOMY.md) — versioned family/subtype data, naming prefixes, validation boundaries, and compatibility.
- [`contracts/ASSET_REGISTRY.md`](contracts/ASSET_REGISTRY.md) — v1 YAML registry shape, revisioning, commands, import/export, and rollback semantics.
- [`contracts/ASSET_DISCOVERY.md`](contracts/ASSET_DISCOVERY.md) — explicit Markdown candidate syntax, deterministic reports, confirmation, ambiguity, and provenance.
- [`contracts/ASSET_DECOMPOSITION.md`](contracts/ASSET_DECOMPOSITION.md) — decomposition input/report contracts, graph coordination, recommendations, guided corrections, and rollback.
- [`contracts/ASSET_WORKBOOK.md`](contracts/ASSET_WORKBOOK.md) — derived ODS sheets, versioned template data, determinism, dry-run, and failure behavior.
- [`contracts/ASSET_AUDIT.md`](contracts/ASSET_AUDIT.md) — deterministic read-only asset findings, severity policy, source consistency, and compatibility.
- [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md) — visual provenance, revision-bound references, immutable generation jobs, attempt receipts, retries, and the canonical review workflow.
- [`contracts/VISUAL_JOB_PLANS.md`](contracts/VISUAL_JOB_PLANS.md) — deterministic profile-aware job derivation, dependency ordering, batching, workload estimates, and readiness blockers.
- [`contracts/CAPTURE_PROFILES.md`](contracts/CAPTURE_PROFILES.md) — camera, background, lighting, validation, required views, isolated items, technical sheets, and exact versioned inheritance.
- [`contracts/HUMANOID_PROFILES.md`](contracts/HUMANOID_PROFILES.md) — neutral body bases, humanoid views, wearable categories, assembled outputs, and data-defined specialization of capture profiles.
- [`contracts/CREATURE_PROFILES.md`](contracts/CREATURE_PROFILES.md) — data-defined quadruped, bird, fish, insect, and fantasy-creature anatomy, components, states, views, and outputs.
- [`contracts/HARD_SURFACE_PROFILES.md`](contracts/HARD_SURFACE_PROFILES.md) — data-defined props, vehicles, buildings, modular kits, interiors, construction components, connection matrices, states, views, and outputs.
- [`contracts/VISUAL_PROFILES.md`](contracts/VISUAL_PROFILES.md) — data-defined tree, plant, UI, VFX, locomotion, and motion-set profiles with typed components, variants, states, views, and outputs.
- [`contracts/VISUAL_BIBLE.md`](contracts/VISUAL_BIBLE.md) — project-level visual direction, palette, materials, detail levels, budgets, and prompt constraints.
- [`contracts/PROMPT_COMPILER.md`](contracts/PROMPT_COMPILER.md) — versioned prompt layers, approved-reference resolution, structured constraints, deterministic rendering, and prompt hashing.
- [`contracts/CODEX_ORCHESTRATION.md`](contracts/CODEX_ORCHESTRATION.md) — declarative Codex policy, deterministic next-action plans, checkpoints, validation, and resumability.
- [`contracts/CODEX_AGENTS.md`](contracts/CODEX_AGENTS.md) — versioned specialist roles, capabilities, routing, evidence boundaries, and human approval limits.
- [`contracts/CODEX_SKILL.md`](contracts/CODEX_SKILL.md) — versioned project-local `$ludowright` skill package, lifecycle semantics, checksums, and safe failure behavior.
- [`contracts/IMAGEGEN_EXECUTION.md`](contracts/IMAGEGEN_EXECUTION.md) — provider boundary, deterministic operation manifests, one-view execution, PNG validation, conflicts, dry-run, and rollback.
- [`contracts/IMAGE_NORMALIZATION.md`](contracts/IMAGE_NORMALIZATION.md) — bounded image inputs, EXIF orientation, dimensions, padding, backgrounds, thumbnails, guides, checksums, and rollback.
- [`contracts/TECHNICAL_SHEETS.md`](contracts/TECHNICAL_SHEETS.md) — approved PNG inputs, data-defined templates, deterministic placement, output reports, dry-run, conflicts, and rollback.
- [`contracts/JSON_SCHEMAS.md`](contracts/JSON_SCHEMAS.md) — generated Draft 2020-12 schemas, registry, fixtures, checksums, drift checking, and compatibility policy.
- [`contracts/PROJECT_FILESYSTEM.md`](contracts/PROJECT_FILESYSTEM.md) — root discovery, canonical repository paths, symlink rejection, atomic writes, bounded reads, and exclusive locks.
- [`contracts/STRUCTURED_REPOSITORIES.md`](contracts/STRUCTURED_REPOSITORIES.md) — strict JSON/YAML parsing, canonical serialization, document digests, snapshots, and conflict detection.
- [`contracts/EVENT_LOG.md`](contracts/EVENT_LOG.md) — immutable events, JSON Lines replay, correlation, causation, sequence, hash chaining, and explicit tail recovery.
- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — rebuildable SQLite workflow state, entity indexes, event checkpoints, transactions, and canonical-source consistency.
- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — contiguous plans, dry runs, consistent backups, receipts, transactional apply, and guarded rollback.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — typed nodes and edges, observed revisions, freshness states, invalidation paths, refresh rules, and canonical graph persistence.
- [`contracts/INTERVIEW_QUESTIONS.md`](contracts/INTERVIEW_QUESTIONS.md) — declarative questionnaire shapes, safe dependencies, answer provenance, and pending-question semantics.
- [`contracts/DOCUMENT_TEMPLATES.md`](contracts/DOCUMENT_TEMPLATES.md) — versioned Jinja manifests, inheritance, project overrides, deterministic output, and sandbox boundaries.
- [`contracts/DOCUMENT_REFRESH.md`](contracts/DOCUMENT_REFRESH.md) — source hashes, stale planning, manual-section preservation, atomic persistence, and rollback.
- [`contracts/DOCUMENTATION_AUDIT.md`](contracts/DOCUMENTATION_AUDIT.md) — versioned audit policy, deterministic findings, and read-only validity semantics.
- [`contracts/ATLAS.md`](contracts/ATLAS.md) — canonical documentation metadata, deterministic indexes, link findings, and orphan detection.
- [`commands/INTERVIEW.md`](commands/INTERVIEW.md) — interview CLI syntax, resumable session files, skip/defer policy, and JSON interaction data.
- [`commands/INIT.md`](commands/INIT.md) — create-only project initialization, templates, dry-run, rollback, and CLI output.
- [`commands/DOCUMENTS.md`](commands/DOCUMENTS.md) — incremental document refresh syntax, dry-run, output, and failure behavior.
- [`commands/DOCS.md`](commands/DOCS.md) — deterministic documentation audit syntax, policy, findings, and check behavior.
- [`commands/ATLAS.md`](commands/ATLAS.md) — ATLAS generation, integrity checking, and JSON output.
- [`commands/ASSETS.md`](commands/ASSETS.md) — asset registry CRUD, discovery, decomposition, ODS export, audit, validation, batch import/export, dry-run, and failure behavior.
- [`commands/CODEX.md`](commands/CODEX.md) — install, update, verify, and remove the project-local Codex skill.
- [`commands/REVIEWS.md`](commands/REVIEWS.md) — apply receipt-bound visual reviews with approval, correction, rejection, supersession, dry-run, and rollback semantics.
- [`commands/IMAGES.md`](commands/IMAGES.md) — normalize local images into deterministic PNG outputs and reports.
- [`commands/SHEETS.md`](commands/SHEETS.md) — assemble approved PNGs into deterministic technical sheets and reports.
- [`commands/PACKAGES.md`](commands/PACKAGES.md) — create manifests and build reproducible ZIP releases with checksums, dry-run, and create-only behavior.
- [`commands/AUDIT.md`](commands/AUDIT.md) — read-only global readiness audit syntax, Rich/JSON output, check policy, and failure behavior.
- [`commands/RELEASES.md`](commands/RELEASES.md) — local release verification, warning policy, checksum manifest, dry-run, and create-only behavior.
- [`contracts/CLI.md`](contracts/CLI.md) — dual human/JSON surfaces, response envelope, error codes, exit codes, version output, diagnostics, and compatibility rules.
- [`contracts/PROJECT_AUDITS.md`](contracts/PROJECT_AUDITS.md) — global readiness categories, source evidence, deterministic findings, immutable SQLite inspection, and conflict policy.
- [`contracts/RELEASE_VERIFICATION.md`](contracts/RELEASE_VERIFICATION.md) — release gates, warning policy, checksum-verifiable manifest, archive inspection, and compatibility.
- [`contracts/PACKAGE_MANIFESTS.md`](contracts/PACKAGE_MANIFESTS.md) — package inventory shape, path policy, source versions, provenance, exclusions, and compatibility.
- [`contracts/PACKAGE_BUILDS.md`](contracts/PACKAGE_BUILDS.md) — reproducible ZIP members, package index, release directory, safety limits, and rollback.

Published machine-readable contracts are stored under `schemas/v1/`. The source models live under `src/ludowright/contracts/`.

Published canonical contracts include the project manifest, project template,
package manifest,
package index, project-audit report, release manifest, and release verification
report. Digital signing and remote publication remain outside PR56.

The guided-documentation model is implemented in `src/ludowright/domain/interviews.py`, orchestrated by `src/ludowright/application/interviews.py`, and adapted at the external boundary by `src/ludowright/contracts/interviews.py`. The published interview contracts are `interview-questionnaire` and `interview-session`; CLI presentation lives in `src/ludowright/cli/interview.py`.

The document template engine is implemented in `src/ludowright/application/document_templates.py`, its manifest contract lives in `src/ludowright/contracts/document_templates.py`, and versioned `minimal`, `product`, and `architecture` template data lives in `src/ludowright/template_data/`. The architecture pack is cataloged in [`architecture/ARCHITECTURE_DOCUMENT_SET.md`](architecture/ARCHITECTURE_DOCUMENT_SET.md). ATLAS generation is implemented by `src/ludowright/application/atlas.py` using `docs/atlas.json`; incremental refresh is implemented by `src/ludowright/application/document_refresh.py` with state persistence in `src/ludowright/infrastructure/document_refresh.py`; documentation auditing is implemented by `src/ludowright/application/documentation_audit.py` using the declarative `docs/audit-policy.json`.

The ATLAS scanner uses `src/ludowright/infrastructure/documentation.py` for
bounded, read-only Markdown access. The `atlas` command is registered in
`src/ludowright/cli/app.py` and participates in the unified quality gate.
The `docs audit` command shares the same CLI envelope and participates in the
quality gate with `--check`.

The Codex skill installer is implemented in
`integrations/codex/skill_installer.py`; its versioned manifest and entrypoint
are data under `integrations/codex/skills/ludowright/`. The orchestration policy
and pure next-action planner live in `integrations/codex/orchestration.py` and
the same package-data directory. The CLI adapter lives in
`src/ludowright/cli/codex.py` and uses the shared filesystem boundary, lock, and
CLI envelope. The policy planner does not change canonical project state, the
event log, SQLite, or provider outputs.

ImageGen operation execution and terminal receipt recording are implemented by
`integrations/codex/imagegen.py` and
`src/ludowright/infrastructure/generation_receipts.py`. They consume a
selected job and matching compiled prompt, reuse `ProjectFilesystem`,
`JsonDocumentRepository`, and the project lock, and persist candidate generated
references with checksums and provenance. Reviews, approvals, event-log
projection, and SQLite indexing are coordinated by
`src/ludowright/application/visual_review.py` and its canonical repositories;
SQLite remains a derived index.

Image normalization is implemented by
`src/ludowright/infrastructure/image_normalization.py` and orchestrated by
`src/ludowright/application/image_normalization.py`; the `images normalize`
command lives in `src/ludowright/cli/images.py`. It creates only derived PNGs
and an `image-normalization` report, using Pillow behind the infrastructure
boundary and the shared filesystem lock/atomic-write rules.

Technical-sheet assembly is implemented by
`src/ludowright/infrastructure/technical_sheets.py` and orchestrated by
`src/ludowright/application/technical_sheets.py`; the `sheets assemble` command
lives in `src/ludowright/cli/sheets.py`. It consumes explicit requests,
approved references, and normalized PNG checksums, loads the data-defined
`minimal` template, and creates a deterministic sheet plus provenance report.
It does not mutate canonical references, approvals, the event log, the
dependency graph, or SQLite.

Package manifest generation is implemented by
`src/ludowright/application/package_manifest.py` over the bounded scanner in
`src/ludowright/infrastructure/package_manifest.py`; the `package manifest`
command is presented by `src/ludowright/cli/packages.py`. The v1 contract,
schema, fixture, provenance summary, explicit exclusions, deterministic
checksums, and create-only/dry-run semantics are published. ZIP package
building is implemented by `src/ludowright/application/package_builder.py`
over `PackageArchiveBuilder` in `src/ludowright/infrastructure/package_manifest.py`;
it consumes the manifest, validates source checksums, writes fixed ZIP metadata,
and publishes a v1 `package-index` alongside the release archive. Release
verification is implemented by `src/ludowright/application/release_verification.py`
and presented by `src/ludowright/cli/release.py`; it validates the audit,
manifest, index, canonical ZIP, and cross-checksums before creating a local
SHA-256 release manifest.

The global project audit is implemented by
`src/ludowright/application/project_audit.py` and presented by
`src/ludowright/cli/audit.py`. It composes the existing canonical repositories
and audits product, documents, assets, references, jobs, approvals, sheets,
and package readiness without writing project state. The v1 `project-audit`
contract records source evidence, stable findings, category summaries, and
recommended actions. Release verification consumes that report as its first
gate and applies the explicit `block` or `allow` warning policy without
mutating project state.

Project initialization is implemented by
`src/ludowright/application/initialization.py` and presented by the top-level
`init` command. It loads the data-defined template from
`src/ludowright/templates/`, composes the existing filesystem, event-log,
dependency-graph, structured-repository, and SQLite adapters, and writes the
project marker only after validation. Initialization is create-only, supports
Rich/JSON output and dry-run, rejects unsafe paths and symlinks, and performs
conservative rollback after partial failure. The template and manifest
provenance contracts are published at v1; the state store remains at schema v2.

The supported installation, first-project, character/custom-profile,
troubleshooting, update, and uninstall path is documented in
`getting-started/`. It uses the
repository checkout with `uv`, keeps the Python and platform requirements
explicit, exercises the non-interactive `init` and project-local Codex skill
commands, and records conservative recovery for published CLI error codes.
Clean-room package installation remains reserved for the later public-beta
readiness slice.

The initial asset taxonomy is loaded by
`src/ludowright/application/asset_taxonomy.py` from versioned JSON data under
`src/ludowright/taxonomy_data/`. Asset registry commands are orchestrated by
`src/ludowright/application/asset_registry.py` and presented by
`src/ludowright/cli/assets.py` over the shared structured repositories.
Asset discovery is orchestrated by
`src/ludowright/application/asset_discovery.py`; it uses the safe project
filesystem, explicit Markdown markers, and the registry batch operation for
confirmed candidates.
Asset decomposition is orchestrated by
`src/ludowright/application/asset_decomposition.py`; it reuses the registry
mutation boundary, persists cross-asset prerequisites through the canonical
dependency graph, and derives recommendations from versioned data.
Asset workbook export is orchestrated by
`src/ludowright/application/asset_workbook.py`; it projects the registry and
dependency graph through the data-defined template in
`src/ludowright/workbook_data/` and writes validated ODS packages through
`src/ludowright/infrastructure/ods.py`.
Asset audit is orchestrated by `src/ludowright/application/asset_audit.py`; it
reads the same canonical registry and graph without creating project state and
returns the published `asset-audit` report through
`src/ludowright/cli/assets.py`.
The visual bible contract is implemented by
`src/ludowright/domain/visual_bibles.py` and
`src/ludowright/contracts/visual_bible.py`; it publishes the strict v1
`visual-bible` schema without introducing persistence or provider execution.
The prompt compiler is implemented by
`src/ludowright/domain/prompt_compiler.py` and
`src/ludowright/application/prompt_compiler.py`; it loads versioned data from
`src/ludowright/prompt_data/`, resolves only approved references for the exact
target, and publishes deterministic `prompt-template` and `compiled-prompt`
schemas without invoking a provider or changing persisted job formats.
Humanoid profiles are implemented by
`src/ludowright/domain/humanoid_profiles.py` and
`src/ludowright/application/humanoid_profiles.py`; they load versioned
`minimal` data from `src/ludowright/profile_data/`, reuse the generic
capture-profile and sheet contracts, and derive immutable outputs without
creating project state or image files.

Creature and animal profiles are implemented by
`src/ludowright/domain/creature_profiles.py` and
`src/ludowright/application/creature_profiles.py`; they load the five
versioned manifests from `src/ludowright/profile_data/creature/`, reuse the
generic capture-profile and sheet contracts, and derive anatomy-specific
outputs without creating project state or image files.

Environment and hard-surface profiles are implemented by
`src/ludowright/domain/hard_surface_profiles.py` and
`src/ludowright/application/hard_surface_profiles.py`; they load the five
versioned manifests from `src/ludowright/profile_data/hard-surface/`, reuse the
generic capture-profile and sheet contracts, validate directed construction
connection matrices, and derive deterministic outputs without creating project
state or image files.

## Codex integration

- [`contracts/CODEX_SKILL.md`](contracts/CODEX_SKILL.md) — versioned skill package and lifecycle contract;
- [`commands/CODEX.md`](commands/CODEX.md) — skill installation, verification, update, and removal;
- [`decisions/0034-versioned-codex-skill-installer.md`](decisions/0034-versioned-codex-skill-installer.md) — adapter boundary and atomic-install decision.
- [`decisions/0035-codex-orchestration-policy.md`](decisions/0035-codex-orchestration-policy.md) — declarative policy boundary and deterministic planning.
- [`decisions/0036-imagegen-job-execution.md`](decisions/0036-imagegen-job-execution.md) — provider boundary, immutable operation record, and safe rollback.
- [`decisions/0037-generation-receipts.md`](decisions/0037-generation-receipts.md) — durable terminal receipts, generated references, checksums, and rollback semantics.
- [`decisions/0038-visual-review-workflow.md`](decisions/0038-visual-review-workflow.md) — receipt-bound human approval, reviewer separation, dependency invalidation, supersession, and rollback.
- [`decisions/0039-codex-specialist-agents.md`](decisions/0039-codex-specialist-agents.md) — versioned specialist catalog, deterministic routing, and no agent approval authority.
- [`decisions/0040-image-normalization.md`](decisions/0040-image-normalization.md) — Pillow boundary, deterministic derived outputs, metadata handling, and safe persistence.
- [`decisions/0041-deterministic-technical-sheet-assembly.md`](decisions/0041-deterministic-technical-sheet-assembly.md) — data-defined layouts, approved inputs, deterministic rendering, and create-only persistence.
- [`decisions/0042-deterministic-package-manifest.md`](decisions/0042-deterministic-package-manifest.md) — deterministic inventory boundary, exclusions, and manifest-only staging.
- [`decisions/0043-deterministic-package-builder.md`](decisions/0043-deterministic-package-builder.md) — fixed ZIP metadata, package index, release directory, and create-only rollback.
- [`decisions/0044-deterministic-project-audit.md`](decisions/0044-deterministic-project-audit.md) — read-only global readiness report, immutable SQLite inspection, deterministic evidence, and conflict policy.
- [`decisions/0045-deterministic-release-verification.md`](decisions/0045-deterministic-release-verification.md) — deterministic local release gates, checksum manifest, warning policy, and no-signing boundary.
- [`decisions/0046-deterministic-project-initialization.md`](decisions/0046-deterministic-project-initialization.md) — versioned data templates, create-only initialization, marker-last persistence, and conservative rollback.

Planned documents:

- approval checkpoints;
- recovery and retry behavior;
- phase-execution orchestration.

## Visual production

- [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md) — provenance, immutable generation jobs, receipts, retries, and reviews.
- [`contracts/CAPTURE_PROFILES.md`](contracts/CAPTURE_PROFILES.md) — reusable camera, view, isolation, validation, and technical-sheet requirements.
- [`contracts/HUMANOID_PROFILES.md`](contracts/HUMANOID_PROFILES.md) — initial humanoid body-base, wearable, per-view, and assembled-output profile data.
- [`contracts/CREATURE_PROFILES.md`](contracts/CREATURE_PROFILES.md) — initial creature and animal anatomy, component, state, per-view, and assembled-output profile data.
- [`contracts/HARD_SURFACE_PROFILES.md`](contracts/HARD_SURFACE_PROFILES.md) — initial props, vehicles, buildings, modular-kit, and interior profile data with directed connection matrices.
- [`contracts/VISUAL_BIBLE.md`](contracts/VISUAL_BIBLE.md) — shared visual direction and constraints consumed by later visual-foundation slices.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — revision-aware invalidation from approved references and asset components to jobs, outputs, sheets, and packages.

Planned detailed documents:

- segmented character references;
- garments and props;
- provenance and licensing operations.

## Implementation

- [`plans/IMPLEMENTATION_PLAN.md`](plans/IMPLEMENTATION_PLAN.md) — ordered PR program for the first stable release.

Future bounded changes should receive their own plan under `plans/`.

## Examples

- [`examples/MINIMAL.md`](examples/MINIMAL.md) — deterministic Lantern Path
  example inputs, fixture checksum, workflow boundaries, and local execution.
- [`examples/2D.md`](examples/2D.md) — Starfall Courier sprite workflow,
  custom capture profile, approval gate, and deterministic fixture.
- [`examples/LOW_POLY_3D.md`](examples/LOW_POLY_3D.md) — Copper & Forge
  humanoid/building workflow with segmented components and approval gates.
- [`examples/MODULAR_ENVIRONMENT.md`](examples/MODULAR_ENVIRONMENT.md) —
  Mossbridge Commons modular building, road, foliage, socket, and connection
  workflow.

## Quality

- [`quality/ENGINEERING_QUALITY.md`](quality/ENGINEERING_QUALITY.md) — pre-commit, unified quality commands, local-first end-to-end validation, migration compatibility matrix, clean-room package installation, coverage, property tests, schema drift, dependency audits, secret scanning, CI, and failure policy.
- [`quality/CODEX_AGENT_EVALS.md`](quality/CODEX_AGENT_EVALS.md) — offline specialist-agent conformance scenarios and safety invariants.
- [`contracts/JSON_SCHEMAS.md`](contracts/JSON_SCHEMAS.md) — schema-generation, checksum, fixture, and compatibility validation rules.
- [`contracts/STRUCTURED_REPOSITORIES.md`](contracts/STRUCTURED_REPOSITORIES.md) — parser limits, deterministic round trips, duplicate-key rejection, and optimistic concurrency tests.
- [`contracts/EVENT_LOG.md`](contracts/EVENT_LOG.md) — replay integrity, chained hashes, sequence, concurrency, corruption, and incomplete-tail recovery tests.
- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — WAL, strict tables, rollback, concurrency, checkpoint, source-digest, corruption, and rebuild tests.
- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — catalog, dry-run, backup, failure rollback, explicit restore, tampering, and concurrency tests.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — cycle rejection, revision propagation, impact-path selection, refresh blocking, contract round-trip, and repository conflict tests.
- [`contracts/CLI.md`](contracts/CLI.md) — envelope invariants, deterministic JSON, global options, diagnostics, quality failures, and exit-code tests.

Planned detailed documents:

- snapshot testing;
- digital release signing and remote publication;
- performance budgets.

## Security

- [Security Policy](https://github.com/raillen/ludowright/blob/main/SECURITY.md) — vulnerability reporting and current security requirements.
- [`contracts/PROJECT_FILESYSTEM.md`](contracts/PROJECT_FILESYSTEM.md) — local path containment, symbolic-link policy, atomic replacement, and lock ownership.
- [`contracts/STRUCTURED_REPOSITORIES.md`](contracts/STRUCTURED_REPOSITORIES.md) — bounded UTF-8 parsing, safe YAML restrictions, duplicate-key rejection, and exact-byte conflict detection.
- [`contracts/EVENT_LOG.md`](contracts/EVENT_LOG.md) — canonical event lines, integrity-chain meaning, parser limits, atomic append, and explicit recovery boundaries.
- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — SQLite sidecar safety, parameterized operations, strict schemas, short transactions, and corruption isolation.
- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — trusted migration code, durable backups, strict receipts, digest-guarded rollback, and fail-closed versions.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — bounded graph documents, typed identities, cycle rejection, deterministic causes, and optimistic write conflicts.
- [`contracts/CLI.md`](contracts/CLI.md) — bounded machine output, expected-error mapping, read-only diagnostics, no-color policy, and traceback boundaries.

Planned detailed documents:

- threat model;
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

- [`decisions/0014-stable-dual-surface-cli-contract.md`](decisions/0014-stable-dual-surface-cli-contract.md) — accepted Rich human output, one canonical JSON envelope, stable semantic errors and process codes, version output, and read-only diagnostics.
- [`decisions/0015-guided-interview-question-model.md`](decisions/0015-guided-interview-question-model.md) — accepted immutable questionnaires, typed answers, safe acyclic dependencies, provenance, and deterministic progress projection.
- [`decisions/0016-resumable-interview-cli.md`](decisions/0016-resumable-interview-cli.md) — accepted canonical session snapshots, questionnaire drift conflicts, event auditing, and rollback on partial persistence failure.
- [`decisions/0017-deterministic-document-template-engine.md`](decisions/0017-deterministic-document-template-engine.md) — accepted versioned data templates, allow-listed inheritance, sandboxed rendering, and deterministic output.
- [`decisions/0018-deterministic-atlas-index-and-integrity.md`](decisions/0018-deterministic-atlas-index-and-integrity.md) — accepted canonical-source metadata, offline link checks, orphan detection, and read-only generation.
- [`decisions/0019-incremental-document-refresh.md`](decisions/0019-incremental-document-refresh.md) — accepted source-hash planning, generated/manual boundaries, and rollback-coordinated persistence.
- [`decisions/0020-deterministic-documentation-audit.md`](decisions/0020-deterministic-documentation-audit.md) — accepted declarative policy, explicit contradiction rules, stale-reference findings, and read-only audit behavior.
- [`decisions/0021-data-driven-asset-taxonomy.md`](decisions/0021-data-driven-asset-taxonomy.md) — accepted versioned taxonomy data, family naming prefixes, and validation boundaries.
- [`decisions/0022-versioned-asset-registry-persistence.md`](decisions/0022-versioned-asset-registry-persistence.md) — accepted v1 YAML registry persistence, event auditing, derived indexing, and rollback.
- [`decisions/0023-deterministic-asset-discovery.md`](decisions/0023-deterministic-asset-discovery.md) — accepted explicit Markdown candidate declarations, deterministic IDs, confirmation, and fail-closed ambiguity handling.
- [`decisions/0024-asset-decomposition-workflow.md`](decisions/0024-asset-decomposition-workflow.md) — accepted aggregate-preserving decomposition, canonical graph prerequisites, derived recommendations, and cross-resource rollback.
- [`decisions/0026-deterministic-asset-audit.md`](decisions/0026-deterministic-asset-audit.md) — accepted read-only asset findings, severity policy, source consistency, and profile-gap handling.
- [`decisions/0027-versioned-visual-bible-contract.md`](decisions/0027-versioned-visual-bible-contract.md) — accepted strict project-level visual direction schema and provider-neutral boundaries.
- [`decisions/0028-deterministic-provider-neutral-prompt-compiler.md`](decisions/0028-deterministic-provider-neutral-prompt-compiler.md) — accepted data-defined prompt layers, approved-reference binding, allow-listed rendering, and canonical hashing.
- [`decisions/0029-data-defined-humanoid-wearable-profiles.md`](decisions/0029-data-defined-humanoid-wearable-profiles.md) — accepted data-defined humanoid specialization, closed neutral representation policy, and reuse of generic capture-profile semantics.
- [`decisions/0030-data-defined-creature-animal-profiles.md`](decisions/0030-data-defined-creature-animal-profiles.md) — accepted data-defined creature specialization, closed anatomy catalog, explicit states, and reuse of generic capture-profile semantics.
- [`decisions/0031-data-defined-hard-surface-profiles.md`](decisions/0031-data-defined-hard-surface-profiles.md) — accepted data-defined environment and hard-surface specialization, exact family/subtype mapping, and directed construction connection matrices.
- [`decisions/0032-data-defined-visual-specialty-profiles.md`](decisions/0032-data-defined-visual-specialty-profiles.md) — accepted data-defined foliage, UI, VFX, and animation specialization with typed requirements and deterministic generic-profile derivation.
- [`decisions/0033-deterministic-visual-job-planner.md`](decisions/0033-deterministic-visual-job-planner.md) — accepted pure visual-job planning over resolved profiles, exact references, dependency order, and provider-neutral estimates.
- [`decisions/0013-versioned-acyclic-dependency-invalidation-graph.md`](decisions/0013-versioned-acyclic-dependency-invalidation-graph.md) — accepted typed revision-aware DAG dependencies, stale and review propagation, persisted impact paths, safe refresh, and canonical JSON persistence.
- [`decisions/0012-explicit-backed-up-schema-migrations.md`](decisions/0012-explicit-backed-up-schema-migrations.md) — accepted explicit contiguous migration plans, dry runs, durable SQLite backups, strict receipts, transactional apply, and guarded rollback.
- [`decisions/0011-rebuildable-sqlite-state-index.md`](decisions/0011-rebuildable-sqlite-state-index.md) — accepted SQLite as a rebuildable derived index with WAL, strict short transactions, source digests, event checkpoints, and explicit consistency states.
- [`decisions/0010-hash-chained-append-only-event-log.md`](decisions/0010-hash-chained-append-only-event-log.md) — accepted canonical JSON Lines events, correlation, causation, contiguous replay, chained SHA-256 integrity, atomic append, and explicit tail recovery.
- [`decisions/0009-canonical-structured-document-repositories.md`](decisions/0009-canonical-structured-document-repositories.md) — accepted strict JSON/YAML loaders, deterministic serialization, exact-byte snapshots, locks, and optimistic digest conflicts.
- [`decisions/0008-safe-project-filesystem-boundary.md`](decisions/0008-safe-project-filesystem-boundary.md) — accepted canonical relative paths, symlink denial, atomic file replacement, bounded reads, and exclusive project locks.
- [`decisions/0007-generated-versioned-json-schemas.md`](decisions/0007-generated-versioned-json-schemas.md) — accepted strict Pydantic adapters, checked-in generated schemas, fixtures, checksum manifest, and drift enforcement.
- [`decisions/0006-exact-versioned-capture-profile-inheritance.md`](decisions/0006-exact-versioned-capture-profile-inheritance.md) — accepted exact parent revisions, deterministic override-by-ID ordering, and separate/assembled sheet requirements.
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
