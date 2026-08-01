"""Load versioned environment and hard-surface profile data."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from pydantic import ValidationError

from ludowright.contracts import HardSurfaceProfileContract
from ludowright.domain import HardSurfaceProfile, InvalidCaptureProfileError, validate_slug


class HardSurfaceProfileError(RuntimeError):
    """Base error for packaged hard-surface profile loading."""


class HardSurfaceProfileNotFoundError(HardSurfaceProfileError):
    """Raised when a requested packaged hard-surface profile is unavailable."""


class HardSurfaceProfileDefinitionError(HardSurfaceProfileError):
    """Raised when packaged hard-surface profile data is malformed."""


def load_hard_surface_profile(profile_id: str) -> HardSurfaceProfile:
    """Load and validate one versioned hard-surface profile from package data."""
    try:
        validate_slug(profile_id)
    except ValueError as error:
        raise HardSurfaceProfileNotFoundError(
            f"hard-surface profile ID is not canonical: {profile_id!r}"
        ) from error

    resource = resources.files("ludowright").joinpath(
        "profile_data", "hard-surface", profile_id, "manifest.json"
    )
    try:
        raw = json.loads(
            _decode_profile_data(resource.read_bytes()),
            object_pairs_hook=_unique_object,
        )
        contract = HardSurfaceProfileContract.model_validate(raw)
        return contract.to_domain()
    except HardSurfaceProfileError:
        raise
    except (json.JSONDecodeError, InvalidCaptureProfileError, ValidationError) as error:
        raise HardSurfaceProfileDefinitionError(
            f"hard-surface profile manifest is invalid: {profile_id!r}"
        ) from error
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise HardSurfaceProfileNotFoundError(
            f"hard-surface profile is not available: {profile_id!r}"
        ) from error


def _decode_profile_data(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise HardSurfaceProfileDefinitionError(
            "hard-surface profile data cannot contain a UTF-8 BOM"
        )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HardSurfaceProfileDefinitionError(
            "hard-surface profile data must be valid UTF-8"
        ) from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HardSurfaceProfileDefinitionError(
                "hard-surface profile JSON cannot contain duplicate keys"
            )
        result[key] = value
    return result


__all__ = [
    "HardSurfaceProfileDefinitionError",
    "HardSurfaceProfileError",
    "HardSurfaceProfileNotFoundError",
    "load_hard_surface_profile",
]
