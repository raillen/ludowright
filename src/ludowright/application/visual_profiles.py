"""Load versioned foliage, UI, VFX, and animation profile data."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from pydantic import ValidationError

from ludowright.contracts import VisualProfileContract
from ludowright.domain import InvalidCaptureProfileError, VisualProfile, validate_slug


class VisualProfileError(RuntimeError):
    """Base error for packaged visual-profile loading."""


class VisualProfileNotFoundError(VisualProfileError):
    """Raised when a requested packaged visual profile is unavailable."""


class VisualProfileDefinitionError(VisualProfileError):
    """Raised when packaged visual-profile data is malformed."""


def load_visual_profile(profile_id: str) -> VisualProfile:
    """Load and validate one versioned visual profile from package data."""
    try:
        validate_slug(profile_id)
    except ValueError as error:
        raise VisualProfileNotFoundError(
            f"visual profile ID is not canonical: {profile_id!r}"
        ) from error

    resource = resources.files("ludowright").joinpath(
        "profile_data", "visual", profile_id, "manifest.json"
    )
    try:
        raw = json.loads(
            _decode_profile_data(resource.read_bytes()),
            object_pairs_hook=_unique_object,
        )
        contract = VisualProfileContract.model_validate(raw)
        return contract.to_domain()
    except VisualProfileError:
        raise
    except (json.JSONDecodeError, InvalidCaptureProfileError, ValidationError) as error:
        raise VisualProfileDefinitionError(
            f"visual profile manifest is invalid: {profile_id!r}"
        ) from error
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise VisualProfileNotFoundError(
            f"visual profile is not available: {profile_id!r}"
        ) from error


def _decode_profile_data(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise VisualProfileDefinitionError("visual profile data cannot contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise VisualProfileDefinitionError("visual profile data must be valid UTF-8") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VisualProfileDefinitionError("visual profile JSON cannot contain duplicate keys")
        result[key] = value
    return result


__all__ = [
    "VisualProfileDefinitionError",
    "VisualProfileError",
    "VisualProfileNotFoundError",
    "load_visual_profile",
]
