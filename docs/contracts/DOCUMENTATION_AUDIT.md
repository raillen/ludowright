# Documentation audit contract

The documentation audit is a deterministic, read-only review of the repository's
canonical documentation tree. It composes the ATLAS integrity report with a
versioned policy stored at `docs/audit-policy.json`.

The policy is data, not Python logic. It declares:

- required topics and their canonical Markdown source;
- exact, case-insensitive phrase pairs that must not appear together;
- deprecated relative paths and their replacement sources.

The published contracts are `documentation-audit-policy` and
`documentation-audit`, with generated JSON Schemas under
`schemas/v1/`.

## Report semantics

The report preserves ATLAS `broken_links` and `orphan_documents`, then adds
stable findings with one of these codes:

| Code | Meaning |
| --- | --- |
| `missing-canonical-topic` | A required policy topic is absent from the discovered and indexed sources. |
| `duplicate-canonical-source` | Multiple metadata entries claim the same canonical source. |
| `contradictory-claim` | Both exact phrases in a contradiction rule were found. |
| `stale-reference` | A link points to an alias or a policy-deprecated path. |

The result is valid only when ATLAS has no broken links or orphan documents and
the policy produces no findings. The audit never edits Markdown, metadata, or
the policy. It is intentionally a conservative heuristic: contradiction rules
must be authored explicitly and do not claim general natural-language reasoning.

Policy paths and discovered links are bounded by the existing safe
documentation filesystem. Symlinks, traversal, external reads, and unsafe
relative paths are rejected by the shared infrastructure.
