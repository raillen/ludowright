"""Versioned visual-reference, job, receipt, and review contracts."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    HttpsUriText,
    PositiveRevision,
    RepositoryPathText,
    ReviewText,
    RevisionText,
    Sha256Text,
    Slug,
    UtcTimestampText,
)
from ludowright.contracts.governance import ReviewActorContract
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

    @classmethod
    def from_domain(cls, value: ReferenceProvenance) -> Self:
        return cls(
            origin=value.origin,
            content_revision=value.content_revision.value,
            source_uri=value.source_uri.value if value.source_uri is not None else None,
            source_job_id=value.source_job_id.value if value.source_job_id is not None else None,
            source_receipt_id=(
                value.source_receipt_id.value if value.source_receipt_id is not None else None
            ),
            parent_reference_ids=tuple(item.value for item in value.parent_reference_ids),
            creator=value.creator.value if value.creator is not None else None,
            license_label=value.license_label.value if value.license_label is not None else None,
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

    @classmethod
    def from_domain(cls, value: VisualReference) -> Self:
        return cls(
            id=value.id.value,
            name=value.name.value,
            target=ReferenceTargetContract.from_domain(value.target),
            role=value.role,
            provenance=ReferenceProvenanceContract.from_domain(value.provenance),
            status=value.status,
            approval_id=value.approval_id.value if value.approval_id is not None else None,
            superseded_by=value.superseded_by.value if value.superseded_by is not None else None,
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


class GenerationOutputValidationContract(ContractModel):
    """Bounded validation facts for one persisted generated PNG."""

    format: Literal["png"] = "png"
    animated: Literal[False] = False
    width: Annotated[int, Field(ge=1, le=4_294_967_295)]
    height: Annotated[int, Field(ge=1, le=4_294_967_295)]


class GenerationOutputContract(ContractModel):
    """One generated reference and its exact immutable artifact identity."""

    reference_id: Slug
    role: ReferenceRole
    path: RepositoryPathText
    sha256: Sha256Text
    size_bytes: Annotated[int, Field(ge=1, le=64 * 1024 * 1024)]
    validation: GenerationOutputValidationContract

    @model_validator(mode="after")
    def validate_output(self) -> Self:
        path = PurePosixPath(self.path)
        if (
            path.is_absolute()
            or path.as_posix() != self.path
            or any(segment in {".", ".."} for segment in path.parts)
        ):
            raise ValueError("generation output paths must be normalized relative paths")
        if not self.path.endswith(".png"):
            raise ValueError("generation output paths must use the .png extension")
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
    tool: DisplayText | None = None
    request_revision: RevisionText
    operation_id: Slug | None = None
    prompt_hash: Sha256Text | None = None
    started_at: UtcTimestampText | None = None
    completed_at: UtcTimestampText | None = None
    output_reference_ids: tuple[Slug, ...] = ()
    outputs: Annotated[tuple[GenerationOutputContract, ...], Field(max_length=64)] = ()
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
        if (self.started_at is None) != (self.completed_at is None):
            raise ValueError("generation receipt timestamps must be provided together")
        output_ids = tuple(output.reference_id for output in self.outputs)
        if self.outputs and output_ids != self.output_reference_ids:
            raise ValueError("generation receipt outputs must match its reference IDs")
        if self.outputs and self.status is not ReceiptStatus.SUCCEEDED:
            raise ValueError("only a successful generation receipt may contain output details")
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
    reviewer: ReviewActorContract | None = None
    producer: ReviewActorContract | None = None

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
            reviewer=self.reviewer.to_domain() if self.reviewer is not None else None,
            producer=self.producer.to_domain() if self.producer is not None else None,
        )

    @classmethod
    def from_domain(cls, value: VisualReview) -> Self:
        return cls(
            id=value.id.value,
            receipt_id=value.receipt_id.value,
            outcome=value.outcome,
            reviewed_reference_ids=tuple(item.value for item in value.reviewed_reference_ids),
            note=value.note.value if value.note is not None else None,
            approval_id=value.approval_id.value if value.approval_id is not None else None,
            supersedes=value.supersedes.value if value.supersedes is not None else None,
            reviewer=ReviewActorContract.from_domain(value.reviewer)
            if value.reviewer is not None
            else None,
            producer=ReviewActorContract.from_domain(value.producer)
            if value.producer is not None
            else None,
        )

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        self.to_domain()
        return self
