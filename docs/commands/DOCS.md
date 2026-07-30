# Documentation audit CLI

Run the read-only audit from a repository root with:

```bash
ludowright docs audit
```

The command reads `docs/atlas.json` and `docs/audit-policy.json` by default.
Override them when auditing a compatible repository:

```bash
ludowright docs audit PATH --metadata docs/atlas.json --policy docs/audit-policy.json
```

Use `--check` as a quality gate. It returns the stable `checks-failed` error
code when ATLAS or the configured policy is invalid. Without `--check`, the
command still returns the complete report and its `valid` field so callers can
inspect findings without a process failure.

The human surface uses Rich and includes a Markdown report. The JSON surface
uses the shared CLI envelope:

```bash
ludowright --json docs audit
```

The response data contains the report contract, policy and metadata digests,
the Markdown projection, all findings, and the final validity state. The
operation is local-first and read-only; it has no idempotency side effects and
does not rewrite stale documents.
