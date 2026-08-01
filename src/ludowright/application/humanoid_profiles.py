"""Load versioned humanoid profile data from the package."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from pydantic import ValidationError

from ludowright.contracts import HumanoidProfileContract
from ludowright.domain import HumanoidProfile, InvalidCaptureProfileError, validate_slug


class HumanoidProfileError(RuntimeError):
    """Base error for packaged humanoid profile loading."""


class HumanoidProfileNotFoundError(HumanoidProfileError):
    """Raised when a requested packaged profile is unavailable."""


class HumanoidProfileDefinitionError(HumanoidProfileError):
    """Raised when packaged humanoid profile data is malformed."""


def load_humanoid_profile(profile_id: str = "minimal") -> HumanoidProfile:
    """Load and validate one versioned humanoid profile from package data."""
    try:
        validate_slug(profile_id)
    except ValueError as error:
        raise HumanoidProfileNotFoundError(
            f"humanoid profile ID is not canonical: {profile_id!r}"
        ) from error

    resource = resources.files("ludowright").joinpath(
        "profile_data", "humanoid", profile_id, "manifest.json"
    )
    try:
        raw = json.loads(
            _decode_profile_data(resource.read_bytes()),
            object_pairs_hook=_unique_object,
        )
        contract = HumanoidProfileContract.model_validate(raw)
        return contract.to_domain()
    except HumanoidProfileError:
        raise
    except (json.JSONDecodeError, InvalidCaptureProfileError, ValidationError) as error:
        raise HumanoidProfileDefinitionError(
            f"humanoid profile manifest is invalid: {profile_id!r}"
        ) from error
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise HumanoidProfileNotFoundError(
            f"humanoid profile is not available: {profile_id!r}"
        ) from error


def _decode_profile_data(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise HumanoidProfileDefinitionError("humanoid profile data cannot contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HumanoidProfileDefinitionError("humanoid profile data must be valid UTF-8") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HumanoidProfileDefinitionError(
                "humanoid profile JSON cannot contain duplicate keys"
            )
        result[key] = value
    return result


__all__ = [
    "HumanoidProfileDefinitionError",
    "HumanoidProfileError",
    "HumanoidProfileNotFoundError",
    "load_humanoid_profile",
]
