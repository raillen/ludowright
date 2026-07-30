# ADR 0018 — Deterministic ATLAS Index and Integrity Report

- **Status:** Accepted
- **Date:** 2026-07-31
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `ATLAS.md`, `JSON_SCHEMAS.md`, `PROJECT_FILESYSTEM.md`, `STRUCTURED_REPOSITORIES.md`, `CLI.md`

## Context

The repository has a human-maintained `docs/ATLAS.md`, but no machine-readable
index of canonical sources. Link errors, documents omitted from navigation, and
source relationships could therefore remain unnoticed until a documentation
build or a human review.

The first implementation must inspect local Markdown without fetching external
websites, following symlinks, or replacing canonical documents as a side effect.

## Decision

LudoWright stores versioned canonical-source metadata in `docs/atlas.json`
under the published `atlas-metadata` contract. `AtlasGenerator` reads that
metadata through the strict structured repository and scans Markdown through a
bounded, symlink-rejecting documentation filesystem adapter.

The generator returns a versioned `atlas-report` containing:

- a sorted document index;
- exact metadata bytes digest;
- local relative links;
- broken-file, broken-anchor, unsafe-path, and missing-source findings;
- sorted Markdown files absent from metadata as orphan documents.

External URI links are not dereferenced. Relative links must resolve within the
documentation root. Generation and `--check` are read-only; writing or replacing
`docs/ATLAS.md` requires a separate explicit workflow.

## Alternatives considered

### Parse `ATLAS.md` as the only source

Rejected. A presentation document is not a sufficiently strict machine-readable
source for ownership, canonical-source relationships, and stable diagnostics.

### Add front matter to every Markdown file

Deferred. It would spread metadata across dozens of documents and create noisy
cross-cutting edits. A versioned sidecar keeps the initial contract auditable and
can be migrated to front matter later if authoring evidence justifies it.

### Dereference external links during generation

Rejected. Network availability, credentials, and remote content would make local
validation nondeterministic and unsafe.

### Rewrite the canonical ATLAS during analysis

Rejected. A read-only integrity check must not overwrite approved documentation;
explicit persistence needs its own conflict, lock, and review policy.

## Consequences

Positive:

- missing and orphaned documentation becomes machine-detectable;
- reports are stable in CI, CLI, and Codex contexts;
- source metadata remains explicit and reviewable;
- local analysis remains offline and bounded.

Costs:

- adding a canonical Markdown file requires updating `docs/atlas.json`;
- the sidecar and generated report are additional versioned contracts;
- heading-anchor validation implements a deterministic subset of Markdown slug
  behavior and must evolve deliberately if the documentation renderer changes.

## Compatibility

The `atlas-metadata` and `atlas-report` schemas are published as v1 with
fixtures. Changes to path rules, source ownership, finding reasons, or output
ordering require compatibility analysis, schema/fixture updates, and a new ADR
when the interpretation changes.
