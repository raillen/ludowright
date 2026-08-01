"""Published contracts for deterministic local release verification."""

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
from ludowright.contracts.project_audit import (
    ProjectAuditFindingContract,
    ProjectAuditState,
)

ReleaseWarningPolicy = Literal["block", "allow"]
ReleaseVerificationState = Literal["ready", "ready-with-warnings", "blocked"]
ReleaseGateState = Literal["passed", "warning", "failed"]
ReleaseArtifactKind = Literal["package-manifest", "package-index", "package-archive"]
ReleaseManifestState = Literal["planned", "created", "unchanged", "not-created"]

RELEASE_ARTIFACT_KIND_ORDER: tuple[ReleaseArtifactKind, ...] = (
    "package-manifest",
    "package-index",
    "package-archive",
)


class ReleaseArtifactContract(ContractModel):
    """One release artifact and its exact SHA-256 identity."""

    kind: ReleaseArtifactKind
    path: PackagePathText
    size_bytes: NonNegativeRevision
    sha256: Sha256Text


class ReleaseManifestContract(ContractModel):
    """Checksum-verifiable manifest prepared beside a local package release."""

    schema_version: Literal[1] = 1
    kind: Literal["release-manifest"] = "release-manifest"
    project_id: Slug
    package_id: Slug
    release_directory: PackagePathText
    release_manifest_path: PackagePathText
    integrity: Literal["sha256"] = "sha256"
    archive_member_count: NonNegativeRevision
    artifacts: Annotated[tuple[ReleaseArtifactContract, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        kinds = tuple(item.kind for item in self.artifacts)
        if kinds != RELEASE_ARTIFACT_KIND_ORDER:
            raise ValueError("release manifest artifacts must use canonical order")
        paths = tuple(item.path for item in self.artifacts)
        if len(set(paths)) != len(paths):
            raise ValueError("release manifest artifact paths must be unique")
        if self.release_manifest_path in paths:
            raise ValueError("release manifest cannot describe itself as an artifact")
        if not self.release_manifest_path.startswith(f"{self.release_directory}/"):
            raise ValueError("release manifest must remain inside its release directory")
        return self


class ReleaseGateContract(ContractModel):
    """One deterministic release gate result."""

    code: Slug
    state: ReleaseGateState
    detail: ReviewText
    paths: Annotated[tuple[PackagePathText, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        if self.paths != tuple(sorted(self.paths)):
            raise ValueError("release gate paths must be sorted")
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("release gate paths must be unique")
        return self


class ReleaseSummaryContract(ContractModel):
    """Stable summary projections for human and automation consumers."""

    artifact_count: NonNegativeRevision
    archive_member_count: NonNegativeRevision
    archive_size_bytes: NonNegativeRevision
    audit_error_count: NonNegativeRevision
    audit_warning_count: NonNegativeRevision
    gate_count: NonNegativeRevision


class ReleaseVerificationReportContract(ContractModel):
    """Published result of local project and package release verification."""

    schema_version: Literal[1] = 1
    kind: Literal["release-verification"] = "release-verification"
    dry_run: bool
    project_id: Slug
    project_name: DisplayText
    package_id: Slug
    release_directory: PackagePathText
    release_manifest_path: PackagePathText
    warning_policy: ReleaseWarningPolicy
    audit_state: ProjectAuditState
    audit_source_digest: Sha256Text
    state: ReleaseVerificationState
    valid: bool
    manifest_state: ReleaseManifestState
    summary: ReleaseSummaryContract
    gates: Annotated[tuple[ReleaseGateContract, ...], Field(max_length=32)]
    audit_findings: Annotated[
        tuple[ProjectAuditFindingContract, ...], Field(max_length=100_000)
    ] = ()
    release_manifest: ReleaseManifestContract | None = None

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        gate_codes = tuple(gate.code for gate in self.gates)
        if len(set(gate_codes)) != len(gate_codes):
            raise ValueError("release gate codes must be unique")
        if gate_codes != tuple(sorted(gate_codes)):
            raise ValueError("release gates must be sorted")

        if tuple(sorted(self.audit_findings, key=_finding_sort_key)) != self.audit_findings:
            raise ValueError("release audit findings must be sorted")

        errors = sum(finding.severity == "error" for finding in self.audit_findings)
        warnings = sum(finding.severity == "warning" for finding in self.audit_findings)
        failed_gates = sum(gate.state == "failed" for gate in self.gates)
        warning_gates = sum(gate.state == "warning" for gate in self.gates)
        effective_failures = failed_gates + (warning_gates if self.warning_policy == "block" else 0)
        expected_state: ReleaseVerificationState = (
            "blocked" if effective_failures else "ready-with-warnings" if warning_gates else "ready"
        )
        if self.state != expected_state:
            raise ValueError("release verification state must match gates and warning policy")
        if self.valid != (self.state != "blocked"):
            raise ValueError("release verification validity must match its state")
        if self.audit_state == "blocked" and not any(
            gate.code == "project-audit" and gate.state == "failed" for gate in self.gates
        ):
            raise ValueError("blocked project audits require a failed project-audit gate")
        if self.audit_state == "needs-review" and not any(
            gate.code == "project-audit" and gate.state == "warning" for gate in self.gates
        ):
            raise ValueError("review-required audits require a warning project-audit gate")

        if self.summary.gate_count != len(self.gates):
            raise ValueError("release summary gate count must match gates")
        if self.summary.audit_error_count != errors:
            raise ValueError("release summary error count must match audit findings")
        if self.summary.audit_warning_count != warnings:
            raise ValueError("release summary warning count must match audit findings")
        artifact_count = len(self.release_manifest.artifacts) if self.release_manifest else 0
        archive_member_count = (
            self.release_manifest.archive_member_count if self.release_manifest else 0
        )
        archive_size_bytes = 0
        if self.release_manifest:
            archive_size_bytes = next(
                item.size_bytes
                for item in self.release_manifest.artifacts
                if item.kind == "package-archive"
            )
        if self.summary.artifact_count != artifact_count:
            raise ValueError("release summary artifact count must match the manifest")
        if self.summary.archive_member_count != archive_member_count:
            raise ValueError("release summary member count must match the manifest")
        if self.summary.archive_size_bytes != archive_size_bytes:
            raise ValueError("release summary archive size must match the manifest")

        if self.release_manifest is not None:
            if self.release_manifest.project_id != self.project_id:
                raise ValueError("release manifest project must match the report")
            if self.release_manifest.package_id != self.package_id:
                raise ValueError("release manifest package must match the report")
            if self.release_manifest.release_directory != self.release_directory:
                raise ValueError("release manifest directory must match the report")
            if self.release_manifest.release_manifest_path != self.release_manifest_path:
                raise ValueError("release manifest path must match the report")
        if self.valid and self.release_manifest is None:
            raise ValueError("a valid release verification requires a release manifest")
        if self.valid and self.manifest_state == "not-created":
            raise ValueError("a valid release verification requires a prepared manifest state")
        return self


__all__ = [
    "RELEASE_ARTIFACT_KIND_ORDER",
    "ReleaseArtifactContract",
    "ReleaseArtifactKind",
    "ReleaseGateContract",
    "ReleaseGateState",
    "ReleaseManifestContract",
    "ReleaseManifestState",
    "ReleaseSummaryContract",
    "ReleaseVerificationReportContract",
    "ReleaseVerificationState",
    "ReleaseWarningPolicy",
]


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
