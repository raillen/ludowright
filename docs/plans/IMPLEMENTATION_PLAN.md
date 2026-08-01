# Implementation Plan to LudoWright 1.0

This plan divides the first stable release into small, ordered, testable pull requests. A later PR may be split further, but unrelated steps should not be combined merely to reduce PR count.

## Phase A — Repository foundation

### PR 1 — Product and repository foundation

- product vision, roadmap, architecture overview, ATLAS, AGENTS, and project start;
- Python package skeleton;
- CI and baseline tests;
- Apache-2.0 license.

Exit: repository installs, imports, tests, and clearly explains the product.

### PR 2 — Community and governance baseline

- contributing guide;
- code of conduct;
- security policy;
- support policy;
- governance;
- issue and PR templates;
- labels and CODEOWNERS guidance.

### PR 3 — Documentation site

- MkDocs Material;
- navigation generated from canonical docs;
- link checking;
- GitHub Pages workflow;
- local preview instructions.

### PR 4 — Engineering quality baseline

- pre-commit;
- Hypothesis;
- coverage policy;
- dependency and secret scanning;
- release-quality command group.

## Phase B — Domain and contracts

### PR 5 — Core identifiers and versions

- typed project, asset, component, reference, job, decision, and package IDs;
- schema, template, and profile versions;
- slug and naming validation.

### PR 6 — Project domain model

- project identity, stage, targets, engine, dimensions, and lifecycle;
- status transitions and invariants.

### PR 7 — Decision and approval model

- decision states;
- approval states;
- superseding relationships;
- immutable history.

### PR 8 — Asset domain model

- families, subtypes, components, variants, states, priorities, ownership, and status.

### PR 9 — Reference and visual-job model

- reference provenance;
- visual jobs;
- generation receipts;
- review outcomes;
- retry and superseding behavior.

### PR 10 — Capture-profile model

- views, components, states, variations, camera, background, lighting, validation, and sheet requirements;
- profile inheritance rules.

### PR 11 — JSON Schema publication

- generated and versioned schemas;
- contract fixtures;
- compatibility tests.

## Phase C — State, storage, and migrations

### PR 12 — Project filesystem abstraction

- project-root discovery;
- normalized repository-relative paths;
- atomic writes;
- locks and safe directory creation.

### PR 13 — YAML and JSON repositories

- structured file adapters;
- canonical formatting;
- round-trip and corruption tests.

### PR 14 — Event log

- append-only JSON Lines events;
- event types and correlation IDs;
- replay-oriented tests.

### PR 15 — SQLite state store

- indexed state and workflow progress;
- transaction policy;
- consistency checks against canonical files.

### PR 16 — Migration framework

- schema migration discovery;
- dry run;
- backup;
- rollback metadata;
- migration tests.

### PR 17 — Dependency and invalidation graph

- typed edges;
- stale propagation;
- impact explanation;
- cycle checks.

## Phase D — CLI and project lifecycle

### PR 18 — CLI foundation

- Typer application;
- Rich output;
- JSON output envelope;
- stable errors and exit codes;
- `--version` and diagnostics.

### PR 19 — Project initialization

- `ludowright init`;
- template selection;
- initial manifest and directories;
- non-interactive mode;
- dry run.

### PR 20 — Project status

- readiness stages;
- blockers;
- stale outputs;
- recommended next actions;
- human and JSON output.

### PR 21 — Decision commands

- record, list, supersede, and inspect decisions;
- approval commands and audit trail.

### PR 22 — Structural audit

- missing paths;
- corrupt state;
- mismatched versions;
- unexpected approved-file mutations;
- repair guidance.

## Phase E — Guided documentation

### PR 23 — Interview question model

Status: implemented in the current slice. The model is independent of the CLI and persistence layers; PR24 will consume it.

- question types;
- dependencies;
- validation;
- answer provenance;
- pending-question calculation.

### PR 24 — Interview CLI

Status: implemented in the current slice. Sessions are canonical JSON snapshots with event-log auditing; SQLite cursor projection and document rendering remain separate concerns.

- next question;
- answer recording;
- skip and defer policies;
- resumability;
- JSON interaction contract.

### PR 25 — Document template engine

Status: implemented in the current slice. The engine publishes a versioned
minimal Jinja template, supports allow-listed inheritance and project-local
overrides, and returns deterministic Markdown without persisting it.

- Jinja2 environment;
- template inheritance;
- project overrides;
- deterministic rendering;
- snapshot tests.

