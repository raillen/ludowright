"""Published contract for deterministic asset completeness audits."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    NonNegativeRevision,
    PositiveRevision,
    RepositoryPathText,
    ReviewText,
    Sha256Text,
    Slug,
)

AssetAuditState = Literal["empty", "valid", "findings"]
AssetAuditSeverity = Literal["error", "warning"]
AssetAuditFindingCode = Literal[
    "orphan-asset-node",
    "missing-specification",
    "invalid-dependency",
    "missing-capture-profile",
    "incomplete-production-metadata",
]
AssetAuditGraphState = Literal["current", "absent"]


class AssetAuditFindingContract(ContractModel):
    """One deterministic finding produced by the asset audit."""

    code: AssetAuditFindingCode
    severity: AssetAuditSeverity
    subject: ReviewText
    asset_id: Slug | None = None
    related_subjects: Annotated[tuple[ReviewText, ...], Field(max_length=32)] = ()
    message: ReviewText

    @model_validator(mode="after")
    def validate_related_subjects(self) -> Self:
        if tuple(sorted(self.related_subjects)) != self.related_subjects:
            raise ValueError("asset audit related subjects must be sorted")
        if len(set(self.related_subjects)) != len(self.related_subjects):
            raise ValueError("asset audit related subjects must be unique")
        return self


class AssetAuditReportContract(ContractModel):
    """Stable read-only result for one asset audit."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-audit"] = "asset-audit"
    state: AssetAuditState
    dry_run: bool
    registry_path: RepositoryPathText
    registry_version: PositiveRevision
    state_store_schema_version: PositiveRevision
    dependency_graph_path: RepositoryPathText
    dependency_graph_revision: NonNegativeRevision
    dependency_graph_state: AssetAuditGraphState
    asset_count: Annotated[int, Field(ge=0, le=100_000)]
    source_digest: Sha256Text
    findings: Annotated[tuple[AssetAuditFindingContract, ...], Field(max_length=100_000)] = ()
    valid: bool = True

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if tuple(sorted(self.findings, key=_finding_sort_key)) != self.findings:
            raise ValueError("asset audit findings must be sorted")
        has_findings = bool(self.findings)
        expected_state: AssetAuditState = "findings" if has_findings else "valid"
        if self.state == "empty" and (self.asset_count != 0 or self.findings):
            raise ValueError("an empty asset audit requires zero assets and findings")
        if self.state != "empty" and self.state != expected_state:
            raise ValueError("asset audit state must match its findings")
        expected_valid = not any(finding.severity == "error" for finding in self.findings)
        if self.valid != expected_valid:
            raise ValueError("asset audit validity must match blocking findings")
        if self.dependency_graph_state == "absent" and self.dependency_graph_revision != 0:
            raise ValueError("an absent dependency graph must have revision zero")
        if self.dependency_graph_state == "current" and self.dependency_graph_revision < 1:
            raise ValueError("a current dependency graph requires a positive revision")
        return self

    @property
    def error_count(self) -> int:
        """Return the number of blocking findings."""
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        """Return the number of non-blocking findings."""
        return sum(finding.severity == "warning" for finding in self.findings)


def _finding_sort_key(
    finding: AssetAuditFindingContract,
) -> tuple[str, str, str, tuple[str, ...], str, str]:
    """Return the canonical ordering for findings."""
    return (
        finding.code,
        finding.subject,
        finding.asset_id or "",
        finding.related_subjects,
        finding.severity,
        finding.message,
    )
