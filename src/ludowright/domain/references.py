"""Visual references, provenance, approval projection, and superseding rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit

from ludowright.domain.errors import (
    InvalidReferenceError,
    InvalidReferenceTransitionError,
)
from ludowright.domain.governance import SubjectRevision
from ludowright.domain.identifiers import (
    ApprovalId,
    AssetId,
    AssetStateId,
    ComponentId,
    JobId,
    ReceiptId,
    ReferenceId,
    VariantId,
)
from ludowright.domain.names import DisplayName

MAX_SOURCE_URI_LENGTH = 2_048


class ReferenceOrigin(StrEnum):
    """How a visual reference entered the project."""

    EXTERNAL = "external"
    GENERATED = "generated"
    CAPTURED = "captured"
    DERIVED = "derived"


class ReferenceRole(StrEnum):
    """Production purpose served by a visual reference."""

    IDENTITY = "identity"
    SILHOUETTE = "silhouette"
    PROPORTION = "proportion"
    CONSTRUCTION = "construction"
    MATERIAL = "material"
    COLOR = "color"
    STYLE = "style"
    CONTEXT = "context"
    NEGATIVE = "negative"
    OUTPUT = "output"
    OTHER = "other"


class ReferenceStatus(StrEnum):
    """Catalog status projected from review and approval records."""

    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


_REFERENCE_TRANSITIONS: dict[ReferenceStatus, frozenset[ReferenceStatus]] = {
    ReferenceStatus.CANDIDATE: frozenset(
        {
            ReferenceStatus.APPROVED,
            ReferenceStatus.REJECTED,
            ReferenceStatus.ARCHIVED,
        }
    ),
    ReferenceStatus.APPROVED: frozenset(
        {
            ReferenceStatus.REVOKED,
            ReferenceStatus.SUPERSEDED,
            ReferenceStatus.ARCHIVED,
        }
    ),
    ReferenceStatus.REJECTED: frozenset({ReferenceStatus.ARCHIVED}),
    ReferenceStatus.REVOKED: frozenset(
        {ReferenceStatus.CANDIDATE, ReferenceStatus.ARCHIVED}
    ),
    ReferenceStatus.SUPERSEDED: frozenset({ReferenceStatus.ARCHIVED}),
    ReferenceStatus.ARCHIVED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class SourceUri:
    """A credential-free HTTPS source URI used for external provenance."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidReferenceError("a source URI must be a string")
        if not self.value or self.value != self.value.strip():
            raise InvalidReferenceError("a source URI must be non-empty and trimmed")
        if len(self.value) > MAX_SOURCE_URI_LENGTH:
            raise InvalidReferenceError(
                f"a source URI cannot exceed {MAX_SOURCE_URI_LENGTH} characters"
            )

        parsed = urlsplit(self.value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise InvalidReferenceError("an external source URI must use absolute HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise InvalidReferenceError("a source URI cannot contain credentials")
        if parsed.fragment:
            raise InvalidReferenceError("a source URI cannot contain a fragment")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ReferenceTarget:
    """An asset or one explicitly selected decomposed production item."""

    asset_id: AssetId
    component_id: ComponentId | None = None
    variant_id: VariantId | None = None
    state_id: AssetStateId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, AssetId):
            raise InvalidReferenceError("a reference target requires a typed asset ID")
        item_ids = (self.component_id, self.variant_id, self.state_id)
        if sum(item_id is not None for item_id in item_ids) > 1:
            raise InvalidReferenceError(
                "a reference target may select at most one decomposed item"
            )
        if self.component_id is not None and not isinstance(
            self.component_id, ComponentId
        ):
            raise InvalidReferenceError("a reference component target must be typed")
        if self.variant_id is not None and not isinstance(self.variant_id, VariantId):
            raise InvalidReferenceError("a reference variant target must be typed")
        if self.state_id is not None and not isinstance(self.state_id, AssetStateId):
            raise InvalidReferenceError("a reference state target must be typed")


@dataclass(frozen=True, slots=True)
class ReferenceProvenance:
    """Immutable origin and lineage for one exact reference revision."""

    origin: ReferenceOrigin
    content_revision: SubjectRevision
    source_uri: SourceUri | None = None
    source_job_id: JobId | None = None
    source_receipt_id: ReceiptId | None = None
    parent_reference_ids: tuple[ReferenceId, ...] = ()
    creator: DisplayName | None = None
    license_label: DisplayName | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, ReferenceOrigin):
            raise InvalidReferenceError("reference provenance requires a valid origin")
        if not isinstance(self.content_revision, SubjectRevision):
            raise InvalidReferenceError(
                "reference provenance requires a content revision"
            )
        if self.source_uri is not None and not isinstance(self.source_uri, SourceUri):
            raise InvalidReferenceError("reference source URI must be canonical")
        if self.source_job_id is not None and not isinstance(self.source_job_id, JobId):
            raise InvalidReferenceError("reference source job must be typed")
        if self.source_receipt_id is not None and not isinstance(
            self.source_receipt_id, ReceiptId
        ):
            raise InvalidReferenceError("reference source receipt must be typed")
        if not isinstance(self.parent_reference_ids, tuple):
            raise InvalidReferenceError("reference parent IDs must be an immutable tuple")
        if any(
            not isinstance(parent_id, ReferenceId)
            for parent_id in self.parent_reference_ids
        ):
            raise InvalidReferenceError("reference parent IDs must be typed")
        if len(self.parent_reference_ids) != len(set(self.parent_reference_ids)):
            raise InvalidReferenceError("reference parent IDs must be unique")
        if self.creator is not None and not isinstance(self.creator, DisplayName):
            raise InvalidReferenceError("reference creator must be a display name")
        if self.license_label is not None and not isinstance(
            self.license_label, DisplayName
        ):
            raise InvalidReferenceError("reference license must be a display name")
        self._validate_origin_contract()

    def _validate_origin_contract(self) -> None:
        if self.origin is ReferenceOrigin.EXTERNAL:
            if self.source_uri is None:
                raise InvalidReferenceError(
                    "external reference provenance requires a source URI"
                )
            if self.source_job_id is not None or self.source_receipt_id is not None:
                raise InvalidReferenceError(
                    "external reference provenance cannot name a generation job"
                )
        elif self.origin is ReferenceOrigin.GENERATED:
            if self.source_job_id is None or self.source_receipt_id is None:
                raise InvalidReferenceError(
                    "generated reference provenance requires a job and receipt"
                )
            if self.source_uri is not None:
                raise InvalidReferenceError(
                    "generated reference provenance cannot use an external URI"
                )
        elif self.origin is ReferenceOrigin.CAPTURED:
            if self.creator is None:
                raise InvalidReferenceError(
                    "captured reference provenance requires a creator"
                )
            if self.source_job_id is not None or self.source_receipt_id is not None:
                raise InvalidReferenceError(
                    "captured reference provenance cannot name a generation job"
                )
        elif self.origin is ReferenceOrigin.DERIVED:
            if not self.parent_reference_ids:
                raise InvalidReferenceError(
                    "derived reference provenance requires parent references"
                )