### PR 26 — Product document set

Status: implemented in the current slice. The `product` template pack publishes
vision, audience, pillars, loops, scope, risk, platform, and success entrypoints
with deterministic snapshots; document persistence and interview-context
orchestration remain separate concerns.

- vision, audience, pillars, loops, scope, risk, platform, and success templates.

### PR 27 — Architecture and implementation document set

Status: implemented in the current slice. The `architecture` template pack
publishes ten deterministic entrypoints with contract-backed manifests and
snapshots. The canonical catalog maps each entrypoint to existing sources;
persistence, ATLAS generation, and refresh remain separate concerns.

- system overview, contracts, modules, UI/UX, implementation, quality, security, operations, ADRs, and plans.

### PR 28 — ATLAS generation

Status: implemented in the current slice. The `atlas-metadata` and
`atlas-report` contracts back a deterministic Markdown index, canonical-source
metadata, relative-link validation, and orphan detection. The `atlas` CLI uses
the shared Rich/JSON surfaces and remains read-only by default.

- document index;
- canonical-source metadata;
- broken-link and orphan detection.

### PR 29 — Incremental document refresh

Status: implemented in the current slice. Refresh requests and states are
published as v1 contracts; the application plans affected documents from
source hashes and template/output digests, preserves manual sections, and
persists Markdown, state, and a refresh event with atomic writes, locks, and
rollback. The interview-to-context orchestration remains separate.

- source hashes;
- stale marking;
- affected-document planning;
- preservation of approved manual sections.

### PR 30 — Documentation audit

Status: implemented in the current slice. A versioned repository-local policy
drives deterministic checks for required canonical topics, duplicate sources,
explicit contradiction phrase pairs, and stale references. The `docs audit`
command composes ATLAS integrity with policy findings, supports Rich and JSON
surfaces, and runs in the unified quality gate without modifying documentation.

- missing canonical topics;
- duplicate sources;
- contradictions and stale references;
- report output.

## Phase F — Asset registry

### PR 31 — Asset taxonomy

Status: implemented in the current slice. The `asset-taxonomy` v1 contract and
packaged JSON catalog cover every current asset family, initial data-defined
subtypes, and unique family naming prefixes. The application loader validates
the catalog and composes subtype/prefix policy with the existing domain IDs;
asset registry persistence and commands remain in PR32.

- initial families and subtypes;
- taxonomy extension data;
- naming policy.

### PR 32 — Asset registry commands

Status: implemented in the current slice. The v1 YAML registry is persisted at
`assets/registry.yaml`; commands use the existing asset contract and taxonomy,
append asset events, update the derived SQLite index, support dry-run and
batch import/export, and roll back canonical bytes after partial failure.
Dependencies, document discovery, decomposition, and ODS remain separate
follow-up PRs.

- create, update, list, inspect, archive, and validate assets;
- batch import and export.

### PR 33 — Asset discovery from documents

Status: implemented in the current slice. The workflow scans explicit asset
candidate markers in project Markdown, ignores fenced examples, validates
taxonomy and domain rules, reports deterministic evidence and ambiguity, and
requires explicit candidate confirmation before a batch registry mutation.
Confirmed candidates append `asset.discovered` provenance and reuse the
registry/event/state rollback boundary. Free-text extraction, decomposition,
dependencies, and ODS remain separate concerns.

- candidate extraction workflow;
- user confirmation;
- duplicate and ambiguity handling.

### PR 34 — Asset decomposition

Status: implemented in the current slice. `assets decompose` now validates
complete component, variant, state, and prerequisite-asset replacements,
coordinates the canonical dependency graph with the existing registry
event/state rollback boundary, emits deterministic recommendation reports,
supports inspection, dry-run, guided corrections, Rich and JSON output, and is
idempotent for identical input. The new v1 input/report schemas have fixtures
and generated manifest entries. Recommendation keys are advisory only;
executable capture profiles and independent component graph nodes remain later
visual-foundation work.

- components, variants, states, and asset-to-asset prerequisites;
- data-defined capture-profile recommendation;
- guided corrections and graph/registry rollback.

### PR 35 — ODS export

Status: implemented in the current slice. `assets export-ods` creates a
validated, deterministic, create-only ODS projection from the canonical asset
registry and dependency graph. The six views are defined by versioned data,
the report contract records source/output hashes and revisions, and Rich/JSON,
dry-run, path safety, locking, concurrency, and failure-cleanup behavior are
covered by tests. Visual-reference details are explicitly reported as
unavailable until their canonical contract exists. ODFPy is constrained to
the current 1.4.x line and no SQLite migration is introduced.

