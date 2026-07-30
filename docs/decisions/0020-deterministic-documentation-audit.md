# ADR 0020 — Deterministic documentation audit

- Status: accepted
- Date: 2026-07-30
- Decision owners: LudoWright maintainers

## Context

ATLAS can already detect missing sources, broken links, and orphan Markdown
files. The roadmap also requires a bounded audit for missing canonical topics,
duplicate sources, contradictions, and stale references. A generic language
interpretation layer would be nondeterministic and would make the quality gate
difficult to reproduce offline.

## Decision

Add a read-only `ludowright docs audit` command. Its policy is a versioned JSON
document with explicit required topics, exact phrase-pair contradiction rules,
and deprecated-path replacements. The application reuses ATLAS and the safe
documentation filesystem, returning a published report contract and stable
Markdown projection.

The audit does not automatically rewrite documentation. A contradiction is
only reported when both exact phrases configured by maintainers are present;
the implementation is not a general semantic contradiction detector.

## Consequences

- Documentation quality can run offline in the normal quality gate.
- Policy changes are reviewable as data and have deterministic digests.
- Duplicate canonical metadata is visible before it creates competing truth.
- The system deliberately does not infer claims or propose unreviewed edits.
- Future semantic or migration-aware audits can add versioned policy rules
  without changing the ATLAS contract.
