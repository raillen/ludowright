"""Tests for deterministic visual jobs, receipts, retries, and reviews."""

from __future__ import annotations

import pytest

from ludowright.domain import (
    ApprovalId,
    AssetId,
    DisplayName,
    GenerationReceipt,
    GenerationSeries,
    InvalidGenerationReceiptError,
    InvalidVisualJobError,
    InvalidVisualReviewError,
    JobId,
    ProfileVersion,
    ReceiptId,
    ReceiptStatus,
    ReferenceId,
    ReferenceRole,
    ReferenceTarget,
    ReviewId,
    ReviewNote,
    SubjectRevision,
    VisualJob,
    VisualReview,
    VisualReviewOutcome,
)

REQUEST_REVISION = SubjectRevision("sha256:request123")


def make_job(
    *,
    expected_output_count: int = 2,
    supersedes: JobId | None = None,
) -> VisualJob:
    return VisualJob(
        id=JobId("job-maya-sheet-v1"),
        name=DisplayName("Maya Character Sheet"),
        target=ReferenceTarget(AssetId("chr-maya")),
        profile_version=ProfileVersion(1),
        request_revision=REQUEST_REVISION,
        input_reference_ids=(ReferenceId("ref-maya-identity"),),
        output_roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION),
        expected_output_count=expected_output_count,
        supersedes=supersedes,
    )


def make_receipt(
    *,
    receipt_id: str,
    attempt: int,
    status: ReceiptStatus,
    retry_of: ReceiptId | None = None,
    job_id: JobId | None = None,
    request_revision: SubjectRevision = REQUEST_REVISION,
) -> GenerationReceipt:
    outputs = ()
    failure_note = None
    if status is ReceiptStatus.SUCCEEDED:
        outputs = (
            ReferenceId("ref-maya-sheet-identity"),
            ReferenceId("ref-maya-sheet-construction"),
        )
    elif status is ReceiptStatus.FAILED:
        failure_note = ReviewNote("Provider returned an invalid image response.")

    return GenerationReceipt(
        id=ReceiptId(receipt_id),
        job_id=job_id or JobId("job-maya-sheet-v1"),
        attempt=attempt,
        status=status,
        provider=DisplayName("OpenAI"),
        model=DisplayName("Image Model"),
        request_revision=request_revision,
        output_reference_ids=outputs,
        failure_note=failure_note,
        retry_of=retry_of,
    )


def test_visual_job_preserves_deterministic_contract() -> None:
    job = make_job()

    assert job.profile_version == ProfileVersion(1)
    assert job.request_revision == REQUEST_REVISION
    assert job.expected_output_count == 2
    assert len(job.output_roles) == 2


def test_job_input_references_must_be_immutable_and_unique() -> None:
    with pytest.raises(InvalidVisualJobError, match="immutable tuple"):
        VisualJob(
            id=JobId("job-invalid-list"),
            name=DisplayName("Invalid List"),
            target=ReferenceTarget(AssetId("chr-maya")),
            profile_version=ProfileVersion(1),
            request_revision=REQUEST_REVISION,
            input_reference_ids=[ReferenceId("ref-one")],  # type: ignore[arg-type]
            output_roles=(ReferenceRole.OUTPUT,),
            expected_output_count=1,
        )

    with pytest.raises(InvalidVisualJobError, match="must be unique"):
        VisualJob(
            id=JobId("job-duplicate-input"),
            name=DisplayName("Duplicate Input"),
            target=ReferenceTarget(AssetId("chr-maya")),
            profile_version=ProfileVersion(1),
            request_revision=REQUEST_REVISION,
            input_reference_ids=(ReferenceId("ref-one"), ReferenceId("ref-one")),
            output_roles=(ReferenceRole.OUTPUT,),
            expected_output_count=1,
        )


def test_job_output_count_matches_declared_roles() -> None:
    with pytest.raises(InvalidVisualJobError, match="describe every expected"):
        make_job(expected_output_count=1)

    with pytest.raises(InvalidVisualJobError, match="between 1"):
        make_job(expected_output_count=0)


def test_visual_job_cannot_supersede_itself() -> None:
    with pytest.raises(InvalidVisualJobError, match="supersede itself"):
        make_job(supersedes=JobId("job-maya-sheet-v1"))


