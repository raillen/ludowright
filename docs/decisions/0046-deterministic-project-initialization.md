# ADR 0046: Deterministic Project Initialization

## Status

Accepted and implemented in the project-initialization slice.

## Context

The repository already provides safe project-relative paths, atomic structured
documents, an exclusive project lock, a hash-chained event log, a dependency
graph repository, and a rebuildable SQLite state store. A new project needs one
small orchestration boundary that composes those components without creating a
second persistence model or leaving a marker that looks valid after a partial
failure.

## Decision

Implement `ludowright init PATH --name NAME` as a create-only application use
case with these rules:

- starter layouts are versioned JSON data validated by `template.schema.json`;
- the `minimal` template is the only initial template;
- the ProjectId is derived by the existing domain slugifier;
- missing and empty directories are allowed, while occupied targets and
  existing projects return a conflict;
- `--dry-run` performs validation and produces the complete plan without
  filesystem mutation;
- the target lock, atomic writes, existing path checks, and shared repository
  adapters are reused;
- the event log starts as an empty valid log, the graph contains the project
  node at revision one, and SQLite is initialized at the current schema;
- the project marker is the final canonical file written;
- partial failures remove only known generated artifacts and empty directories,
  preserving unknown content and the original exception cause.

The command supports both Rich human output and the published `cli-response`
JSON envelope. Initialization is deliberately non-interactive when the
required name is supplied; prompting is not part of the core use case.

## Compatibility and migration

The optional `template` field in `project.schema.json` records template
provenance without invalidating existing v1 manifests that omit it. The new
`template.schema.json` is published at schema version 1. No SQLite, event-log,
dependency-graph, or project migration is required. The state store continues
to use the current schema version 2.

## Consequences

Project creation has a deterministic identity, layout, manifest, event-log
starting point, and graph starting point. The SQLite checkpoint includes the
normal state-store update timestamp because SQLite is derived operational state;
canonical project facts remain in the manifest and structured repositories.
Create-only semantics make retries explicit and avoid silently treating a
partially initialized or user-owned directory as safe to reuse.
