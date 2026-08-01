"""Versioned decision and approval serialization contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    ReviewText,
    RevisionText,
    Slug,
)
from ludowright.domain import (
    Approval,
    ApprovalId,
    ApprovalRevision,
    ApprovalStatus,
    ApprovalSubject,
    AssetId,
    AssetStateId,
    CaptureProfileId,
    CaptureSheetId,
    CaptureViewId,
    ComponentId,
    Decision,
    DecisionId,
    DecisionRevision,
    DecisionStatus,
    DisplayName,
    Identifier,
    JobId,
    OwnerId,
    PackageId,
    ProjectId,
    ReceiptId,
    ReferenceId,
    ReviewActor,
    ReviewerKind,
    ReviewId,
    ReviewNote,
    SubjectRevision,
    VariantId,
)


class ApprovalSubjectKind(StrEnum):
    PROJECT = "project"
    ASSET = "asset"
    COMPONENT = "component"
    VARIANT = "variant"
    ASSET_STATE = "asset-state"
    REFERENCE = "reference"
    JOB = "job"
    RECEIPT = "receipt"
    REVIEW = "review"
    CAPTURE_PROFILE = "capture-profile"
    CAPTURE_VIEW = "capture-view"
    CAPTURE_SHEET = "capture-sheet"
    DECISION = "decision"
    PACKAGE = "package"


_SUBJECT_ID_TYPES: dict[ApprovalSubjectKind, type[Identifier]] = {
    ApprovalSubjectKind.PROJECT: ProjectId,
    ApprovalSubjectKind.ASSET: AssetId,
    ApprovalSubjectKind.COMPONENT: ComponentId,
    ApprovalSubjectKind.VARIANT: VariantId,
    ApprovalSubjectKind.ASSET_STATE: AssetStateId,
    ApprovalSubjectKind.REFERENCE: ReferenceId,
    ApprovalSubjectKind.JOB: JobId,
    ApprovalSubjectKind.RECEIPT: ReceiptId,
    ApprovalSubjectKind.REVIEW: ReviewId,
    ApprovalSubjectKind.CAPTURE_PROFILE: CaptureProfileId,
    ApprovalSubjectKind.CAPTURE_VIEW: CaptureViewId,
    ApprovalSubjectKind.CAPTURE_SHEET: CaptureSheetId,
    ApprovalSubjectKind.DECISION: DecisionId,
    ApprovalSubjectKind.PACKAGE: PackageId,
}


def _review_note(value: str | None) -> ReviewNote | None:
    return ReviewNote(value) if value is not None else None


class ReviewActorContract(ContractModel):
    """Persisted review participant identity used by the policy boundary."""

    id: Slug
    kind: ReviewerKind

    def to_domain(self) -> ReviewActor:
        return ReviewActor(id=OwnerId(self.id), kind=self.kind)

    @classmethod
    def from_domain(cls, value: ReviewActor) -> Self:
        return cls(id=value.id.value, kind=value.kind)


class DecisionRevisionContract(ContractModel):
    sequence: Annotated[int, Field(ge=1)]
    status: DecisionStatus
    note: ReviewText | None = None
    superseded_by: Slug | None = None

    def to_domain(self) -> DecisionRevision:
        return DecisionRevision(
            sequence=self.sequence,
            status=self.status,
            note=_review_note(self.note),
            superseded_by=(
                DecisionId(self.superseded_by) if self.superseded_by is not None else None
            ),
        )


class DecisionContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["decision"] = "decision"
    id: Slug
    title: DisplayText
    history: Annotated[tuple[DecisionRevisionContract, ...], Field(min_length=1)]

    def to_domain(self) -> Decision:
        return Decision(
            id=DecisionId(self.id),
            title=DisplayName(self.title),
            history=tuple(revision.to_domain() for revision in self.history),
        )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        self.to_domain()
        return self


class ApprovalSubjectContract(ContractModel):
    subject_kind: ApprovalSubjectKind
    id: Slug
    revision: RevisionText
    label: DisplayText | None = None

    id_types: ClassVar[dict[ApprovalSubjectKind, type[Identifier]]] = _SUBJECT_ID_TYPES

    def to_domain(self) -> ApprovalSubject:
        identifier_type = self.id_types[self.subject_kind]
        return ApprovalSubject(
            id=identifier_type(self.id),
            revision=SubjectRevision(self.revision),
            label=DisplayName(self.label) if self.label is not None else None,
        )

    @classmethod
    def from_domain(cls, value: ApprovalSubject) -> Self:
        return cls(
            subject_kind=ApprovalSubjectKind(value.id.kind),
            id=value.id.value,
            revision=value.revision.value,
            label=value.label.value if value.label is not None else None,
        )


class ApprovalRevisionContract(ContractModel):
    sequence: Annotated[int, Field(ge=1)]
    status: ApprovalStatus
    note: ReviewText | None = None
    superseded_by: Slug | None = None

    def to_domain(self) -> ApprovalRevision:
        return ApprovalRevision(
            sequence=self.sequence,
            status=self.status,
            note=_review_note(self.note),
            superseded_by=(
                ApprovalId(self.superseded_by) if self.superseded_by is not None else None
            ),
        )

    @classmethod
    def from_domain(cls, value: ApprovalRevision) -> Self:
        return cls(
            sequence=value.sequence,
            status=value.status,
            note=value.note.value if value.note is not None else None,
            superseded_by=(value.superseded_by.value if value.superseded_by is not None else None),
        )


class ApprovalContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["approval"] = "approval"
    id: Slug
    subject: ApprovalSubjectContract
    history: Annotated[tuple[ApprovalRevisionContract, ...], Field(min_length=1)]

    def to_domain(self) -> Approval:
        return Approval(
            id=ApprovalId(self.id),
            subject=self.subject.to_domain(),
            history=tuple(revision.to_domain() for revision in self.history),
        )

    @classmethod
    def from_domain(cls, value: Approval) -> Self:
        return cls(
            id=value.id.value,
            subject=ApprovalSubjectContract.from_domain(value.subject),
            history=tuple(ApprovalRevisionContract.from_domain(item) for item in value.history),
        )

    @model_validator(mode="after")
    def validate_approval(self) -> Self:
        self.to_domain()
        return self
