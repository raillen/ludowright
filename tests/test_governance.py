"""Tests for immutable decisions, approvals, and superseding relationships."""

from __future__ import annotations

import unicodedata
from dataclasses import FrozenInstanceError

import pytest

from ludowright.domain import (
    Approval,
    ApprovalId,
    ApprovalRevision,
    ApprovalStatus,
    ApprovalSubject,
    Decision,
    DecisionId,
    DecisionRevision,
    DecisionStatus,
    DisplayName,
    Identifier,
    InvalidApprovalError,
    InvalidApprovalTransitionError,
    InvalidDecisionError,
    InvalidDecisionTransitionError,
    ReferenceId,
    ReviewNote,
    SubjectRevision,
)


def make_subject(revision: str = "sha256:abc123") -> ApprovalSubject:
    return ApprovalSubject(
        id=ReferenceId("ref-maya-front"),
        revision=SubjectRevision(revision),
        label=DisplayName("Maya Front Reference"),
    )


def test_review_note_preserves_normalized_multiline_text() -> None:
    note = ReviewNote("Approved proportions.\nKeep the current silhouette.")

    assert str(note) == "Approved proportions.\nKeep the current silhouette."


@pytest.mark.parametrize(
    "value",
    [
        "",
        " surrounding whitespace ",
        "unsupported\u200bformat",
        "x" * 4_001,
        unicodedata.normalize("NFD", "Aprovação"),
        None,
    ],
)
def test_invalid_review_notes_are_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        ReviewNote(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    ["", " contains-space", "contains space", "ação", "/path", "x" * 129, None],
)
def test_invalid_subject_revisions_are_rejected(value: object) -> None:
    with pytest.raises(InvalidApprovalError):
        SubjectRevision(value)  # type: ignore[arg-type]


def test_subject_revision_supports_checksums_versions_and_git_shas() -> None:
    assert str(SubjectRevision("sha256:abc123")) == "sha256:abc123"
    assert str(SubjectRevision("v12")) == "v12"
    assert str(SubjectRevision("git:0123456789abcdef")) == "git:0123456789abcdef"


def test_approval_subject_requires_canonical_value_types() -> None:
    with pytest.raises(InvalidApprovalError, match="typed identifier"):
        ApprovalSubject(
            id=Identifier("generic"),
            revision=SubjectRevision("v1"),
        )

    with pytest.raises(InvalidApprovalError, match="typed identifier"):
        ApprovalSubject(
            id="ref-maya-front",  # type: ignore[arg-type]
            revision=SubjectRevision("v1"),
        )

    with pytest.raises(InvalidApprovalError, match="subject revision"):
        ApprovalSubject(
            id=ReferenceId("ref-maya-front"),
            revision="v1",  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidApprovalError, match="display name"):
        ApprovalSubject(
            id=ReferenceId("ref-maya-front"),
            revision=SubjectRevision("v1"),
            label="Maya",  # type: ignore[arg-type]
        )


def test_decision_starts_proposed_and_accepts_immutably() -> None:
    proposed = Decision.propose(
        DecisionId("decision-camera"),
        DisplayName("Use an isometric camera"),
        ReviewNote("Initial technical direction."),
    )

    accepted = proposed.accept(ReviewNote("Approved for pre-production."))

    assert proposed.status is DecisionStatus.PROPOSED
    assert accepted.status is DecisionStatus.ACCEPTED
    assert accepted.id is proposed.id
    assert [revision.sequence for revision in accepted.history] == [1, 2]
    assert accepted.current.note == ReviewNote("Approved for pre-production.")


def test_decision_history_is_immutable() -> None:
    decision = Decision.propose(
        DecisionId("decision-immutable"),
        DisplayName("Keep immutable decisions"),
    )

    with pytest.raises(FrozenInstanceError):
        decision.title = DisplayName("Changed")  # type: ignore[misc]

    with pytest.raises(TypeError):
        decision.history[0] = DecisionRevision(1, DecisionStatus.REJECTED)  # type: ignore[index]


