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


class InvalidReferenceError(DomainValidationError):
    """Raised when a visual reference or its provenance is invalid."""


class InvalidReferenceTransitionError(InvalidReferenceError):
    """Raised when a visual reference transition is not allowed."""


class InvalidVisualJobError(DomainValidationError):
    """Raised when a deterministic visual job specification is invalid."""


class InvalidVisualPlanError(DomainValidationError):
    """Raised when a deterministic visual-job plan is invalid."""


class InvalidGenerationReceiptError(DomainValidationError):
    """Raised when a generation receipt or retry series is invalid."""


class InvalidVisualReviewError(DomainValidationError):
    """Raised when a visual review record violates its contract."""


class InvalidCaptureProfileError(DomainValidationError):
    """Raised when a capture profile or requirement is invalid."""


class InvalidCaptureProfileInheritanceError(InvalidCaptureProfileError):
    """Raised when capture-profile inheritance cannot be resolved safely."""


class InvalidVisualBibleError(DomainValidationError):
    """Raised when a visual bible violates a canonical visual rule."""


class InvalidPromptCompilationError(DomainValidationError):
    """Raised when a prompt template, reference, or compiled result is invalid."""


class InvalidEventError(DomainValidationError):
    """Raised when an event type, payload, or immutable record is invalid."""


class InvalidDependencyGraphError(DomainValidationError):
    """Raised when dependency nodes, edges, or invalidations are inconsistent."""


class DependencyCycleError(InvalidDependencyGraphError):
    """Raised when dependency edges would create a directed cycle."""


class DependencyRefreshError(InvalidDependencyGraphError):
    """Raised when a stale node cannot be safely refreshed from its inputs."""


class InvalidInterviewError(DomainValidationError):
    """Raised when an interview questionnaire or answer violates its invariants."""
