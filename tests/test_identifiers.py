"""Tests for canonical names, slugs, and typed identifiers."""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from ludowright.domain import (
    AssetId,
    DisplayName,
    InvalidIdentifierError,
    InvalidNameError,
    ProjectId,
    slugify,
    validate_slug,
)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "Uppercase",
        "two--hyphens",
        "leading-",
        "-trailing",
        "contains_underscore",
        "contains/slash",
        "ação",
        "con",
        "lpt9",
        "a" * 81,
    ],
)
def test_invalid_slugs_are_rejected(value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_slug(value)


def test_slugify_normalizes_international_display_names() -> None:
    assert slugify("Última Ficha: Edição 2000!") == "ultima-ficha-edicao-2000"
    assert slugify("CON") == "con-item"


def test_identifier_types_do_not_compare_equal() -> None:
    project_id = ProjectId("shared-value")
    asset_id = AssetId("shared-value")

    assert project_id != asset_id
    assert len({project_id, asset_id}) == 2
    assert repr(project_id) == "ProjectId('shared-value')"


def test_identifier_can_be_created_explicitly_from_name() -> None:
    identifier = ProjectId.from_name("Locadora 2000")

    assert identifier == ProjectId("locadora-2000")
    assert str(identifier) == "locadora-2000"


@pytest.mark.parametrize(
    "value",
    [
        "",
        " surrounding whitespace ",
        "line\nbreak",
        "zero\u200bwidth",
        "a" * 121,
        unicodedata.normalize("NFD", "Edição"),
    ],
)
def test_invalid_display_names_are_rejected(value: str) -> None:
    with pytest.raises(InvalidNameError):
        DisplayName(value)


def test_display_name_preserves_valid_unicode() -> None:
    name = DisplayName("Última Ficha — Edição Brasileira")

    assert str(name) == "Última Ficha — Edição Brasileira"


_SLUG_SOURCE_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " áéíóúâêôãõç-_/.,:;!?()[]"
)


@given(st.text(alphabet=_SLUG_SOURCE_ALPHABET, min_size=1, max_size=200))
def test_slugify_always_returns_an_idempotent_valid_slug(value: str) -> None:
    assume(any(character.isalnum() for character in value))

    slug = slugify(value)

    assert validate_slug(slug) == slug
    assert slugify(slug) == slug
    assert len(slug) <= 80
