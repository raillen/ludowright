## Summary

Describe the change and the problem it solves.

## Scope

- [ ] The PR addresses one coherent problem.
- [ ] Unrelated refactoring is excluded or clearly justified.

## Changes

- 

## Validation

List the commands and manual checks performed.

```bash
uv run ludowright quality check
```

For release-related changes:

```bash
uv run ludowright quality release
```

## Contracts and compatibility

- [ ] No persisted schema, manifest, project layout, or CLI JSON contract changed.
- [ ] Or: versions, migrations, compatibility handling, tests, and documentation were added.

Describe compatibility impact:

## Documentation

- [ ] Canonical documentation was updated.
- [ ] `docs/ATLAS.md` was updated when navigation changed.
- [ ] An ADR was added for a durable architectural decision.
- [ ] An RFC was added for a large cross-cutting proposal.
- [ ] No documentation change is needed, with explanation below.

## Security and privacy

- [ ] Paths and untrusted files were considered.
- [ ] Secrets and personal data are not logged or committed.
- [ ] Destructive behavior has explicit confirmation and `--dry-run` where applicable.
- [ ] External-service uploads are explicit and documented.
- [ ] No security impact, with explanation below.

## Generated artifacts and AI workflows

- [ ] Provenance is preserved for generated artifacts.
- [ ] Approved artifacts are not silently overwritten.
- [ ] Real ImageGen calls are not required by normal CI.
- [ ] Codex behavior was evaluated when applicable.
- [ ] Not applicable.

## Risks and limitations

Describe residual risk, unsupported cases, and follow-up work.

## Checklist

- [ ] Tests cover the change.
- [ ] Public interfaces are typed.
- [ ] Human and JSON CLI behavior remain consistent where applicable.
- [ ] Changelog impact was considered.
- [ ] The change follows `CONTRIBUTING.md`, `SECURITY.md`, and `AGENTS.md`.
