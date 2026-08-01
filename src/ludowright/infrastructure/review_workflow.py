"""Canonical persistence adapters for the visual review workflow."""

from __future__ import annotations

from ludowright.contracts import ApprovalContract, VisualReferenceContract, VisualReviewContract
from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath
from ludowright.infrastructure.generation_receipts import GENERATED_REFERENCE_DIRECTORY
from ludowright.infrastructure.structured import (
    JsonDocumentRepository,
    StructuredDocumentSnapshot,
)

VISUAL_REVIEW_DIRECTORY = RepositoryPath(".ludowright/visual-reviews")
APPROVAL_DIRECTORY = RepositoryPath(".ludowright/approvals")
VISUAL_REVIEW_LOCK = "visual-review"
VISUAL_REVIEW_MAX_BYTES = 2_000_000


class VisualReviewRepository:
    """Persist review, approval, and generated-reference contracts safely."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("visual review persistence requires ProjectFilesystem")
        self._filesystem = filesystem

    def review_path(self, review_id: str) -> RepositoryPath:
        return VISUAL_REVIEW_DIRECTORY.child(f"{review_id}.json")

    def approval_path(self, approval_id: str) -> RepositoryPath:
        return APPROVAL_DIRECTORY.child(f"{approval_id}.json")

    def reference_path(self, reference_id: str) -> RepositoryPath:
        return GENERATED_REFERENCE_DIRECTORY.child(f"{reference_id}.json")

    def load_review(self, review_id: str) -> StructuredDocumentSnapshot[VisualReviewContract]:
        return self._review_repository(review_id).load()

    def load_review_optional(
        self,
        review_id: str,
    ) -> StructuredDocumentSnapshot[VisualReviewContract] | None:
        return self._review_repository(review_id).load_optional()

    def create_review(
        self, value: VisualReviewContract
    ) -> StructuredDocumentSnapshot[VisualReviewContract]:
        return self._review_repository(value.id).create(value)

    def load_approval(self, approval_id: str) -> StructuredDocumentSnapshot[ApprovalContract]:
        return self._approval_repository(approval_id).load()

    def load_approval_optional(
        self,
        approval_id: str,
    ) -> StructuredDocumentSnapshot[ApprovalContract] | None:
        return self._approval_repository(approval_id).load_optional()

    def create_approval(
        self, value: ApprovalContract
    ) -> StructuredDocumentSnapshot[ApprovalContract]:
        return self._approval_repository(value.id).create(value)

    def replace_approval(
        self,
        snapshot: StructuredDocumentSnapshot[ApprovalContract],
        value: ApprovalContract,
    ) -> StructuredDocumentSnapshot[ApprovalContract]:
        return self._approval_repository(snapshot.value.id).replace(snapshot, value)

    def load_reference(
        self, reference_id: str
    ) -> StructuredDocumentSnapshot[VisualReferenceContract]:
        return self._reference_repository(reference_id).load()

    def replace_reference(
        self,
        snapshot: StructuredDocumentSnapshot[VisualReferenceContract],
        value: VisualReferenceContract,
    ) -> StructuredDocumentSnapshot[VisualReferenceContract]:
        return self._reference_repository(snapshot.value.id).replace(snapshot, value)

    def _review_repository(
        self,
        review_id: str,
    ) -> JsonDocumentRepository[VisualReviewContract]:
        return JsonDocumentRepository(
            self._filesystem,
            self.review_path(review_id),
            VisualReviewContract,
            max_bytes=VISUAL_REVIEW_MAX_BYTES,
        )

    def _approval_repository(
        self,
        approval_id: str,
    ) -> JsonDocumentRepository[ApprovalContract]:
        return JsonDocumentRepository(
            self._filesystem,
            self.approval_path(approval_id),
            ApprovalContract,
            max_bytes=VISUAL_REVIEW_MAX_BYTES,
        )

    def _reference_repository(
        self,
        reference_id: str,
    ) -> JsonDocumentRepository[VisualReferenceContract]:
        return JsonDocumentRepository(
            self._filesystem,
            self.reference_path(reference_id),
            VisualReferenceContract,
            max_bytes=VISUAL_REVIEW_MAX_BYTES,
        )


__all__ = [
    "APPROVAL_DIRECTORY",
    "VISUAL_REVIEW_DIRECTORY",
    "VISUAL_REVIEW_LOCK",
    "VISUAL_REVIEW_MAX_BYTES",
    "VisualReviewRepository",
]
