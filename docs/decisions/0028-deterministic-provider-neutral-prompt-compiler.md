# ADR 0028: Deterministic Provider-Neutral Prompt Compiler

- Status: accepted
- Date: 2026-08-01
- Scope: visual prompt compilation

## Context

The visual bible now publishes shared visual direction and positive/negative
constraints, while approved references already carry exact content revisions.
The next visual-foundation slice needs to combine those inputs into a prompt
that can be reviewed, hashed, and later consumed by a visual-job planner. A
provider-specific request would couple the core to ImageGen details before
profiles and execution contracts exist. A general-purpose template language
would also enlarge the trust boundary for project-controlled prompt content.

## Decision

Implement a pure application service over immutable domain values:

1. prompt templates are versioned JSON package data;
2. each template declares ordered positive or negative layers;
3. rendering uses a small allow-list of named placeholders and no expression
   evaluation;
4. reference resolution requires explicit IDs, approved status, exact target
   equality, and preserves each reference `content_revision`;
5. output is a strict `compiled-prompt` v1 contract;
6. the SHA-256 hash is computed from a canonical payload containing every
   meaningful input except the hash itself;
7. no provider, filesystem, persistence, image, or CLI operation is part of
   this slice.

The first package template is `minimal`. It is intentionally provider-neutral
and uses the same output for human review, future job planning, and contract
fixtures.

## Consequences

Positive consequences:

- prompt compilation is reproducible and testable without network access;
- approved-reference provenance is bound into the compiled identity;
- template expansion does not require Python changes;
- later providers can consume a stable core result without owning domain rules.

Trade-offs:

- the initial placeholder vocabulary is intentionally small;
- target display uses canonical IDs because asset naming/display contracts are
  outside this slice;
- custom project templates are not supported yet, so package data remains the
  trusted template boundary.

## Compatibility

This ADR adds only the v1 `prompt-template` and `compiled-prompt` contracts.
Existing visual reference, visual job, event-log, dependency-graph, SQLite,
and filesystem formats remain unchanged. Changing the placeholder vocabulary,
hash payload, or required fields requires a new contract/ADR review and an
explicit compatibility decision.
