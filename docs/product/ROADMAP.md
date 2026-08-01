# Product Roadmap

This roadmap describes product capability, not fixed dates. Minor-version boundaries may change when real project validation shows that a capability should move, but the dependency order should remain stable.

## 0.x — Build and stabilize the complete workflow

### 0.1 Foundation

- Python package and CLI entry point;
- repository standards, license, governance, contribution files;
- Ruff, mypy, pytest, pre-commit, and GitHub Actions;
- MkDocs documentation skeleton;
- stable logging and error model.

### 0.2 Project Core

- `ludowright init`;
- project manifest;
- filesystem layout;
- state store and event log;
- decisions and approvals;
- schema and template versioning;
- migrations, backup, and dry-run behavior;
- project status and structural audit.

### 0.3 Guided Documentation

- schema-driven interview engine foundation: published questionnaires, typed validation, safe dependencies, and answer provenance;
- deterministic pending-question calculation with blocked and not-applicable states;
- interview CLI with resumable canonical sessions, event auditing, and explicit skip/defer policy;
- deterministic, versioned document template engine with inheritance and project overrides;
- initial modular product-document set for vision, audience, pillars, loops, scope, risk, platform, and success;
- initial architecture and implementation document set for system overview, contracts, modules, UI/UX, implementation, quality, security, operations, ADRs, and plans;
- deterministic ATLAS index with canonical-source metadata, broken-link detection, and orphan detection;
- modular GDD and ATLAS generation;
- product, architecture, UI/UX, implementation, quality, security, production, ADR, and plan templates;
- incremental document updates and staleness detection.
- deterministic documentation audit for missing topics, duplicate canonical
  sources, explicit contradictions, and stale references.

The initial refresh slice uses explicit versioned requests and source hashes,
preserves manual sections, and reports affected documents. Automatic context
assembly from interview answers remains a later bounded capability.

### 0.4 Asset Registry

- canonical asset taxonomy and schema;
- data-defined initial families, subtypes, and naming policy;
- versioned YAML asset registry with create, update, list, inspect, archive, and validate commands;
- deterministic batch import/export with dry-run and rollback behavior;
- deterministic candidate discovery from game documentation with explicit confirmation;
- manual and guided asset creation;
- components, variants, states, priorities, and ownership;
- deterministic decomposition with prerequisite-asset dependency edges,
  guided corrections, and advisory capture-profile recommendations;
- YAML registry and derived ODS export (implemented through PR35, including
  overview, decomposition, reference-availability, status, priority, and
  dependency views);
- deterministic orphan and completeness audits (implemented through PR36;
  visual references, jobs, approvals, sheets, and package readiness remain
  later audit scopes).

### 0.5 Visual Foundation

- versioned visual-bible schema for shared shape, proportion, palette, material,
  lighting, camera, detail, budget, and positive/negative constraints
  (implemented through PR37);
- provider-neutral layered prompt compilation, approved-reference resolution,
  structured positive/negative constraints, and deterministic prompt hashing
  (implemented through PR38);
- capture-profile model and inheritance;
- initial data-defined humanoid and wearable profile with neutral body-base
  policy, per-view requirements, isolated categories, and assembled outputs
  (implemented through PR39; project-local profile persistence remains later);
- initial creature and animal profiles for quadrupeds, birds, fish, insects, and
  fantasy creatures with anatomy-specific views, components, states, and
  outputs (implemented through PR40; project-local profile persistence remains
  later);
- initial environment and hard-surface profiles for props, vehicles, buildings,
  modular kits, and interiors with directed connection matrices (implemented
  through PR41; project-local profile persistence remains later);
- initial foliage, UI, VFX, and animation profiles (implemented through PR42);
- visual-job planning and profile-aware job derivation (implemented through
  PR43; project-local profile selection and execution remain later).

### 0.6 Codex and ImageGen Workflow

- versioned project-local `$ludowright` skill with install, update, verification,
  removal, checksums, dry-run, and rollback (implemented through PR44);
- declarative Codex orchestration policy with status-first inspection, unresolved
  question handling, decision recording, validation gates, human approval
  checkpoints, and durable resume planning (implemented through PR45);
- provider-bound ImageGen execution with deterministic operation manifests,
  one PNG per view, safe paths, atomic writes, dry-run, conflict detection, and
  rollback (implemented through PR46);
- Codex-specific agents and routing (versioned nine-agent catalog and pure
  deterministic router implemented through PR49);
- offline specialist-agent conformance evals for status, decisions, references,
  receipts, selective regeneration, approval, and safety (implemented through
  PR50);
- approved-reference selection;
- prompt, input, output, and checksum receipts (receipts, candidate generated
  references, metadata, timestamps, and PNG validation implemented through
  PR47);
- retries, superseding, and selective correction (receipt retries through PR47;
  review correction and supersession through PR48);
- human approval checkpoints with reviewer separation and dependency
  invalidation (implemented through PR48).

