# ADR 0036: Provider-Bound ImageGen Job Execution

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decision owners:** LudoWright maintainers
- **Related contracts:** `IMAGEGEN_EXECUTION.md`, `REFERENCES_AND_VISUAL_JOBS.md`, `VISUAL_JOB_PLANS.md`, `PROMPT_COMPILER.md`, `PROJECT_FILESYSTEM.md`, `STRUCTURED_REPOSITORIES.md`

## Context

The visual-job planner and prompt compiler already produce immutable,
provider-neutral inputs. The next slice needs to execute one ready job through
the Codex ImageGen capability while preserving path safety, deterministic
retries, one-view-per-image behavior, and failure cleanup. The core must not
depend on a network SDK or make a provider response look like a completed
generation receipt.

## Decision

1. Keep execution in `integrations/codex/imagegen.py` behind the injected
   `ImageGenProvider` protocol. The provider returns one PNG byte payload for
   one output view.
2. Publish an immutable `imagegen-operation` v1 contract and persist it as
   `operation.json` in the output directory before provider calls. Its
   deterministic digest binds the job revision, prompt hash/content, inputs,
   target, and output paths.
3. Reuse `RepositoryPath`, `ProjectFilesystem`, the project lock, atomic writes,
   and `JsonDocumentRepository`; do not introduce a second path, lock, or JSON
   serialization implementation.
4. Validate returned payloads as bounded non-animated PNGs before writing them.
   Existing files are conflicts, never overwrite candidates.
5. Roll back all artifacts created by the attempt after provider, validation, or
   write failure. Generation receipts, generated references, checksums,
   timestamps, and approvals remain later contracts.

## Alternatives considered

### Put the provider SDK in the domain or application

Rejected because it would couple deterministic business rules to credentials,
network behavior, and a vendor API. The injected protocol keeps the host adapter
replaceable and the core testable offline.

### Persist a generation receipt during execution

Rejected because a receipt needs provider/model metadata, output references,
checksums, attempt identity, and terminal status. Creating a partial receipt in
this slice would blur the distinction between an operation and a completed
generation attempt.

### Send all views in one provider request

Rejected because it breaks the one-view-per-image invariant and makes partial
output recovery ambiguous. One operation output maps to one provider call and
one PNG path.

## Consequences

### Positive

- deterministic operation identity and output layout;
- safe local-first execution with no network dependency in the core;
- atomic create-only behavior and explicit conflict handling;
- provider payload validation before persistence;
- failures do not leave a project that appears complete;
- PR47 can add receipts without changing the job or prompt contracts.

### Negative

- the operation manifest is not yet a generation receipt and cannot by itself
  prove provider success beyond the presence of validated output files;
- provider selection, timeout policy, and remote request semantics remain host
  responsibilities;
- a failed attempt is cleaned up, so failure history is not durable until the
  receipt/event-log slices exist.

## Compatibility and migration

This ADR adds only the `imagegen-operation` v1 schema and fixture. It does not
change the event log, SQLite state store, dependency graph, visual-job contract,
compiled-prompt contract, or migration catalog. Existing projects need no
migration. Future receipt persistence must reference this operation without
rewriting it.
