# Technical Sheets CLI

## Assemble a sheet

```bash
ludowright sheets assemble REQUEST OUTPUT_DIRECTORY [PROJECT]
ludowright sheets assemble requests/lantern.json sheets/lantern .
```

`REQUEST` is a repository-relative `technical-sheet-request` JSON file.
`OUTPUT_DIRECTORY` is a repository-relative destination. The optional
`PROJECT` is the project root; when omitted, the CLI discovers it from the
current directory.

The request must select a versioned template and approved references whose
declared PNG files exist and have matching checksums. The initial data pack is
the `minimal` template, version 1.

## Dry-run and repetition

```bash
ludowright sheets assemble requests/lantern.json sheets/lantern . --dry-run
ludowright --json sheets assemble requests/lantern.json sheets/lantern .
```

`--dry-run` validates and renders in memory without creating files. A repeated
operation with identical request, template, and inputs returns `unchanged`.
Existing partial or different targets return `conflict`; no existing artifact
is overwritten.

The operation creates `sheet.png` and `technical-sheet.json`. The report is
written last and is the success marker for the artifact pair. A failed write
removes files and directories created by that invocation when safe to do so.

## Output modes and errors

Human output uses Rich and reports the state, sheet kind, template, output path,
report path, and dimensions. JSON output uses the published `cli-response`
envelope with `state`, `dry_run`, template information, paths, the complete
`technical-sheet` report, and warnings.

Expected failures use the shared CLI contract:

- invalid request, path, reference, PNG, or checksum: `invalid-input`, exit 4;
- existing partial or different output: `conflict`, exit 5;
- rollback failure or unreadable persisted output: `corrupt-state`, exit 6.

The command is non-interactive and local-first. It does not call ImageGen,
write to the event log, update SQLite, or mutate approvals.

## Validation

```bash
uv run pytest --no-cov tests/test_technical_sheets.py -q
uv run ludowright sheets assemble --help
```
