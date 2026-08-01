"""Tests for data-defined environment and hard-surface profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    HardSurfaceProfileNotFoundError,
    load_hard_surface_profile,
)
from ludowright.contracts import HardSurfaceProfileContract
from ludowright.domain import AssetFamily, HardSurfaceProfileKind

FIXTURE = Path("tests/fixtures/contracts/v1/hard-surface-profile.json")
PROFILE_IDS = tuple(kind.value for kind in HardSurfaceProfileKind)


@pytest.mark.parametrize("profile_id", PROFILE_IDS)
def test_catalog_profile_is_valid_and_derives_generic_capture_profile(profile_id: str) -> None:
    profile = load_hard_surface_profile(profile_id)
    capture_profile = profile.to_capture_profile()

    expected_classifications = {
        "prop": (AssetFamily.PROP, None),
        "vehicle": (AssetFamily.VEHICLE, "vehicle"),
        "building": (AssetFamily.ARCHITECTURE, "building"),
        "modular-kit": (AssetFamily.ENVIRONMENT, "modular-environment"),
        "interior": (AssetFamily.ENVIRONMENT, "interior"),
    }
    expected_family, expected_subtype = expected_classifications[profile_id]

    assert capture_profile.family is expected_family
    assert (capture_profile.subtype.value if capture_profile.subtype else None) == expected_subtype
    assert profile.construction_views
    assert profile.components
    assert profile.connection_matrix
    assert profile.states
    assert any(sheet.assembled_sheet for sheet in capture_profile.sheets)


def test_profile_loading_and_derivation_are_deterministic() -> None:
    first = tuple(load_hard_surface_profile(profile_id) for profile_id in PROFILE_IDS)
    second = tuple(load_hard_surface_profile(profile_id) for profile_id in PROFILE_IDS)

    assert first == second
    assert tuple(profile.to_capture_profile() for profile in first) == tuple(
        profile.to_capture_profile() for profile in second
    )


def test_profile_fixture_validates_and_round_trips() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    contract = HardSurfaceProfileContract.model_validate(payload)

    assert contract.to_domain().id.value == "hard-surface-fixture"
    assert (
        HardSurfaceProfileContract.model_validate(
            contract.model_dump(mode="json", exclude_none=True)
        )
        == contract
    )


def test_profile_rejects_classification_mismatch_and_unknown_construction_view() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["capture_profile"]["family"] = "vehicle"
    with pytest.raises(ValidationError):
        HardSurfaceProfileContract.model_validate(payload)

    invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid["construction_views"][0]["view_id"] = "missing-view"
    with pytest.raises(ValidationError):
        HardSurfaceProfileContract.model_validate(invalid)


def test_connection_matrix_rejects_duplicate_rows_and_self_loops() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["connection_matrix"].append(payload["connection_matrix"][0].copy())
    with pytest.raises(ValidationError):
        HardSurfaceProfileContract.model_validate(payload)

    invalid = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid["connection_matrix"][0]["target_component_id"] = "root"
    with pytest.raises(ValidationError):
        HardSurfaceProfileContract.model_validate(invalid)


def test_unknown_profile_is_reported_as_not_found() -> None:
    with pytest.raises(HardSurfaceProfileNotFoundError):
        load_hard_surface_profile("does-not-exist")


@pytest.mark.parametrize("profile_id", ("../prop", "Vehicle", ""))
def test_noncanonical_profile_id_cannot_escape_package_catalog(profile_id: str) -> None:
    with pytest.raises(HardSurfaceProfileNotFoundError):
        load_hard_surface_profile(profile_id)
