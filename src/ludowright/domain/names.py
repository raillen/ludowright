"""Canonical human-readable names and repository-safe slugs."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ludowright.domain.errors import InvalidIdentifierError, InvalidNameError

MAX_SLUG_LENGTH = 80
MAX_DISPLAY_NAME_LENGTH = 120

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")
_RESERVED_SLUGS = {
    "aux",
    "clock",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def validate_slug(value: str) -> str:
    """Validate and return a canonical lowercase ASCII slug."""
    if not value:
        raise InvalidIdentifierError("a slug cannot be empty")
    if len(value) > MAX_SLUG_LENGTH:
        raise InvalidIdentifierError(
            f"a slug cannot exceed {MAX_SLUG_LENGTH} characters"
        )
    if not value.isascii():
        raise InvalidIdentifierError("a slug must contain ASCII characters only")
    if _SLUG_PATTERN.fullmatch(value) is None:
        raise InvalidIdentifierError(
            "a slug must use lowercase letters, digits, and single hyphen separators"
        )
    if value in _RESERVED_SLUGS:
        raise InvalidIdentifierError(f"{value!r} is reserved and cannot be used as a slug")
    return value


def slugify(value: str) -> str:
    """Convert a human-readable value into a canonical repository-safe slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_SEPARATOR_PATTERN.sub("-", ascii_value).strip("-")
    slug = slug[:MAX_SLUG_LENGTH].rstrip("-")

    if not slug:
        raise InvalidIdentifierError("the value does not contain characters usable in a slug")
    if slug in _RESERVED_SLUGS:
        slug = f"{slug}-item"

    return validate_slug(slug)


@dataclass(frozen=True, slots=True)
class DisplayName:
    """A normalized human-readable name that is never used directly as a path."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidNameError("a display name cannot be empty")
        if self.value != self.value.strip():
            raise InvalidNameError("a display name cannot have surrounding whitespace")
        if unicodedata.normalize("NFC", self.value) != self.value:
            raise InvalidNameError("a display name must use canonical Unicode NFC normalization")
        if len(self.value) > MAX_DISPLAY_NAME_LENGTH:
            raise InvalidNameError(
                f"a display name cannot exceed {MAX_DISPLAY_NAME_LENGTH} characters"
            )
        if any(unicodedata.category(character).startswith("C") for character in self.value):
            raise InvalidNameError("a display name cannot contain control or format characters")

    def __str__(self) -> str:
        return self.value
