"""Tests for visual reference provenance, status, and replacement rules."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ludowright.domain import (
    ApprovalId,
    AssetId,
    ComponentId,
    DisplayName,
    InvalidReferenceError,
    InvalidReferenceTransitionError,
    JobId,
    ReceiptId,
    ReferenceId,
    ReferenceOrigin,
    ReferenceProvenance,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    SourceUri,
    SubjectRevision,
    VariantId,
    VisualReference,
)


def external_provenance() -> ReferenceProvenance:
    return ReferenceProvenance(
        origin=ReferenceOrigin.EXTERNAL,
        content_revision=SubjectRevision("sha256:external123"),
        source_uri=SourceUri("https://example.com/reference.png"),
        creator=DisplayName("Example Artist"),
        license_label=DisplayName("Licensed Reference"),
    )


def make_reference(
    *,
    status: ReferenceStatus = ReferenceStatus.CANDIDATE,
    approval_id: ApprovalId | None = None,
    superseded_by: ReferenceId | None = None,
    provenance: ReferenceProvenance | None = None,
) -> VisualReference:
    return VisualReference(
        id=ReferenceId("ref-maya-identity"),
        name=DisplayName("Maya Identity Reference"),
        target=ReferenceTarget(AssetId("chr-maya")),
        role=ReferenceRole.IDENTITY,
        provenance=provenance or external_provenance(),
        status=status,
        approval_id=approval_id,
        superseded_by=superseded_by,
    )


def test_source_uri_accepts_credential_free_https() -> None:
    uri = SourceUri("https://example.com/art/reference.png?version=2")

    assert str(uri) == "https://example.com/art/reference.png?version=2"


@pytest.mark.parametrize(
    "value",
    [
        "",
        " https://example.com/reference.png",
        "http://example.com/reference.png",
        "https://example-user@example.com/reference.png",
        "https://example.com/reference.png#fragment",
        "not-a-uri",
        "https://example.com/" + "x" * 2_050,
    ],
)
def test_invalid_source_uris_are_rejected(value: str) -> None:
    with pytest.raises(InvalidReferenceError):
        SourceUri(value)


def test_reference_target_selects_at_most_one_decomposed_item() -> None:
    target = ReferenceTarget(
        AssetId("chr-maya"),
        component_id=ComponentId("base-body"),
    )

    assert target.component_id == ComponentId("base-body")

    with pytest.raises(InvalidReferenceError, match="at most one"):
        ReferenceTarget(
            AssetId("chr-maya"),
            component_id=ComponentId("base-body"),
            variant_id=VariantId("winter"),
        )


def test_external_provenance_requires_a_source_uri() -> None:
    with pytest.raises(InvalidReferenceError, match="requires a source URI"):
        ReferenceProvenance(
            origin=ReferenceOrigin.EXTERNAL,
            content_revision=SubjectRevision("sha256:external123"),
        )


def test_generated_provenance_requires_job_and_receipt() -> None:
    provenance = ReferenceProvenance(
        origin=ReferenceOrigin.GENERATED,
        content_revision=SubjectRevision("sha256:generated123"),
        source_job_id=JobId("job-maya-front"),
        source_receipt_id=ReceiptId("receipt-maya-front-1"),
    )

    assert provenance.source_job_id == JobId("job-maya-front")

    with pytest.raises(InvalidReferenceError, match="requires a job and receipt"):
        ReferenceProvenance(
            origin=ReferenceOrigin.GENERATED,
            content_revision=SubjectRevision("sha256:generated123"),
            source_job_id=JobId("job-maya-front"),
        )


def test_captured_provenance_requires_a_creator() -> None:
    with pytest.raises(InvalidReferenceError, match="requires a creator"):
        ReferenceProvenance(
            origin=ReferenceOrigin.CAPTURED,
            content_revision=SubjectRevision("sha256:capture123"),
        )

    provenance = ReferenceProvenance(
        origin=ReferenceOrigin.CAPTURED,
        content_revision=SubjectRevision("sha256:capture123"),
        creator=DisplayName("Raillen Santos"),
    )
    assert provenance.creator == DisplayName("Raillen Santos")


def test_derived_provenance_requires_unique_parent_references() -> None:
    parent = ReferenceId("ref-maya-front")
    provenance = ReferenceProvenance(
        origin=ReferenceOrigin.DERIVED,
        content_revision=SubjectRevision("sha256:derived123"),
        parent_reference_ids=(parent,),
    )

    assert provenance.parent_reference_ids == (parent,)

    with pytest.raises(InvalidReferenceError, match="requires parent"):
        ReferenceProvenance(
            origin=ReferenceOrigin.DERIVED,
            content_revision=SubjectRevision("sha256:derived123"),
        )

    with pytest.raises(InvalidReferenceError, match="must be unique"):
        ReferenceProvenance(
            origin=ReferenceOrigin.DERIVED,
            content_revision=SubjectRevision("sha256:derived123"),
            parent_reference_ids=(parent, parent),
        )


def test_reference_cannot_derive_from_itself() -> None:
    provenance = ReferenceProvenance(
        origin=ReferenceOrigin.DERIVED,
        content_revision=SubjectRevision("sha256:self123"),
        parent_reference_ids=(ReferenceId("ref-maya-identity"),),
    )

    with pytest.raises(InvalidReferenceError, match="derive from itself"):
        make_reference(provenance=provenance)


def test_reference_is_immutable_and_starts_as_candidate() -> None:
    reference = make_reference()

    assert reference.status is ReferenceStatus.CANDIDATE
    with pytest.raises(FrozenInstanceError):
        reference.status = ReferenceStatus.APPROVED  # type: ignore[misc]


def test_reference_approval_is_revision_bound_and_idempotent() -> None:
    candidate = make_reference()
    approval_id = ApprovalId("approval-maya-identity-v1")

    approved = candidate.approve(approval_id)

    assert approved.status is ReferenceStatus.APPROVED
    assert approved.approval_id == approval_id
    assert approved.approve(approval_id) is approved

    with pytest.raises(InvalidReferenceTransitionError, match="change the approval"):
        approved.approve(ApprovalId("approval-maya-identity-v2"))


def test_approved_reference_can_be_revoked_and_reconsidered() -> None:
    approved = make_reference().approve(ApprovalId("approval-maya-identity-v1"))

    revoked = approved.revoke()
    reconsidered = revoked.reconsider()

    assert revoked.status is ReferenceStatus.REVOKED
    assert revoked.approval_id is None
    assert reconsidered.status is ReferenceStatus.CANDIDATE


def test_approved_reference_can_be_superseded() -> None:
    approved = make_reference().approve(ApprovalId("approval-maya-identity-v1"))
    replacement = ReferenceId("ref-maya-identity-v2")

    superseded = approved.supersede(replacement)

    assert superseded.status is ReferenceStatus.SUPERSEDED
    assert superseded.superseded_by == replacement
    assert superseded.supersede(replacement) is superseded

    with pytest.raises(InvalidReferenceTransitionError, match="change the replacement"):
        superseded.supersede(ReferenceId("ref-maya-identity-v3"))


def test_reference_cannot_supersede_itself() -> None:
    approved = make_reference().approve(ApprovalId("approval-maya-identity-v1"))

    with pytest.raises(InvalidReferenceTransitionError, match="itself"):
        approved.supersede(approved.id)


def test_rejected_reference_can_only_be_archived() -> None:
    rejected = make_reference().reject()

    archived = rejected.archive()

    assert archived.status is ReferenceStatus.ARCHIVED
    with pytest.raises(InvalidReferenceTransitionError):
        rejected.approve(ApprovalId("approval-invalid"))


def test_status_specific_fields_are_required() -> None:
    with pytest.raises(InvalidReferenceError, match="requires an approval"):
        make_reference(status=ReferenceStatus.APPROVED)

    with pytest.raises(InvalidReferenceError, match="requires a replacement"):
        make_reference(status=ReferenceStatus.SUPERSEDED)
