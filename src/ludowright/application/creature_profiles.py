"""Load versioned creature and animal profile data from the package."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from pydantic import ValidationError

from ludowright.contracts import CreatureProfileContract
from ludowright.domain import CreatureProfile, InvalidCaptureProfileError, validate_slug


class CreatureProfileError(RuntimeError):
    """Base error for packaged creature profile loading."""


class CreatureProfileNotFoundError(CreatureProfileError):
    """Raised when a requested packaged creature profile is unavailable."""


class CreatureProfileDefinitionError(CreatureProfileError):
    """Raised when packaged creature profile data is malformed."""


def load_creature_profile(profile_id: str) -> CreatureProfile:
    """Load and validate one versioned creature profile from package data."""
    try:
        validate_slug(profile_id)
    except ValueError as error:
        raise CreatureProfileNotFoundError(
            f"creature profile ID is not canonical: {profile_id!r}"
        ) from error

    resource = resources.files("ludowright").joinpath(
        "profile_data", "creature", profile_id, "manifest.json"
    )
    try:
        raw = json.loads(
            _decode_profile_data(resource.read_bytes()),
            object_pairs_hook=_unique_object,
        )
        contract = CreatureProfileContract.model_validate(raw)
        return contract.to_domain()
    except CreatureProfileError:
        raise
    except (json.JSONDecodeError, InvalidCaptureProfileError, ValidationError) as error:
        raise CreatureProfileDefinitionError(
            f"creature profile manifest is invalid: {profile_id!r}"
        ) from error
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise CreatureProfileNotFoundError(
            f"creature profile is not available: {profile_id!r}"
        ) from error


def _decode_profile_data(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise CreatureProfileDefinitionError("creature profile data cannot contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CreatureProfileDefinitionError("creature profile data must be valid UTF-8") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CreatureProfileDefinitionError(
                "creature profile JSON cannot contain duplicate keys"
            )
        result[key] = value
    return result


__all__ = [
    "CreatureProfileDefinitionError",
    "CreatureProfileError",
    "CreatureProfileNotFoundError",
    "load_creature_profile",
]
