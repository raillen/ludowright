# ADR 0003: Revision-bound approvals and immutable logical histories

- **Status:** accepted
- **Date:** 2026-07-29
- **Decision owners:** Raillen Santos
- **Related issue or RFC:** Implementation Plan PR 7
- **Affected contracts:** decisions, approvals, references, generation receipts, documents, assets, future event log and authorization policy

## Context

LudoWright will generate and revise documents, visual references, prompts, specs, sheets, and packages. An approval attached only to an entity ID becomes ambiguous after the underlying content changes.

Likewise, a mutable decision or approval status would erase the sequence that led to the current result and make retries, audits, migrations, and Codex orchestration harder to verify.

The future event log will capture operational metadata, but domain objects must still reject impossible state histories when loaded independently.

## Decision drivers

- prevent stale approvals from silently applying to changed content;
- preserve superseding relationships;
- make retries idempotent;
- maintain deterministic validation outside persistence;
- separate logical state history from operational event metadata;
- support human approval policies without embedding authorization in the core domain;
- keep records readable in repository-native formats.

## Decision

LudoWright will:

1. model decisions and approvals as immutable aggregates with ordered revision tuples;
2. require every decision history to begin with `proposed` sequence 1;
3. require every approval history to begin with `pending` sequence 1;
4. require positive contiguous sequence numbers;
5. reject transitions not present in explicit state maps;
6. make repeated identical transitions idempotent without appending duplicate entries;
7. represent replacement through `superseded_by` pointing to a different typed ID;
8. add `ApprovalId` as a canonical typed identifier;
9. bind each approval to a typed entity ID and immutable revision fingerprint;
10. require a new approval request when the subject fingerprint changes;
11. treat changes-requested, rejected, withdrawn, revoked, and superseded approval states as terminal according to the documented map;
12. keep actor, timestamp, authorization, command, and correlation metadata outside these aggregates in the future event and policy layers.

## Consequences

### Positive

- approved content cannot change without producing a new fingerprint;
- current status remains derivable from validated history;
- superseded records remain navigable;
- retrying a command does not duplicate history;
- impossible direct constructions fail before persistence;
- the same model works for references, documents, specs, profiles, and packages;
- authorization policy can evolve without changing basic state validity.

### Negative and trade-offs

- histories duplicate a small amount of state that the event log will also describe operationally;
- callers must compute or obtain a stable subject fingerprint;
- corrected content requires a new approval record rather than reopening the old one;
- an authorization layer is still necessary before the model is safe for team workflows;
- timestamps and actors are intentionally absent from the domain revisions.

## Compatibility and migration

No persisted decision or approval schema exists yet.

After schema publication, changes to status values, transition maps, fingerprint grammar, revision sequence rules, or superseding semantics require migration and compatibility handling.

Adding `ApprovalId` extends ADR 0001 consistently with its typed-identifier rule and does not alter the universal slug grammar.

## Security and privacy

Approval state does not imply authorization. Future application services must verify reviewer permissions and human checkpoints.

Fingerprints must not contain credentials, personal data, private URLs, or confidential content. They identify immutable content; they do not store the content itself.

Generation agents must not approve their own output when project policy requires independent review.

## Validation

- unit tests for every state family;
- invalid direct-history construction tests;
- immutability tests;
- idempotent retry tests;
- self-superseding and replacement-conflict tests;
- subject fingerprint validation;
- strict typing, coverage, documentation, dependency audit, and secret scanning.

## Follow-up work

- publish Pydantic and JSON Schema representations;
- add actor and timestamp metadata through the event log;
- add authorization and separation-of-duties policies;
- detect approvals made stale by dependency changes;
- expose approval queues through CLI and Codex;
- link approved visual references to generation receipts and checksums.

## References

- `docs/contracts/DECISIONS_AND_APPROVALS.md`
- `docs/contracts/IDENTIFIERS_AND_VERSIONS.md`
- `docs/plans/IMPLEMENTATION_PLAN.md`
