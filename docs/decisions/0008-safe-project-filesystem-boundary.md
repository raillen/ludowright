# ADR 0008: Safe Project Filesystem Boundary

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contract:** `PROJECT_FILESYSTEM.md`

## Context

LudoWright will read and write project manifests, asset specifications, visual references, event logs, SQLite state, generated documents, packages, and migration backups.

Accepting arbitrary absolute paths or directly calling `Path.write_text()` throughout the application would create several risks:

- path traversal outside the project;
- different behavior on Windows, Linux, and macOS;
- symbolic-link escapes;
- partial files after interruption;
- concurrent writers corrupting structured state;
- stale lock removal based on unsafe assumptions;
- difficulty auditing which code may touch project files.

A single filesystem boundary is therefore required before adding YAML, JSON, event-log, database, migration, and packaging repositories.

## Decision

All canonical project file operations use `ProjectFilesystem` and `RepositoryPath`.

### Root boundary

A project root is discovered through the nearest regular marker file:

```text
.ludowright/project.json
```

The root is resolved once and becomes the containment boundary for all later operations.

### Canonical paths

Repository paths are cross-platform ASCII paths using normalized forward-slash segments. Traversal, absolute paths, backslashes, Unicode file names, uppercase names, trailing dots, and Windows device names are rejected.

Human Unicode names remain structured data and are not converted implicitly into paths.

### Symlink policy

Project-controlled symlinks are rejected for canonical reads, writes, directory creation, markers, and locks.

The initial system has no trusted-symlink mode.

### Atomic writes

Writes use a temporary sibling file, file synchronization, atomic replacement, and parent-directory synchronization where supported.

Atomic replacement is the default file update behavior for structured repositories.

### Advisory locks

Multi-writer coordination uses exclusive lock files under `.ludowright/locks/`.

Locks include validated ownership metadata and verify token plus file identity before release.

The initial system never breaks stale locks automatically.

### Bounded reads

Infrastructure supports byte limits. Higher-level repositories choose limits appropriate to each format.

## Consequences

### Positive

- project writes cannot intentionally target arbitrary absolute paths;
- path behavior is consistent across supported operating systems;
- symlink escapes are blocked by default;
- readers do not observe partially written structured files;
- concurrent application operations can coordinate explicitly;
- stale-lock recovery remains a deliberate, auditable action;
- later repositories share one security boundary;
- tests can inject temporary roots without changing domain code.

### Negative

- canonical repository paths cannot contain human Unicode names;
- symlink-based project layouts are unsupported initially;
- callers must translate domain IDs into explicit repository paths;
- advisory locks cannot prevent unrelated external tools from writing files;
- filesystem-level atomicity does not create a transaction across several files;
- explicit recovery is required after a process crashes while holding a lock.

## Alternatives considered

### Use arbitrary `pathlib.Path` values

Rejected because every caller would need to reimplement containment, symlink, portability, and atomicity rules.

### Normalize unsafe input automatically

Rejected because silently converting traversal, uppercase, Unicode, or repeated separators can create collisions and hide caller mistakes.

### Permit symlinks after resolving the final path

Rejected because symlink ancestors can redirect writes outside the root and introduce time-of-check/time-of-use hazards.

### Write directly to final files

Rejected because interruption can leave truncated JSON, YAML, manifests, or state files.

### Use only database transactions

Rejected because many canonical files and generated artifacts live outside SQLite. Database transactions do not protect those files.

### Automatically delete old locks

Rejected because age alone does not prove abandonment, especially across hosts, clock changes, slow operations, and network filesystems.

### Use platform-specific kernel locks only

Deferred. Kernel locks differ significantly across operating systems and filesystems. Exclusive lock files provide a portable initial protocol and inspectable metadata. A future implementation may add kernel-level locking behind the same application contract.

## Security considerations

- canonical paths reject traversal and platform-reserved names;
- existing symlink ancestors and targets are rejected;
- lock metadata is bounded and validated before trust;
- ownership mismatch never deletes the observed lock;
- reads can enforce size limits;
- temporary files remain in the destination directory;
- future archive extraction must add separate zip-slip and expansion-limit defenses;
- authorization and approval policy remain outside the filesystem adapter.

## Compatibility

The marker path, path grammar, lock directory, and lock metadata shape become infrastructure contracts.

Changing them after project initialization exists requires:

- compatibility analysis;
- migration or dual-read behavior;
- fixtures;
- cross-platform tests;
- documentation;
- an ADR or RFC according to impact.

## Follow-up

- canonical YAML and JSON repositories;
- append-only event log;
- SQLite state store;
- migration backups and rollback metadata;
- filesystem audit commands;
- explicit stale-lock inspection and recovery;
- archive and package safety;
- approved-file mutation detection.
