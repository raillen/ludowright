# Structural audit command

Run a read-only structural audit from a project directory or any descendant:

```bash
ludowright audit ./my-game
ludowright --json audit ./my-game
```

The audit checks the project manifest, hash-chained event log, dependency graph,
SQLite state store, and source digests tracked by the derived index. It does
not create missing files, run migrations, recover an event-log tail, rebuild
the graph, or modify approved files.

An issue result is a verification failure, not an instruction to repair
automatically:

- human mode prints Rich component states, findings, and repair guidance;
- JSON mode returns the complete result in the `cli-response` envelope;
- clean projects exit `0`;
- findings use `checks-failed` and exit `1`;
- no project root uses `project-not-found` and exit `3`.

The command refuses to inspect a live SQLite WAL as an immutable snapshot. Stop
active writers and run the audit again. Preserve corrupt files as diagnostic
evidence before applying any repair described by the report.

See the [Structural Audit Contract](../contracts/STRUCTURAL_AUDIT.md) for
stable finding codes and the [CLI Contract](../contracts/CLI.md) for the
response envelope.
