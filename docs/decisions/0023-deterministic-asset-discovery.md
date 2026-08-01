# ADR 0023 — Deterministic Asset Discovery and Explicit Confirmation

- Status: accepted
- Date: 2026-08-01
- Decision owners: LudoWright maintainers
- Related contracts: `ASSET_DISCOVERY.md`, `ASSET_REGISTRY.md`, `PROJECT_FILESYSTEM.md`, `EVENT_LOG.md`

## Context

The v1 asset registry can store valid assets, but entering every asset again
by hand would make the documentation-to-registry workflow slow and difficult
to audit. Unstructured natural-language extraction would also create false
positives and would make the result depend on a model or prompt version.

## Decision

Use a reserved, explicit Markdown declaration for discovery:

```markdown
<!-- ludowright:asset-candidate family="character" subtype="humanoid" --> Maya
```

The scanner reads project-generated Markdown below
`.ludowright/documents/`, ignores fenced code blocks, validates each
declaration against the published asset contract and taxonomy, and returns a
versioned report with source path, line, evidence, and a deterministic
candidate ID. Missing IDs are derived from the taxonomy prefix and a canonical
name slug.

No candidate is written to the registry without an explicit `--confirm`
selection. Confirmation delegates to one batch operation in the existing
registry service. The operation appends `asset.discovered` with source
provenance and uses the existing registry/event/state rollback boundary.

Duplicate suggested IDs are ambiguous. IDs already in the registry are
rejected. Invalid declarations are reported and cannot be confirmed.

## Alternatives considered

### Natural-language or model-based extraction

Rejected for this stage. It would introduce non-deterministic classification,
unverifiable false positives, a larger trust boundary, and no stable replay
without a model receipt system.

### Automatically create every extracted candidate

Rejected. A documentation mention is not approval to create canonical project
state. Explicit confirmation is required for safety and reviewability.

### Persist a separate discovery database

Rejected. The registry and event log already provide canonical asset state and
an audit trail. Reports can be regenerated from source documents, while a
confirmed asset remains durable outside the conversation.

## Consequences

Positive:

- repeated scans produce stable candidates and reports;
- users can review evidence before changing the registry;
- duplicate and existing IDs fail closed;
- CLI, scripts and Codex share one confirmation contract;
- provenance is available in the event log;
- the parser has no network, execution, or model dependency.

Costs and limitations:

- documents must include the explicit declaration syntax;
- changing a declaration's line or content changes its candidate ID;
- natural-language asset mentions remain undiscovered until annotated;
- decomposition, cross-asset dependencies, ODS, and completeness auditing are
  separate workflows with their own contracts.

## Compatibility

Candidate, issue and report contracts are published as schema v1. Changes to
marker syntax, ID derivation, issue meanings, or confirmation semantics require
a new version, retained fixtures, and compatibility documentation.
