"""Tests for data-defined creature and animal profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    CreatureProfileNotFoundError,
    load_creature_profile,
)
from ludowright.contracts import CreatureProfileContract
from ludowright.domain import AssetFamily, CreatureProfileKind

FIXTURE = Path("tests/fixtures/contracts/v1/creature-profile.json")
PROFILE_IDS = tuple(kind.value for kind in CreatureProfileKind)


@pytest.mark.parametrize("profile_id", PROFILE_IDS)
def test_catalog_profile_is_valid_and_derives_generic_capture_profile(profile_id: str) -> None:
    profile = load_creature_profile(profile_id)
    capture_profile = profile.to_capture_profile()

    assert capture_profile.family is AssetFamily.CREATURE
    assert capture_profile.subtype is not None
    assert capture_profile.subtype.value == profile_id
    assert profile.anatomy_views
    assert profile.components
    assert profile.states
    assert any(sheet.assembled_sheet for sheet in capture_profile.sheets)


def test_profile_loading_and_derivation_are_deterministic() -> None:
    first = tuple(load_creature_profile(profile_id) for profile_id in PROFILE_IDS)
    second = tuple(load_creature_profile(profile_id) for profile_id in PROFILE_IDS)

    assert first == second
    assert tuple(profile.to_capture_profile() for profile in first) == tuple(
        profile.to_capture_profile() for profile in second
    )


def test_profile_fixture_validates_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    contract = CreatureProfileContract.model_validate(payload)

    assert contract.to_domain().id.value == "creature-fixture"
    assert (
        CreatureProfileContract.model_validate(contract.model_dump(mode="json", exclude_none=True))
        == contract
    )


def test_profile_rejects_subtype_mismatch_and_unknown_anatomy_view() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["anatomy"]["kind"] = "bird"
    with pytest.raises(ValidationError):
        CreatureProfileContract.model_validate(payload)

    invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid["anatomy_views"][0]["view_id"] = "missing-view"
    with pytest.raises(ValidationError):
        CreatureProfileContract.model_validate(invalid)


def test_unknown_profile_is_reported_as_not_found() -> None:
    with pytest.raises(CreatureProfileNotFoundError):
        load_creature_profile("does-not-exist")


@pytest.mark.parametrize("profile_id", ("../minimal", "Bird", ""))
def test_noncanonical_profile_id_cannot_escape_package_catalog(profile_id: str) -> None:
    with pytest.raises(CreatureProfileNotFoundError):
        load_creature_profile(profile_id)
