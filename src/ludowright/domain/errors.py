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
