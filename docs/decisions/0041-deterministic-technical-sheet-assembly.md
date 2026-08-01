# ADR 0041: Deterministic Technical Sheet Assembly

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `TECHNICAL_SHEETS.md`, `IMAGE_NORMALIZATION.md`, `CAPTURE_PROFILES.md`, `REFERENCES_AND_VISUAL_JOBS.md`, `PROJECT_FILESYSTEM.md`, `CLI.md`

## Context

Capture profiles declare technical-sheet needs, and the visual review workflow
now produces approved references. The next bounded step needs to turn explicit
approved PNG inputs into auditable sheets without introducing provider state,
layout logic hidden in prompts, or destructive regeneration.

## Decision

1. Define `technical-sheet-template`, `technical-sheet-request`, and
   `technical-sheet` as published v1 Pydantic contracts with fixtures and JSON
   Schemas.
2. Store the initial `minimal` layout as package JSON data and require one
   versioned layout declaration for each canonical sheet kind.
3. Keep Pillow inside infrastructure. The application service validates the
   request, approved reference status, PNG checksum, and template before
   rendering, then persists the PNG and report through the shared filesystem
   boundary.
4. Use fixed geometry, input order, background, font, and PNG encoding for
   deterministic output. Treat exact repeats as `unchanged` and all partial or
   divergent targets as conflicts.
5. Use the existing project lock, atomic writes, create-only targets, dry-run,
   and rollback. The report is written last and acts as the success marker.
6. Keep sheets derived. This stage does not mutate references, approvals, the
   event log, dependency graph, or SQLite state.

## Alternatives considered

### Put layout rules in Python

Rejected: it would make each new template a code change and obscure the
versioned compatibility boundary. Data-defined layouts preserve a stable
renderer and allow future packs.

### Re-render or overwrite existing sheets

Rejected: an existing artifact may be manually reviewed or included in another
workflow. Exact-byte idempotency is safe; divergence must be explicit.

### Assemble from unapproved references

Rejected: technical sheets are production-facing derived artifacts and must
retain the human approval boundary established by the visual review workflow.

## Consequences

### Positive

- sheets are reproducible from explicit request files and checksums;
- output placement and provenance are inspectable without opening the image;
- templates can expand as data without branching the renderer;
- failures do not leave a successful-looking report behind;
- the stage is independent of providers, network access, SQLite migrations, and
  package ZIP policy.

### Negative

- the initial renderer supports PNG only and uses a built-in font;
- no interactive layout editing or visual review UI exists;
- a request must be prepared explicitly and reference approval must already
  exist;
- sheet outputs are not yet included in release packages or global audits.

## Compatibility and migration

This is an additive v1 contract publication. Existing project formats,
event-log records, dependency-graph files, SQLite tables, and migrations are
unchanged. PR53 may consume the report and output as package inputs without
changing this contract.