def test_successful_receipt_requires_outputs_without_failure_note() -> None:
    receipt = make_receipt(
        receipt_id="receipt-maya-1",
        attempt=1,
        status=ReceiptStatus.SUCCEEDED,
    )

    assert len(receipt.output_reference_ids) == 2

    with pytest.raises(InvalidGenerationReceiptError, match="requires generated"):
        GenerationReceipt(
            id=ReceiptId("receipt-empty-success"),
            job_id=JobId("job-maya-sheet-v1"),
            attempt=1,
            status=ReceiptStatus.SUCCEEDED,
            provider=DisplayName("OpenAI"),
            model=DisplayName("Image Model"),
            request_revision=REQUEST_REVISION,
        )


def test_failed_receipt_requires_failure_note_and_no_outputs() -> None:
    with pytest.raises(InvalidGenerationReceiptError, match="requires a failure note"):
        GenerationReceipt(
            id=ReceiptId("receipt-failed-no-note"),
            job_id=JobId("job-maya-sheet-v1"),
            attempt=1,
            status=ReceiptStatus.FAILED,
            provider=DisplayName("OpenAI"),
            model=DisplayName("Image Model"),
            request_revision=REQUEST_REVISION,
        )

    with pytest.raises(InvalidGenerationReceiptError, match="only a successful"):
        GenerationReceipt(
            id=ReceiptId("receipt-failed-output"),
            job_id=JobId("job-maya-sheet-v1"),
            attempt=1,
            status=ReceiptStatus.FAILED,
            provider=DisplayName("OpenAI"),
            model=DisplayName("Image Model"),
            request_revision=REQUEST_REVISION,
            output_reference_ids=(ReferenceId("ref-invalid"),),
            failure_note=ReviewNote("Failed."),
        )


def test_retry_receipt_requires_previous_receipt_id() -> None:
    with pytest.raises(InvalidGenerationReceiptError, match="requires the previous"):
        make_receipt(
            receipt_id="receipt-maya-2",
            attempt=2,
            status=ReceiptStatus.CANCELLED,
        )

    with pytest.raises(InvalidGenerationReceiptError, match="first attempt"):
        make_receipt(
            receipt_id="receipt-maya-1",
            attempt=1,
            status=ReceiptStatus.CANCELLED,
            retry_of=ReceiptId("receipt-previous"),
        )


def test_generation_series_retries_failed_attempt_then_succeeds() -> None:
    job = make_job()
    first = make_receipt(
        receipt_id="receipt-maya-1",
        attempt=1,
        status=ReceiptStatus.FAILED,
    )
    second = make_receipt(
        receipt_id="receipt-maya-2",
        attempt=2,
        status=ReceiptStatus.SUCCEEDED,
        retry_of=first.id,
    )

    series = GenerationSeries(job).append(first).append(second)

    assert series.current == second
    assert series.succeeded is True
    assert len(series.receipts) == 2


def test_generation_series_rejects_non_contiguous_or_wrong_retry() -> None:
    first = make_receipt(
        receipt_id="receipt-maya-1",
        attempt=1,
        status=ReceiptStatus.FAILED,
    )
    wrong_retry = make_receipt(
        receipt_id="receipt-maya-2",
        attempt=2,
        status=ReceiptStatus.CANCELLED,
        retry_of=ReceiptId("receipt-other"),
    )

    with pytest.raises(InvalidGenerationReceiptError, match="immediately previous"):
        GenerationSeries(make_job(), (first, wrong_retry))

    skipped = make_receipt(
        receipt_id="receipt-maya-3",
        attempt=3,
        status=ReceiptStatus.CANCELLED,
        retry_of=first.id,
    )
    with pytest.raises(InvalidGenerationReceiptError, match="contiguous"):
        GenerationSeries(make_job(), (first, skipped))


def test_successful_series_cannot_be_retried() -> None:
    first = make_receipt(
        receipt_id="receipt-maya-1",
        attempt=1,
        status=ReceiptStatus.SUCCEEDED,
    )
    retry = make_receipt(
        receipt_id="receipt-maya-2",
        attempt=2,
        status=ReceiptStatus.CANCELLED,
        retry_of=first.id,
    )

    with pytest.raises(InvalidGenerationReceiptError, match="cannot be retried"):
        GenerationSeries(make_job(), (first, retry))


