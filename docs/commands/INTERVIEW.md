# Interview CLI

The interview CLI runs a published questionnaire against a local project and keeps the session in the repository. It uses the shared `cli-response` envelope in JSON mode and the same domain model used by future Codex adapters.

## Como usar

The questionnaire path is project-relative and must point to a valid `interview-questionnaire` JSON document. The session ID is a stable slug; the default is `default`.

```bash
ludowright interview next PROJECT --questionnaire questionnaire.json --session concept
ludowright interview answer question-id PROJECT --value 'coop' --session concept --questionnaire questionnaire.json
ludowright interview defer PROJECT question-id --session concept --questionnaire questionnaire.json
ludowright interview skip PROJECT optional-question --session concept --questionnaire questionnaire.json
```

Answer values accept JSON literals. Use a JSON array for multi-choice values, a JSON number for numeric values, `true` or `false` for booleans, and a plain string for text or a choice ID.

Automation uses the global or command-local JSON option:

```bash
ludowright --json interview next PROJECT --questionnaire questionnaire.json --session concept
ludowright interview answer question-id PROJECT --value 4 --session concept --questionnaire questionnaire.json --json
```

The response `data` is the published `interview-interaction` contract at `schemas/v1/interview-interaction.schema.json`. It contains the session and questionnaire IDs, the operation, the next question projection, and deterministic progress fields: pending, required pending, blocked, not applicable, answered, skipped, deferred, and completion.

## Como funciona

`next` is read-only. If no session exists, it evaluates an empty in-memory session and does not create files. A mutating command creates or atomically updates:

```text
.ludowright/interviews/<session-id>.json
```

The session file is a versioned `interview-session` contract containing an exact questionnaire snapshot, its source digest, validated answers, dispositions, and answer provenance. The current questionnaire must have the same digest when a session is resumed; otherwise the command fails with `conflict` instead of silently changing the meaning of stored answers.

Each mutation also appends an immutable event to `.ludowright/events.jsonl`:

- `interview.answer-recorded`;
- `interview.question-skipped`;
- `interview.question-deferred`.

The session write and event append use a per-session lock. If event persistence fails after the session write, the prior session bytes are restored; a new session file is removed. The original failure remains visible.

## Políticas

- `skip` is optional-only. Required questions cannot be skipped.
- `defer` is allowed for an actionable question and keeps required work incomplete.
- answering a blocked, not-applicable, or already skipped question is rejected unless it is an existing answer or disposition being intentionally replaced;
- dispositions are not answers and can be replaced by a later answer;
- all paths are repository-relative and use the existing filesystem safety boundary.

## Limitações

This slice does not render documents or persist a SQLite cursor. The session JSON is the canonical resumable answer state; SQLite remains a rebuildable derived index. Template selection and document generation are subsequent roadmap steps.
