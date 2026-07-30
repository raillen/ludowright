"""Deterministic, read-only documentation policy auditing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ludowright.application.atlas import AtlasGenerationError, AtlasGenerator
from ludowright.contracts import (
    AtlasDocumentMetadataContract,
    AtlasLinkContract,
    DocumentationAuditPolicyContract,
    DocumentationAuditReportContract,
    DocumentationFindingContract,
)
from ludowright.infrastructure import (
    DocumentationFilesystem,
    DocumentationFilesystemError,
    JsonDocumentRepository,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    StructuredDocumentError,
)


class DocumentationAuditError(RuntimeError):
    """Raised when documentation audit inputs cannot be safely analyzed."""


@dataclass(frozen=True, slots=True)
class DocumentationAudit:
    """A validated audit report and its deterministic Markdown projection."""

    report: DocumentationAuditReportContract
    markdown: str

    @property
    def valid(self) -> bool:
        """Return whether ATLAS and all configured policy checks passed."""
        return self.report.valid


class DocumentationAuditor:
    """Analyze ATLAS and a repository-local documentation audit policy."""

    def __init__(
        self,
        root: Path | str,
        *,
        docs_directory: str = "docs",
        metadata_path: str = "docs/atlas.json",
        policy_path: str = "docs/audit-policy.json",
    ) -> None:
        try:
            self._documentation = DocumentationFilesystem(root, docs_directory=docs_directory)
            self._atlas = AtlasGenerator(
                self._documentation.root,
                docs_directory=docs_directory,
                metadata_path=metadata_path,
            )
            self._policy_repository = JsonDocumentRepository(
                ProjectFilesystem(self._documentation.root),
                RepositoryPath.parse(policy_path),
                DocumentationAuditPolicyContract,
            )
        except (
            DocumentationFilesystemError,
            ProjectFilesystemError,
            ValueError,
            TypeError,
        ) as error:
            raise DocumentationAuditError(
                "documentation audit inputs are not safe or usable"
            ) from error

    def generate(self) -> DocumentationAudit:
        """Return a deterministic report without modifying the repository."""
        try:
            atlas = self._atlas.generate()
            policy_snapshot = self._policy_repository.load()
            policy = policy_snapshot.value
            discovered = set(self._documentation.list_markdown())
        except AtlasGenerationError as error:
            raise DocumentationAuditError(str(error)) from error
        except (
            DocumentationFilesystemError,
            FileNotFoundError,
            OSError,
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
        ) as error:
            raise DocumentationAuditError(
                f"documentation audit inputs could not be read: {error}"
            ) from error

        try:
            findings = self._findings(
                atlas.report.documents, atlas.report.links, policy, discovered
            )
        except (DocumentationFilesystemError, FileNotFoundError, OSError) as error:
            raise DocumentationAuditError(
                f"documentation audit documents could not be read: {error}"
            ) from error
        report = DocumentationAuditReportContract(
            version=atlas.report.version,
            metadata_digest=atlas.report.metadata_digest,
            policy_digest=policy_snapshot.digest,
            atlas_valid=atlas.valid,
            broken_links=atlas.report.broken_links,
            orphan_documents=atlas.report.orphan_documents,
            findings=tuple(sorted(findings, key=_finding_sort_key)),
        )
        return DocumentationAudit(report=report, markdown=render_documentation_audit(report))

    def _findings(
        self,
        documents: tuple[AtlasDocumentMetadataContract, ...],
        links: tuple[AtlasLinkContract, ...],
        policy: DocumentationAuditPolicyContract,
        discovered: set[str],
    ) -> list[DocumentationFindingContract]:
        findings: list[DocumentationFindingContract] = []
        metadata_sources = {document.canonical_source for document in documents}
        for topic in policy.topics:
            if (
                topic.canonical_source not in discovered
                or topic.canonical_source not in metadata_sources
            ):
                findings.append(
                    DocumentationFindingContract(
                        code="missing-canonical-topic",
                        subject=topic.id,
                        message=(
                            f"Required topic '{topic.title}' is not represented by canonical "
                            f"source '{topic.canonical_source}'."
                        ),
                        related_paths=(topic.canonical_source,),
                    )
                )

        source_paths: defaultdict[str, list[str]] = defaultdict(list)
        for document in documents:
            source_paths[document.canonical_source].append(document.path)
        for canonical_source, paths in sorted(source_paths.items()):
            if len(paths) > 1:
                findings.append(
                    DocumentationFindingContract(
                        code="duplicate-canonical-source",
                        subject=canonical_source,
                        message=(
                            f"Multiple metadata entries claim '{canonical_source}' as canonical."
                        ),
                        related_paths=tuple(sorted(paths)),
                    )
                )

        canonical_by_path = {document.path: document.canonical_source for document in documents}
        deprecated = {item.path: item.replacement for item in policy.deprecated_references}
        for link in links:
            replacement = deprecated.get(link.target)
            if replacement is None and link.target in canonical_by_path:
                canonical_source = canonical_by_path[link.target]
                if canonical_source != link.target:
                    replacement = canonical_source
            if replacement is None:
                continue
            findings.append(
                DocumentationFindingContract(
                    code="stale-reference",
                    subject=link.target,
                    message=f"Reference '{link.target}' is stale; use '{replacement}'.",
                    related_paths=tuple(sorted({link.source, link.target, replacement})),
                    replacement=replacement,
                )
            )

        for rule in policy.contradictions:
            if not self._documentation.exists(rule.left.path) or not self._documentation.exists(
                rule.right.path
            ):
                continue
            left = self._documentation.read_markdown(rule.left.path).casefold()
            right = self._documentation.read_markdown(rule.right.path).casefold()
            if rule.left.phrase.casefold() in left and rule.right.phrase.casefold() in right:
                findings.append(
                    DocumentationFindingContract(
                        code="contradictory-claim",
                        subject=rule.id,
                        message=f"Contradictory policy claims detected: {rule.title}.",
                        related_paths=tuple(sorted({rule.left.path, rule.right.path})),
                    )
                )
        return findings


def render_documentation_audit(report: DocumentationAuditReportContract) -> str:
    """Render a stable Markdown report from one audit result."""
    lines = [
        "# Documentation Audit Report",
        "",
        "This report is derived from ATLAS metadata and the versioned audit policy.",
        "",
        "## Summary",
        "",
        f"- ATLAS: {'valid' if report.atlas_valid else 'invalid'}",
        f"- Broken links: {len(report.broken_links)}",
        f"- Orphan documents: {len(report.orphan_documents)}",
        f"- Policy findings: {len(report.findings)}",
        f"- Status: {'valid' if report.valid else 'invalid'}",
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("No policy findings.")
    else:
        for finding in report.findings:
            paths = ", ".join(f"`{path}`" for path in finding.related_paths)
            suffix = f" Related paths: {paths}." if paths else ""
            lines.append(f"- **{finding.code}** `{finding.subject}` — {finding.message}{suffix}")
    lines.append("")
    return "\n".join(lines)


def _finding_sort_key(finding: DocumentationFindingContract) -> tuple[str, str, tuple[str, ...]]:
    return finding.code, finding.subject, finding.related_paths
