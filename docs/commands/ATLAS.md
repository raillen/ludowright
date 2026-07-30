# ATLAS CLI

The `atlas` command indexes the repository's Markdown documentation and
reports whether canonical-source metadata and relative links are consistent.

## Usage

```bash
ludowright atlas
ludowright --json atlas
ludowright atlas --check
ludowright atlas REPOSITORY --metadata docs/atlas.json --docs-directory docs
```

The default repository is the current directory. `--metadata` and
`--docs-directory` are repository-relative safe paths. External HTTP and HTTPS
links are reported in the index but are not fetched.

## Human output

Rich output shows document and link counts, integrity findings, and the
generated Markdown index. It is intended for review and local navigation.

## JSON output

JSON uses the published `cli-response` envelope. Its `data` contains the
`atlas-report` fields plus:

- `markdown`: deterministic generated index text;
- `valid`: `true` only when no broken links or orphan documents exist.

## Check mode

Without `--check`, the command returns the report even when findings exist. With
`--check`, any broken link or orphan produces `checks-failed` and exit code 1;
the complete report remains in the response `data` for automation and review.

The command is read-only. It never replaces `docs/ATLAS.md` implicitly.
