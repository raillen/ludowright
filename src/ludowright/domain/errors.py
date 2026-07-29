"""Domain-specific validation errors."""

from __future__ import annotations


class DomainValidationError(ValueError):
    """Base class for invalid canonical domain values."""


class InvalidIdentifierError(DomainValidationError):
    """Raised when an identifier does not follow the canonical grammar."""


class InvalidNameError(DomainValidationError):
    """Raised when a human-readable name is not canonical or safe."""


class InvalidVersionError(DomainValidationError):
    """Raised when a revision version is malformed or unsupported."""


class InvalidProjectError(DomainValidationError):
    """Raised when a project aggregate violates a domain invariant."""


class InvalidProjectTransitionError(InvalidProjectError):
    """Raised when a project stage or lifecycle transition is not allowed."""


class InvalidDecisionError(DomainValidationError):
    """Raised when a decision or its immutable history is invalid."""


class InvalidDecisionTransitionError(InvalidDecisionError):
    """Raised when a decision transition is not allowed."""


class InvalidApprovalError(DomainValidationError):
    """Raised when an approval request or its immutable history is invalid."""


class InvalidApprovalTransitionError(InvalidApprovalError):
    """Raised when an approval transition is not allowed."""


class InvalidAssetError(DomainValidationError):
    """Raised when an asset aggregate violates a domain invariant."""


class InvalidAssetTransitionError(InvalidAssetError):
    """Raised when an asset production transition is not allowed."""
