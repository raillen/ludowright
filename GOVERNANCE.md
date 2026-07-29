# LudoWright Governance

## Current model

LudoWright currently uses a **maintainer-led open-source model**.

The repository owner is the initial lead maintainer and final decision maker while the project is pre-alpha. This is intentional: the schemas, product boundaries, extension model, and compatibility policy need a coherent foundation before governance is distributed more broadly.

## Roles

### Contributors

Anyone who reports issues, improves documentation, submits code, creates profiles, reviews changes, or participates constructively.

### Reviewers

Trusted contributors who regularly review a specific area and provide non-binding technical recommendations.

### Maintainers

People with repository write access who can triage issues, review and merge pull requests, manage releases, and enforce project policies.

### Lead maintainer

Responsible for product direction, final conflict resolution, release approval, security coordination, and changes to governance.

## Decision process

Prefer this order:

1. documented evidence and reproducible behavior;
2. existing product principles and canonical architecture;
3. rough consensus among active maintainers and affected contributors;
4. an explicit lead-maintainer decision when consensus is unavailable.

Decisions should not remain only in chat or review comments.

Use:

- issues for problem definition and bounded proposals;
- pull requests for implementation;
- ADRs for durable architectural decisions;
- RFCs for large, cross-cutting, or ecosystem-facing proposals;
- roadmap documents for sequencing rather than hidden commitments.

## Changes requiring an ADR

Create an ADR for changes to:

- dependency direction;
- persistence and state storage;
- public schemas and manifests;
- CLI machine-readable contracts;
- project directory layout;
- migration strategy;
- plugin and extension boundaries;
- security or approval models;
- Codex orchestration architecture;
- provenance requirements;
- compatibility guarantees.

## Changes requiring an RFC

An RFC should precede work that:

- introduces a major subsystem;
- changes the project's product boundary;
- adds a public extension ecosystem;
- creates a service or hosted component;
- adds a desktop application;
- materially changes licensing or commercial strategy;
- requires coordinated migration across several stable contracts.

## Pull request authority

Maintainers may merge changes after required checks pass and the change meets the documented definition of done.

Authors should not be the sole approver of high-risk changes involving:

- security;
- destructive migrations;
- release tooling;
- approval bypasses;
- plugin execution;
- archive extraction;
- secrets;
- provenance removal.

During the single-maintainer phase, these changes require additional evidence: focused tests, explicit risk notes, and a documented self-review checklist.

## Releases

The lead maintainer approves releases during pre-alpha.

A release requires:

- passing CI;
- version and changelog updates;
- migration notes when applicable;
- release verification;
- documentation consistency;
- known limitations;
- reproducible package artifacts.

## Becoming a reviewer or maintainer

Trust is earned through sustained work, not a fixed number of commits.

Relevant signals include:

- accurate technical contributions;
- constructive reviews;
- respect for project boundaries;
- attention to tests, documentation, compatibility, and security;
- reliable follow-through;
- responsible handling of private reports.

Maintainer access may be reduced or removed for inactivity, security needs, repeated policy violations, or loss of project trust.

## Conflicts of interest

Participants should disclose financial, employment, or product interests that could reasonably affect a decision.

Commercial use of LudoWright is allowed under its license, but repository decisions should protect the health of the open project rather than favor an undisclosed private implementation.

## Governance changes

Changes to this document require a dedicated pull request explaining the motivation, transition impact, and affected roles.