### 0.7 Sheets and Packages

- image normalization and alignment (initial deterministic workflow implemented
  through PR51);
- turnarounds, component sheets, prop sheets, detail sheets, and scale sheets
  (initial deterministic assembly implemented through PR52; contact-sheet
  packaging remains later);
- deterministic assembly from approved images (implemented through PR52);
- package manifest inventory, checksums, source versions, provenance, and
  exclusions (manifest implemented through PR53; archive indexes and ZIP output
  implemented through PR54; global readiness audit implemented through PR55;
  release verification implemented through PR56; digital signing and remote
  publication remain outside this slice);
- release-readiness checks (implemented through PR56).

### 0.8 Guided Orchestration

- project orchestrator;
- interviewer, game-design, technical-architecture, asset-planning, visual-direction, generation, consistency-review, quality-audit, and release-verification roles;
- resumable phases and recommended next actions;
- bounded parallel delegation;
- complete phase execution and provider-backed agent evaluation.

### 0.9 Public Beta

- clean installation path;
- complete public documentation;
- minimal example project (implemented through PR57), 2D sprite example
  (implemented through PR58), and low-poly 3D example (implemented through
  PR59), and modular-environment example (implemented through PR60);
- end-to-end tests and migration tests;
- usability and compatibility fixes from real projects;
- release candidate.

## 1.0 — Stable production framework

The first stable release supports the complete sequence:

```text
idea → intake → documentation → asset registry → visual bible
→ visual jobs → ImageGen → approval → technical sheets → audit → package
```

Release gates include stable schemas, tested migrations, usable CLI without Codex, functional Codex skill, traceable generation, valid ODS export, complete package manifests, documentation, real examples, and no known data-loss defects.

## 1.x — Expand practical production coverage

### 1.1 Expanded asset families

Richer profiles for animals, birds, fish, insects, creatures, vehicles, buildings, interiors, foliage, terrains, UI, VFX, and animation poses.

### 1.2 Template packs

Data-driven packs for cozy, farming, shop simulation, survival, RPG, metroidvania, strategy, visual novel, horror, isometric, low-poly 3D, and 2D sprite projects.

### 1.3 Production intelligence

Complexity estimates, asset budgets, critical dependencies, scope risk, feature-creep detection, milestone completeness, and cut recommendations.

### 1.4 Visual quality assistance

Scale normalization, silhouette and palette comparisons, background checks, overlays, side-by-side reports, and assisted visual review without claiming geometric reconstruction.

### 1.5 GitHub workflow

Issue and milestone generation, PR plans, CI validation, documentation-impact checks, release notes, and artifact publication.

### 1.6 Team workflow

Owners, reviewers, approvals, handoffs, blockers, area reports, conflict handling, and small-team workflows while retaining Git as the source of truth.

### 1.7 Localization

English and Brazilian Portuguese UI and templates, controlled translations, glossaries, neutral IDs, and cross-language divergence checks.

### 1.8 Extension SDK

Public Python API, custom validators, generators, asset families, capture profiles, template packs, plugins, hooks, and permission declarations.

### 1.9 Stabilization

Deprecation cleanup, API hardening, performance work, large-project testing, migration quality, and preparation for the next major architecture.

## 2.x — Production graph and handoffs

### 2.0 Production Graph

A queryable graph connecting documents, mechanics, assets, references, prompts, decisions, risks, code, tests, and milestones. It supports impact analysis and compact context packs for Codex.

### 2.1 DCC handoff

Blender-oriented manifests and helper scripts for collections, names, scale, pivots, sockets, materials, LODs, collision expectations, and modeling checklists.

### 2.2 Engine handoff

Export contracts and validation for Godot, Unity, Unreal, and custom engines, including paths, import settings, scenes or prefabs, resources, and metadata.

### 2.3 Production tracking

Milestones, capacity, estimates, blockers, dependencies, asset progress, and production reports connected to canonical project content.

### 2.4 Visual variant systems

Composable characters, garments, modular kits, seasonal variants, damage states, growth states, palette variants, skins, and compatibility matrices.

### 2.5 Automated project audits

Deep checks for contradictions, undocumented mechanics, missing implementation, unlicensed references, irreproducible prompts, missing tests, orphan outputs, and ignored risks.

## 3.0 — LudoWright Studio

An optional desktop interface over the same core may provide:

- project navigation;
- visual asset and reference browsing;
- job and approval dashboards;
- side-by-side visual review;
- technical-sheet layout;
- interactive production graph;
- production dashboards;
- Codex-assisted workflows.

The Studio must never fork or replace core behavior.

## Explicitly deferred

The roadmap does not commit to:

- autonomous approval of canonical visual references;
- exact 3D reconstruction from generated views;
- a hosted multi-tenant service;
- broad multi-provider AI support;
- built-in game-engine or modeling functionality.

These require separate evidence, security analysis, and product decisions.