- derived workbook;
- views for overview, components, references, status, priority, and dependencies;
- deterministic formatting and validation.

### PR 36 — Asset audit

- Status: implemented in the current slice. `assets audit` is a deterministic,
  read-only report over the canonical registry and dependency graph. It detects
  orphan asset nodes, incomplete specifications and ownership metadata,
  invalid asset dependencies, and the current absence of executable persisted
  capture profiles. Blocking findings use `--check` and the shared
  `checks-failed` envelope; the new v1 report has a fixture and generated
  schema. Existing registry, graph, event-log, and SQLite formats remain
  compatible without migration.

- orphans;
- missing specs;
- invalid dependencies;
- missing capture profiles;
- incomplete production metadata.

## Phase G — Visual foundation

### PR 37 — Visual bible schema

Status: implemented in the current slice. The `visual-bible` v1 contract
publishes immutable project-level shape, proportion, palette, material,
lighting, camera, detail-level, budget, and positive/negative constraint data.
It reuses camera and lighting semantics from capture profiles and does not yet
persist project files, compile prompts, or execute visual jobs.

- shape language, proportions, palette, materials, lighting, camera, level of detail, budget, and negative constraints.

### PR 38 — Prompt compiler

Status: implemented in the current slice. The provider-neutral compiler loads
the versioned `minimal` template from package data, renders positive and
negative layers from a validated visual bible, resolves only explicitly
selected approved references for the exact target, and publishes strict v1
`prompt-template` and `compiled-prompt` contracts. The canonical SHA-256 hash
covers template, visual bible, target, layers, constraints, and reference
revisions. No provider, CLI, persistence, SQLite migration, event-log change,
or visual-job schema change is introduced.

- layered prompt templates;
- structured constraints;
- negative constraints;
- reference resolution;
- prompt hashing.

### PR 39 — Humanoid and wearable profiles

Status: implemented in the current slice. The v1 `humanoid-profile` contract
loads the versioned `minimal` package data, makes the neutral body-base policy
and humanoid wearable categories explicit, and deterministically derives the
existing generic capture profile with per-view and assembled outputs. No
project-local profile persistence, visual-job planning, provider execution,
event-log change, SQLite migration, or image generation is introduced.

- body base;
- per-view images;
- hair, garments, footwear, accessories, props, details, and assembled outputs;
- neutral representation policy.

### PR 40 — Creature and animal profiles

Status: implemented in the current slice. The v1 `creature-profile` contract
loads five versioned package manifests for quadrupeds, birds, fish, insects,
and fantasy creatures. It validates anatomy-specific views, components, and
states against the existing generic capture profile and deterministically
derives assembled and detail outputs. No project-local profile persistence,
visual-job planning, provider execution, event-log change, SQLite migration,
or image generation is introduced.

- quadrupeds, birds, fish, insects, and fantasy creatures;
- anatomy-specific views, components, and states;
- deterministic assembled and anatomy-detail outputs.

### PR 41 — Environment and hard-surface profiles

Status: implemented in the current slice. The v1 `hard-surface-profile`
contract loads five versioned package manifests for props, vehicles, buildings,
modular kits, and interiors. It validates exact asset-family/subtype mapping,
construction components, directed connection matrices, states, views, and
outputs, then deterministically derives the existing generic capture profile.
No project-local profile persistence, visual-job planning, provider execution,
event-log change, SQLite migration, dependency-graph mutation, or image
generation is introduced.

- props, vehicles, buildings, modular kits, and interiors;
- construction components and directed connection matrices;
- deterministic assembled and construction-detail outputs.

### PR 42 — Foliage, UI, VFX, and animation profiles

Status: implemented in the current slice. The v1 `visual-profile` contract
loads eight deterministic package-data profiles for trees, plants, UI,
particle and shader effects, locomotion, and motion sets. It validates exact
taxonomy mappings, typed components, optional variants, required states,
specialized views, and capture-sheet outputs while deriving the existing
generic capture profile. No project-local profile persistence, visual-job
planning, provider execution, event-log change, SQLite migration,
dependency-graph mutation, or image generation is introduced.

- trees and plants;
- UI components;
- VFX concepts;
- pose and animation references.

### PR 43 — Visual-job planner