def test_accepted_decision_can_be_superseded() -> None:
    accepted = Decision.propose(
        DecisionId("decision-renderer-v1"),
        DisplayName("Use renderer version one"),
    ).accept()

    replacement = DecisionId("decision-renderer-v2")
    superseded = accepted.supersede(
        replacement,
        ReviewNote("A later benchmark changed the technical choice."),
    )

    assert superseded.status is DecisionStatus.SUPERSEDED
    assert superseded.current.superseded_by == replacement
    assert superseded.supersede(replacement) is superseded

    with pytest.raises(InvalidDecisionTransitionError, match="replacement"):
        superseded.supersede(DecisionId("decision-renderer-v3"))


def test_decision_cannot_supersede_itself() -> None:
    decision = Decision.propose(
        DecisionId("decision-self"),
        DisplayName("Self replacement"),
    ).accept()

    with pytest.raises(InvalidDecisionTransitionError, match="itself"):
        decision.supersede(decision.id)


def test_rejected_and_withdrawn_decisions_are_terminal() -> None:
    rejected = Decision.propose(
        DecisionId("decision-rejected"),
        DisplayName("Rejected direction"),
    ).reject()
    withdrawn = Decision.propose(
        DecisionId("decision-withdrawn"),
        DisplayName("Withdrawn direction"),
    ).withdraw()

    assert rejected.reject() is rejected
    assert withdrawn.withdraw() is withdrawn
    with pytest.raises(InvalidDecisionTransitionError):
        rejected.accept()
    with pytest.raises(InvalidDecisionTransitionError):
        withdrawn.accept()


def test_invalid_decision_histories_are_rejected() -> None:
    with pytest.raises(InvalidDecisionError, match="non-empty tuple"):
        Decision(
            id=DecisionId("decision-empty"),
            title=DisplayName("Empty history"),
            history=(),
        )

    with pytest.raises(InvalidDecisionError, match="non-empty tuple"):
        Decision(
            id=DecisionId("decision-list-history"),
            title=DisplayName("Mutable history"),
            history=[DecisionRevision(1, DecisionStatus.PROPOSED)],  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidDecisionError, match="invalid revision"):
        Decision(
            id=DecisionId("decision-invalid-revision"),
            title=DisplayName("Invalid revision"),
            history=("proposed",),  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidDecisionError, match="begin with proposed"):
        Decision(
            id=DecisionId("decision-wrong-start"),
            title=DisplayName("Wrong start"),
            history=(DecisionRevision(1, DecisionStatus.ACCEPTED),),
        )

    with pytest.raises(InvalidDecisionError, match="contiguous"):
        Decision(
            id=DecisionId("decision-gap"),
            title=DisplayName("Sequence gap"),
            history=(
                DecisionRevision(1, DecisionStatus.PROPOSED),
                DecisionRevision(3, DecisionStatus.ACCEPTED),
            ),
        )

    with pytest.raises(InvalidDecisionError, match="invalid decision history"):
        Decision(
            id=DecisionId("decision-invalid-transition"),
            title=DisplayName("Invalid transition"),
            history=(
                DecisionRevision(1, DecisionStatus.PROPOSED),
                DecisionRevision(
                    2,
                    DecisionStatus.SUPERSEDED,
                    superseded_by=DecisionId("decision-replacement"),
                ),
            ),
        )


def test_decision_revision_requires_canonical_types() -> None:
    with pytest.raises(InvalidDecisionError, match="positive integer"):
        DecisionRevision(True, DecisionStatus.PROPOSED)

    with pytest.raises(InvalidDecisionError, match="valid status"):
        DecisionRevision(1, "proposed")  # type: ignore[arg-type]

    with pytest.raises(InvalidDecisionError, match="review note"):
        DecisionRevision(1, DecisionStatus.PROPOSED, note="note")  # type: ignore[arg-type]


