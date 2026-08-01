# Project Filesystem Contract

## Purpose

LudoWright stores canonical project files, generated artifacts, indexes, lock records, and future databases inside one project root.

The filesystem layer must prevent common local-project hazards:

- path traversal;
- platform-dependent file names;
- symbolic-link escapes;
- partial writes after interruption;
- concurrent writers overwriting one another;
- unbounded reads of untrusted files;
- accidental use of arbitrary absolute paths.

The canonical implementation lives in:

```text
src/ludowright/infrastructure/filesystem.py
```

This is an infrastructure adapter. Domain objects do not import filesystem APIs.

## Project root marker

A LudoWright project is identified by the regular file:

```text
.ludowright/project.json
```

`ProjectFilesystem.discover()` starts from a file or directory and searches the nearest ancestor containing this marker.

Discovery rules:

- the starting path must exist;
- the nearest marker wins;
- the marker must be a regular file;
- a symbolic-link marker is rejected;
- discovery stops with `ProjectRootNotFoundError` when no marker exists.

The content of `project.json` will be defined by the project repository and initialization phases. Root discovery only establishes the trusted boundary.

## Repository-relative paths

All operations use `RepositoryPath` rather than arbitrary `Path` or string values.

A repository path:

- is relative to the project root;
- is already normalized;
- uses forward slashes;
- contains ASCII only;
- uses lowercase letters, digits, dots, hyphens, and underscores inside segments;
- contains no empty, `.` or `..` segments;
- contains no backslashes;
- contains no Windows-reserved device names;
- contains no segment ending with a dot;
- is at most 1,024 characters;
- uses segments no longer than 255 characters.

Examples:

```text
.ludowright/project.json
assets/chr-maya/spec.json
references/chr-maya/front.png
schemas/v1/project.schema.json
```

Rejected examples:

```text
../outside
/assets/item.json
assets/../outside
assets//item
assets\item
Assets/Item.json
assets/con.json
assets/ação.json
```

Human-readable Unicode names belong in structured data. They are never used directly as canonical repository paths.

## Root containment

`ProjectFilesystem` resolves one existing root directory to its canonical absolute location.

Every repository path is joined beneath that root and checked before use.

The adapter rejects:

- a target outside the root;
- a symbolic link in any existing path prefix;
- a symbolic-link target;
- a non-directory ancestor during directory creation;
- a non-regular target during file writes.

This contract deliberately does not follow project-controlled symlinks. Supporting trusted symlink mounts later would require an explicit policy, allowlist, audit trail, and security review.

## Safe directory creation

`ensure_directory()` creates each missing segment separately.

For every segment it verifies that an existing entry is:

- not a symbolic link;
- a directory.

Concurrent creation is handled idempotently. If another process replaces the segment with a symlink or non-directory during creation, the operation fails rather than proceeding.

Default mode is `0755`. More restrictive internal directories, such as the lock directory, request `0700`.

`ProjectFilesystem.list_files()` recursively enumerates regular files below a
safe repository-relative directory. Results are sorted by canonical path,
optional suffix filters are applied before returning, and symlinks or
non-directory ancestors fail closed. The method returns an empty tuple when
the requested directory does not exist and enforces a caller-provided file
count limit.

External integrations may need a conventional case-sensitive filename, such as
Codex's `SKILL.md`. The restricted `write_child_bytes()`, `read_child_bytes()`,
`list_child_files()`, `remove_child_file()`, `directory_exists()`, and
`remove_empty_directory()` methods accept one validated filename beneath an
ordinary `RepositoryPath`. They preserve root containment, reject symlinks,
bound filenames, and reuse the same atomic-write implementation. They do not
permit slashes, traversal, arbitrary absolute paths, or uppercase segments in
`RepositoryPath` itself.

## Atomic writes

`write_bytes()` and `write_text()` use a sibling temporary file in the destination directory.

The operation:

1. validates the canonical target and all existing ancestors;
2. creates missing parent directories safely;
3. creates a unique temporary file in the same directory;
4. writes the complete immutable payload;
5. flushes Python buffers;
6. calls `fsync()` on the temporary file;
7. revalidates the target;
8. replaces the target with `os.replace()`;
9. synchronizes the parent directory where supported;
10. removes the temporary file after any failure.