Status: implemented in the current slice. The pure `VisualJobPlanner` derives
required jobs from resolved capture profiles and explicit assets, validates
exact approved references, consumes the dependency graph for deterministic
ordering, groups jobs by exact profile revision, estimates provider-neutral
workload, and returns the published `visual-job-plan` v1 contract with ready or
blocked state. It does not persist plans, mutate the graph, write the event log
or SQLite, select project-local profiles, compile prompts, call a provider, or
execute image generation. The `visual-job-plan` schema, fixture, tests, and ADR
are published.

- required-job derivation;
- dependency ordering;
- batching;
- cost and workload estimates;
- ready and blocked states.

## Phase H — Codex and ImageGen

### PR 44 — Codex skill installer

Status: implemented in the current slice. The project-local `$ludowright` skill
is a versioned data package under `integrations/codex/`. The `codex skill`
commands install, update, verify, and remove it with checksums, framework
version checks, dry-run planning, Rich/JSON output, exclusive locking, atomic
writes, and rollback. Modified or unrelated files are never overwritten or
removed. The published `codex-skill-manifest` and `codex-skill-report` v1
contracts, schemas, fixtures, tests, and ADR are included. Orchestration policy,
receipts, reviews, and approvals remain separate PRs.

- project-local `$ludowright` skill;
- installation, update, verification, and removal;
- version checks.

### PR 45 — Codex orchestration policy

Status: implemented in the current slice. The versioned skill policy declares
ordered phases, validation commands, decision and approval checkpoints, and
durable-resume evidence. A pure planner consumes a read-only observation and
returns one deterministic next action; it does not execute providers or mutate
canonical state. The published `codex-orchestration-policy` and
`codex-orchestration-plan` v1 contracts, schemas, fixtures, tests, and ADR are
included. Provider execution, receipts, reviews, and specialist agents remain
separate concerns after this policy stage; they are implemented incrementally
by PR46, PR47, PR48, and PR49. Agent conformance evals are covered in PR50.

- inspect status first;
- ask only unresolved questions;
- record decisions;
- run validations;
- require approval checkpoints;
- resume safely.

### PR 46 — ImageGen job execution

Status: implemented in the current slice. The Codex integration consumes a
validated job selected from a ready visual-job plan and its matching compiled
prompt, creates a deterministic `imagegen-operation` contract, validates one
PNG per view, writes through the safe filesystem boundary, and rolls back
partial execution. Schema publication, fixture, focused security/concurrency
tests, ADR, and documentation are included. Generation receipts, output
references, checksums, and provider metadata remain PR47 responsibilities.

- translate a ready visual job into an ImageGen operation;
- enforce output path and one-view-per-image policy;
- record prompt and inputs.

### PR 47 — Generation receipts

Status: implemented in the current slice. ImageGen now persists one immutable
terminal receipt per execution attempt, deterministic candidate generated
references, prompt and operation fingerprints, provider/model/tool metadata,
canonical UTC timestamps, output checksums, dimensions, and bounded PNG
validation facts. Failed provider, validation, and write attempts roll back
partial operation artifacts before keeping a failed receipt; retries use
contiguous attempt numbers and `retry_of`. The additive receipt fields preserve
older v1 documents, and no SQLite migration or event-log projection is needed.
The receipt repository, contract fixture/schema, focused security/concurrency
tests, ADR, and documentation are included.

- checksums;
- model and tool metadata when available;
- references and prompt hash;
- timestamps;
- output validation.

### PR 48 — Review workflow

Status: implemented in the current slice. The `ludowright review` workflow
validates successful receipt-bound outputs, requires distinct reviewer and
producer identities, enforces human approval, projects revision-bound approval
and reference status, handles correction, rejection, and supersession, and
updates the canonical dependency graph and hash-chained event log. The
workflow uses the existing safe filesystem, structured repositories, locks,
optimistic graph persistence, deterministic IDs/paths, dry-run, idempotency,
and rollback. Actor fields are additive in the v1 review contract, and no
SQLite migration is required. Focused security, concurrency, rollback, CLI,
contract, and lifecycle tests plus ADR and command documentation are included.

- approve, approve with notes, correct, reject, supersede;
- reviewer separation;
- dependency invalidation.

### PR 49 — Codex specialist agents

Status: implemented in the current slice. The project-local skill revision 3
ships a validated `codex-agent-catalog` with nine data-defined specialist
profiles and one deterministic route per task. `CodexAgentRouter` consumes the
existing orchestration plan, fails closed before status inspection or when a
route/action/capability is incompatible, preserves human checkpoints, and
never grants approval authority. Schemas, fixtures, focused security and
determinism tests, ADR, and canonical contract documentation are included.

