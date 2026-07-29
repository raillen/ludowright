"""Deterministic visual jobs, generation receipts, retries, and reviews."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from ludowright.domain.errors import (
    InvalidGenerationReceiptError,
    InvalidVisualJobError,
    InvalidVisualReviewError,
)
from ludowright.domain.governance import ReviewNote, SubjectRevision
from ludowright.domain.identifiers import (
    ApprovalId,
    JobId,
    ReceiptId,
    ReferenceId,
    ReviewId,
)
from ludowright.domain.names import DisplayName
from ludowright.domain.references import ReferenceRole, ReferenceTarget
from ludowright.domain.versions import ProfileVersion

MAX_EXPECTED_OUTPUTS = 64
MAX_ATTEMPTS = 100


class ReceiptStatus(StrEnum):
    """Terminal result of one generation attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VisualReviewOutcome(StrEnum):
    """Human review outcome for generated visual outputs."""

    ACCEPTED = "accepted"
    CHANGES_REQUESTED = "changes-requested"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class VisualJob:
    """An immutable generation specification that may be retried unchanged."""

    id: JobId
    name: DisplayName
    target: ReferenceTarget
    profile_version: ProfileVersion
    request_revision: SubjectRevision
    input_reference_ids: tuple[ReferenceId, ...]
    output_roles: tuple[ReferenceRole, ...]
    expected_output_count: int
    supersedes: JobId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, JobId):
            raise InvalidVisualJobError("a visual job requires a typed job ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidVisualJobError("a visual job name must be canonical")
        if not isinstance(self.target, ReferenceTarget):
            raise InvalidVisualJobError("a visual job requires a canonical target")
        if not isinstance(self.profile_version, ProfileVersion):
            raise InvalidVisualJobError("a visual job requires a profile version")
        if not isinstance(self.request_revision, SubjectRevision):
            raise InvalidVisualJobError("a visual job requires a request revision")
        self._validate_reference_inputs()
        self._validate_outputs()
        if self.supersedes is not None and not isinstance(self.supersedes, JobId):
            raise InvalidVisualJobError("a superseded job ID must be typed")
        if self.supersedes == self.id:
            raise InvalidVisualJobError("a visual job cannot supersede itself")

    def _validate_reference_inputs(self) -> None:
        if not isinstance(self.input_reference_ids, tuple):
            raise InvalidVisualJobError("job input references must be an immutable tuple")
        if any(
            not isinstance(reference_id, ReferenceId) for reference_id in self.input_reference_ids
        ):
            raise InvalidVisualJobError("job input references must use typed IDs")
        if len(self.input_reference_ids) != len(set(self.input_reference_ids)):
            raise InvalidVisualJobError("job input references must be unique")

    def _validate_outputs(self) -> None:
        if not isinstance(self.output_roles, tuple) or not self.output_roles:
            raise InvalidVisualJobError("a visual job requires output roles")
        if any(not isinstance(role, ReferenceRole) for role in self.output_roles):
            raise InvalidVisualJobError("visual job output roles must be canonical")
        if isinstance(self.expected_output_count, bool) or not isinstance(
            self.expected_output_count, int
        ):
            raise InvalidVisualJobError("expected output count must be an integer")
        if not 1 <= self.expected_output_count <= MAX_EXPECTED_OUTPUTS:
            raise InvalidVisualJobError(
                f"expected output count must be between 1 and {MAX_EXPECTED_OUTPUTS}"
            )
        if len(self.output_roles) != self.expected_output_count:
            raise InvalidVisualJobError(
                "output roles must describe every expected generated output"
            )


@dataclass(frozen=True, slots=True)
class GenerationReceipt:
    """An immutable receipt for one terminal generation attempt."""

    id: ReceiptId
    job_id: JobId
    attempt: int
    status: ReceiptStatus
    provider: DisplayName
    model: DisplayName
    request_revision: SubjectRevision
    output_reference_ids: tuple[ReferenceId, ...] = ()
    failure_note: ReviewNote | None = None
    retry_of: ReceiptId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ReceiptId):
            raise InvalidGenerationReceiptError("a receipt requires a typed ID")
        if not isinstance(self.job_id, JobId):
            raise InvalidGenerationReceiptError("a receipt requires a typed job ID")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int):
            raise InvalidGenerationReceiptError("receipt attempt must be an integer")
        if not 1 <= self.attempt <= MAX_ATTEMPTS:
            raise InvalidGenerationReceiptError(
                f"receipt attempt must be between 1 and {MAX_ATTEMPTS}"
            )
        if not isinstance(self.status, ReceiptStatus):
            raise InvalidGenerationReceiptError("a receipt requires a valid status")
        if not isinstance(self.provider, DisplayName):
            raise InvalidGenerationReceiptError("receipt provider must be canonical")
        if not isinstance(self.model, DisplayName):
            raise InvalidGenerationReceiptError("receipt model must be canonical")
        if not isinstance(self.request_revision, SubjectRevision):
            raise InvalidGenerationReceiptError("receipt request revision must be canonical")
        self._validate_outputs()
        self._validate_retry()

    def _validate_outputs(self) -> None:
        if not isinstance(self.output_reference_ids, tuple):
            raise InvalidGenerationReceiptError(
                "receipt output references must be an immutable tuple"
            )
        if any(
            not isinstance(reference_id, ReferenceId) for reference_id in self.output_reference_ids
        ):
            raise InvalidGenerationReceiptError("receipt output references must use typed IDs")
        if len(self.output_reference_ids) != len(set(self.output_reference_ids)):
            raise InvalidGenerationReceiptError("receipt output references must be unique")
        if self.status is ReceiptStatus.SUCCEEDED:
            if not self.output_reference_ids:
                raise InvalidGenerationReceiptError(
                    "a successful receipt requires generated outputs"
                )
            if self.failure_note is not None:
                raise InvalidGenerationReceiptError(
                    "a successful receipt cannot contain a failure note"
                )
        elif self.output_reference_ids:
            raise InvalidGenerationReceiptError(
                "only a successful receipt may contain generated outputs"
            )
        elif self.status is ReceiptStatus.FAILED and self.failure_note is None:
            raise InvalidGenerationReceiptError("a failed receipt requires a failure note")

    def _validate_retry(self) -> None:
        if self.attempt == 1:
            if self.retry_of is not None:
                raise InvalidGenerationReceiptError("the first attempt cannot be a retry")
        else:
            if not isinstance(self.retry_of, ReceiptId):
                raise InvalidGenerationReceiptError(
                    "a retry attempt requires the previous receipt ID"
                )
            if self.retry_of == self.id:
                raise InvalidGenerationReceiptError("a receipt cannot retry itself")


