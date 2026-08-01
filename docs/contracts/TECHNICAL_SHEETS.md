# Technical Sheet Contract

## Purpose

`technical-sheet` v1 describes one deterministic, derived PNG assembled from
approved visual references and a versioned data template. The assembler is a
local application workflow; it does not replace references, approvals, the
event log, the dependency graph, or the SQLite state index.

The published contracts are:

- `technical-sheet-template` — versioned layout data;
- `technical-sheet-request` — explicit inputs for one sheet;
- `technical-sheet` — output provenance, dimensions, checksums, and placements.

Their schemas and compatibility fixtures are published under `schemas/v1/` and
`tests/fixtures/contracts/v1/`.

## Request

A request identifies a sheet, the exact template revision, one of the supported
sheet kinds, and at least one input:

```text
turnaround | component | prop | detail | scale
```

Each input contains a stable ID, human label, approved `reference_id`, a
repository-relative `.png` path, and the exact SHA-256 of that PNG. Input IDs,
reference IDs, and image paths are unique within a request. The request is
validated before any output directory is created.

The reference document must be in `approved` status and contain an approval
ID. PNG validation is independent of that status: the file must be a regular,
bounded, non-animated PNG whose checksum matches the request.

## Templates

Templates are package data, not Python branches. Each template has an ID,
integer version, background color, and one layout declaration for every
canonical sheet kind in the fixed order above. A layout declares:

- semantic layout (`grid` or `turnaround` in the initial pack);
- number of columns;
- cell width and height;
- margin, gutter, and label height.

The initial `minimal` template is version 1. It is intentionally small and
audit-friendly. Future templates can add data packs without changing the
renderer or the persisted report contract.

## Output

The assembler creates exactly two files beneath the requested output directory:

```text
sheet.png
technical-sheet.json
```

The report records the request path and digest, template revision, selected
layout, canvas geometry, every input fact, deterministic placement order, and
the output PNG checksum and dimensions. The report is written last, so its
presence is the success marker for the pair of artifacts.

## Determinism and idempotency

The renderer uses fixed geometry, fixed RGB background composition, stable
input order, the Pillow default font, and fixed PNG encoding options. An exact
repeat returns `unchanged` when both output bytes and the canonical report
match. A partial target or any changed target is a `conflict`; existing files
are never silently overwritten.

`--dry-run` performs request, approval, path, PNG, checksum, template, and
render validation but creates no directory or file. Dry-run reports the same
planned paths and report data as the corresponding real operation.

## Safety and failure behavior

- paths are repository-relative and must pass the shared filesystem boundary;
- traversal and symlink components are rejected;
- inputs and outputs are bounded by the existing filesystem limits;
- the project lock `technical-sheet-assembly` serializes cooperating runs;
- writes use the shared atomic filesystem adapter;
- a failure after the first output write removes only files and directories
  created by this operation;
- if cleanup itself fails, the service raises `TechnicalSheetRollbackError`
  while preserving the original failure as its cause;
- the workflow is local-first and makes no network or provider call.

The workflow does not mutate the event log, dependency graph, SQLite state,
reference documents, approval documents, or normalized input images. Those
integrations belong to later audit/package work when their contracts are
available.

## Compatibility

This is a new additive v1 publication. It requires no migration and does not
change existing project files. A future incompatible layout or report change
requires a new schema version or an explicit migration. The renderer currently
produces PNG only and does not infer geometry from opaque images.
