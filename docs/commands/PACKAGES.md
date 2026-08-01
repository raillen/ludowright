# Packages CLI

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

This command produces the manifest only. ZIP creation and package indexes are
provided by the separate `package build` command; global readiness audits and
release verification remain later roadmap stages.

## Build a release package

Build a reproducible ZIP and its external index from an existing manifest:

```bash
ludowright package build PROJECT MANIFEST_PATH RELEASE_DIRECTORY
```

For example:

```bash
ludowright package build ./my-game release/package-manifest.json release
```

The manifest's `package_id` determines the output names. The example creates:

```text
release/<package_id>.zip
release/<package_id>.index.json
```

The ZIP also contains the source manifest and index under the reserved
`__ludowright__/` directory. Members, timestamps, compression settings,
permissions, and ordering are fixed for reproducibility. The builder verifies
that every file still has the size and checksum recorded by the manifest.

Use `--dry-run` to validate and calculate the exact outputs without creating a
lock, directory, ZIP, or index:

```bash
ludowright package build ./my-game release/package-manifest.json release --dry-run
```

Build outputs are create-only. An exact repeat is `unchanged`; a partial or
different release is a conflict and is never overwritten. The release directory
must be project-relative and outside `.ludowright`. A failure during the two
writes removes artifacts and empty directories created by that invocation.

Machine output uses the same envelope:

```bash
ludowright --json package build ./my-game release/package-manifest.json release
```