@dataclass(frozen=True, slots=True)
class GenerationSeries:
    """A job and its contiguous append-only generation attempts."""

    job: VisualJob
    receipts: tuple[GenerationReceipt, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.job, VisualJob):
            raise InvalidGenerationReceiptError("a generation series requires a visual job")
        if not isinstance(self.receipts, tuple):
            raise InvalidGenerationReceiptError("generation receipts must be an immutable tuple")
        if any(not isinstance(receipt, GenerationReceipt) for receipt in self.receipts):
            raise InvalidGenerationReceiptError("generation series contains an invalid receipt")
        self._validate_receipt_history()

    def _validate_receipt_history(self) -> None:
        seen_ids: set[ReceiptId] = set()
        previous: GenerationReceipt | None = None
        for expected_attempt, receipt in enumerate(self.receipts, start=1):
            if receipt.id in seen_ids:
                raise InvalidGenerationReceiptError("receipt IDs must be unique")
            seen_ids.add(receipt.id)
            if receipt.job_id != self.job.id:
                raise InvalidGenerationReceiptError("every receipt must belong to the series job")
            if receipt.request_revision != self.job.request_revision:
                raise InvalidGenerationReceiptError("receipt request revision must match the job")
            if (
                receipt.status is ReceiptStatus.SUCCEEDED
                and len(receipt.output_reference_ids) != self.job.expected_output_count
            ):
                raise InvalidGenerationReceiptError(
                    "successful receipt output count must match the job"
                )
            if receipt.attempt != expected_attempt:
                raise InvalidGenerationReceiptError(
                    "generation receipt attempts must be contiguous"
                )
            if previous is not None:
                if previous.status is ReceiptStatus.SUCCEEDED:
                    raise InvalidGenerationReceiptError(
                        "a successful generation series cannot be retried"
                    )
                if receipt.retry_of != previous.id:
                    raise InvalidGenerationReceiptError(
                        "a retry must reference the immediately previous receipt"
                    )
            previous = receipt

    @property
    def current(self) -> GenerationReceipt | None:
        """Return the most recent terminal attempt, if any."""
        return self.receipts[-1] if self.receipts else None

    @property
    def succeeded(self) -> bool:
        """Return whether the series ended in a successful attempt."""
        return self.current is not None and self.current.status is ReceiptStatus.SUCCEEDED

    def append(self, receipt: GenerationReceipt) -> Self:
        """Append the next valid terminal attempt."""
        if not isinstance(receipt, GenerationReceipt):
            raise InvalidGenerationReceiptError("only a receipt may be appended")
        return type(self)(job=self.job, receipts=(*self.receipts, receipt))

    def validate_review(self, review: VisualReview) -> VisualReview:
        """Validate that a review names exact outputs from a successful receipt."""
        if not isinstance(review, VisualReview):
            raise InvalidVisualReviewError("generation series requires a visual review")
        receipt = next(
            (item for item in self.receipts if item.id == review.receipt_id),
            None,
        )
        if receipt is None:
            raise InvalidVisualReviewError(
                "visual review receipt does not belong to the generation series"
            )
        if receipt.status is not ReceiptStatus.SUCCEEDED:
            raise InvalidVisualReviewError("only successful generation outputs may be reviewed")
        if not set(review.reviewed_reference_ids).issubset(receipt.output_reference_ids):
            raise InvalidVisualReviewError(
                "visual review references must come from the named receipt"
            )
        return review


