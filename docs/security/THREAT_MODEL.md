# Security Threat Model

This document is the current security review for the public-beta and 1.0
readiness chain. It describes the local-first trust boundaries, the controls
already implemented, the evidence that protects them, and the risks that are
intentionally outside the current release boundary.

## Scope and security posture

LudoWright is a local application that reads and writes a repository owned by
the user. The project root, project files, generated artifacts, package
archives, external references, provider output, and configuration are treated
as untrusted input unless a contract explicitly establishes a stronger
invariant.

The core does not provide a process sandbox, an account system, or a remote
multi-tenant boundary. A local user who already has write access to the
project or host can bypass application-level controls. The controls below
protect the repository from accidental corruption, path escape, unsafe
parsing, and unapproved derived state; they do not replace host isolation.

## Assets and trust boundaries

| Asset or boundary | Threat source | Required invariant | Primary control |
|---|---|---|---|
| Canonical project files | CLI input, manual edits, concurrent local processes | only safe project-relative regular files are read or replaced | `ProjectFilesystem`, `RepositoryPath`, atomic writes, exclusive locks |
| Structured JSON/YAML | malformed or hostile project documents | bounded, UTF-8, JSON-compatible data with no executable YAML tags | strict repositories and Pydantic contracts |
| Templates and context | project overrides or model-produced text | declared files only; no Python object access or arbitrary template code | allow-listed files, bounded context, `SandboxedEnvironment`, safe filters |
| Event log and SQLite index | truncation, tampering, interrupted writes | canonical events remain hash-verifiable; SQLite is rebuildable | hash chaining, bounded reads, transactions, checkpoints, migrations |
| Migrations and backups | incompatible or partial state changes | no silent downgrade; failure leaves a restorable state | contiguous plans, durable backup receipts, digest-guarded rollback |
| Package inventory and ZIP | traversal, symlinks, special files, ZIP metadata, resource exhaustion | relative regular members with fixed metadata and bounded size | scanner and archive validator, checksums, create-only release writes |
| Generated references and provider output | malformed files or unapproved provenance | output is validated, receipt-bound, and not approved implicitly | PNG validation, checksums, receipt and human review boundaries |
| Secrets and private data | source files, logs, fixtures, external providers | no credentials in the repository or accidental upload | detect-secrets, explicit provider boundary, provenance and reporting policy |

## Threat and control matrix

The following matrix records the review result. “Residual” means a known risk
that requires an explicit future boundary; it is not silently treated as
solved.

| Threat | Impact | Current control and evidence | Residual risk |
|---|---|---|---|
| `..`, absolute paths, platform device names, or symlink prefixes escape the project root | file disclosure or overwrite | filesystem, package, template, initialization, ATLAS, and command tests reject unsafe paths and links | trusted host processes can still access the host directly |
| Atomic replacement races with another writer | corrupted or lost canonical data | project locks, create-only outputs, inode/token ownership checks, and rollback tests | a compromised local process can remove locks or files outside the application protocol |
| YAML tags, aliases, duplicate keys, or oversized structured input trigger code execution or resource abuse | code execution, ambiguity, or denial of service | safe YAML loader, JSON duplicate-key rejection, UTF-8/value/depth limits, and negative parser tests | no general-purpose fuzzing campaign is part of this slice |
| Jinja template overrides reach Python internals | code execution or secret disclosure | declared-path allowlist, bounded project loader, sandboxed environment, cleared globals, safe filters, and sandbox regression test | project templates are still user-controlled code-like data and require review before sharing |
| ZIP traversal, symlink metadata, noncanonical members, or decompression expansion | extraction escape or denial of service | bounded scanner, fixed metadata, sorted unique members, path validation, archive inspection, and hostile-archive regression tests | digital signatures and remote package publication are deferred |
| Event/state corruption or unsafe migration | loss of history or inconsistent index | hash-chain verification, rebuildable SQLite, explicit backups, contiguous migration planning, receipts, and rollback tests | recovery still depends on the user retaining the project directory and backups |
| Model/provider output is trusted or uploaded implicitly | privacy, licensing, or approval failure | provider adapter is isolated; operation/receipt provenance is explicit; only human review changes approval state | provider policy and network transport are outside the local core |
| Credentials enter source, fixtures, logs, or reports | account compromise or data leakage | detect-secrets in pre-commit and scheduled CI, no real credentials in fixtures, and reporting guidance | users remain responsible for secrets in files supplied to external tools |
| Vulnerable dependency reaches a release | supply-chain compromise | uv-managed dependency workflow, `pip-audit` in quality and scheduled security CI, and no known advisories in the current gate | transitive vulnerability remediation still requires an update and compatibility review |

## Evidence and release checks

Run the bounded security regression set with:

```bash
uv run pytest --no-cov tests/test_package_builder.py tests/test_document_templates.py
```

Run the repository security checks with:

```bash
uv run pre-commit run detect-secrets --all-files
uv run pip-audit
uv run ludowright quality check
```

The full quality gate also validates schemas, documentation links and policy,
clean-room installation, end-to-end provenance, packaging, and release
verification. A release must not bypass a failed security or quality check.

## Release boundary and follow-up

This review does not add network access, a plugin execution engine, digital
signatures, remote publication, or a sandbox for arbitrary local processes.
Those capabilities require separate contracts, threat analysis, and release
gates. The remaining PR62 work is documentation audit follow-up, beta feedback
from real projects, and the release-candidate checklist.
