# Interview Questions

This contract defines the first guided-documentation building block: a deterministic questionnaire and its answer model. It is declarative. Templates may describe questions and safe dependencies, but they cannot execute Python or arbitrary expressions.

## Published questionnaire

The public v1 contract is `interview-questionnaire`, implemented by `QuestionnaireContract` and published as `schemas/v1/interview-questionnaire.schema.json`. The checked-in fixture is `tests/fixtures/contracts/v1/interview-questionnaire.json`.

Each questionnaire has a stable slug ID, display title, and ordered unique questions. Question IDs and option IDs are typed identifiers and are never display labels or filesystem paths.

The initial question types are `text`, `single-choice`, `multi-choice`, `boolean`, `integer`, and `number`. Validation is strict: booleans are not accepted as integers or numbers, choice values must be declared, text cannot contain control characters or surrounding whitespace, and numeric bounds are inclusive.

## Dependencies

Dependencies are typed predicates with one of `equals`, `not-equals`, `contains`, or `not-contains`. `contains` operators apply only to multi-choice answers. The model rejects unknown dependencies, duplicate dependencies, incompatible expected values, and cycles. No expression language or code evaluation is part of the contract.

Questions are evaluated in declaration order:

- unanswered applicable questions are `pending`;
- questions whose dependencies are unanswered are `blocked`;
- questions whose dependencies are answered but false are `not_applicable`;
- answered questions are `answered`;
- `required_pending` and required blocked questions determine completion.

This prevents an unresolved dependency from being mistaken for a completed interview. `next_question` selects the first required pending question, falling back to the first optional pending question.

## Answers and provenance

`InterviewSession` is immutable. Recording or replacing an answer returns a new session and validates the value against the question. Every `AnswerRecord` carries `AnswerProvenance` with source (`human`, `codex`, `imported`, or `default`), a timezone-aware UTC timestamp, and optional actor and source reference.

Answer sessions are not persisted by this PR. The session contracts are adapters for the interview CLI and state-store work in PR24; the questionnaire schema is the only newly published persisted contract in this slice.

## Compatibility

The questionnaire schema remains at `schema_version: 1`. Adding a new question type, dependency operator, or required field is a compatibility decision and requires a new schema version or an explicitly compatible extension. Existing question ordering and IDs must remain stable for resumable sessions.
