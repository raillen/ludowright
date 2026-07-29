"""Tests for asset classification, decomposition, ownership, and progress."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ludowright.domain import (
    Asset,
    AssetClassification,
    AssetComponent,
    AssetFamily,
    AssetId,
    AssetOwner,
    AssetPriority,
    AssetState,
    AssetStateId,
    AssetStatus,
    AssetSubtype,
    AssetVariant,
    ComponentId,
    DisplayName,
    InvalidAssetError,
    InvalidAssetTransitionError,
    OwnerId,
    OwnerKind,
    VariantId,
)

AssetItem = AssetComponent | AssetVariant | AssetState

_STATUS_PATH = (
    AssetStatus.SPECIFIED,
    AssetStatus.READY,
    AssetStatus.IN_PRODUCTION,
    AssetStatus.IN_REVIEW,
    AssetStatus.COMPLETED,
)


def complete_item(item: AssetItem) -> AssetItem:
    current = item
    for status in _STATUS_PATH:
        current = current.transition_status(status)
    return current


def make_owner() -> AssetOwner:
    return AssetOwner(
        id=OwnerId("character-team"),
        label=DisplayName("Character Team"),
        kind=OwnerKind.TEAM,
    )


def make_asset(
    *,
    status: AssetStatus = AssetStatus.PLANNED,
    components: tuple[AssetComponent, ...] = (),
    variants: tuple[AssetVariant, ...] = (),
    states: tuple[AssetState, ...] = (),
) -> Asset:
    return Asset(
        id=AssetId("chr-maya"),
        name=DisplayName("Maya"),
        classification=AssetClassification(
            AssetFamily.CHARACTER,
            AssetSubtype("humanoid"),
        ),
        priority=AssetPriority.HIGH,
        status=status,
        owner=make_owner(),
        components=components,
        variants=variants,
        states=states,
    )


def test_asset_preserves_classification_priority_and_owner() -> None:
    asset = make_asset()

    assert asset.id == AssetId("chr-maya")
    assert asset.classification.family is AssetFamily.CHARACTER
    assert asset.classification.subtype == AssetSubtype("humanoid")
    assert asset.priority is AssetPriority.HIGH
    assert asset.owner == make_owner()


def test_asset_aggregate_is_immutable() -> None:
    asset = make_asset()

    with pytest.raises(FrozenInstanceError):
        asset.status = AssetStatus.COMPLETED  # type: ignore[misc]


def test_other_family_requires_an_extensible_subtype() -> None:
    with pytest.raises(InvalidAssetError, match="requires a subtype"):
        AssetClassification(AssetFamily.OTHER)

    classification = AssetClassification(
        AssetFamily.OTHER,
        AssetSubtype("holographic-installation"),
    )
    assert str(classification.subtype) == "holographic-installation"


@pytest.mark.parametrize(
    "value",
    ["", "Uppercase", "contains space", "two--hyphens", "ação", None],
)
def test_invalid_asset_subtypes_are_rejected(value: object) -> None:
    with pytest.raises(InvalidAssetError):
        AssetSubtype(value)  # type: ignore[arg-type]


def test_owner_supports_people_teams_roles_and_automation() -> None:
    for kind in OwnerKind:
        owner = AssetOwner(
            id=OwnerId(f"owner-{kind.value}"),
            label=DisplayName(f"Owner {kind.value}"),
            kind=kind,
        )
        assert owner.kind is kind


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AssetOwner(  # type: ignore[arg-type]
            id="owner",
            label=DisplayName("Owner"),
            kind=OwnerKind.PERSON,
        ),
        lambda: AssetOwner(  # type: ignore[arg-type]
            id=OwnerId("owner"),
            label="Owner",
            kind=OwnerKind.PERSON,
        ),
        lambda: AssetOwner(  # type: ignore[arg-type]
            id=OwnerId("owner"),
            label=DisplayName("Owner"),
            kind="person",
        ),
    ],
)
def test_invalid_owner_fields_are_rejected(factory: object) -> None:
    with pytest.raises(InvalidAssetError):
        factory()  # type: ignore[operator]


def test_component_hierarchy_supports_nested_parts() -> None:
    body = AssetComponent(ComponentId("base-body"), DisplayName("Base Body"))
    hand = AssetComponent(
        ComponentId("left-hand"),
        DisplayName("Left Hand"),
        parent_id=body.id,
    )
    fingernail = AssetComponent(
        ComponentId("left-fingernails"),
        DisplayName("Left Fingernails"),
        parent_id=hand.id,
        required=False,
    )

    asset = make_asset(components=(body, hand, fingernail))

    assert asset.components[1].parent_id == body.id
    assert asset.components[2].parent_id == hand.id


def test_component_cannot_reference_itself() -> None:
    with pytest.raises(InvalidAssetError, match="own parent"):
        AssetComponent(
            ComponentId("self-parent"),
            DisplayName("Self Parent"),
            parent_id=ComponentId("self-parent"),
        )


def test_unknown_component_parent_is_rejected() -> None:
    component = AssetComponent(
        ComponentId("shirt-button"),
        DisplayName("Shirt Button"),
        parent_id=ComponentId("missing-shirt"),
    )

    with pytest.raises(InvalidAssetError, match="unknown parent"):
        make_asset(components=(component,))


def test_component_cycles_are_rejected() -> None:
    component_a = AssetComponent(
        ComponentId("component-a"),
        DisplayName("Component A"),
        parent_id=ComponentId("component-b"),
    )
    component_b = AssetComponent(
        ComponentId("component-b"),
        DisplayName("Component B"),
        parent_id=ComponentId("component-a"),
    )

    with pytest.raises(InvalidAssetError, match="cannot contain cycles"):
        make_asset(components=(component_a, component_b))


@pytest.mark.parametrize(
    ("collection", "message"),
    [
        (
            (
                AssetComponent(ComponentId("duplicate"), DisplayName("One")),
                AssetComponent(ComponentId("duplicate"), DisplayName("Two")),
            ),
            "component IDs",
        ),
        (
            (
                AssetVariant(VariantId("duplicate"), DisplayName("One")),
                AssetVariant(VariantId("duplicate"), DisplayName("Two")),
            ),
            "variant IDs",
        ),
        (
            (
                AssetState(AssetStateId("duplicate"), DisplayName("One")),
                AssetState(AssetStateId("duplicate"), DisplayName("Two")),
            ),
            "state IDs",
        ),
    ],
)
def test_decomposition_ids_must_be_unique(
    collection: tuple[AssetComponent, ...]
    | tuple[AssetVariant, ...]
    | tuple[AssetState, ...],
    message: str,
) -> None:
    kwargs: dict[str, object]
    if isinstance(collection[0], AssetComponent):
        kwargs = {"components": collection}
    elif isinstance(collection[0], AssetVariant):
        kwargs = {"variants": collection}
    else:
        kwargs = {"states": collection}

    with pytest.raises(InvalidAssetError, match=message):
        make_asset(**kwargs)  # type: ignore[arg-type]


def test_decomposition_collections_must_be_immutable_tuples() -> None:
    with pytest.raises(InvalidAssetError, match="must be tuples"):
        make_asset(
            components=[  # type: ignore[arg-type]
                AssetComponent(ComponentId("body"), DisplayName("Body"))
            ]
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("components", "invalid component"),
        ("variants", "invalid variant"),
        ("states", "invalid state"),
    ],
)
def test_decomposition_rejects_wrong_item_types(field: str, message: str) -> None:
    with pytest.raises(InvalidAssetError, match=message):
        make_asset(**{field: ("invalid",)})  # type: ignore[arg-type]


def test_variants_and_states_are_distinct_production_concepts() -> None:
    summer = AssetVariant(
        VariantId("summer-outfit"),
        DisplayName("Summer Outfit"),
        required=False,
    )
    damaged = AssetState(
        AssetStateId("damaged"),
        DisplayName("Damaged"),
    )

    asset = make_asset(variants=(summer,), states=(damaged,))

    assert asset.variants == (summer,)
    assert asset.states == (damaged,)


def test_item_status_transitions_are_immutable_and_adjacent() -> None:
    component = AssetComponent(ComponentId("base-body"), DisplayName("Base Body"))

    specified = component.transition_status(AssetStatus.SPECIFIED)

    assert component.status is AssetStatus.PLANNED
    assert specified.status is AssetStatus.SPECIFIED
    assert specified.transition_status(AssetStatus.SPECIFIED) is specified

    with pytest.raises(InvalidAssetTransitionError):
        component.transition_status(AssetStatus.IN_PRODUCTION)


def test_invalid_item_target_status_is_rejected() -> None:
    variant = AssetVariant(VariantId("winter"), DisplayName("Winter"))

    with pytest.raises(InvalidAssetTransitionError, match="target status"):
        variant.transition_status("completed")  # type: ignore[arg-type]


def test_required_items_block_asset_completion() -> None:
    body = AssetComponent(ComponentId("base-body"), DisplayName("Base Body"))
    optional_hat = AssetVariant(
        VariantId("festival-hat"),
        DisplayName("Festival Hat"),
        required=False,
    )
    open_state = complete_item(
        AssetState(AssetStateId("open"), DisplayName("Open"))
    )
    assert isinstance(open_state, AssetState)

    asset = make_asset(
        status=AssetStatus.IN_REVIEW,
        components=(body,),
        variants=(optional_hat,),
        states=(open_state,),
    )

    assert asset.incomplete_required_items == (body.id,)
    assert asset.is_completion_ready is False
    assert asset.can_transition_status(AssetStatus.COMPLETED) is False

    with pytest.raises(InvalidAssetTransitionError):
        asset.transition_status(AssetStatus.COMPLETED)


def test_optional_items_do_not_block_completion() -> None:
    optional_variant = AssetVariant(
        VariantId("holiday"),
        DisplayName("Holiday Variant"),
        required=False,
    )
    asset = make_asset(
        status=AssetStatus.IN_REVIEW,
        variants=(optional_variant,),
    )

    completed = asset.transition_status(AssetStatus.COMPLETED)

    assert completed.status is AssetStatus.COMPLETED
    assert completed.incomplete_required_items == ()


def test_completed_required_items_allow_asset_completion() -> None:
    body = complete_item(
        AssetComponent(ComponentId("base-body"), DisplayName("Base Body"))
    )
    backpack = complete_item(
        AssetComponent(ComponentId("backpack"), DisplayName("Backpack"))
    )
    closed = complete_item(
        AssetState(AssetStateId("closed"), DisplayName("Closed"))
    )
    assert isinstance(body, AssetComponent)
    assert isinstance(backpack, AssetComponent)
    assert isinstance(closed, AssetState)

    asset = make_asset(
        status=AssetStatus.IN_REVIEW,
        components=(body, backpack),
        states=(closed,),
    )

    completed = asset.transition_status(AssetStatus.COMPLETED)

    assert completed.status is AssetStatus.COMPLETED
    assert completed.is_completion_ready is True


def test_completed_asset_cannot_contain_incomplete_required_items() -> None:
    body = AssetComponent(ComponentId("base-body"), DisplayName("Base Body"))

    with pytest.raises(InvalidAssetError, match="incomplete required"):
        make_asset(status=AssetStatus.COMPLETED, components=(body,))


def test_completed_asset_can_reopen_review_then_archive() -> None:
    completed = make_asset(status=AssetStatus.COMPLETED)

    in_review = completed.transition_status(AssetStatus.IN_REVIEW)
    completed_again = in_review.transition_status(AssetStatus.COMPLETED)
    archived = completed_again.transition_status(AssetStatus.ARCHIVED)

    assert archived.status is AssetStatus.ARCHIVED
    assert archived.can_transition_status(AssetStatus.COMPLETED) is False


def test_cancelled_asset_can_return_to_planning_or_archive() -> None:
    cancelled = make_asset().transition_status(AssetStatus.CANCELLED)

    assert cancelled.transition_status(AssetStatus.PLANNED).status is AssetStatus.PLANNED
    assert cancelled.transition_status(AssetStatus.ARCHIVED).status is AssetStatus.ARCHIVED


def test_invalid_asset_target_status_is_rejected() -> None:
    asset = make_asset()

    assert asset.can_transition_status("specified") is False  # type: ignore[arg-type]
    with pytest.raises(InvalidAssetTransitionError):
        asset.transition_status("specified")  # type: ignore[arg-type]


_EXPECTED_STATUS_TRANSITIONS = {
    AssetStatus.PLANNED: {AssetStatus.SPECIFIED, AssetStatus.CANCELLED},
    AssetStatus.SPECIFIED: {
        AssetStatus.PLANNED,
        AssetStatus.READY,
        AssetStatus.CANCELLED,
    },
    AssetStatus.READY: {
        AssetStatus.SPECIFIED,
        AssetStatus.IN_PRODUCTION,
        AssetStatus.CANCELLED,
    },
    AssetStatus.IN_PRODUCTION: {
        AssetStatus.READY,
        AssetStatus.IN_REVIEW,
        AssetStatus.CANCELLED,
    },
    AssetStatus.IN_REVIEW: {
        AssetStatus.IN_PRODUCTION,
        AssetStatus.COMPLETED,
        AssetStatus.CANCELLED,
    },
    AssetStatus.COMPLETED: {AssetStatus.IN_REVIEW, AssetStatus.ARCHIVED},
    AssetStatus.CANCELLED: {AssetStatus.PLANNED, AssetStatus.ARCHIVED},
    AssetStatus.ARCHIVED: set(),
}


@given(st.sampled_from(list(AssetStatus)), st.sampled_from(list(AssetStatus)))
def test_asset_status_transition_matrix_is_explicit(
    current: AssetStatus,
    target: AssetStatus,
) -> None:
    asset = make_asset(status=current)
    expected = target is current or target in _EXPECTED_STATUS_TRANSITIONS[current]

    assert asset.can_transition_status(target) is expected
