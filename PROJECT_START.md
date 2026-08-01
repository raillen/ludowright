# Project Start

## What LudoWright is

LudoWright is a Codex-native framework with a deterministic Python core. It turns game ideas and decisions into structured documentation, asset inventories, visual-reference jobs, approvals, technical sheets, audits, and production packages.

## Product promise

A user should be able to return to a repository after a long break and answer, without relying on chat history:

- what the game is;
- what has been decided;
- which documents are canonical;
- which assets are required;
- which references are approved;
- what is blocked or missing;
- what changed and what it affects;
- whether the project is ready for a milestone or package.

## Architectural stance

LudoWright has three distinct layers:

1. **Core and application:** deterministic domain rules, schemas, workflows, state, validation, migrations, and packaging.
2. **Interfaces and infrastructure:** CLI, filesystem, SQLite, YAML, ODS, Git, and image assembly.
3. **Codex adapter:** skill, agents, hooks, prompt compilation, ImageGen execution, and guided conversations.

The Codex layer may orchestrate the framework, but must not become its database or sole source of business rules.

## Delivery sequence

Development proceeds in this order:

1. repository foundation;
2. domain and schemas;
3. project state and migrations;
4. CLI contracts;
5. guided documentation;
6. asset registry;
7. visual bible and capture profiles;
8. visual jobs, provenance, and approvals;
9. Codex skill and ImageGen workflow;
10. deterministic sheet assembly;
11. audits and packaging;
12. real project examples and public beta.

## Current phase

The repository has completed the foundation and core domain/contract slices and is now in the Codex integration, derived-artifact, and packaging phase. Guided documentation includes the published v1 questionnaire and session contracts, immutable question/session rules, a resumable `interview` CLI with event-log auditing, a deterministic versioned document template engine, the initial product and architecture document sets, deterministic ATLAS generation with source/link integrity checks, incremental document refresh with source hashes, stale planning, manual-section preservation, rollback, and a declarative documentation audit. The initial data-driven asset taxonomy, v1 YAML registry commands, deterministic Markdown asset discovery with explicit confirmation, deterministic asset decomposition with canonical prerequisite graph edges, deterministic derived ODS asset workbook export, deterministic read-only asset completeness audits, the v1 project-level visual bible contract, the provider-neutral deterministic prompt compiler, data-defined humanoid/wearable, creature/animal, environment/hard-surface, and visual-specialty profiles, the pure deterministic visual-job planner, the versioned project-local `$ludowright` skill installer, its status-first orchestration policy, the provider-bound ImageGen operation executor, durable generation receipts, candidate generated references, the canonical visual review workflow, the versioned specialist-agent catalog and router, the offline specialist-agent conformance eval suite, deterministic image normalization, deterministic technical-sheet assembly, the v1 deterministic package manifest, and the reproducible package builder are now implemented; global audit, release verification, examples, and beta remain later slices in `docs/plans/IMPLEMENTATION_PLAN.md`.

## Navigation

Use `docs/ATLAS.md` as the canonical map of product, architecture, implementation, quality, security, governance, and operations documentation.
