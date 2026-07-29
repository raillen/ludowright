# Append-Only Project Event Log

## Purpose

LudoWright records significant project changes as immutable events so state can be audited, explained, replayed, and compared with canonical files and future SQLite indexes.

The event log provides:

- canonical JSON Lines storage;
- strictly increasing sequence numbers;
- typed event and correlation identifiers;
- optional causation links;
- canonical UTC timestamps;
- immutable JSON-compatible payloads;
- SHA-256 hashes for each event body;
- a hash chain across the full sequence;
- complete replay validation before append;
- explicit recovery of only an incomplete trailing fragment;
- project-relative atomic writes and exclusive locking.

The canonical implementation lives in:

```text
src/ludowright/domain/events.py
src/ludowright/infrastructure/event_log.py
```

The default file is:

```text
.ludowright/events.jsonl
```

## Architectural position

```text
Application use case
        ↓
EventDraft
        ↓
EventLog append and replay
        ↓
ProjectFilesystem lock + atomic replacement
        ↓
.ludowright/events.jsonl
```

The event log records facts after an application operation has been validated. It does not replace domain invariants, canonical project files, approvals, or future database transactions.

## Event identifiers

`EventId` identifies one immutable record.

Automatically generated IDs use:

```text
event-<32 lowercase hexadecimal characters>
```

Callers may provide a deterministic `EventId` for imports, migrations, tests, or idempotent workflows. An ID may appear only once in the log.

## Correlation identifiers

`CorrelationId` groups events that belong to one logical operation or workflow.

Examples:

```text
project-init-2026-07-29
asset-import-batch-12
visual-review-session-4
```

Correlation does not imply causation or sequence adjacency. Events from one operation may be interleaved with other work in future storage implementations.

## Causation identifiers

An event may contain `causation_id` referencing the event that directly caused it.

A causation reference must point to an event earlier in the same log. Forward references and self-causation are rejected.

Correlation and causation serve different purposes:

- correlation groups a larger operation;
- causation links one event to an earlier triggering event.

## Event types

`EventType` uses namespaced lowercase words separated by dots or hyphens.

Grammar:

```text
[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+
```

Valid examples:

```text
project.created
project.stage-changed
asset.component-added
reference.approved
visual-job.completed
```

Invalid examples:

```text
project
Project.created
project_created
project..created
```

Event types contain 3 to 100 characters. The namespace should identify the aggregate or workflow area.

## Immutable payloads

An `EventDraft` accepts one JSON object payload.

Allowed values are:

- objects with string keys;
- arrays;
- strings;
- booleans;
- integers;
- finite floating-point numbers;
- null.

The domain converts objects to read-only mappings and arrays to tuples. Later caller mutations therefore cannot change the event being appended.

Payloads reject:

- non-string object keys;
- sets and arbitrary Python objects;
- byte strings;
- dates and timestamps as Python objects;
- `NaN` and infinity;
- more than 64 nesting levels;
- more than 50,000 values.

A timestamp that belongs to the business payload should be serialized explicitly as a canonical string.

## Event record fields

Every JSON Lines record contains exactly:

| Field | Meaning |
|---|---|
| `schema_version` | Event-line contract revision, currently `1` |
| `sequence` | Positive contiguous sequence beginning at `1` |
| `event_id` | Unique typed event identifier |
| `event_type` | Canonical namespaced type |
| `occurred_at` | Canonical UTC timestamp |
| `correlation_id` | Logical operation identifier |
| `causation_id` | Earlier causing event or `null` |
| `payload` | Immutable JSON object |
| `previous_hash` | Previous record hash or `null` for sequence `1` |
| `hash` | SHA-256 of the canonical event body |

Unknown or missing fields are rejected during replay.

## Canonical timestamp

Timestamps are normalized to UTC and serialized with six fractional digits:

```text
2026-07-29T12:30:45.123456Z
```

Naive datetimes and alternate persisted forms are rejected. This avoids local-time ambiguity and formatting drift.

## Canonical JSON Lines

Each event occupies exactly one compact JSON object followed by one newline.

Serialization uses:

- UTF-8 without BOM;
- sorted object keys;
- compact separators;
- native Unicode;
- finite numbers only;
- no blank lines;
- one trailing newline per record.

Replay rejects semantically equivalent lines with alternate whitespace or key ordering. The log is generated infrastructure data, not a hand-formatted authoring surface.

## Event hash

The event hash is SHA-256 over canonical JSON containing every event field except `hash` itself.

The hashed body includes `previous_hash`. Therefore changing any of the following changes the hash:

- sequence;
- ID;
- type;
- timestamp;
- correlation or causation;
- payload;
- previous hash.

## Hash chain

Sequence `1` requires:

```json
"previous_hash": null
```

Every later event requires the exact hash of the immediately preceding record.