def test_series_receipts_must_match_job_revision_and_output_count() -> None:
    wrong_revision = make_receipt(
        receipt_id="receipt-wrong-revision",
        attempt=1,
        status=ReceiptStatus.CANCELLED,
        request_revision=SubjectRevision("sha256:other-request"),
    )
    with pytest.raises(InvalidGenerationReceiptError, match="revision must match"):
        GenerationSeries(make_job(), (wrong_revision,))

    one_output = GenerationReceipt(
        id=ReceiptId("receipt-one-output"),
        job_id=JobId("job-maya-sheet-v1"),
        attempt=1,
        status=ReceiptStatus.SUCCEEDED,
        provider=DisplayName("OpenAI"),
        model=DisplayName("Image Model"),
        request_revision=REQUEST_REVISION,
        output_reference_ids=(ReferenceId("ref-one-output"),),
    )
    with pytest.raises(InvalidGenerationReceiptError, match="output count"):
        GenerationSeries(make_job(), (one_output,))


def test_accepted_review_requires_approval_record() -> None:
    output = ReferenceId("ref-maya-sheet-identity")

    review = VisualReview(
        id=ReviewId("review-maya-1"),
        receipt_id=ReceiptId("receipt-maya-1"),
        outcome=VisualReviewOutcome.ACCEPTED,
        reviewed_reference_ids=(output,),
        approval_id=ApprovalId("approval-maya-output"),
    )
    assert review.approval_id == ApprovalId("approval-maya-output")

    with pytest.raises(InvalidVisualReviewError, match="requires an approval"):
        VisualReview(
            id=ReviewId("review-maya-invalid"),
            receipt_id=ReceiptId("receipt-maya-1"),
            outcome=VisualReviewOutcome.ACCEPTED,
            reviewed_reference_ids=(output,),
        )


def test_changes_requested_and_rejected_reviews_require_notes() -> None:
    output = ReferenceId("ref-maya-sheet-identity")

    with pytest.raises(InvalidVisualReviewError, match="require a note"):
        VisualReview(
            id=ReviewId("review-maya-changes"),
            receipt_id=ReceiptId("receipt-maya-1"),
            outcome=VisualReviewOutcome.CHANGES_REQUESTED,
            reviewed_reference_ids=(output,),
        )

    rejected = VisualReview(
        id=ReviewId("review-maya-rejected"),
        receipt_id=ReceiptId("receipt-maya-1"),
        outcome=VisualReviewOutcome.REJECTED,
        reviewed_reference_ids=(output,),
        note=ReviewNote("The face no longer matches the approved identity."),
    )
    assert rejected.outcome is VisualReviewOutcome.REJECTED


def test_generation_series_validates_reviewed_outputs() -> None:
    receipt = make_receipt(
        receipt_id="receipt-maya-1",
        attempt=1,
        status=ReceiptStatus.SUCCEEDED,
    )
    series = GenerationSeries(make_job(), (receipt,))
    review = VisualReview(
        id=ReviewId("review-maya-1"),
        receipt_id=receipt.id,
        outcome=VisualReviewOutcome.ACCEPTED,
        reviewed_reference_ids=(receipt.output_reference_ids[0],),
        approval_id=ApprovalId("approval-maya-output"),
    )

    assert series.validate_review(review) is review

    unrelated = VisualReview(
        id=ReviewId("review-unrelated"),
        receipt_id=receipt.id,
        outcome=VisualReviewOutcome.REJECTED,
        reviewed_reference_ids=(ReferenceId("ref-unrelated"),),
        note=ReviewNote("Unrelated output."),
    )
    with pytest.raises(InvalidVisualReviewError, match="must come from"):
        series.validate_review(unrelated)


def test_visual_review_cannot_supersede_itself() -> None:
    with pytest.raises(InvalidVisualReviewError, match="supersede itself"):
        VisualReview(
            id=ReviewId("review-self"),
            receipt_id=ReceiptId("receipt-maya-1"),
            outcome=VisualReviewOutcome.REJECTED,
            reviewed_reference_ids=(ReferenceId("ref-output"),),
            note=ReviewNote("Rejected."),
            supersedes=ReviewId("review-self"),
        )
