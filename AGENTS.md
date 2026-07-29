# LudoWright Agent Guide

## Start here

Read these files before making changes:

1. `PROJECT_START.md`
2. `docs/ATLAS.md`
3. the canonical document for the area being changed
4. relevant ADRs and implementation plans

## Product boundary

LudoWright is a local-first, repository-native framework for planning, documenting, visualizing, validating, and packaging game projects through Codex.

It is not a game engine, DCC application, 3D model generator, project-management replacement, or cloud-only platform.

## Canonical architecture

- Domain rules belong in `src/ludowright/domain/`.
- Use cases and orchestration belong in `src/ludowright/application/`.
- CLI presentation belongs in `src/ludowright/cli/`.
- Filesystem, SQLite, ODS, image processing, and Git adapters belong in `src/ludowright/infrastructure/`.
- Codex-specific integration belongs in `integrations/codex/`.
- Templates and profiles are data, not embedded Python constants.

The core must not depend on Codex-specific prompts or tools.

## Required engineering rules

- Python 3.12 or newer.
- Fully typed public interfaces.
- Pydantic models at external data boundaries.
- Deterministic paths, IDs, manifests, and outputs.
- Human and JSON output modes for CLI commands.
- `--dry-run` for destructive or migratory operations.
- No important state may exist only in a model conversation.
- Never overwrite approved artifacts silently.
- Store provenance for generated documents and visual references.
- Keep spreadsheets derived from canonical structured data.

## Documentation rules

- `docs/ATLAS.md` is the main navigation map.
- Each subject has one canonical source.
- Architecture describes the current system.
- ADRs record decisions and rationale.
- Plans describe bounded implementation work.
- Update documentation in the same PR as behavior changes.
- Avoid monolithic GDDs or duplicated specifications.

## Visual-generation rules

- Generate one technical view per image.
- Use approved references whenever available.
- Save prompts, reference checksums, job metadata, and output checksums.
- Technical sheets are assembled deterministically from approved images.
- Do not regenerate a contact sheet with ImageGen.
- Body-base references use neutral bodysuits, fitted neutral clothing, or technical mannequins.
- Never infer that image references are geometrically exact blueprints.

## Validation

Before completing a change, run the relevant subset of:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

When schemas, templates, manifests, or CLI contracts change, add contract or snapshot tests.

## Pull requests

- Keep PRs small and independently reviewable.
- Do not combine unrelated refactoring and features.
- Include tests, documentation, migration notes, and risks.
- Create an ADR for decisions that change architecture, schemas, compatibility, security, or extension boundaries.
- Prefer squash merging.

## Definition of done

A change is complete only when code, tests, documentation, examples, schemas, migrations, changelog impact, and Codex behavior have been considered.