Replay verifies:

1. contiguous sequence;
2. unique event IDs;
3. valid causation references;
4. each event body hash;
5. each previous-hash link;
6. canonical line bytes.

Changing, inserting, deleting, or reordering a complete record invalidates the chain from that point onward.

## Security meaning of the hash chain

The chain detects accidental corruption and unauthenticated modification when a trusted expected hash or trusted history exists.

It is **not** a digital signature. A party able to rewrite the entire file can recompute every hash.

Future release manifests, Git history, package signatures, backups, or remote attestations may anchor a trusted terminal hash. This PR does not claim author authentication or tamper-proof storage.

## Replay snapshot

`replay()` returns `EventLogSnapshot` containing:

- the immutable ordered event tuple;
- exact file byte length;
- SHA-256 digest of the complete log revision;
- derived last sequence;
- derived last event hash.

An absent or zero-byte file is a valid empty log.

## Append algorithm

Appending one event performs:

1. acquire the `event-log` project lock;
2. read the current file within the configured limit;
3. replay and validate the complete current sequence;
4. verify event-ID uniqueness and causation;
5. assign the next sequence;
6. assign or validate the event ID and UTC timestamp;
7. calculate the chained hash;
8. serialize one canonical line;
9. enforce line and total-log limits;
10. atomically replace the file with the previous bytes plus the new line;
11. release the lock.

A corrupt or incomplete log blocks append. The writer never silently skips invalid history.

## Why the first version rewrites the file

The initial implementation uses `ProjectFilesystem.write_bytes()` to atomically replace the complete log under a lock.

This is O(n) in current log size, but it preserves:

- sibling temporary-file writes;
- payload synchronization;
- atomic `os.replace()`;
- parent-directory synchronization;
- symlink denial;
- clean failure behavior.

Unsafe partial append is a worse initial tradeoff than bounded whole-file replacement. Segmenting or journaling may be introduced after real performance measurements, with migration and replay compatibility.

## Limits

Default limits are:

- 64 MiB for the complete log;
- 1 MiB for one event line.

Both limits are configurable positive integers. The line limit cannot exceed the total-log limit.

Reaching the total limit should trigger archival or segmentation work. The application must not simply raise the limit indefinitely without operational planning.

## Incomplete tail

A non-empty file that does not end in newline contains an incomplete trailing fragment.

Normal replay and append raise `IncompleteEventLogTailError`, reporting:

- byte length of the complete newline-terminated prefix;
- byte length of the incomplete tail.

No automatic repair occurs.

## Explicit tail recovery

`recover_incomplete_tail()`:

1. acquires the event-log lock;
2. identifies the complete newline-terminated prefix;
3. fully replays and validates that prefix;
4. atomically replaces the file with the validated prefix;
5. reports the removed byte count.

Recovery refuses to proceed when any complete line in the prefix is corrupt.

A complete JSON object without a final newline is still considered an incomplete tail and is discarded by explicit recovery. This is intentional: only newline-committed records belong to the log.

## Concurrency

All LudoWright writers use the same project lock name:

```text
event-log
```

The lock covers read, replay, sequence assignment, hash calculation, and atomic replacement. Concurrent writers therefore receive unique contiguous sequences.

The lock coordinates LudoWright processes only. An external editor can still modify the file, but the next replay detects invalid bytes or a broken chain.

## Error model

| Error | Meaning |
|---|---|
| `EventLogError` | Base append, configuration, or persistence error |
| `CorruptEventLogError` | A complete line, field set, sequence, hash, or chain is invalid |
| `IncompleteEventLogTailError` | Bytes exist after the final complete newline |
| `InvalidEventError` | Event type, payload, record, or hash violates domain rules |

Filesystem lock, containment, and write errors remain visible when they describe the underlying failure accurately.

## Compatibility policy

The following are persisted contracts:

- default path;
- field names and required field set;
- schema version;
- timestamp representation;
- event-type grammar;
- payload limits and JSON-compatible value model;
- canonical JSON serialization;
- hash input and algorithm;
- sequence and causation rules;
- newline commit rule;
- recovery semantics.

Incompatible changes require:

- a new event schema version;
- retained replay support or an explicit migration;
- fixtures for old and new lines;
- dry-run migration behavior;
- backup and rollback metadata;
- documentation and an ADR or RFC.

Existing events must never silently acquire a different interpretation.

## Boundaries

The event log does not provide:

- user authorization;
- digital signatures;
- distributed consensus;
- cross-machine locking;
- automatic conflict merging;
- database transactions;
- canonical aggregate reconstruction by itself;
- event upcasting or migration yet;
- long-term archival or compaction yet.

The upcoming SQLite store may index replayed events and workflow progress, but canonical human-editable files remain authoritative where specified by the architecture.
