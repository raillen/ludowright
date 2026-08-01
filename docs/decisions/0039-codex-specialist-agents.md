# ADR 0039: Versioned Codex specialist agents and routing

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `CODEX_AGENTS.md`, `CODEX_ORCHESTRATION.md`, `CODEX_SKILL.md`, `CLI.md`, `DECISIONS_AND_APPROVALS.md`

## Context

PR45 defines the deterministic next-action policy and PR48 defines the human
review boundary, but the Codex adapter still lacks explicit specialist roles.
Free-form delegation could select the wrong scope, bypass a checkpoint, or turn
an agent suggestion into an implicit decision. The roles must remain data,
versioned with the local skill, and testable without invoking Codex or a provider.

## Decision

1. Ship a versioned `codex-agent-catalog` as `agents.json` in the project-local
   skill package.
2. Define nine bounded specialist profiles and one deterministic route per
   task: interviewer, game-design architect, technical architect, asset
   planner, visual director, generation operator, consistency reviewer, quality
   auditor, and release verifier.
3. Require each profile to declare capabilities, read/write scopes, guidance,
   allowed orchestration actions, and forbidden approval/overwrite boundaries.
4. Use `CodexAgentRouter` as a pure adapter. It consumes an orchestration plan,
   checks status inspection, route/action compatibility, and required
   capabilities, then returns `codex-agent-route` without mutating state.
5. Set `can_approve` to `false` in the contract. Human approval remains an
   explicit plan checkpoint and no specialist is an approval authority.
6. Increase the skill revision to 3 and protect all payloads with the existing
   skill manifest checksum and atomic installer.

## Alternatives considered

### Put role prompts in the core application

Rejected because Codex-specific instructions would leak into the deterministic
core and become a second source of orchestration behavior.

### Choose an agent with Python conditionals scattered through the adapter

Rejected because routing rules would be harder to inspect, version, hash, and
extend. The catalog keeps the mapping declarative and the router generic.

### Let specialist agents approve their own outputs

Rejected because generation and approval require separation of duties. Agents
may prepare evidence or propose a review, but acceptance remains human-owned.

## Consequences

### Positive

- roles, capabilities, and routes are reviewable as data;
- identical plans produce identical routes;
- missing status, capabilities, or allowed actions fail closed;
- the local skill remains self-contained and checksum-verified;
- PR50 can evaluate each route and boundary independently.

### Negative

- the router selects roles but does not execute complete phases;
- task taxonomy is intentionally small and must grow through versioned data;
- the catalog duplicates some human-readable scope descriptions already present
  in the roadmap, although it is the normative adapter input.

## Compatibility and migration

The new `codex-agent-catalog` and `codex-agent-route` schemas are additive v1
contracts. Existing skill revision 2 installations are intact but outdated and
are upgraded by the existing `codex skill update` transaction. No project files,
event-log entries, SQLite tables, graph revisions, or migrations change.
