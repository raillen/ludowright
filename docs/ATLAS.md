# LudoWright Documentation Atlas

This is the main navigation map for humans and agents. Each subject should have one canonical source.

## Project entry points

- [Repository README](https://github.com/raillen/ludowright/blob/main/README.md) — project overview, status, setup, and primary links.
- [Project Start](https://github.com/raillen/ludowright/blob/main/PROJECT_START.md) — orientation for contributors and agents.
- [Agent Guide](https://github.com/raillen/ludowright/blob/main/AGENTS.md) — concise operational rules for Codex and other repository agents.
- `atlas.json` — versioned canonical-source metadata consumed by the ATLAS generator.

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
- [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md) — visual provenance, revision-bound references, immutable generation jobs, attempt receipts, retries, and reviews.
- [`contracts/CAPTURE_PROFILES.md`](contracts/CAPTURE_PROFILES.md) — camera, background, lighting, validation, required views, isolated items, technical sheets, and exact versioned inheritance.
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
- [`commands/DOCUMENTS.md`](commands/DOCUMENTS.md) — incremental document refresh syntax, dry-run, output, and failure behavior.
- [`commands/DOCS.md`](commands/DOCS.md) — deterministic documentation audit syntax, policy, findings, and check behavior.
- [`commands/ATLAS.md`](commands/ATLAS.md) — ATLAS generation, integrity checking, and JSON output.
- [`commands/ASSETS.md`](commands/ASSETS.md) — asset registry CRUD, discovery, validation, batch import/export, dry-run, and failure behavior.
- [`contracts/CLI.md`](contracts/CLI.md) — dual human/JSON surfaces, response envelope, error codes, exit codes, version output, diagnostics, and compatibility rules.

Published machine-readable contracts are stored under `schemas/v1/`. The source models live under `src/ludowright/contracts/`.

Planned canonical contracts:

- project manifest;
- release manifest.

The guided-documentation model is implemented in `src/ludowright/domain/interviews.py`, orchestrated by `src/ludowright/application/interviews.py`, and adapted at the external boundary by `src/ludowright/contracts/interviews.py`. The published interview contracts are `interview-questionnaire` and `interview-session`; CLI presentation lives in `src/ludowright/cli/interview.py`.

The document template engine is implemented in `src/ludowright/application/document_templates.py`, its manifest contract lives in `src/ludowright/contracts/document_templates.py`, and versioned `minimal`, `product`, and `architecture` template data lives in `src/ludowright/template_data/`. The architecture pack is cataloged in [`architecture/ARCHITECTURE_DOCUMENT_SET.md`](architecture/ARCHITECTURE_DOCUMENT_SET.md). ATLAS generation is implemented by `src/ludowright/application/atlas.py` using `docs/atlas.json`; incremental refresh is implemented by `src/ludowright/application/document_refresh.py` with state persistence in `src/ludowright/infrastructure/document_refresh.py`; documentation auditing is implemented by `src/ludowright/application/documentation_audit.py` using the declarative `docs/audit-policy.json`.

The ATLAS scanner uses `src/ludowright/infrastructure/documentation.py` for
bounded, read-only Markdown access. The `atlas` command is registered in
`src/ludowright/cli/app.py` and participates in the unified quality gate.
The `docs audit` command shares the same CLI envelope and participates in the
quality gate with `--check`.

The initial asset taxonomy is loaded by
`src/ludowright/application/asset_taxonomy.py` from versioned JSON data under
`src/ludowright/taxonomy_data/`. Asset registry commands are orchestrated by
`src/ludowright/application/asset_registry.py` and presented by
`src/ludowright/cli/assets.py` over the shared structured repositories.
Asset discovery is orchestrated by
`src/ludowright/application/asset_discovery.py`; it uses the safe project
filesystem, explicit Markdown markers, and the registry batch operation for
confirmed candidates.

## Codex integration

Planned documents:

- skill installation and invocation;
- agent roles and routing;
- ImageGen job execution;
- approval checkpoints;
- recovery and retry behavior;
- evals for agent compliance.

## Visual production

- [`contracts/REFERENCES_AND_VISUAL_JOBS.md`](contracts/REFERENCES_AND_VISUAL_JOBS.md) — provenance, immutable generation jobs, receipts, retries, and reviews.
- [`contracts/CAPTURE_PROFILES.md`](contracts/CAPTURE_PROFILES.md) — reusable camera, view, isolation, validation, and technical-sheet requirements.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — revision-aware invalidation from approved references and asset components to jobs, outputs, sheets, and packages.

Planned detailed documents:

- visual bible schema;
- asset decomposition and registry taxonomy extensions;
- segmented character references;
- garments and props;
- creatures, vehicles, architecture, foliage, UI, VFX, and modular kits;
- deterministic technical-sheet assembly;
- provenance and licensing operations.

## Implementation

- [`plans/IMPLEMENTATION_PLAN.md`](plans/IMPLEMENTATION_PLAN.md) — ordered PR program for the first stable release.

Future bounded changes should receive their own plan under `plans/`.

## Quality

- [`quality/ENGINEERING_QUALITY.md`](quality/ENGINEERING_QUALITY.md) — pre-commit, unified quality commands, coverage, property tests, schema drift, dependency audits, secret scanning, CI, and failure policy.
- [`contracts/JSON_SCHEMAS.md`](contracts/JSON_SCHEMAS.md) — schema-generation, checksum, fixture, and compatibility validation rules.
- [`contracts/STRUCTURED_REPOSITORIES.md`](contracts/STRUCTURED_REPOSITORIES.md) — parser limits, deterministic round trips, duplicate-key rejection, and optimistic concurrency tests.
- [`contracts/EVENT_LOG.md`](contracts/EVENT_LOG.md) — replay integrity, chained hashes, sequence, concurrency, corruption, and incomplete-tail recovery tests.
- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — WAL, strict tables, rollback, concurrency, checkpoint, source-digest, corruption, and rebuild tests.
- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — catalog, dry-run, backup, failure rollback, explicit restore, tampering, and concurrency tests.
- [`contracts/DEPENDENCY_GRAPH.md`](contracts/DEPENDENCY_GRAPH.md) — cycle rejection, revision propagation, impact-path selection, refresh blocking, contract round-trip, and repository conflict tests.
- [`contracts/CLI.md`](contracts/CLI.md) — envelope invariants, deterministic JSON, global options, diagnostics, quality failures, and exit-code tests.

Planned detailed documents:

- snapshot testing;
- agent evals;
- release verification;
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
