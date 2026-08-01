"""Typed identifiers for canonical LudoWright entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from ludowright.domain.names import slugify, validate_slug


@dataclass(frozen=True, slots=True)
class Identifier:
    """Base value object for a canonical entity identifier."""

    value: str
    kind: ClassVar[str] = "identifier"

    def __post_init__(self) -> None:
        validate_slug(self.value)

    @classmethod
    def from_name(cls, name: str) -> Self:
        """Create an identifier by explicitly slugifying a display name."""
        return cls(slugify(name))

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"


class ProjectId(Identifier):
    """Identifier for a game project."""

    kind = "project"


class AssetId(Identifier):
    """Identifier for a planned or produced asset."""

    kind = "asset"


class ComponentId(Identifier):
    """Identifier for a component belonging to an asset."""

    kind = "component"


class VariantId(Identifier):
    """Identifier for a production variant belonging to an asset."""

    kind = "variant"


class AssetStateId(Identifier):
    """Identifier for a functional or visual state belonging to an asset."""

    kind = "asset-state"


class OwnerId(Identifier):
    """Identifier for a person, team, role, or automation owner."""

    kind = "owner"


class ReferenceId(Identifier):
    """Identifier for an external, candidate, approved, or rejected reference."""

    kind = "reference"


class JobId(Identifier):
    """Identifier for a deterministic workflow or generation job."""

    kind = "job"


class ReceiptId(Identifier):
    """Identifier for one immutable generation attempt receipt."""

    kind = "receipt"


class ReviewId(Identifier):
    """Identifier for one immutable visual review record."""

    kind = "review"


class CaptureProfileId(Identifier):
    """Identifier for a reusable capture-profile lineage."""

    kind = "capture-profile"


class CaptureViewId(Identifier):
    """Identifier for a required capture view within a profile."""

    kind = "capture-view"


class CaptureSheetId(Identifier):
    """Identifier for a technical-sheet requirement within a profile."""

    kind = "capture-sheet"


class VisualBibleId(Identifier):
    """Identifier for a versioned project visual bible."""

    kind = "visual-bible"


class DecisionId(Identifier):
    """Identifier for a recorded project decision."""

    kind = "decision"


class ApprovalId(Identifier):
    """Identifier for a review approval request and its immutable history."""

    kind = "approval"


class EventId(Identifier):
    """Identifier for one immutable event-log record."""

    kind = "event"


class CorrelationId(Identifier):
    """Identifier grouping events that belong to one logical operation."""

    kind = "correlation"


class PackageId(Identifier):
    """Identifier for a reproducible project or production package."""

    kind = "package"


class QuestionnaireId(Identifier):
    """Identifier for a declarative guided-interview questionnaire."""

    kind = "questionnaire"


class InterviewSessionId(Identifier):
    """Identifier for one resumable guided-interview session."""

    kind = "interview-session"


class QuestionId(Identifier):
    """Identifier for one question within a questionnaire."""

    kind = "question"


class OptionId(Identifier):
    """Identifier for one selectable option within a question."""

    kind = "option"
