# Echoes Architecture Brief

## Architectural goal

Keep product truth deterministic, local-first, and reviewable.

## Layers

### Domain

Owns invariants and state transitions.

### Application

Coordinates explicit use cases.


## Boundaries

- Domain does not import infrastructure.
- Codex does not become the source of truth.
