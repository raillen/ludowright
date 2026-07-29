# Decisions and Approvals Contract

## Purpose

LudoWright must preserve why a project choice was made and whether a specific generated or authored artifact revision was approved.

Decisions and approvals solve different problems:

- a **decision** records a project choice;
- an **approval** reviews one immutable revision of an entity.

Both use append-only logical histories. They do not store mutable status fields that can be overwritten without evidence of the previous state.

## Review notes

`ReviewNote` stores a normalized explanation attached to a transition.

It:

- supports Unicode in NFC form;
- allows line breaks and tabs;
- rejects surrounding whitespace and unsupported control characters;
- is limited to 4,000 characters.

A note explains the transition. Actor identity, timestamps, correlation IDs, and command provenance belong to the future event log.

## Decisions

A decision has:

- `DecisionId`;
- human-readable title;
- ordered tuple of `DecisionRevision` entries.

Every decision begins at sequence 1 with `proposed`.

```text
proposed ─┬→ accepted → superseded
          ├→ rejected
          └→ withdrawn
```

Rules:

- accepted decisions may be superseded only by a different `DecisionId`;
- rejected, withdrawn, and superseded decisions are terminal;
- repeating the current transition is idempotent and does not append history;
- trying to replace an already superseded decision with a different ID is an error;
- revision sequence numbers are positive, contiguous, and append-only.

A new decision that replaces an old one is a separate aggregate. The old accepted decision stores `superseded_by` pointing to the new ID.

## Approval subjects

An approval is never attached only to a floating entity ID.

`ApprovalSubject` contains:

- a typed entity identifier;
- an immutable `SubjectRevision` fingerprint;
- optional human-readable label.

Examples of valid revision fingerprints:

```text
sha256:abc123
v12
git:0123456789abcdef
```

The fingerprint grammar is portable ASCII and accepts letters, digits, `.`, `_`, `:`, `+`, and `-` after the first alphanumeric character.

This allows different subsystems to bind approval to:

- a file checksum;
- schema or profile version;
- Git commit;
- generation receipt;
- deterministic manifest revision.

When the content changes, the fingerprint changes and a new approval request is required.

## Approvals

An approval has:

- `ApprovalId`;
- immutable `ApprovalSubject`;
- ordered tuple of `ApprovalRevision` entries.

Every approval begins at sequence 1 with `pending`.

```text
pending ─┬→ approved ─┬→ revoked
         │            └→ superseded
         ├→ changes-requested
         ├→ rejected
         └→ withdrawn
```

Rules:

- changes requested, rejected, and withdrawn close the request;
- a corrected artifact revision receives a new approval request;
- only an approved request can be revoked or superseded;
- superseding requires a different `ApprovalId`;
- terminal states cannot be reopened;
- repeated identical transitions are idempotent;
- revision sequences are positive, contiguous, and append-only.

## Immutability and event history

Decision and approval histories record logical state evolution. Each transition returns a new aggregate and leaves the original unchanged.

The future event log will record operational metadata such as:

- actor;
- timestamp;
- command;
- correlation ID;
- source tool;
- before and after fingerprints.

The event log does not replace the domain history. Domain history determines whether the current state is valid even when loaded outside the original event store.

## Human approval boundary

The domain model describes allowed states. It does not decide who is authorized to approve.

Future application and policy layers must enforce:

- required reviewer roles;
- separation between generation and approval agents;
- explicit human checkpoints;
- approval requirements by asset or document type;
- destructive-operation confirmation;
- stale-approval detection.

## Serialization

Published YAML and JSON shapes will be introduced with the schema layer.

Expected primitive serialization:

- typed IDs as canonical strings;
- statuses as lowercase enum values;
- revision sequence as integer;
- subject fingerprint as string;
- history as an ordered array.
