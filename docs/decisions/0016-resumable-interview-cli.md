# ADR 0016 — Resumable Interview CLI Persistence

## Status

Accepted

## Context

The question model is now available, but a CLI needs to resume after process or conversation boundaries. Answers must not live only in workflow context, and a resumed session must not silently reinterpret answers when its questionnaire changes.

## Decision

Persist each interview session as a canonical JSON document under `.ludowright/interviews/<session-id>.json`. The document stores an exact questionnaire snapshot, the source questionnaire digest, validated answers, skip/defer dispositions, and provenance. The existing `JsonDocumentRepository` provides bounded parsing, Pydantic validation, canonical serialization, atomic writes, and optimistic digest checks.

Every mutating command appends a namespaced event to the existing hash-chained event log. A per-session project lock covers loading, mutation, session replacement, and event append. If event append fails after a session replacement, the previous exact bytes are restored or the newly created file is removed.

`next` is read-only. Skip is optional-only; defer is allowed for actionable questions but never makes required work complete. The CLI returns the shared `cli-response` envelope in JSON mode.

## Consequences

Positive consequences:

- sessions survive CLI and Codex process boundaries;
- questionnaire drift fails closed with a conflict;
- answers remain canonical and auditable instead of being hidden in SQLite context;
- event replay can explain the interaction history;
- human and machine clients use the same application use cases.

Trade-offs:

- session files duplicate the questionnaire as an immutable snapshot;
- session write and event append are coordinated by rollback under one application lock, not one cross-resource transaction;
- SQLite indexing of interview sessions remains future derived-state work.

## Alternatives rejected

- **SQLite-only sessions:** would make a rebuildable index the source of product answers.
- **Event-log-only sessions:** would require a replay projection before every CLI read and would not provide a convenient canonical editable snapshot.
- **Conversation-only progress:** cannot resume reliably or provide provenance.
