"""Shared bounded guidance validation for visual profile specializations."""

from __future__ import annotations

import unicodedata

from ludowright.domain.errors import InvalidCaptureProfileError

MAX_PROFILE_GUIDANCE_LENGTH = 1_000


def validate_profile_guidance(value: str, field_name: str) -> None:
    """Validate one bounded, normalized, control-free profile guidance value."""
    if not isinstance(value, str) or not value:
        raise InvalidCaptureProfileError(f"{field_name} cannot be empty")
    if len(value) > MAX_PROFILE_GUIDANCE_LENGTH:
        raise InvalidCaptureProfileError(
            f"{field_name} cannot exceed {MAX_PROFILE_GUIDANCE_LENGTH} characters"
        )
    if unicodedata.normalize("NFC", value) != value:
        raise InvalidCaptureProfileError(f"{field_name} must use Unicode NFC")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise InvalidCaptureProfileError(f"{field_name} cannot contain control characters")


__all__ = ["MAX_PROFILE_GUIDANCE_LENGTH", "validate_profile_guidance"]