- interviewer;
- game-design architect;
- technical architect;
- asset planner;
- visual director;
- generation operator;
- consistency reviewer;
- quality auditor;
- release verifier.

### PR 50 — Agent eval suite

Status: implemented in the current slice. The offline table-driven suite covers
all nine published routes and verifies status-first routing, decision and
approval boundaries, exact approved-reference enforcement, prompt/receipt
lineage, selective regeneration without overwrite, and human review
projection. It uses temporary projects and an injected PNG provider, so it does
not call Codex, the network, or a real provider. The fixture, focused tests,
canonical quality documentation, and ATLAS updates are included. Full phase
execution and provider-backed model evaluation remain future work.

- state inspection;
- no decision reinvention;
- approved-reference enforcement;
- prompt receipt creation;
- selective regeneration;
- approval and safety rules.

## Phase I — Sheets, audits, and packages

### PR 51 — Image normalization

Status: implemented in the current slice. The `images normalize` command
accepts bounded local PNG, JPEG, and WebP inputs, applies EXIF orientation,
fits visible content to a deterministic canvas, and creates transparent,
neutral, thumbnail, and alignment-guide PNGs plus a versioned report. The
workflow uses Pillow only in infrastructure, shared project paths and locks,
atomic create-only writes, dry-run, exact-repeat idempotency, and rollback.
No approved reference, event log, SQLite state, or migration is changed;
technical-sheet composition remains PR52.

- dimensions;
- padding;
- orientation metadata;
- alignment guides;
- thumbnails;
- transparent and neutral backgrounds.

### PR 52 — Technical sheet assembly

Status: implemented in the current slice. The non-interactive `sheets
assemble` command consumes explicit requests, approved references, and exact
normalized PNG checksums. It loads the data-defined version 1 `minimal`
template and creates deterministic turnaround, component, prop, detail, or
scale sheets plus a `technical-sheet` provenance report. The workflow supports
human and JSON CLI output, dry-run, exact-repeat `unchanged`, create-only
conflict detection, project locking, atomic writes, and rollback of artifacts
created after a partial failure. Paths and symlinks use the shared filesystem
boundary. It does not mutate approvals, references, the event log, dependency
graph, or SQLite; package manifests and global audits remain later PRs.

- turnarounds;
- component and prop sheets;
- detail and scale sheets;
- deterministic layouts.

### PR 53 — Package manifest

- included files;
- checksums;
- source versions;
- licensing and provenance;
- missing or excluded items.

### PR 54 — Package builder

- safe ZIP generation;
- package index;
- release directory;
- reproducibility tests.

### PR 55 — Global project audit

- product, documents, assets, references, jobs, approvals, sheets, and package readiness;
- machine-readable report.

### PR 56 — Release verifier

- blocking gates;
- warning policy;
- release summary;
- signed or checksum-verifiable manifest preparation.

## Phase J — Examples and public beta

### PR 57 — Minimal example

A small project exercising initialization, documentation, assets, jobs, approval, sheet assembly, and packaging with fixture images.

### PR 58 — 2D example

A sprite-oriented game showing profile customization and non-3D asset workflows.

### PR 59 — Low-poly 3D example

A complete character and environment reference flow with segmented components.

### PR 60 — Modular environment example

Buildings, foliage, roads, sockets, modules, and connection rules.

### PR 61 — Installation and tutorial set

Linux, Windows, macOS, Codex skill, first project, character workflow, custom profile, troubleshooting, update, and uninstall.

### PR 62 — Public beta and 1.0 readiness

- clean-room installation tests;
- end-to-end validation;
- migration matrix;
- security review;
- documentation audit;
- beta feedback fixes;
- release candidate and stable release checklist.

## Cross-cutting requirements

Every PR must consider:

- typed public interfaces;
- deterministic behavior;
- tests appropriate to the risk;
- documentation and ATLAS updates;
- migration or compatibility impact;
- security and path safety;
- human and JSON CLI behavior;
- Codex behavior and evals when affected;
- provenance for generated outputs.

## Definition of 1.0 readiness

LudoWright 1.0 is ready only when a clean environment can install the package and skill, initialize a project, complete guided intake, generate modular documents, build an asset registry and ODS export, plan and record visual-generation jobs, approve references, assemble technical sheets, audit the project, and build a reproducible package without relying on hidden conversation state.