@dataclass(frozen=True, slots=True)
class VisualReview:
    """A human review of exact output references from one receipt."""

    id: ReviewId
    receipt_id: ReceiptId
    outcome: VisualReviewOutcome
    reviewed_reference_ids: tuple[ReferenceId, ...]
    note: ReviewNote | None = None
    approval_id: ApprovalId | None = None
    supersedes: ReviewId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ReviewId):
            raise InvalidVisualReviewError("a visual review requires a typed ID")
        if not isinstance(self.receipt_id, ReceiptId):
            raise InvalidVisualReviewError("a visual review requires a receipt ID")
        if not isinstance(self.outcome, VisualReviewOutcome):
            raise InvalidVisualReviewError("a visual review requires a valid outcome")
        self._validate_reviewed_outputs()
        if self.supersedes is not None and not isinstance(self.supersedes, ReviewId):
            raise InvalidVisualReviewError("a superseded review ID must be typed")
        if self.supersedes == self.id:
            raise InvalidVisualReviewError("a visual review cannot supersede itself")
        self._validate_outcome_contract()

    def _validate_reviewed_outputs(self) -> None:
        if not isinstance(self.reviewed_reference_ids, tuple):
            raise InvalidVisualReviewError("reviewed references must be an immutable tuple")
        if not self.reviewed_reference_ids:
            raise InvalidVisualReviewError("a visual review requires output references")
        if any(
            not isinstance(reference_id, ReferenceId)
            for reference_id in self.reviewed_reference_ids
        ):
            raise InvalidVisualReviewError("reviewed references must use typed IDs")
        if len(self.reviewed_reference_ids) != len(set(self.reviewed_reference_ids)):
            raise InvalidVisualReviewError("reviewed reference IDs must be unique")

    def _validate_outcome_contract(self) -> None:
        if self.outcome is VisualReviewOutcome.ACCEPTED:
            if not isinstance(self.approval_id, ApprovalId):
                raise InvalidVisualReviewError(
                    "an accepted visual review requires an approval record"
                )
            if self.note is not None and not isinstance(self.note, ReviewNote):
                raise InvalidVisualReviewError("visual review note must be canonical")
        else:
            if not isinstance(self.note, ReviewNote):
                raise InvalidVisualReviewError(
                    "changes-requested and rejected reviews require a note"
                )
            if self.approval_id is not None:
                raise InvalidVisualReviewError(
                    "only an accepted visual review may name an approval"
                )