def test_decision_requires_canonical_types() -> None:
    revision = (DecisionRevision(1, DecisionStatus.PROPOSED),)

    with pytest.raises(InvalidDecisionError, match="decision ID"):
        Decision(
            id="decision-invalid",  # type: ignore[arg-type]
            title=DisplayName("Invalid ID"),
            history=revision,
        )

    with pytest.raises(InvalidDecisionError, match="display name"):
        Decision(
            id=DecisionId("decision-invalid-title"),
            title="Invalid title",  # type: ignore[arg-type]
            history=revision,
        )


def test_superseded_decision_revision_requires_a_different_replacement() -> None:
    with pytest.raises(InvalidDecisionError, match="requires a replacement"):
        DecisionRevision(2, DecisionStatus.SUPERSEDED)

    with pytest.raises(InvalidDecisionError, match="only a superseded"):
        DecisionRevision(
            1,
            DecisionStatus.PROPOSED,
            superseded_by=DecisionId("decision-unexpected"),
        )

    with pytest.raises(InvalidDecisionError, match="cannot supersede itself"):
        Decision(
            id=DecisionId("decision-self-history"),
            title=DisplayName("Self history"),
            history=(
                DecisionRevision(1, DecisionStatus.PROPOSED),
                DecisionRevision(2, DecisionStatus.ACCEPTED),
                DecisionRevision(
                    3,
                    DecisionStatus.SUPERSEDED,
                    superseded_by=DecisionId("decision-self-history"),
                ),
            ),
        )


def test_approval_starts_pending_and_approves_one_revision() -> None:
    pending = Approval.request(
        ApprovalId("approval-maya-front-v1"),
        make_subject(),
        ReviewNote("Ready for visual review."),
    )

    approved = pending.approve(ReviewNote("Identity and proportions match."))

    assert pending.status is ApprovalStatus.PENDING
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.subject is pending.subject
    assert [revision.sequence for revision in approved.history] == [1, 2]
    assert approved.approve() is approved


def test_approved_request_can_be_revoked_or_superseded() -> None:
    approved = Approval.request(
        ApprovalId("approval-maya-front-v1"),
        make_subject(),
    ).approve()

    revoked = approved.revoke(ReviewNote("The source image license changed."))
    assert revoked.status is ApprovalStatus.REVOKED

    replacement = ApprovalId("approval-maya-front-v2")
    superseded = approved.supersede(replacement)
    assert superseded.status is ApprovalStatus.SUPERSEDED
    assert superseded.current.superseded_by == replacement
    assert superseded.supersede(replacement) is superseded

    with pytest.raises(InvalidApprovalTransitionError, match="replacement"):
        superseded.supersede(ApprovalId("approval-maya-front-v3"))


def test_approval_cannot_supersede_itself() -> None:
    approval = Approval.request(
        ApprovalId("approval-self"),
        make_subject(),
    ).approve()

    with pytest.raises(InvalidApprovalTransitionError, match="itself"):
        approval.supersede(approval.id)


def test_changes_requested_rejected_and_withdrawn_are_terminal() -> None:
    pending = Approval.request(ApprovalId("approval-terminal"), make_subject())

    changes = pending.request_changes(ReviewNote("Correct the hand silhouette."))
    rejected = pending.reject(ReviewNote("The identity does not match."))
    withdrawn = pending.withdraw(ReviewNote("A newer generation is ready."))

    assert changes.status is ApprovalStatus.CHANGES_REQUESTED
    assert rejected.status is ApprovalStatus.REJECTED
    assert withdrawn.status is ApprovalStatus.WITHDRAWN
    with pytest.raises(InvalidApprovalTransitionError):
        changes.approve()
    with pytest.raises(InvalidApprovalTransitionError):
        rejected.approve()
    with pytest.raises(InvalidApprovalTransitionError):
        withdrawn.approve()


