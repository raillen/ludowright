"""Tests for data-defined humanoid and wearable profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    HumanoidProfileNotFoundError,
    load_humanoid_profile,
)
from ludowright.contracts import HumanoidProfileContract
from ludowright.domain import (
    HumanoidWearableKind,
    NeutralRepresentationMode,
)

FIXTURE = Path("tests/fixtures/contracts/v1/humanoid-profile.json")


def test_minimal_profile_covers_body_wearable_categories_and_outputs() -> None:
    profile = load_humanoid_profile()

    assert profile.id.value == "humanoid-minimal"
    assert profile.version.value == 1
    assert profile.neutral_representation.mode is NeutralRepresentationMode.NEUTRAL_BODYSUIT
    assert profile.body_base.id.value == "base-body"
    assert set(profile.wearable_ids_by_kind) == set(HumanoidWearableKind)
    assert profile.to_capture_profile().required_view_ids == (
        profile.capture_profile.views[0].id,
        profile.capture_profile.views[1].id,
        profile.capture_profile.views[2].id,
    )
    assert tuple(sheet.id.value for sheet in profile.to_capture_profile().sheets) == (
        "assembled-turnaround",
        "component-views",
    )


def test_profile_loading_and_derivation_are_deterministic() -> None:
    first = load_humanoid_profile()
    second = load_humanoid_profile()

    assert first == second
    assert first.to_capture_profile() == second.to_capture_profile()


def test_profile_fixture_validates_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    contract = HumanoidProfileContract.model_validate(payload)

    assert contract.to_domain().id.value == "humanoid-fixture"
    assert (
        HumanoidProfileContract.model_validate(contract.model_dump(mode="json", exclude_none=True))
        == contract
    )


def test_profile_rejects_unknown_policy_and_duplicate_component_mapping() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["neutral_representation"]["mode"] = "bare-body"
    with pytest.raises(ValidationError):
        HumanoidProfileContract.model_validate(payload)

    invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid["capture_profile"]["requirements"].append(
        {
            "id": "unlisted-component",
            "name": "Unlisted",
            "requirement_kind": "component",
        }
    )
    with pytest.raises(ValidationError):
        HumanoidProfileContract.model_validate(invalid)


def test_unknown_profile_is_reported_as_not_found() -> None:
    with pytest.raises(HumanoidProfileNotFoundError):
        load_humanoid_profile("does-not-exist")
