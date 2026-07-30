# ADR 0015 — Declarative Guided-Interview Question Model

## Status

Accepted

## Context

Guided documentation needs to ask bounded questions, resume safely, and calculate what remains without putting product state in a conversation. The first model must be usable by a future CLI and document-template engine while remaining independent of Typer, SQLite, Codex prompts, or filesystem layout.

## Decision

Introduce an immutable domain model for ordered questionnaires, typed question values, safe declarative dependencies, answer provenance, and pending-question projection.

Dependencies use a small fixed operator set and must form an acyclic graph. Unresolved dependencies are reported as blocked; false dependencies are reported as not applicable. Required pending and required blocked questions determine completion. All output collections preserve questionnaire declaration order for deterministic interaction.

Publish only the questionnaire definition as the v1 `interview-questionnaire` JSON contract in this slice. Answer-session adapters exist in the contracts package for the next CLI slice but are not registered as standalone persisted schemas yet.

## Consequences

Positive consequences:

- the interview engine has no arbitrary code execution surface;
- answer validation and progress calculation are reusable across CLI, Codex, and tests;
- provenance is part of the answer value rather than an external side channel;
- future persistence can serialize immutable sessions without changing domain rules.

Trade-offs:

- the first release supports only six answer shapes and four dependency operators;
- conditional logic must be extended through a versioned contract rather than ad hoc expressions;
- the CLI and durable session persistence remain separate follow-up work.

## Alternatives rejected

- **Free-form expressions:** unsafe, hard to validate, and non-deterministic across runtimes.
- **CLI-owned question logic:** would duplicate rules for Codex and future interfaces.
- **Conversation-only answers:** cannot support reliable resumption, provenance, or audit.
