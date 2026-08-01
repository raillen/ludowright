"""Published contract for the deterministic global project audit."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    NonNegativeRevision,
    ReviewText,
    Sha256Text,
    Slug,
)
from ludowright.contracts.package_manifest import PackagePathText

ProjectAuditCategory = Literal[
    "product",
    "documents",
    "assets",
    "references",
    "jobs",
    "approvals",
    "sheets",
    "package",
]
ProjectAuditState = Literal["ready", "needs-review", "blocked"]
ProjectAuditSeverity = Literal["error", "warning"]
ProjectAuditSourceState = Literal["current", "missing", "invalid"]

PROJECT_AUDIT_CATEGORY_ORDER: tuple[ProjectAuditCategory, ...] = (
    "product",
    "documents",
    "assets",
    "references",
    "jobs",
    "approvals",
    "sheets",
    "package",
)


class ProjectAuditSourceContract(ContractModel):
    """One canonical file observed by the audit."""

    path: PackagePathText
    state: ProjectAuditSourceState
    digest: Sha256Text | None = None
    item_count: NonNegativeRevision = 0
    size_bytes: NonNegativeRevision | None = None
    detail: ReviewText


class ProjectAuditFindingContract(ContractModel):
    """One deterministic blocking or review-required audit finding."""

    code: Slug
    category: ProjectAuditCategory
    severity: ProjectAuditSeverity
    subject: ReviewText
    paths: Annotated[tuple[PackagePathText, ...], Field(max_length=32)] = ()
    related_ids: Annotated[tuple[Slug, ...], Field(max_length=64)] = ()
    message: ReviewText
    remediation: ReviewText

    @model_validator(mode="after")
    def validate_ordered_references(self) -> Self:
        if self.paths != tuple(sorted(self.paths)):
            raise ValueError("project audit finding paths must be sorted")
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("project audit finding paths must be unique")
        if self.related_ids != tuple(sorted(self.related_ids)):
            raise ValueError("project audit finding IDs must be sorted")
        if len(set(self.related_ids)) != len(self.related_ids):
            raise ValueError("project audit finding IDs must be unique")
        return self


class ProjectAuditCategoryContract(ContractModel):
    """Summary of one audited readiness category."""

    category: ProjectAuditCategory
    state: ProjectAuditState
    item_count: NonNegativeRevision = 0
    error_count: NonNegativeRevision = 0
    warning_count: NonNegativeRevision = 0


class ProjectAuditActionContract(ContractModel):
    """Deterministic remediation suggestion derived from findings."""

    code: Slug
    category: ProjectAuditCategory
    finding_codes: Annotated[tuple[Slug, ...], Field(max_length=32)] = ()
    detail: ReviewText

    @model_validator(mode="after")
    def validate_finding_codes(self) -> Self:
        if self.finding_codes != tuple(sorted(self.finding_codes)):
            raise ValueError("project audit action codes must be sorted")
        if len(set(self.finding_codes)) != len(self.finding_codes):
            raise ValueError("project audit action codes must be unique")
        return self


class ProjectAuditReportContract(ContractModel):
    """Machine-readable readiness report across the project production chain."""

    schema_version: Literal[1] = 1
    kind: Literal["project-audit"] = "project-audit"
    dry_run: bool
    project_id: Slug
    project_name: DisplayText
    state: ProjectAuditState
    valid: bool
    source_digest: Sha256Text
    sources: Annotated[tuple[ProjectAuditSourceContract, ...], Field(max_length=100_000)] = ()
    categories: tuple[ProjectAuditCategoryContract, ...]
    findings: Annotated[tuple[ProjectAuditFindingContract, ...], Field(max_length=100_000)] = ()
    recommended_actions: Annotated[
        tuple[ProjectAuditActionContract, ...], Field(max_length=100)
    ] = ()

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        categories = tuple(item.category for item in self.categories)
        if categories != PROJECT_AUDIT_CATEGORY_ORDER:
            raise ValueError("project audit categories must use canonical order")
        if tuple(item.path for item in self.sources) != tuple(
            sorted(item.path for item in self.sources)
        ):
            raise ValueError("project audit sources must be sorted")
        if len({item.path for item in self.sources}) != len(self.sources):
            raise ValueError("project audit sources must be unique")
        if tuple(sorted(self.findings, key=_finding_sort_key)) != self.findings:
            raise ValueError("project audit findings must be sorted")
        if (
            tuple(sorted(self.recommended_actions, key=_action_sort_key))
            != self.recommended_actions
        ):
            raise ValueError("project audit actions must be sorted")

        error_count = sum(finding.severity == "error" for finding in self.findings)
        warning_count = sum(finding.severity == "warning" for finding in self.findings)
        expected_state: ProjectAuditState = (
            "blocked" if error_count else "needs-review" if warning_count else "ready"
        )
        if self.state != expected_state:
            raise ValueError("project audit state must match findings")
        if self.valid != (self.state == "ready"):
            raise ValueError("project audit validity must match its state")

        findings_by_category = {
            category: (
                sum(
                    finding.category == category and finding.severity == "error"
                    for finding in self.findings
                ),
                sum(
                    finding.category == category and finding.severity == "warning"
                    for finding in self.findings
                ),
            )
            for category in PROJECT_AUDIT_CATEGORY_ORDER
        }
        for summary in self.categories:
            expected_errors, expected_warnings = findings_by_category[summary.category]
            if (summary.error_count, summary.warning_count) != (
                expected_errors,
                expected_warnings,
            ):
                raise ValueError("project audit category counts must match findings")
            expected_category_state: ProjectAuditState = (
                "blocked" if expected_errors else "needs-review" if expected_warnings else "ready"
            )
            if summary.state != expected_category_state:
                raise ValueError("project audit category state must match findings")
        return self

    @property
    def error_count(self) -> int:
        """Return the number of blocking findings."""
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        """Return the number of review-required findings."""
        return sum(finding.severity == "warning" for finding in self.findings)


def _finding_sort_key(
    finding: ProjectAuditFindingContract,
) -> tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]]:
    return (
        finding.category,
        finding.code,
        finding.subject,
        finding.severity,
        finding.paths,
        finding.related_ids,
    )


def _action_sort_key(
    action: ProjectAuditActionContract,
) -> tuple[str, str, tuple[str, ...]]:
    return action.category, action.code, action.finding_codes


__all__ = [
    "PROJECT_AUDIT_CATEGORY_ORDER",
    "ProjectAuditActionContract",
    "ProjectAuditCategory",
    "ProjectAuditCategoryContract",
    "ProjectAuditFindingContract",
    "ProjectAuditReportContract",
    "ProjectAuditSeverity",
    "ProjectAuditSourceContract",
    "ProjectAuditSourceState",
    "ProjectAuditState",
]
