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

The repository is in **Project Core**. The CLI foundation and the decision and
approval governance slice are implemented; project initialization, status, and
structural audit remain separate lifecycle slices in the ordered PR plan.

Governance quick start:

```bash
ludowright decision record ./my-game --id camera-choice --title "Câmera isométrica"
ludowright decision list ./my-game
ludowright approval request ./my-game --id front-review \
  --subject-kind reference --subject-id maya-front --revision sha256:abc123
```

See [`docs/commands/GOVERNANCE.md`](docs/commands/GOVERNANCE.md) for the
complete command and failure contract.

## Navigation

Use `docs/ATLAS.md` as the canonical map of product, architecture, implementation, quality, security, governance, and operations documentation.
