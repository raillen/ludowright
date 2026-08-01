"""Tests for the immutable visual-bible contract and domain invariants."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.contracts import VisualBibleContract
from ludowright.domain import (
    DetailLevel,
    DetailLevelRule,
    InvalidVisualBibleError,
    LevelOfDetail,
    VisualText,
)

FIXTURE = Path("tests/fixtures/contracts/v1/visual-bible.json")


def load_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_visual_bible_fixture_validates_and_converts_to_domain() -> None:
    contract = VisualBibleContract.model_validate(load_payload())
    domain = contract.to_domain()

    assert domain.id.value == "default-visual-bible"
    assert domain.project_id.value == "ludowright-demo"
    assert domain.version.value == 1
    assert domain.camera.projection.value == "orthographic"
    assert domain.level_of_detail.default_level is DetailLevel.MEDIUM
    assert len(domain.palette) == 3


def test_visual_bible_requires_unique_entry_ids() -> None:
    payload = load_payload()
    proportions = payload["proportions"]
    assert isinstance(proportions, list)
    payload["proportions"] = [*proportions, copy.deepcopy(proportions[0])]

    with pytest.raises(ValidationError, match="proportion rule IDs"):
        VisualBibleContract.model_validate(payload)


def test_visual_bible_rejects_constraint_overlap() -> None:
    payload = load_payload()
    prompt_constraints = payload["prompt_constraints"]
    negative_constraints = payload["negative_constraints"]
    assert isinstance(prompt_constraints, list)
    assert isinstance(negative_constraints, list)
    negative_constraints.append(prompt_constraints[0])

    with pytest.raises(ValidationError, match="cannot contain the same statement"):
        VisualBibleContract.model_validate(payload)


def test_visual_bible_requires_default_detail_rule() -> None:
    payload = load_payload()
    level_of_detail = payload["level_of_detail"]
    assert isinstance(level_of_detail, dict)
    level_of_detail["default_level"] = "hero"

    with pytest.raises(ValidationError, match="default detail level"):
        VisualBibleContract.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "budget",
            {
                "max_visual_jobs": 0,
                "max_generated_outputs": 1,
                "max_references_per_asset": 1,
            },
            "greater than or equal to 1",
        ),
        (
            "palette",
            [{"id": "ink", "name": "Ink", "color": "#ffffff", "role": "primary"}],
            "string_pattern_mismatch",
        ),
    ],
)
def test_visual_bible_rejects_unsafe_numeric_and_color_values(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = load_payload()
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        VisualBibleContract.model_validate(payload)


def test_shape_language_rejects_repeated_primary_descriptor() -> None:
    payload = load_payload()
    shape_language = payload["shape_language"]
    assert isinstance(shape_language, dict)
    shape_language["secondary"] = [shape_language["primary"]]

    with pytest.raises(ValidationError, match="primary descriptor"):
        VisualBibleContract.model_validate(payload)


def test_domain_rejects_empty_or_duplicate_detail_bands() -> None:
    rule = DetailLevelRule(DetailLevel.MEDIUM, VisualText("Preserve the main forms."))

    with pytest.raises(InvalidVisualBibleError, match="at least one rule"):
        LevelOfDetail(DetailLevel.MEDIUM, ())

    with pytest.raises(InvalidVisualBibleError, match="unique values"):
        LevelOfDetail(DetailLevel.MEDIUM, (rule, rule))


def test_visual_text_rejects_control_characters() -> None:
    with pytest.raises(InvalidVisualBibleError, match="control"):
        VisualText("line one\nline two")
