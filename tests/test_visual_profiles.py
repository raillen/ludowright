"""Tests for data-defined foliage, UI, VFX, and animation profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    VisualProfileNotFoundError,
    load_visual_profile,
)
from ludowright.contracts import VisualProfileContract
from ludowright.domain import AssetFamily, VisualProfileKind

FIXTURE = Path("tests/fixtures/contracts/v1/visual-profile.json")
PROFILE_IDS = tuple(kind.value for kind in VisualProfileKind)


@pytest.mark.parametrize("profile_id", PROFILE_IDS)
def test_catalog_profile_is_valid_and_derives_generic_capture_profile(profile_id: str) -> None:
    profile = load_visual_profile(profile_id)
    capture_profile = profile.to_capture_profile()

    expected_classifications = {
        "tree": (AssetFamily.VEGETATION, "large-tree"),
        "plant": (AssetFamily.VEGETATION, "plant"),
        "interface-icon": (AssetFamily.UI, "interface-icon"),
        "menu": (AssetFamily.UI, "menu"),
        "particle-effect": (AssetFamily.VFX, "particle-effect"),
        "shader-effect": (AssetFamily.VFX, "shader-effect"),
        "locomotion": (AssetFamily.ANIMATION, "locomotion"),
        "motion-set": (AssetFamily.ANIMATION, "motion-set"),
    }
    expected_family, expected_subtype = expected_classifications[profile_id]

    assert capture_profile.family is expected_family
    assert capture_profile.subtype is not None
    assert capture_profile.subtype.value == expected_subtype
    assert profile.guidance
    assert profile.views
    assert profile.components
    assert profile.states
    assert any(sheet.assembled_sheet for sheet in capture_profile.sheets)


def test_profile_loading_and_derivation_are_deterministic() -> None:
    first = tuple(load_visual_profile(profile_id) for profile_id in PROFILE_IDS)
    second = tuple(load_visual_profile(profile_id) for profile_id in PROFILE_IDS)

    assert first == second
    assert tuple(profile.to_capture_profile() for profile in first) == tuple(
        profile.to_capture_profile() for profile in second
    )


def test_profile_fixture_validates_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    contract = VisualProfileContract.model_validate(payload)

    assert contract.to_domain().id.value == "visual-fixture"
    assert (
        VisualProfileContract.model_validate(contract.model_dump(mode="json", exclude_none=True))
        == contract
    )


def test_profile_rejects_classification_and_requirement_mismatches() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["capture_profile"]["family"] = "vfx"
    with pytest.raises(ValidationError):
        VisualProfileContract.model_validate(payload)

    invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid["capture_profile"]["requirements"][2]["requirement_kind"] = "state"
    with pytest.raises(ValidationError):
        VisualProfileContract.model_validate(invalid)


def test_profile_rejects_duplicate_or_unknown_view_and_missing_subject() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["views"].append(payload["views"][0].copy())
    with pytest.raises(ValidationError):
        VisualProfileContract.model_validate(payload)

    invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid["views"][0]["view_id"] = "missing-view"
    with pytest.raises(ValidationError):
        VisualProfileContract.model_validate(invalid)

    invalid_subject = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid_subject["components"][0]["kind"] = "icon"
    with pytest.raises(ValidationError):
        VisualProfileContract.model_validate(invalid_subject)


def test_unknown_profile_is_reported_as_not_found() -> None:
    with pytest.raises(VisualProfileNotFoundError):
        load_visual_profile("does-not-exist")


@pytest.mark.parametrize("profile_id", ("../tree", "Interface-Icon", ""))
def test_noncanonical_profile_id_cannot_escape_package_catalog(profile_id: str) -> None:
    with pytest.raises(VisualProfileNotFoundError):
        load_visual_profile(profile_id)
