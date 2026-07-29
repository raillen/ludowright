"""Tests for versioned JSON Schema publication and compatibility fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.contracts import (
    CONTRACTS,
    JSON_SCHEMA_DRAFT,
    SCHEMA_VERSION,
    publication_drift,
    publication_files,
)
from ludowright.contracts.registry import ContractDefinition

FIXTURE_ROOT = Path("tests/fixtures/contracts") / f"v{SCHEMA_VERSION}"
SCHEMA_ROOT = Path("schemas") / f"v{SCHEMA_VERSION}"


@pytest.mark.parametrize("definition", CONTRACTS, ids=lambda item: item.name)
def test_canonical_fixture_validates_against_contract(
    definition: ContractDefinition,
) -> None:
    fixture_path = FIXTURE_ROOT / f"{definition.name}.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    instance = definition.model.model_validate(payload)

    assert instance.schema_version == SCHEMA_VERSION
    assert instance.kind == definition.name


@pytest.mark.parametrize("definition", CONTRACTS, ids=lambda item: item.name)
def test_contracts_reject_unknown_fields(definition: ContractDefinition) -> None:
    fixture_path = FIXTURE_ROOT / f"{definition.name}.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        definition.model.model_validate(payload)


def test_checked_in_schema_publication_has_no_drift() -> None:
    assert publication_drift(SCHEMA_ROOT) == ()


def test_every_published_schema_uses_stable_metadata() -> None:
    rendered = publication_files()

    for definition in CONTRACTS:
        schema = json.loads(rendered[definition.filename])
        assert schema["$schema"] == JSON_SCHEMA_DRAFT
        assert schema["$id"] == definition.schema_id
        assert schema["title"] == definition.title
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
        assert schema["properties"]["kind"]["const"] == definition.name


def test_manifest_locks_every_schema_checksum() -> None:
    rendered = publication_files()
    manifest = json.loads(rendered["manifest.json"])

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["json_schema_draft"] == JSON_SCHEMA_DRAFT
    assert [entry["name"] for entry in manifest["schemas"]] == [
        definition.name for definition in CONTRACTS
    ]

    for entry in manifest["schemas"]:
        content = rendered[entry["file"]]
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert entry["sha256"] == digest


def test_publication_is_deterministic() -> None:
    assert publication_files() == publication_files()


@pytest.mark.parametrize("definition", CONTRACTS, ids=lambda item: item.name)
def test_v1_compatibility_fixture_round_trips(
    definition: ContractDefinition,
) -> None:
    fixture_path = FIXTURE_ROOT / f"{definition.name}.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    instance = definition.model.model_validate(payload)
    serialized = instance.model_dump(mode="json", exclude_none=True)

    reloaded = definition.model.model_validate(serialized)

    assert reloaded == instance
