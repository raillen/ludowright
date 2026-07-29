"""Project aggregate, lifecycle, and platform targets."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from enum import StrEnum

from ludowright.domain.errors import InvalidProjectError, InvalidProjectTransitionError
from ludowright.domain.identifiers import ProjectId
from ludowright.domain.names import DisplayName

MAX_ENGINE_VERSION_LENGTH = 64


class ProjectDimension(StrEnum):
    """Primary spatial representation used by the game."""

    TWO_D = "2d"
    TWO_POINT_FIVE_D = "2.5d"
    THREE_D = "3d"
    MIXED = "mixed"


class PlatformFamily(StrEnum):
    """Broad target-platform families that remain stable across hardware generations."""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"
    PLAYSTATION = "playstation"
    XBOX = "xbox"
    NINTENDO = "nintendo"
    STEAM_DECK = "steam-deck"
    XR = "xr"
    OTHER = "other"


class ProjectStage(StrEnum):
    """Current production stage of a game project."""

    CONCEPT = "concept"
    PRE_PRODUCTION = "pre-production"
    PRODUCTION = "production"
    VALIDATION = "validation"
    RELEASED = "released"
    POST_RELEASE = "post-release"


class ProjectLifecycle(StrEnum):
    """Operational lifecycle state independent of production stage."""

    ACTIVE = "active"
    ON_HOLD = "on-hold"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ARCHIVED = "archived"


_STAGE_TRANSITIONS: dict[ProjectStage, frozenset[ProjectStage]] = {
    ProjectStage.CONCEPT: frozenset({ProjectStage.PRE_PRODUCTION}),
    ProjectStage.PRE_PRODUCTION: frozenset(
        {ProjectStage.CONCEPT, ProjectStage.PRODUCTION}
    ),
    ProjectStage.PRODUCTION: frozenset(
        {ProjectStage.PRE_PRODUCTION, ProjectStage.VALIDATION}
    ),
    ProjectStage.VALIDATION: frozenset(
        {ProjectStage.PRODUCTION, ProjectStage.RELEASED}
    ),
    ProjectStage.RELEASED: frozenset(
        {ProjectStage.VALIDATION, ProjectStage.POST_RELEASE}
    ),
    ProjectStage.POST_RELEASE: frozenset({ProjectStage.RELEASED}),
}

_LIFECYCLE_TRANSITIONS: dict[ProjectLifecycle, frozenset[ProjectLifecycle]] = {
    ProjectLifecycle.ACTIVE: frozenset(
        {
            ProjectLifecycle.ON_HOLD,
            ProjectLifecycle.CANCELLED,
            ProjectLifecycle.COMPLETED,
            ProjectLifecycle.ARCHIVED,
        }
    ),
    ProjectLifecycle.ON_HOLD: frozenset(
        {
            ProjectLifecycle.ACTIVE,
            ProjectLifecycle.CANCELLED,
            ProjectLifecycle.COMPLETED,
            ProjectLifecycle.ARCHIVED,
        }
    ),
    ProjectLifecycle.CANCELLED: frozenset(
        {ProjectLifecycle.ACTIVE, ProjectLifecycle.ARCHIVED}
    ),
    ProjectLifecycle.COMPLETED: frozenset(
        {ProjectLifecycle.ACTIVE, ProjectLifecycle.ARCHIVED}
    ),
    ProjectLifecycle.ARCHIVED: frozenset(),
}

_COMPLETABLE_STAGES = frozenset({ProjectStage.RELEASED, ProjectStage.POST_RELEASE})


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    """Stable machine identity and human-facing names for a project."""

    id: ProjectId
    name: DisplayName
    codename: DisplayName | None = None


@dataclass(frozen=True, slots=True)
class EngineSpec:
    """A game engine selection without coupling the domain to an engine catalog."""

    name: DisplayName
    version: str | None = None

    def __post_init__(self) -> None:
        if self.version is None:
            return
        if not self.version:
            raise InvalidProjectError("an engine version cannot be empty")
        if self.version != self.version.strip():
            raise InvalidProjectError("an engine version cannot have surrounding whitespace")
        if len(self.version) > MAX_ENGINE_VERSION_LENGTH:
            raise InvalidProjectError(
                f"an engine version cannot exceed {MAX_ENGINE_VERSION_LENGTH} characters"
            )
        if any(
            unicodedata.category(character).startswith("C")
            for character in self.version
        ):
            raise InvalidProjectError("an engine version cannot contain control characters")


@dataclass(frozen=True, slots=True)
class ProjectTarget:
    """A target platform family with an optional generation or storefront label."""

    platform: PlatformFamily
    label: DisplayName | None = None

    def __post_init__(self) -> None:
        if self.platform is PlatformFamily.OTHER and self.label is None:
            raise InvalidProjectError("an 'other' platform target requires a label")


@dataclass(frozen=True, slots=True)
class Project:
    """Immutable aggregate for project identity and lifecycle decisions."""

    identity: ProjectIdentity
    dimensions: ProjectDimension
    targets: frozenset[ProjectTarget]
    stage: ProjectStage = ProjectStage.CONCEPT
    lifecycle: ProjectLifecycle = ProjectLifecycle.ACTIVE
    engine: EngineSpec | None = None

    def __post_init__(self) -> None:
        if not self.targets:
            raise InvalidProjectError("a project requires at least one target platform")
        if self.lifecycle is ProjectLifecycle.COMPLETED and self.stage not in _COMPLETABLE_STAGES:
            raise InvalidProjectError(
                "a completed project must be in the released or post-release stage"
            )

    def can_transition_stage(self, target: ProjectStage) -> bool:
        """Return whether the requested stage transition is currently valid."""
        if target is self.stage:
            return True
        if self.lifecycle is not ProjectLifecycle.ACTIVE:
            return False
        return target in _STAGE_TRANSITIONS[self.stage]

    def transition_stage(self, target: ProjectStage) -> Project:
        """Return a new project at an adjacent allowed production stage."""
        if target is self.stage:
            return self
        if not self.can_transition_stage(target):
            raise InvalidProjectTransitionError(
                f"cannot transition project stage from {self.stage.value!r} "
                f"to {target.value!r} while lifecycle is {self.lifecycle.value!r}"
            )
        return replace(self, stage=target)

    def can_transition_lifecycle(self, target: ProjectLifecycle) -> bool:
        """Return whether the requested lifecycle transition is valid."""
        if target is self.lifecycle:
            return True
        if target not in _LIFECYCLE_TRANSITIONS[self.lifecycle]:
            return False
        if target is ProjectLifecycle.COMPLETED and self.stage not in _COMPLETABLE_STAGES:
            return False
        return True

    def transition_lifecycle(self, target: ProjectLifecycle) -> Project:
        """Return a new project in an allowed lifecycle state."""
        if target is self.lifecycle:
            return self
        if not self.can_transition_lifecycle(target):
            raise InvalidProjectTransitionError(
                f"cannot transition project lifecycle from {self.lifecycle.value!r} "
                f"to {target.value!r} at stage {self.stage.value!r}"
            )
        return replace(self, lifecycle=target)