Using the same directory keeps the temporary file on the same filesystem, preserving atomic replacement semantics.

When replacing an existing regular file, its mode is preserved. New files default to `0644` unless a mode is supplied.

An atomic write protects readers from partial files. It does not by itself coordinate multiple legitimate writers. Callers use project locks for multi-step or conflicting operations.

## Bounded reads

`read_bytes()` and `read_text()` accept an optional byte limit.

The adapter checks the initial file size and also verifies the bytes actually read. This catches a file that grows between metadata inspection and reading.

A size limit must be a non-negative integer.

Higher-level repositories define suitable limits for manifests, YAML, JSON, event logs, images, and databases.

## Exclusive project locks

`ProjectFilesystem.lock()` creates an exclusive lock file under:

```text
.ludowright/locks/<name>.lock
```

Lock names use lowercase ASCII letters, digits, and single hyphen separators.

Acquisition uses exclusive file creation. Only one process can create the same lock file successfully.

Lock metadata contains:

- random 128-bit ownership token;
- lock name;
- process ID;
- hostname;
- timezone-aware creation timestamp.

Metadata is bounded, validated, and written with `fsync()`.

## Lock timeouts

A lock accepts:

- non-negative timeout;
- positive polling interval.

The default timeout is zero, producing an immediate `ProjectLockTimeoutError` when another writer holds the lock.

Waiting uses a monotonic clock so wall-clock adjustments do not affect timeout behavior.

## Lock ownership

Release verifies:

- the lock file still exists beneath the project root;
- it is not a symbolic link;
- device and inode match the acquired file;
- metadata is well formed;
- the ownership token matches.

A mismatch raises `ProjectLockOwnershipError` and leaves the replacement lock untouched.

Repeated release of an already released lock is a no-op.

## Stale locks

The initial contract does **not** remove stale locks automatically.

Automatically deleting a lock based only on age can corrupt work when:

- a long-running operation is still valid;
- clocks disagree;
- a network filesystem delays visibility;
- the original process runs on another host;
- process identifiers are reused.

A future recovery command may inspect lock metadata and require explicit human confirmation before breaking a lock. That operation must be auditable and must never be hidden inside ordinary acquisition.

## Lock scope

Locks are advisory within LudoWright. External tools can still modify project files directly.

Higher-level services should use stable names such as:

```text
project-write
manifest-update
asset-registry
schema-migration
package-build
```

Multi-file transactions should hold one appropriate lock for the entire operation and use atomic writes for each individual file.

## Error model

The infrastructure exposes:

| Error | Meaning |
|---|---|
| `ProjectFilesystemError` | Base filesystem contract failure |
| `ProjectRootNotFoundError` | No project marker was found |
| `UnsafeProjectPathError` | Path, symlink, or containment rule failed |
| `ProjectLockTimeoutError` | Exclusive lock was unavailable before timeout |
| `ProjectLockOwnershipError` | Lock metadata or ownership changed unexpectedly |

Standard exceptions such as `FileNotFoundError`, `UnicodeDecodeError`, and `OSError` remain visible when they accurately describe the underlying operation.

## Security boundaries

This layer protects path and write mechanics. It does not decide:

- whether a user is authorized;
- whether content is semantically valid;
- whether an approved artifact may be replaced;
- which schema version a document uses;
- which migration is allowed;
- whether an image is safe or licensed;
- whether an archive may be extracted;
- whether an external process modified a file.

Those decisions belong to application services, contracts, approvals, repositories, migration tooling, and audits.

## Future repository adapters

The next implementation step builds YAML and JSON repositories on this abstraction.

Those adapters must add:

- bounded parsing;
- canonical formatting;
- schema validation;
- corruption errors;
- round-trip tests;
- lock selection;
- approval and version checks where applicable.

They must not bypass `RepositoryPath`, atomic writes, or symlink protection by calling arbitrary filesystem paths directly.
