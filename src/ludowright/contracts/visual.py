"""Versioned visual-reference, job, receipt, and review contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    HttpsUriText,
    PositiveRevision,
    ReviewText,
    RevisionText,
    Slug,
)
from ludowright.domain import (
    ApprovalId,
    AssetId,
    AssetStateId,
    ComponentId,
    DisplayName,
    GenerationReceipt,
    JobId,
    ProfileVersion,
    ReceiptId,
    ReceiptStatus,
    ReferenceId,
    ReferenceOrigin,
    ReferenceProvenance,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    ReviewId,
    ReviewNote,
    SourceUri,
    SubjectRevision,
    VariantId,
    VisualJob,
    VisualReference,
    VisualReview,
    VisualReviewOutcome,
)


class ReferenceTargetContract(ContractModel):
    asset_id: Slug
    component_id: Slug | None = None
    variant_id: Slug | None = None
    state_id: Slug | None = None

    @classmethod
    def from_domain(cls, value: ReferenceTarget) -> Self:
        return cls(
            asset_id=value.asset_id.value,
            component_id=value.component_id.value if value.component_id is not None else None,
            variant_id=value.variant_id.value if value.variant_id is not None else None,
            state_id=value.state_id.value if value.state_id is not None else None,
        )

    def to_domain(self) -> ReferenceTarget:
        return ReferenceTarget(
            asset_id=AssetId(self.asset_id),
            component_id=(
                ComponentId(self.component_id) if self.component_id is not None else None
            ),
            variant_id=(VariantId(self.variant_id) if self.variant_id is not None else None),
            state_id=(AssetStateId(self.state_id) if self.state_id is not None else None),
        )

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        self.to_domain()
        return self


class ReferenceProvenanceContract(ContractModel):
    origin: ReferenceOrigin
    content_revision: RevisionText
    source_uri: HttpsUriText | None = None
    source_job_id: Slug | None = None
    source_receipt_id: Slug | None = None
    parent_reference_ids: tuple[Slug, ...] = ()
    creator: DisplayText | None = None
    license_label: DisplayText | None = None

    def to_domain(self) -> ReferenceProvenance:
        return ReferenceProvenance(
            origin=self.origin,
            content_revision=SubjectRevision(self.content_revision),
            source_uri=SourceUri(self.source_uri) if self.source_uri is not None else None,
            source_job_id=(JobId(self.source_job_id) if self.source_job_id is not None else None),
            source_receipt_id=(
                ReceiptId(self.source_receipt_id) if self.source_receipt_id is not None else None
            ),
            parent_reference_ids=tuple(
                ReferenceId(reference_id) for reference_id in self.parent_reference_ids
            ),
            creator=DisplayName(self.creator) if self.creator is not None else None,
            license_label=(
                DisplayName(self.license_label) if self.license_label is not None else None
            ),
        )

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        self.to_domain()
        return self


class VisualReferenceContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["visual-reference"] = "visual-reference"
    id: Slug
    name: DisplayText
    target: ReferenceTargetContract
    role: ReferenceRole
    provenance: ReferenceProvenanceContract
    status: ReferenceStatus = ReferenceStatus.CANDIDATE
    approval_id: Slug | None = None
    superseded_by: Slug | None = None

    def to_domain(self) -> VisualReference:
        return VisualReference(
            id=ReferenceId(self.id),
            name=DisplayName(self.name),
            target=self.target.to_domain(),
            role=self.role,
            provenance=self.provenance.to_domain(),
            status=self.status,
            approval_id=(ApprovalId(self.approval_id) if self.approval_id is not None else None),
            superseded_by=(
                ReferenceId(self.superseded_by) if self.superseded_by is not None else None
            ),
        )

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        self.to_domain()
        return self


class VisualJobContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["visual-job"] = "visual-job"
    id: Slug
    name: DisplayText
    target: ReferenceTargetContract
    profile_version: PositiveRevision
    request_revision: RevisionText
    input_reference_ids: tuple[Slug, ...]
    output_roles: Annotated[tuple[ReferenceRole, ...], Field(min_length=1)]
    expected_output_count: Annotated[int, Field(ge=1, le=64)]
    supersedes: Slug | None = None

    @classmethod
    def from_domain(cls, value: VisualJob) -> Self:
        return cls(
            id=value.id.value,
            name=value.name.value,
            target=ReferenceTargetContract.from_domain(value.target),
            profile_version=value.profile_version.value,
            request_revision=value.request_revision.value,
            input_reference_ids=tuple(item.value for item in value.input_reference_ids),
            output_roles=value.output_roles,
            expected_output_count=value.expected_output_count,
            supersedes=value.supersedes.value if value.supersedes is not None else None,
        )

    def to_domain(self) -> VisualJob:
        return VisualJob(
            id=JobId(self.id),
            name=DisplayName(self.name),
            target=self.target.to_domain(),
            profile_version=ProfileVersion(self.profile_version),
            request_revision=SubjectRevision(self.request_revision),
            input_reference_ids=tuple(
                ReferenceId(reference_id) for reference_id in self.input_reference_ids
            ),
            output_roles=self.output_roles,
            expected_output_count=self.expected_output_count,
            supersedes=JobId(self.supersedes) if self.supersedes is not None else None,
        )

    @model_validator(mode="after")
    def validate_job(self) -> Self:
        self.to_domain()
        return self


class GenerationReceiptContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["generation-receipt"] = "generation-receipt"
    id: Slug
    job_id: Slug
    attempt: Annotated[int, Field(ge=1, le=100)]
    status: ReceiptStatus
    provider: DisplayText
    model: DisplayText
    request_revision: RevisionText
    output_reference_ids: tuple[Slug, ...] = ()
    failure_note: ReviewText | None = None
    retry_of: Slug | None = None

    def to_domain(self) -> GenerationReceipt:
        return GenerationReceipt(
            id=ReceiptId(self.id),
            job_id=JobId(self.job_id),
            attempt=self.attempt,
            status=self.status,
            provider=DisplayName(self.provider),
            model=DisplayName(self.model),
            request_revision=SubjectRevision(self.request_revision),
            output_reference_ids=tuple(
                ReferenceId(reference_id) for reference_id in self.output_reference_ids
            ),
            failure_note=(ReviewNote(self.failure_note) if self.failure_note is not None else None),
            retry_of=ReceiptId(self.retry_of) if self.retry_of is not None else None,
        )

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        self.to_domain()
        return self


class VisualReviewContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["visual-review"] = "visual-review"
    id: Slug
    receipt_id: Slug
    outcome: VisualReviewOutcome
    reviewed_reference_ids: Annotated[tuple[Slug, ...], Field(min_length=1)]
    note: ReviewText | None = None
    approval_id: Slug | None = None
    supersedes: Slug | None = None

    def to_domain(self) -> VisualReview:
        return VisualReview(
            id=ReviewId(self.id),
            receipt_id=ReceiptId(self.receipt_id),
            outcome=self.outcome,
            reviewed_reference_ids=tuple(
                ReferenceId(reference_id) for reference_id in self.reviewed_reference_ids
            ),
            note=ReviewNote(self.note) if self.note is not None else None,
            approval_id=(ApprovalId(self.approval_id) if self.approval_id is not None else None),
            supersedes=(ReviewId(self.supersedes) if self.supersedes is not None else None),
        )

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        self.to_domain()
        return self
