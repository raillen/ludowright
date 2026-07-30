"""Tests for the versioned, data-driven asset taxonomy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    AssetTaxonomyValidationError,
    load_asset_taxonomy,
)
from ludowright.contracts import AssetTaxonomyContract
from ludowright.domain import AssetFamily, AssetId, AssetSubtype


def test_packaged_taxonomy_is_complete_and_deterministic() -> None:
    first = load_asset_taxonomy()
    second = load_asset_taxonomy()

    assert first == second
    assert len(first.contract.families) == len(AssetFamily)
    assert tuple(definition.family.value for definition in first.contract.families) == tuple(
        sorted(family.value for family in AssetFamily)
    )
    assert len(first.source_digest) == 64
    assert first.contract.version == 1


def test_subtypes_are_data_driven_and_family_specific() -> None:
    taxonomy = load_asset_taxonomy()

    assert taxonomy.supports_subtype(AssetFamily.CHARACTER, "humanoid")
    assert not taxonomy.supports_subtype(AssetFamily.CHARACTER, "quadruped")
    assert taxonomy.supports_subtype(AssetFamily.OTHER, "custom")

    classification = taxonomy.validate_classification(
        AssetFamily.CHARACTER,
        AssetSubtype("humanoid"),
    )
    assert classification.family is AssetFamily.CHARACTER
    assert classification.subtype == AssetSubtype("humanoid")


def test_taxonomy_rejects_undeclared_subtypes() -> None:
    with pytest.raises(AssetTaxonomyValidationError, match="not declared"):
        load_asset_taxonomy().validate_classification(AssetFamily.CHARACTER, "quadruped")


def test_taxonomy_preserves_domain_rule_for_other_without_subtype() -> None:
    with pytest.raises(AssetTaxonomyValidationError, match="requires a subtype"):
        load_asset_taxonomy().validate_classification(AssetFamily.OTHER)


@pytest.mark.parametrize(
    ("family", "asset_id"),
    [
        (AssetFamily.CHARACTER, "prop-maya"),
        (AssetFamily.PROP, "prop"),
        (AssetFamily.PROP, "prop-"),
    ],
)
def test_naming_policy_rejects_invalid_family_prefixes(
    family: AssetFamily,
    asset_id: str,
) -> None:
    with pytest.raises(AssetTaxonomyValidationError):
        load_asset_taxonomy().validate_asset_id(family, asset_id)


def test_naming_policy_accepts_canonical_asset_ids() -> None:
    taxonomy = load_asset_taxonomy()

    result = taxonomy.validate_asset_id(AssetFamily.PROP, AssetId("prop-arcade-cabinet"))

    assert result is not None
    assert result.value == "prop-arcade-cabinet"
    assert taxonomy.naming_rule(AssetFamily.CHARACTER).prefix == "chr"


def test_taxonomy_contract_rejects_missing_family() -> None:
    payload = load_asset_taxonomy().contract.model_dump(mode="json")
    payload["families"] = payload["families"][:-1]

    with pytest.raises(ValidationError, match="cover every asset family"):
        AssetTaxonomyContract.model_validate(payload)


def test_taxonomy_data_is_json_and_matches_the_loaded_contract() -> None:
    data_path = Path("src/ludowright/taxonomy_data/asset-taxonomy.json")
    payload = json.loads(data_path.read_text(encoding="utf-8"))

    assert payload == load_asset_taxonomy().contract.model_dump(mode="json")
