# ADR 0042: Deterministic Package Manifest Boundary

## Status

Accepted and implemented in PR53.

## Context

LudoWright needs a reviewable inventory before it creates ZIP packages or
claims release readiness. The inventory must identify exact files, source
revisions, checksums, provenance, licensing declarations, and known omissions.
It must also be safe for repositories containing ordinary case-sensitive names
such as `README.md` while preserving the existing filesystem and structured
document boundaries.

## Decision

Introduce a versioned `package-manifest` Pydantic contract and a derived
`PackageManifestService`.

The service:

1. scans only one resolved project root;
2. rejects symlinks, special files, traversal, path escapes, and bounded-scan
   violations;
3. includes regular project files with size and SHA-256 checksums;
4. validates known project, event-log, graph, registry, state, and visual
   reference sources through existing adapters;
5. records provenance and license summaries from visual-reference contracts;
6. excludes transient/tool-cache paths, rebuildable SQLite state, and its own
   output explicitly;
7. writes one canonical JSON artifact atomically under a project lock;
8. never replaces a different existing manifest and treats exact repeats as
   unchanged;
9. keeps dry runs read-only and does not mutate canonical project state.

The manifest path stored in the contract uses a package-specific portable path
validator that accepts case-sensitive filenames. The CLI output path remains a
shared `RepositoryPath`, preserving the established safe atomic-write API.

## Alternatives considered

### Reuse `RepositoryPath` for every inventory entry

Rejected because it rejects valid case-sensitive repository documents and would
make package coverage depend on a lowercase naming policy that the package
format does not require.

### Include SQLite and lock files in package contents

Rejected because SQLite is a rebuildable derived index and locks are transient
coordination state. Both are reported explicitly instead.

### Build the ZIP in the same stage

Rejected to keep the manifest independently reviewable and to separate
inventory determinism from archive writer and release-directory policy in PR54.

## Compatibility and migration

This adds the published `package-manifest` v1 schema and fixture. It does not
change existing persisted project contracts, event-log records, graph records,
or SQLite schema version 2. No migration is required. Future incompatible
manifest semantics require a new schema version and an explicit migration
policy.

## Consequences

Package builders can consume a stable, checksum-verifiable input without
reimplementing path or provenance rules. The manifest is intentionally not a
signature and does not certify release readiness; those responsibilities remain
with later builder, audit, and verifier stages.
