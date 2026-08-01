# ADR 0025: Deterministic Derived Asset ODS Export

## Status

Accepted

## Context

The asset registry and dependency graph are canonical structured documents.
Planning work needs a workbook view, but an ODS file must not become a second
mutable database or silently overwrite an approved artifact. ODFPy also emits
runtime-dependent ZIP metadata unless the package is normalized explicitly.

## Decision

Implement `assets export-ods` as a derived, create-only projection with these
boundaries:

- the application service reads only the existing asset registry and
  dependency-graph repositories;
- the workbook layout is versioned JSON data, not Python template constants;
- the report is a published Pydantic contract with source and output hashes;
- ODS ZIP entries are canonicalized and validated before atomic creation;
- normal exports coordinate the existing decomposition and registry locks and
  use a separate workbook lock for the output target;
- dry-run renders in memory and has no filesystem side effects;
- an existing target, unsafe path, or unsafe symlink is rejected;
- unavailable visual-reference details are represented explicitly rather than
  inferred or duplicated from conversation state.

## Consequences

The workbook can be regenerated deterministically from canonical project state
and audited by its source digest. The current project state-store schema and
event log remain unchanged. ODS export does not yet provide reference
metadata, capture profiles, audits, or write-back editing; those belong to
later bounded roadmap steps.

The runtime adds ODFPy, currently constrained to the published 1.4.x line.
Future template additions require a versioned contract and compatibility
review.

## Rejected alternatives

- Storing workbook rows in SQLite would duplicate canonical structured data.
- Overwriting one fixed workbook would destroy approved artifacts and make
  reruns unsafe.
- Embedding per-template branching in Python would make future template packs
  harder to version and audit.
