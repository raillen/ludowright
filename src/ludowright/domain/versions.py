"""Monotonic revision versions for persisted LudoWright contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Self

from ludowright.domain.errors import InvalidVersionError

MAX_REVISION = 2_147_483_647
_REVISION_PATTERN = re.compile(r"^v?([1-9][0-9]*)$")


@dataclass(frozen=True, order=True, slots=True)
class RevisionVersion:
    """A positive monotonic revision for a versioned contract."""

    value: int
    kind: ClassVar[str] = "revision"

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidVersionError("a revision version must be an integer")
        if self.value < 1:
            raise InvalidVersionError("a revision version must be greater than zero")
        if self.value > MAX_REVISION:
            raise InvalidVersionError(f"a revision version cannot exceed {MAX_REVISION}")

    @classmethod
    def parse(cls, value: int | str) -> Self:
        """Parse an integer, decimal string, or canonical `vN` tag."""
        if isinstance(value, bool):
            raise InvalidVersionError("a boolean is not a revision version")
        if isinstance(value, int):
            return cls(value)

        match = _REVISION_PATTERN.fullmatch(value)
        if match is None:
            raise InvalidVersionError(
                "a revision string must be a positive integer or canonical vN tag"
            )
        return cls(int(match.group(1)))

    @property
    def tag(self) -> str:
        """Return the canonical human-facing `vN` representation."""
        return f"v{self.value}"

    def __str__(self) -> str:
        return str(self.value)


class SchemaVersion(RevisionVersion):
    """Version of a persisted data schema."""

    kind = "schema"


class TemplateVersion(RevisionVersion):
    """Version of a deterministic document or sheet template."""

    kind = "template"


class ProfileVersion(RevisionVersion):
    """Version of a capture, asset-family, or production profile."""

    kind = "profile"
