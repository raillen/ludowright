# Security Policy

Security and privacy are product requirements for LudoWright, especially because it manages local project files, generated artifacts, external references, archives, plugins, and AI-assisted workflows.

## Supported versions

LudoWright is currently pre-alpha. Until the first stable release, security fixes are applied to the latest development line only.

After `1.0`, this file will list the supported release branches and maintenance windows.

## Reporting a vulnerability

Do not disclose vulnerabilities in a public issue, discussion, pull request, or social post.

Use GitHub's private vulnerability reporting feature for this repository when available. Include:

- affected version or commit;
- operating system;
- reproduction steps;
- expected and observed behavior;
- potential impact;
- proof of concept, logs, or sample files when safe;
- suggested remediation, when known.

Do not include real secrets, private game assets, personal data, or third-party confidential material in the report.

## Response process

Maintainers will aim to:

1. acknowledge a complete report;
2. reproduce and classify the issue;
3. identify affected versions and data paths;
4. prepare a fix and regression tests;
5. coordinate disclosure when appropriate;
6. publish remediation and upgrade guidance.

No fixed response-time guarantee is offered during pre-alpha development.

## Security boundaries

High-risk areas include:

- archive extraction and packaging;
- path traversal and symbolic links;
- template loading and rendering;
- plugin and hook execution;
- untrusted YAML, JSON, Markdown, image, and ODS files;
- external reference downloads;
- command execution requested through Codex;
- secret and token handling;
- project migrations and destructive operations;
- generated output paths;
- provenance and checksum validation.

## Required practices

Contributions must follow these rules:

- never commit credentials or tokens;
- validate all paths before reading or writing;
- prevent archives from escaping their destination;
- treat project and external files as untrusted input;
- avoid arbitrary code execution from templates and configuration;
- require explicit approval for destructive operations;
- provide `--dry-run` for migrations and destructive commands;
- preserve backups before irreversible state changes;
- minimize data sent to external services;
- avoid logging secrets or unnecessary personal data;
- pin and review security-sensitive dependencies;
- add regression tests for resolved vulnerabilities.

## AI and ImageGen considerations

The Codex integration must not:

- assume model output is trusted;
- execute generated commands without appropriate safeguards;
- upload references implicitly;
- reuse rejected assets as approved references;
- conceal which files or references were sent to an external service;
- store important approval state only in a conversation.

Generated content must remain traceable to its job, prompt, references, and approval state.

## Disclosure

Security advisories will credit reporters who request attribution and follow coordinated disclosure, unless legal or safety considerations prevent it.