def test_pending_approval_cannot_be_revoked_or_superseded() -> None:
    pending = Approval.request(ApprovalId("approval-pending"), make_subject())

    with pytest.raises(InvalidApprovalTransitionError):
        pending.revoke()
    with pytest.raises(InvalidApprovalTransitionError):
        pending.supersede(ApprovalId("approval-new"))


def test_invalid_approval_histories_are_rejected() -> None:
    with pytest.raises(InvalidApprovalError, match="non-empty tuple"):
        Approval(
            id=ApprovalId("approval-empty"),
            subject=make_subject(),
            history=(),
        )

    with pytest.raises(InvalidApprovalError, match="non-empty tuple"):
        Approval(
            id=ApprovalId("approval-list-history"),
            subject=make_subject(),
            history=[ApprovalRevision(1, ApprovalStatus.PENDING)],  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidApprovalError, match="invalid revision"):
        Approval(
            id=ApprovalId("approval-invalid-revision"),
            subject=make_subject(),
            history=("pending",),  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidApprovalError, match="begin with pending"):
        Approval(
            id=ApprovalId("approval-wrong-start"),
            subject=make_subject(),
            history=(ApprovalRevision(1, ApprovalStatus.APPROVED),),
        )

    with pytest.raises(InvalidApprovalError, match="contiguous"):
        Approval(
            id=ApprovalId("approval-gap"),
            subject=make_subject(),
            history=(
                ApprovalRevision(1, ApprovalStatus.PENDING),
                ApprovalRevision(3, ApprovalStatus.APPROVED),
            ),
        )

    with pytest.raises(InvalidApprovalError, match="invalid approval history"):
        Approval(
            id=ApprovalId("approval-invalid-transition"),
            subject=make_subject(),
            history=(
                ApprovalRevision(1, ApprovalStatus.PENDING),
                ApprovalRevision(2, ApprovalStatus.REVOKED),
            ),
        )


def test_approval_revision_requires_canonical_types() -> None:
    with pytest.raises(InvalidApprovalError, match="positive integer"):
        ApprovalRevision(True, ApprovalStatus.PENDING)

    with pytest.raises(InvalidApprovalError, match="valid status"):
        ApprovalRevision(1, "pending")  # type: ignore[arg-type]

    with pytest.raises(InvalidApprovalError, match="review note"):
        ApprovalRevision(1, ApprovalStatus.PENDING, note="note")  # type: ignore[arg-type]


def test_approval_requires_canonical_types() -> None:
    revision = (ApprovalRevision(1, ApprovalStatus.PENDING),)

    with pytest.raises(InvalidApprovalError, match="approval ID"):
        Approval(
            id="approval-invalid",  # type: ignore[arg-type]
            subject=make_subject(),
            history=revision,
        )

    with pytest.raises(InvalidApprovalError, match="approval subject"):
        Approval(
            id=ApprovalId("approval-invalid-subject"),
            subject="subject",  # type: ignore[arg-type]
            history=revision,
        )


def test_superseded_approval_revision_requires_a_different_replacement() -> None:
    with pytest.raises(InvalidApprovalError, match="requires a replacement"):
        ApprovalRevision(2, ApprovalStatus.SUPERSEDED)

    with pytest.raises(InvalidApprovalError, match="only a superseded"):
        ApprovalRevision(
            1,
            ApprovalStatus.PENDING,
            superseded_by=ApprovalId("approval-unexpected"),
        )

    with pytest.raises(InvalidApprovalError, match="cannot supersede itself"):
        Approval(
            id=ApprovalId("approval-self-history"),
            subject=make_subject(),
            history=(
                ApprovalRevision(1, ApprovalStatus.PENDING),
                ApprovalRevision(2, ApprovalStatus.APPROVED),
                ApprovalRevision(
                    3,
                    ApprovalStatus.SUPERSEDED,
                    superseded_by=ApprovalId("approval-self-history"),
                ),
            ),
        )
