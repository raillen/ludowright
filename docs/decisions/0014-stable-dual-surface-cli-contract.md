# ADR 0014 — Stable Dual-Surface CLI Contract

- Status: Accepted
- Date: 2026-07-29
- Decision owners: LudoWright maintainers

## Context

LudoWright must serve individual developers, teams, shell scripts, CI pipelines, Codex skills, and future desktop or API adapters.

A CLI optimized only for humans produces colored prose that automation must scrape. A CLI optimized only for machines becomes unnecessarily difficult to operate interactively. The existing bootstrap commands also emitted unrelated JSON shapes, making integrations command-specific and fragile.

The CLI needs one stable machine surface, readable human output, predictable process codes, and reusable handling for expected domain and persistence failures.

## Decision

Adopt a dual-surface CLI built with Typer and Rich:

- human-readable Rich output by default;
- canonical JSON when global or command-local `--json` is selected;
- one published `cli-response` envelope for all parsed commands;
- stable string error codes;
- stable numeric process exit codes;
- a shared command runtime for expected-error mapping;
- minimal human `--version` output and enveloped JSON version output;
- a read-only `diagnostics` command;
- explicit `--no-color` support.

The JSON envelope contains:

```text
schema_version
kind
command
ok
data
error
meta
```

Success requires no error. Failure requires an error and may preserve partial structured data.

The runtime maps known project, validation, conflict, and corruption exceptions to stable codes. Unexpected exceptions are re-raised inside command execution instead of being silently hidden.

Parser-level usage errors remain Typer/Click errors with exit code 2 because they occur before a command callback and response context exist.

## Rationale

### One envelope instead of command-specific JSON

A common envelope lets callers implement success, failure, version, and metadata handling once. Command-specific information stays inside `data`.

### Error strings plus process codes

Shells need compact numeric codes, while structured integrations need semantic categories. Keeping both avoids overloading one representation.

### Rich only on the human surface

Rich improves readability but ANSI and presentation markup are not stable APIs. JSON remains plain canonical UTF-8.

### Expected errors without swallowed defects

Known user or state failures should not print tracebacks. Unexpected defects must remain visible during development and CI instead of being misreported as ordinary validation failures.

### Diagnostics as a successful state report

A missing project is useful diagnostic information and should not make environment inspection fail. Commands that require a project will still use the not-found error category.

## Consequences

### Positive

- Humans receive readable command output.
- Automation receives one deterministic response shape.
- Quality-check failure data remains available with exit code 1.
- Future commands inherit stable error and exit-code behavior.
- JSON Schema enables editor, CI, and external-tool validation.
- Version and diagnostics can be consumed reliably.
- Color can be disabled independently from JSON mode.

### Negative

- Command implementations must separate data collection from human rendering.
- Parser-level errors do not use the JSON envelope.
- Public error and exit-code changes require compatibility review.
- Diagnostics expose environment and path information that users must review before sharing.

### Neutral

- This decision does not define project initialization or lifecycle commands.
- This decision does not add shell completion packaging yet.
- This decision does not create an HTTP API.
- This decision does not guarantee that command-specific `data` shapes are interchangeable.

## Alternatives considered

### Human prose only

Rejected because CI, Codex, and shell tools would need unstable text parsing.

### JSON only

Rejected because interactive use would become less approachable and status-heavy workflows benefit from Rich tables and labels.

### Different JSON object for every command

Rejected because every integration would need custom success, error, and metadata parsing.

### Catch every exception as `internal-error`

Rejected because broad catching can hide defects and make test failures appear like ordinary user errors. Unexpected exceptions should fail visibly until a controlled top-level crash-reporting policy is designed.

### Encode all outcomes only in exit codes

Rejected because numeric codes cannot carry failed checks, conflicting revisions, or remediation detail.

## Compatibility

The initial published envelope is `cli-response` schema version 1.

Incompatible envelope changes require a new schema version and migration or adapter policy. Stable process exit meanings cannot be reassigned.

New commands may define their own documented `data` shapes while reusing the common envelope. New error codes require contract registration, tests, and documentation.

## Validation

The decision is enforced by:

- strict Pydantic response contracts;
- success/failure exclusivity tests;
- non-JSON and non-finite-value rejection;
- compact deterministic serialization tests;
- global and local JSON-mode tests;
- human-output and no-color tests;
- diagnostics tests with and without a project;
- quality-gate success and failure tests;
- usage exit-code tests;
- checked-in JSON Schema and compatibility fixture;
- strict MkDocs validation;
- full repository quality gates.
