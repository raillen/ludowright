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


class ReferenceId(Identifier):
    """Identifier for an external, candidate, approved, or rejected reference."""

    kind = "reference"


class JobId(Identifier):
    """Identifier for a deterministic workflow or generation job."""

    kind = "job"


class DecisionId(Identifier):
    """Identifier for a recorded project decision."""

    kind = "decision"


class PackageId(Identifier):
    """Identifier for a reproducible project or production package."""

    kind = "package"
