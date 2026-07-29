# Product Vision

## Vision

Enable an individual creator or small game team to turn an idea into a structured, traceable, production-ready project without relying on fragmented chats, lost prompts, or stale monolithic documents.

## Mission

LudoWright provides a local-first source of truth for game design, architecture, visual direction, assets, references, production decisions, quality, and release readiness, operated through a deterministic Python core and a guided Codex workflow.

## Primary users

- independent game developers;
- small studios without dedicated production and documentation staff;
- game designers translating ideas into implementable specifications;
- modelers and technical artists receiving structured reference packages;
- Codex users who want repeatable, resumable project workflows.

Secondary users include students, educators, game-jam teams, mod creators, simulator developers, and interactive-visualization teams.

## Core jobs to be done

LudoWright must help users answer:

1. What are we building and why?
2. Which decisions are canonical?
3. Which assets, variants, views, states, and dependencies are required?
4. Which references are approved, rejected, obsolete, or missing?
5. Which documents and outputs became stale after a change?
6. What remains before production, a milestone, or a release package?

## Product pillars

### Structured planning

Use modular canonical documents, explicit decisions, schemas, and dependency relationships instead of one giant GDD.

### Asset production intelligence

Discover, classify, decompose, prioritize, validate, and export assets from a canonical structured registry.

### Controlled visual generation

Generate one technical reference per view or component, reuse approved visual references, record provenance, and assemble technical sheets deterministically.

### Guided Codex operation

Let Codex interview the user, inspect project state, execute bounded workflows, delegate specialist reviews, and resume without depending on chat history.

### Auditable delivery

Produce manifests, checksums, reports, ODS inventories, technical sheets, and packages that can be understood outside the originating conversation.

## Non-goals

LudoWright is not:

- a game engine;
- a DCC or modeling tool;
- a model-3D generator;
- a promise of geometrically exact multi-view blueprints;
- a replacement for Git, Blender, Maya, Godot, Unity, Unreal, Jira, or Linear;
- a mandatory cloud service;
- a system that approves generated work without human review;
- a multi-provider AI abstraction in the initial product generation.

## Product principles

1. Repository state outranks chat state.
2. Deterministic code owns paths, IDs, versions, validation, and packaging.
3. Human approval is required for canonical visual references and major decisions.
4. Every generated artifact must be traceable to inputs, prompts, versions, and checksums.
5. Regenerate only affected outputs.
6. Structured data is canonical; ODS files and rendered documents are derived views.
7. Technical sheets are assembled from approved images, never hallucinated again as a new composite.
8. Safety and representation constraints belong in schemas and policies, not hidden prompt prose.
9. The core remains usable without Codex; Codex provides the guided experience.
10. Every new abstraction must prove value in real game projects.

## Product boundaries for visual references

For humanoid modeling references, the default body presentation is a neutral bodysuit, fitted neutral base clothing, or technical mannequin. A full underside view is not universally required; profiles should request technically useful details such as shoe soles, feet, attachment points, or underside components instead.

Image-generated references are treated as assisted modeling references, not CAD projections. Dimensions, pivots, sockets, material rules, and scale must also exist as structured data.

## Success measures

A successful stable release allows a new user to:

- install the CLI and Codex skill from public documentation;
- initialize a project without editing schemas manually;
- complete a guided intake and generate modular documentation;
- build and export an asset registry;
- define a visual bible and capture profiles;
- create and execute traceable visual-generation jobs;
- approve references and assemble technical sheets;
- run an audit and produce a reproducible package;
- resume the workflow later without the original conversation.

## Long-term direction

The long-term product may add a production graph, DCC and engine handoffs, extension APIs, team workflows, production tracking, and an optional desktop Studio. These remain layers over the same core rather than separate implementations.