# Package Manifest Contract

## Purpose

The `package-manifest` contract is the deterministic inventory boundary between
the repository-native project and the package builder implemented in PR54. It
describes what a package would contain without creating a ZIP archive.

The published v1 schema is:

```text
schemas/v1/package-manifest.schema.json
```

The manifest is a derived artifact. It does not replace the project marker,
event log, dependency graph, or SQLite state store.

## Contents

Each manifest records:

- the stable package and project IDs;
- the relative output path;
- every included regular file, byte size, and SHA-256 checksum;
- versions and checksums for known structured sources;
- visual-reference provenance, approval status, source URI, creator, and
  declared license label;
- a distinct license summary grouped by reference ID;
- known missing optional sources;
- explicit exclusions for transient files, tool caches, rebuildable SQLite
  state, and the manifest output itself.

The persisted manifest never contains an absolute machine path or a timestamp.
File entries are sorted by portable relative path, which makes repeated scans
byte-for-byte reproducible when project inputs are unchanged.

## Path policy

Manifest entries use a package-specific portable path boundary. It accepts
case-sensitive names such as `README.md` while rejecting absolute paths,
backslashes, traversal, empty segments, trailing dots, non-ASCII names, and
Windows device names. The scanner rejects symbolic links and special files
before hashing.

The command output path is still parsed by the shared `RepositoryPath`
boundary, so generated manifest paths use the existing lowercase project path
convention. This keeps atomic writes and lock ownership in the shared
filesystem adapter while allowing inventories to describe ordinary repository
documents.

## Source policy

The scanner includes canonical project files, documentation, source images,
derived visual artifacts, and other regular project files. It excludes:

```text
.git/                       transient
.venv/                      transient
__pycache__/                transient
.pytest_cache/              tool-cache
.mypy_cache/                tool-cache
.ruff_cache/                tool-cache
build/ dist/ site/          transient
.ludowright/locks/          transient
.ludowright/state.sqlite3*  derived-state
<manifest output>           manifest-output
```

The current SQLite state schema is still reported as version 2, but the
rebuildable database is not package content. Event logs and dependency graphs
are included when present and validated through their existing repositories.

Malformed known structured sources fail closed. Missing optional sources are
reported as structured items for the later global audit and release gates.

## Compatibility

This is schema version 1. The package builder and release verifier must consume
this contract without changing its meaning. Incompatible field or path-policy
changes require a new schema version, generated schema, compatibility fixture,
migration guidance, and ADR.

The manifest does not sign content. PR54 uses its checksums to construct a
reproducible archive; PR56 provides blocking local release verification and a
checksum manifest. Digital signing and remote publication remain later
roadmap stages.
