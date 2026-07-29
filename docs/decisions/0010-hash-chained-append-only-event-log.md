# ADR 0010: Hash-Chained Append-Only Event Log

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `EVENT_LOG.md`, `PROJECT_FILESYSTEM.md`, `STRUCTURED_REPOSITORIES.md`

## Context

LudoWright needs an auditable history of significant project operations before the SQLite state store is introduced.

Canonical JSON and YAML files describe current human-editable product data, but they do not explain:

- what operation changed the project;
- which changes belonged to one workflow;
- which event caused a later event;
- what order changes occurred in;
- whether a historical record was inserted, removed, reordered, or modified;
- how a future index can be rebuilt or checked.

A plain text activity log would be easy to write but difficult to replay safely. A database-only history would make the next infrastructure layer the sole source of audit data and would arrive before its transaction and migration policies are established.

## Decision

LudoWright stores project events in one canonical JSON Lines file:

```text
.ludowright/events.jsonl
```

Every record contains:

- schema version;
- contiguous sequence;
- unique event ID;
- namespaced event type;
- canonical UTC timestamp;
- correlation ID;
- optional earlier causation ID;
- immutable JSON object payload;
- previous event hash;
- current event hash.

The current event hash is SHA-256 over canonical JSON for every field except the hash itself. The previous hash is included in that body, producing a chain.

## Domain decision

The domain defines:

- `EventId`;
- `CorrelationId`;
- `EventType`;
- `EventHash`;
- `EventDraft`;
- `EventRecord`;
- immutable bounded JSON payload values.

The domain does not know about files, JSON Lines, locks, or recovery.

Sequence continuity, hash-chain continuity, duplicate IDs, and earlier causation are log-level invariants because they require the complete ordered history.

## Event-type decision

Event types use lowercase namespaced words separated by dots or hyphens.

Examples:

```text
project.created
asset.component-added
reference.approved
```

A namespace separator is mandatory. This prevents unscoped types such as `created` from becoming ambiguous as the product grows.

## Correlation and causation decision

Every event requires a correlation ID.

Causation is optional but, when present, must reference an earlier event in the same log.

Correlation groups a logical operation. Causation expresses a direct historical trigger. The two concepts remain separate.

## Payload decision

Payloads are JSON objects containing only JSON-compatible values. They are deep-frozen by the domain.

The initial bounds are:

- 64 nesting levels;
- 50,000 values.

Payloads must record enough context to audit or index the operation without copying entire aggregates unnecessarily. Large binary or generated artifacts remain referenced by IDs, paths, versions, and checksums.

## Canonical-line decision

Each event is one compact sorted-key UTF-8 JSON object followed by one newline.

Replay rejects alternate whitespace or key order even when the JSON has the same semantic value. The event log is generated infrastructure, and byte canonicality simplifies hashing, fixtures, provenance, and recovery.

A newline is the commit marker for a complete record.

## Hash-chain decision

Sequence `1` has no previous hash. Every later event references the exact hash of the immediately previous record.

Replay validates each body hash and each link.

The chain detects accidental corruption and modification relative to a trusted history or terminal digest. It is not a signature and does not prevent a writer from recomputing an entirely rewritten chain.

## Append decision

Appending acquires one project lock, replays the full current log, assigns the next sequence, calculates the hash, and atomically rewrites the previous bytes plus one line through `ProjectFilesystem`.

This is deliberately O(n). It reuses the already audited atomic replacement and symlink protections and avoids acknowledging a partially appended line.

A segmented or journaled log may replace the physical implementation after measurement, but it must preserve logical replay and migration compatibility.

## Recovery decision

Normal replay and append never repair the log.

An explicit recovery operation may remove only bytes after the final newline. It first validates every complete line in the prefix. Corruption in the prefix blocks recovery.

A valid JSON object without a final newline is not committed and is discarded by explicit recovery.

## Resource limits

The initial defaults are:

- 64 MiB total log size;
- 1 MiB per line.

These bounds prevent an unbounded parser and make whole-file atomic replacement an explicit pre-1.0 tradeoff.

## Consequences

### Positive

- replayable, deterministic audit history;
- exact ordering and unique IDs;
- logical correlation and causation;
- corruption and reordering detection;
- safe recovery from interrupted final writes;
- future SQLite indexes can be checked against an independent history;
- event fixtures remain readable with standard JSON tooling;
- no new runtime dependency.

### Negative

- append cost grows linearly with file size;
- SHA-256 chaining does not authenticate authors;
- a globally ordered local log limits distributed-write scenarios;
- strict canonical JSON rejects manual formatting;
- explicit recovery may discard a complete JSON object that lacks its newline commit marker;
- schema upcasting and event migration are not implemented yet;
- the log and canonical files are not yet one cross-resource transaction.

## Alternatives considered

### Plain JSON Lines without hashes

Rejected because a sequence alone does not detect historical field changes or deletion followed by renumbering.

### SQLite event table immediately

Deferred. SQLite is the next phase and should index or reconcile with established canonical files and event semantics rather than define all three at once.

### Direct operating-system append

Rejected for the initial implementation. It can leave a partial tail and does not reuse the complete atomic-replacement guarantees already implemented.

### One file per event

Rejected initially because it creates large directory counts, multi-file sequence races, and package complexity. It may become useful as a segmented representation only with an index and migration design.

### Cryptographic signatures

Deferred. Signatures require key ownership, rotation, trust anchors, revocation, and release policy. A hash chain is useful integrity metadata but must not be represented as authentication.

### Automatic truncation on startup

Rejected because silent repair can destroy forensic evidence and hide storage problems. Recovery remains explicit and reports removed bytes.

## Compatibility

The line schema, canonical serialization, hash input, sequence rules, timestamp form, path, and newline commit rule are persisted contracts.

Any incompatible change requires:

- a new event schema version;
- retained replay or migration support;
- old and new fixtures;
- backup and rollback metadata;
- dry-run migration output;
- updated integrity tests;
- an ADR or RFC according to impact.

## Security

- complete records are hash-checked and linked;
- duplicate JSON keys and non-finite numbers are rejected;
- unknown or missing fields are rejected;
- event payloads are bounded and immutable;
- reads and lines have byte limits;
- writes remain project-relative, symlink-safe, locked, and atomic;
- incomplete-tail repair is explicit and prefix-validating.

The design does not claim digital signatures, authorization, remote attestation, or tamper-proof storage.
