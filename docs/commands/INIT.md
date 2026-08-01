# Project Initialization CLI

## Command

Create a new local-first LudoWright project with the versioned `minimal`
template:

```bash
ludowright init ./my-game --name "My Game"
```

The command accepts a missing directory or an existing empty directory. It
creates the project marker, initial directories, an empty valid event log, the
initial dependency graph, and the current SQLite state store. The generated
manifest records the project ID and the selected template:

```text
.ludowright/project.json
.ludowright/events.jsonl
.ludowright/dependency-graph.json
.ludowright/state.sqlite3
```

The project ID is derived from the validated display name through the shared
domain slugifier. The display name remains in the manifest; it is never used as
a filesystem path.

## Templates and output

Templates are versioned JSON data under `src/ludowright/templates/` and are
validated by the published `template.schema.json` contract. `minimal` is the
only supported starter template in this slice:

```bash
ludowright init ./my-game --name "My Game" --template minimal
```

Human output uses Rich. Automation uses the existing CLI envelope:

```bash
ludowright --json init ./my-game --name "My Game" --non-interactive
```

The response data includes the absolute project directory, ProjectId,
template ID/version, planned or created files and directories, project schema
version, current state-store schema version, dry-run state, warnings, and final
state.

`--non-interactive` is supported for scripts and CI. Supplying `--name` is
always required; the command never prompts.

## Dry run, idempotency, and failures

Use `--dry-run` to calculate the exact layout without creating a target,
parent directory, lock, or file:

```bash
ludowright --json init ./my-game --name "My Game" --dry-run
```

Initialization is create-only. A missing or empty target may be initialized;
an occupied directory, a target containing a project, and a non-directory
target return a semantic conflict. Existing files are never overwritten, so an
exact repeat is intentionally a conflict rather than a silent no-op.

The operation validates traversal, host-incompatible separators, symlink
components, and unsafe parent entries before writing. It serializes concurrent
initializers with the project lock. The marker is written last, after the event
log, graph, SQLite schema/checkpoint, and project index have been validated.

If an intermediate step fails, atomic writes and conservative rollback remove
only known initialization artifacts and empty directories created by the
operation. Unknown files or symlinks are preserved. The original exception is
retained as the failure cause for diagnostics. SQLite remains the current
rebuildable derived state store at schema version 2; no migration is introduced
by initialization.