@dataclass(frozen=True, slots=True)
class VisualReference:
    """A revision-bound visual reference used by production workflows."""

    id: ReferenceId
    name: DisplayName
    target: ReferenceTarget
    role: ReferenceRole
    provenance: ReferenceProvenance
    status: ReferenceStatus = ReferenceStatus.CANDIDATE
    approval_id: ApprovalId | None = None
    superseded_by: ReferenceId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ReferenceId):
            raise InvalidReferenceError("a visual reference requires a typed ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidReferenceError("a visual reference name must be canonical")
        if not isinstance(self.target, ReferenceTarget):
            raise InvalidReferenceError("a visual reference requires a target")
        if not isinstance(self.role, ReferenceRole):
            raise InvalidReferenceError("a visual reference requires a valid role")
        if not isinstance(self.provenance, ReferenceProvenance):
            raise InvalidReferenceError("a visual reference requires provenance")
        if not isinstance(self.status, ReferenceStatus):
            raise InvalidReferenceError("a visual reference requires a valid status")
        if self.approval_id is not None and not isinstance(
            self.approval_id, ApprovalId
        ):
            raise InvalidReferenceError("a visual reference approval must be typed")
        if self.superseded_by is not None and not isinstance(
            self.superseded_by, ReferenceId
        ):
            raise InvalidReferenceError("a replacement reference ID must be typed")
        if self.id in self.provenance.parent_reference_ids:
            raise InvalidReferenceError("a visual reference cannot derive from itself")
        if self.superseded_by == self.id:
            raise InvalidReferenceError("a visual reference cannot supersede itself")
        self._validate_status_contract()

    def _validate_status_contract(self) -> None:
        if self.status is ReferenceStatus.APPROVED:
            if self.approval_id is None:
                raise InvalidReferenceError(
                    "an approved reference requires an approval record"
                )
        elif self.approval_id is not None:
            raise InvalidReferenceError(
                "only an approved reference may name an approval record"
            )

        if self.status is ReferenceStatus.SUPERSEDED:
            if self.superseded_by is None:
                raise InvalidReferenceError(
                    "a superseded reference requires a replacement"
                )
        elif self.superseded_by is not None:
            raise InvalidReferenceError(
                "only a superseded reference may name a replacement"
            )

    def _transition(
        self,
        status: ReferenceStatus,
        *,
        approval_id: ApprovalId | None = None,
        superseded_by: ReferenceId | None = None,
    ) -> Self:
        if status is self.status:
            if approval_id is not None and approval_id != self.approval_id:
                raise InvalidReferenceTransitionError(
                    "an idempotent transition cannot change the approval"
                )
            if superseded_by is not None and superseded_by != self.superseded_by:
                raise InvalidReferenceTransitionError(
                    "an idempotent transition cannot change the replacement"
                )
            return self
        if status not in _REFERENCE_TRANSITIONS[self.status]:
            raise InvalidReferenceTransitionError(
                f"cannot transition reference from {self.status.value!r} "
                f"to {status.value!r}"
            )
        return replace(
            self,
            status=status,
            approval_id=approval_id,
            superseded_by=superseded_by,
        )

    def approve(self, approval_id: ApprovalId) -> Self:
        """Project an accepted approval onto this exact reference revision."""
        if not isinstance(approval_id, ApprovalId):
            raise InvalidReferenceTransitionError("approval ID must be typed")
        return self._transition(ReferenceStatus.APPROVED, approval_id=approval_id)

    def reject(self) -> Self:
        """Reject a candidate reference."""
        return self._transition(ReferenceStatus.REJECTED)

    def revoke(self) -> Self:
        """Revoke a previously projected approval."""
        return self._transition(ReferenceStatus.REVOKED)

    def reconsider(self) -> Self:
        """Return a revoked reference to candidate review."""
        return self._transition(ReferenceStatus.CANDIDATE)

    def supersede(self, replacement: ReferenceId) -> Self:
        """Replace an approved reference with another canonical reference."""
        if not isinstance(replacement, ReferenceId):
            raise InvalidReferenceTransitionError("replacement ID must be typed")
        if replacement == self.id:
            raise InvalidReferenceTransitionError(
                "a visual reference cannot supersede itself"
            )
        return self._transition(
            ReferenceStatus.SUPERSEDED,
            superseded_by=replacement,
        )

    def archive(self) -> Self:
        """Archive a non-terminal reference record."""
        return self._transition(ReferenceStatus.ARCHIVED)
