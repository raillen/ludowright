# Package Manifest CLI

## Command

Create a deterministic inventory for a discovered project with:

```bash
ludowright package manifest PROJECT OUTPUT_PATH
```

For example:

```bash
ludowright package manifest ./my-game release/package-manifest.json \
  --package-id v0-1-0
```

`PROJECT` may be the project directory or a path below it. `OUTPUT_PATH` is a
project-relative `.json` path. The command validates the project marker before
scanning files.

## Dry run and output modes

Use `--dry-run` to calculate the exact manifest and report without writing the
output or creating a lock file:

```bash
ludowright package manifest ./my-game release/package-manifest.json --dry-run
```

Human output uses Rich. Automation uses the published CLI envelope:

```bash
ludowright --json package manifest ./my-game release/package-manifest.json
```

The JSON data includes the output path, project/package IDs, state, dry-run
flag, counts, complete manifest data, warnings, and current SQLite schema
compatibility information.

## Idempotency and failure behavior

The output is create-only:

- first successful execution returns `state: created`;
- an exact repeat returns `state: unchanged`;
- an existing output with different bytes returns `conflict` and is never
  overwritten;
- concurrent writers serialize through the `package-manifest` project lock;
- scanning or writing failures preserve the original cause and leave no
  apparently valid partial manifest;
- the operation does not mutate canonical sources, event log, dependency graph,
  or SQLite state.

The scanner fails closed on traversal, symlinks, special files, content races,
and configured file/byte limits. Missing optional sources are warnings in the
result and structured entries in the persisted manifest.

## Scope

This command produces the manifest only. ZIP creation, package indexes,
release directories, global readiness audits, and release verification are
separate roadmap stages.
