"""Tests for schema, template, and profile revision versions."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ludowright.domain import (
    InvalidVersionError,
    ProfileVersion,
    SchemaVersion,
    TemplateVersion,
    VisualBibleVersion,
)


def test_revision_parsing_and_canonical_forms() -> None:
    version = SchemaVersion.parse("v12")

    assert version == SchemaVersion(12)
    assert str(version) == "12"
    assert version.tag == "v12"
    assert SchemaVersion.parse("12") == version
    assert SchemaVersion.parse(12) == version


@pytest.mark.parametrize(
    "value",
    [
        True,
        0,
        -1,
        1.0,
        None,
        "",
        "0",
        "v0",
        "01",
        "v01",
        "1.0",
        "V1",
        "version-1",
    ],
)
def test_invalid_revisions_are_rejected(value: object) -> None:
    with pytest.raises(InvalidVersionError):
        SchemaVersion.parse(value)


def test_revision_types_do_not_compare_equal() -> None:
    schema = SchemaVersion(1)
    template = TemplateVersion(1)
    profile = ProfileVersion(1)
    visual_bible = VisualBibleVersion(1)

    assert schema != template
    assert template != profile
    assert profile != visual_bible
    assert len({schema, template, profile, visual_bible}) == 4


def test_revisions_are_ordered_within_the_same_contract_type() -> None:
    assert SchemaVersion(2) > SchemaVersion(1)


@given(st.integers(min_value=1, max_value=2_147_483_647))
def test_revision_tag_round_trip(value: int) -> None:
    version = ProfileVersion(value)

    assert ProfileVersion.parse(version.tag) == version
    assert ProfileVersion.parse(str(version)) == version
