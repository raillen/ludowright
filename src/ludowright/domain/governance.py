"""Immutable decision and approval histories."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from ludowright.domain.errors import (
    InvalidApprovalError,
    InvalidApprovalTransitionError,
    InvalidDecisionError,
    InvalidDecisionTransitionError,
)
from ludowright.domain.identifiers import ApprovalId, DecisionId, Identifier
from ludowright.domain.names import DisplayName

MAX_REVIEW_NOTE_LENGTH = 4_000
MAX_SUBJECT_REVISION_LENGTH = 128
_SUBJECT_REVISION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]*$")


@dataclass(frozen=True, slots=True)
class ReviewNote:
    """A normalized human explanation attached to a state transition."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("a review note cannot be empty")
        if self.value != self.value.strip():
            raise ValueError("a review note cannot have surrounding whitespace")
        if unicodedata.normalize("NFC", self.value) != self.value:
            raise ValueError("a review note must use canonical Unicode NFC normalization")
        if len(self.value) > MAX_REVIEW_NOTE_LENGTH:
            raise ValueError(f"a review note cannot exceed {MAX_REVIEW_NOTE_LENGTH} characters")
        if any(
            unicodedata.category(character).startswith("C") and character not in {"\n", "\t"}
            for character in self.value
        ):
            raise ValueError("a review note cannot contain unsupported control characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SubjectRevision:
    """A checksum, version tag, or other immutable subject fingerprint."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise InvalidApprovalError("a subject revision cannot be empty")
        if len(self.value) > MAX_SUBJECT_REVISION_LENGTH:
            raise InvalidApprovalError(
                f"a subject revision cannot exceed {MAX_SUBJECT_REVISION_LENGTH} characters"
            )
        if not self.value.isascii() or _SUBJECT_REVISION_PATTERN.fullmatch(self.value) is None:
            raise InvalidApprovalError(
                "a subject revision must use portable ASCII fingerprint characters"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ApprovalSubject:
    """An immutable entity revision submitted for human approval."""

    id: Identifier
    revision: SubjectRevision
    label: DisplayName | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, Identifier) or type(self.id) is Identifier:
            raise InvalidApprovalError("an approval subject requires a typed identifier")
        if not isinstance(self.revision, SubjectRevision):
            raise InvalidApprovalError("an approval subject requires a subject revision")
        if self.label is not None and not isinstance(self.label, DisplayName):
            raise InvalidApprovalError("an approval subject label must be a display name")


class DecisionStatus(StrEnum):
    """Logical states of a recorded project decision."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


_DECISION_TRANSITIONS: dict[DecisionStatus, frozenset[DecisionStatus]] = {
    DecisionStatus.PROPOSED: frozenset(
        {DecisionStatus.ACCEPTED, DecisionStatus.REJECTED, DecisionStatus.WITHDRAWN}
    ),
    DecisionStatus.ACCEPTED: frozenset({DecisionStatus.SUPERSEDED}),
    DecisionStatus.REJECTED: frozenset(),
    DecisionStatus.WITHDRAWN: frozenset(),
    DecisionStatus.SUPERSEDED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class DecisionRevision:
    """One logical state in an immutable decision history."""

    sequence: int
    status: DecisionStatus
    note: ReviewNote | None = None
    superseded_by: DecisionId | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise InvalidDecisionError("a decision revision sequence must be a positive integer")
        if not isinstance(self.status, DecisionStatus):
            raise InvalidDecisionError("a decision revision requires a valid status")
        if self.note is not None and not isinstance(self.note, ReviewNote):
            raise InvalidDecisionError("a decision revision note must be a review note")
        if self.status is DecisionStatus.SUPERSEDED:
            if not isinstance(self.superseded_by, DecisionId):
                raise InvalidDecisionError("a superseded decision requires a replacement ID")
        elif self.superseded_by is not None:
            raise InvalidDecisionError("only a superseded decision revision may name a replacement")


@dataclass(frozen=True, slots=True)
class Decision:
    """A project decision with append-only logical state history."""

    id: DecisionId
    title: DisplayName
    history: tuple[DecisionRevision, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, DecisionId):
            raise InvalidDecisionError("a decision requires a typed decision ID")
        if not isinstance(self.title, DisplayName):
            raise InvalidDecisionError("a decision title must be a display name")
        if not isinstance(self.history, tuple) or not self.history:
            raise InvalidDecisionError("a decision history must be a non-empty tuple")
        if any(not isinstance(revision, DecisionRevision) for revision in self.history):
            raise InvalidDecisionError("a decision history contains an invalid revision")

        first = self.history[0]
        if first.sequence != 1 or first.status is not DecisionStatus.PROPOSED:
            raise InvalidDecisionError("a decision history must begin with proposed sequence 1")

        previous = first
        for expected_sequence, revision in enumerate(self.history[1:], start=2):
            if revision.sequence != expected_sequence:
                raise InvalidDecisionError("decision revision sequences must be contiguous")
            if revision.status not in _DECISION_TRANSITIONS[previous.status]:
                raise InvalidDecisionError(
                    f"invalid decision history transition from {previous.status.value!r} "
                    f"to {revision.status.value!r}"
                )
            previous = revision

        current = self.history[-1]
        if current.superseded_by == self.id:
            raise InvalidDecisionError("a decision cannot supersede itself")

    @classmethod
    def propose(
        cls,
        id: DecisionId,
        title: DisplayName,
        note: ReviewNote | None = None,
    ) -> Self:
        """Create a proposed decision with its initial history entry."""
        return cls(
            id=id,
            title=title,
            history=(DecisionRevision(1, DecisionStatus.PROPOSED, note),),
        )

    @property
    def current(self) -> DecisionRevision:
        """Return the current immutable revision."""
        return self.history[-1]

    @property
    def status(self) -> DecisionStatus:
        """Return the current decision status."""
        return self.current.status

    def _transition(
        self,
        status: DecisionStatus,
        note: ReviewNote | None = None,
        superseded_by: DecisionId | None = None,
    ) -> Self:
        if status is self.status:
            if superseded_by is not None and superseded_by != self.current.superseded_by:
                raise InvalidDecisionTransitionError(
                    "an idempotent decision transition cannot change its replacement"
                )
            return self
        if status not in _DECISION_TRANSITIONS[self.status]:
            raise InvalidDecisionTransitionError(
                f"cannot transition decision from {self.status.value!r} to {status.value!r}"
            )
        return type(self)(
            id=self.id,
            title=self.title,
            history=(
                *self.history,
                DecisionRevision(len(self.history) + 1, status, note, superseded_by),
            ),
        )

    def accept(self, note: ReviewNote | None = None) -> Self:
        """Accept a proposed decision."""
        return self._transition(DecisionStatus.ACCEPTED, note)

    def reject(self, note: ReviewNote | None = None) -> Self:
        """Reject a proposed decision."""
        return self._transition(DecisionStatus.REJECTED, note)

    def withdraw(self, note: ReviewNote | None = None) -> Self:
        """Withdraw a proposed decision."""
        return self._transition(DecisionStatus.WITHDRAWN, note)

    def supersede(
        self,
        replacement: DecisionId,
        note: ReviewNote | None = None,
    ) -> Self:
        """Mark an accepted decision as replaced by another decision."""
        if replacement == self.id:
            raise InvalidDecisionTransitionError("a decision cannot supersede itself")
        return self._transition(DecisionStatus.SUPERSEDED, note, replacement)


class ApprovalStatus(StrEnum):
    """Logical states of an approval request for one immutable revision."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


_APPROVAL_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.CHANGES_REQUESTED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.WITHDRAWN,
        }
    ),
    ApprovalStatus.APPROVED: frozenset({ApprovalStatus.REVOKED, ApprovalStatus.SUPERSEDED}),
    ApprovalStatus.CHANGES_REQUESTED: frozenset(),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.WITHDRAWN: frozenset(),
    ApprovalStatus.REVOKED: frozenset(),
    ApprovalStatus.SUPERSEDED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ApprovalRevision:
    """One logical state in an immutable approval history."""

    sequence: int
    status: ApprovalStatus
    note: ReviewNote | None = None
    superseded_by: ApprovalId | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise InvalidApprovalError("an approval revision sequence must be a positive integer")
        if not isinstance(self.status, ApprovalStatus):
            raise InvalidApprovalError("an approval revision requires a valid status")
        if self.note is not None and not isinstance(self.note, ReviewNote):
            raise InvalidApprovalError("an approval revision note must be a review note")
        if self.status is ApprovalStatus.SUPERSEDED:
            if not isinstance(self.superseded_by, ApprovalId):
                raise InvalidApprovalError("a superseded approval requires a replacement ID")
        elif self.superseded_by is not None:
            raise InvalidApprovalError("only a superseded approval revision may name a replacement")


@dataclass(frozen=True, slots=True)
class Approval:
    """An approval request with append-only logical state history."""

    id: ApprovalId
    subject: ApprovalSubject
    history: tuple[ApprovalRevision, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, ApprovalId):
            raise InvalidApprovalError("an approval requires a typed approval ID")
        if not isinstance(self.subject, ApprovalSubject):
            raise InvalidApprovalError("an approval requires an approval subject")
        if not isinstance(self.history, tuple) or not self.history:
            raise InvalidApprovalError("an approval history must be a non-empty tuple")
        if any(not isinstance(revision, ApprovalRevision) for revision in self.history):
            raise InvalidApprovalError("an approval history contains an invalid revision")

        first = self.history[0]
        if first.sequence != 1 or first.status is not ApprovalStatus.PENDING:
            raise InvalidApprovalError("an approval history must begin with pending sequence 1")

        previous = first
        for expected_sequence, revision in enumerate(self.history[1:], start=2):
            if revision.sequence != expected_sequence:
                raise InvalidApprovalError("approval revision sequences must be contiguous")
            if revision.status not in _APPROVAL_TRANSITIONS[previous.status]:
                raise InvalidApprovalError(
                    f"invalid approval history transition from {previous.status.value!r} "
                    f"to {revision.status.value!r}"
                )
            previous = revision

        current = self.history[-1]
        if current.superseded_by == self.id:
            raise InvalidApprovalError("an approval cannot supersede itself")

    @classmethod
    def request(
        cls,
        id: ApprovalId,
        subject: ApprovalSubject,
        note: ReviewNote | None = None,
    ) -> Self:
        """Create a pending approval request for an immutable subject revision."""
        return cls(
            id=id,
            subject=subject,
            history=(ApprovalRevision(1, ApprovalStatus.PENDING, note),),
        )

    @property
    def current(self) -> ApprovalRevision:
        """Return the current immutable revision."""
        return self.history[-1]

    @property
    def status(self) -> ApprovalStatus:
        """Return the current approval status."""
        return self.current.status

    def _transition(
        self,
        status: ApprovalStatus,
        note: ReviewNote | None = None,
        superseded_by: ApprovalId | None = None,
    ) -> Self:
        if status is self.status:
            if superseded_by is not None and superseded_by != self.current.superseded_by:
                raise InvalidApprovalTransitionError(
                    "an idempotent approval transition cannot change its replacement"
                )
            return self
        if status not in _APPROVAL_TRANSITIONS[self.status]:
            raise InvalidApprovalTransitionError(
                f"cannot transition approval from {self.status.value!r} to {status.value!r}"
            )
        return type(self)(
            id=self.id,
            subject=self.subject,
            history=(
                *self.history,
                ApprovalRevision(len(self.history) + 1, status, note, superseded_by),
            ),
        )

    def approve(self, note: ReviewNote | None = None) -> Self:
        """Approve the submitted subject revision."""
        return self._transition(ApprovalStatus.APPROVED, note)

    def request_changes(self, note: ReviewNote | None = None) -> Self:
        """Close the request because the subject revision needs changes."""
        return self._transition(ApprovalStatus.CHANGES_REQUESTED, note)

    def reject(self, note: ReviewNote | None = None) -> Self:
        """Reject the submitted subject revision."""
        return self._transition(ApprovalStatus.REJECTED, note)

    def withdraw(self, note: ReviewNote | None = None) -> Self:
        """Withdraw a pending approval request."""
        return self._transition(ApprovalStatus.WITHDRAWN, note)

    def revoke(self, note: ReviewNote | None = None) -> Self:
        """Revoke a previously approved subject revision."""
        return self._transition(ApprovalStatus.REVOKED, note)

    def supersede(
        self,
        replacement: ApprovalId,
        note: ReviewNote | None = None,
    ) -> Self:
        """Replace an approved request with another approval record."""
        if replacement == self.id:
            raise InvalidApprovalTransitionError("an approval cannot supersede itself")
        return self._transition(ApprovalStatus.SUPERSEDED, note, replacement)
