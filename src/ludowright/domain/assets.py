"""Asset classification, decomposition, ownership, and production progress."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self

from ludowright.domain.errors import InvalidAssetError, InvalidAssetTransitionError
from ludowright.domain.identifiers import (
    AssetId,
    AssetStateId,
    ComponentId,
    Identifier,
    OwnerId,
    VariantId,
)
from ludowright.domain.names import DisplayName, validate_slug


class AssetFamily(StrEnum):
    """Stable top-level production families."""

    CHARACTER = "character"
    CREATURE = "creature"
    ENVIRONMENT = "environment"
    ARCHITECTURE = "architecture"
    PROP = "prop"
    VEHICLE = "vehicle"
    VEGETATION = "vegetation"
    TERRAIN = "terrain"
    MATERIAL = "material"
    TEXTURE = "texture"
    ANIMATION = "animation"
    UI = "ui"
    VFX = "vfx"
    AUDIO = "audio"
    OTHER = "other"


class AssetPriority(StrEnum):
    """Relative production priority, independent of current status."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKLOG = "backlog"


class AssetStatus(StrEnum):
    """Production progress shared by assets and decomposed items."""

    PLANNED = "planned"
    SPECIFIED = "specified"
    READY = "ready"
    IN_PRODUCTION = "in-production"
    IN_REVIEW = "in-review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class OwnerKind(StrEnum):
    """Kind of owner responsible for a production item."""

    PERSON = "person"
    TEAM = "team"
    ROLE = "role"
    AUTOMATION = "automation"


_STATUS_TRANSITIONS: dict[AssetStatus, frozenset[AssetStatus]] = {
    AssetStatus.PLANNED: frozenset({AssetStatus.SPECIFIED, AssetStatus.CANCELLED}),
    AssetStatus.SPECIFIED: frozenset(
        {AssetStatus.PLANNED, AssetStatus.READY, AssetStatus.CANCELLED}
    ),
    AssetStatus.READY: frozenset(
        {AssetStatus.SPECIFIED, AssetStatus.IN_PRODUCTION, AssetStatus.CANCELLED}
    ),
    AssetStatus.IN_PRODUCTION: frozenset(
        {AssetStatus.READY, AssetStatus.IN_REVIEW, AssetStatus.CANCELLED}
    ),
    AssetStatus.IN_REVIEW: frozenset(
        {AssetStatus.IN_PRODUCTION, AssetStatus.COMPLETED, AssetStatus.CANCELLED}
    ),
    AssetStatus.COMPLETED: frozenset({AssetStatus.IN_REVIEW, AssetStatus.ARCHIVED}),
    AssetStatus.CANCELLED: frozenset({AssetStatus.PLANNED, AssetStatus.ARCHIVED}),
    AssetStatus.ARCHIVED: frozenset(),
}


def _validate_required(value: bool) -> None:
    if not isinstance(value, bool):
        raise InvalidAssetError("an asset item required flag must be boolean")


def _validate_status_transition(
    current: AssetStatus,
    target: AssetStatus,
    subject: str,
) -> None:
    if target is current:
        return
    if target not in _STATUS_TRANSITIONS[current]:
        raise InvalidAssetTransitionError(
            f"cannot transition {subject} from {current.value!r} to {target.value!r}"
        )


@dataclass(frozen=True, slots=True)
class AssetSubtype:
    """Extensible subtype slug within a stable asset family."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidAssetError("an asset subtype must be a string")
        try:
            validate_slug(self.value)
        except ValueError as error:
            raise InvalidAssetError(str(error)) from error

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AssetClassification:
    """Stable family plus an optional extensible subtype."""

    family: AssetFamily
    subtype: AssetSubtype | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.family, AssetFamily):
            raise InvalidAssetError("an asset classification requires a valid family")
        if self.subtype is not None and not isinstance(self.subtype, AssetSubtype):
            raise InvalidAssetError("an asset classification subtype must be canonical")
        if self.family is AssetFamily.OTHER and self.subtype is None:
            raise InvalidAssetError("the 'other' asset family requires a subtype")


@dataclass(frozen=True, slots=True)
class AssetOwner:
    """A responsible person, team, role, or automation identity."""

    id: OwnerId
    label: DisplayName
    kind: OwnerKind

    def __post_init__(self) -> None:
        if not isinstance(self.id, OwnerId):
            raise InvalidAssetError("an asset owner requires a typed owner ID")
        if not isinstance(self.label, DisplayName):
            raise InvalidAssetError("an asset owner label must be a display name")
        if not isinstance(self.kind, OwnerKind):
            raise InvalidAssetError("an asset owner requires a valid owner kind")


@dataclass(frozen=True, slots=True)
class AssetComponent:
    """A modelable, drawable, audible, or otherwise producible asset part."""

    id: ComponentId
    name: DisplayName
    status: AssetStatus = AssetStatus.PLANNED
    required: bool = True
    parent_id: ComponentId | None = None
    owner: AssetOwner | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ComponentId):
            raise InvalidAssetError("an asset component requires a typed component ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidAssetError("an asset component name must be a display name")
        if not isinstance(self.status, AssetStatus):
            raise InvalidAssetError("an asset component requires a valid status")
        _validate_required(self.required)
        if self.parent_id is not None and not isinstance(self.parent_id, ComponentId):
            raise InvalidAssetError("an asset component parent must be a component ID")
        if self.parent_id == self.id:
            raise InvalidAssetError("an asset component cannot be its own parent")
        if self.owner is not None and not isinstance(self.owner, AssetOwner):
            raise InvalidAssetError("an asset component owner must be canonical")

    def transition_status(self, target: AssetStatus) -> Self:
        """Return a new component in an allowed production status."""
        if not isinstance(target, AssetStatus):
            raise InvalidAssetTransitionError("a component target status must be valid")
        _validate_status_transition(self.status, target, f"component {self.id.value!r}")
        return self if target is self.status else replace(self, status=target)


@dataclass(frozen=True, slots=True)
class AssetVariant:
    """An alternative production expression of an asset."""

    id: VariantId
    name: DisplayName
    status: AssetStatus = AssetStatus.PLANNED
    required: bool = True
    owner: AssetOwner | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, VariantId):
            raise InvalidAssetError("an asset variant requires a typed variant ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidAssetError("an asset variant name must be a display name")
        if not isinstance(self.status, AssetStatus):
            raise InvalidAssetError("an asset variant requires a valid status")
        _validate_required(self.required)
        if self.owner is not None and not isinstance(self.owner, AssetOwner):
            raise InvalidAssetError("an asset variant owner must be canonical")

    def transition_status(self, target: AssetStatus) -> Self:
        """Return a new variant in an allowed production status."""
        if not isinstance(target, AssetStatus):
            raise InvalidAssetTransitionError("a variant target status must be valid")
        _validate_status_transition(self.status, target, f"variant {self.id.value!r}")
        return self if target is self.status else replace(self, status=target)


@dataclass(frozen=True, slots=True)
class AssetState:
    """A functional or visual state such as open, damaged, or sleeping."""

    id: AssetStateId
    name: DisplayName
    status: AssetStatus = AssetStatus.PLANNED
    required: bool = True
    owner: AssetOwner | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, AssetStateId):
            raise InvalidAssetError("an asset state requires a typed state ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidAssetError("an asset state name must be a display name")
        if not isinstance(self.status, AssetStatus):
            raise InvalidAssetError("an asset state requires a valid status")
        _validate_required(self.required)
        if self.owner is not None and not isinstance(self.owner, AssetOwner):
            raise InvalidAssetError("an asset state owner must be canonical")

    def transition_status(self, target: AssetStatus) -> Self:
        """Return a new state in an allowed production status."""
        if not isinstance(target, AssetStatus):
            raise InvalidAssetTransitionError("a state target status must be valid")
        _validate_status_transition(self.status, target, f"state {self.id.value!r}")
        return self if target is self.status else replace(self, status=target)


@dataclass(frozen=True, slots=True)
class Asset:
    """Immutable aggregate for one planned or produced game asset."""

    id: AssetId
    name: DisplayName
    classification: AssetClassification
    priority: AssetPriority = AssetPriority.NORMAL
    status: AssetStatus = AssetStatus.PLANNED
    owner: AssetOwner | None = None
    components: tuple[AssetComponent, ...] = ()
    variants: tuple[AssetVariant, ...] = ()
    states: tuple[AssetState, ...] = ()

    def __post_init__(self) -> None:
        self._validate_scalar_fields()
        self._validate_collections()
        self._validate_component_graph()
        if self.status is AssetStatus.COMPLETED and self.incomplete_required_items:
            raise InvalidAssetError(
                "a completed asset cannot contain incomplete required production items"
            )

    def _validate_scalar_fields(self) -> None:
        if not isinstance(self.id, AssetId):
            raise InvalidAssetError("an asset requires a typed asset ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidAssetError("an asset name must be a display name")
        if not isinstance(self.classification, AssetClassification):
            raise InvalidAssetError("an asset requires a canonical classification")
        if not isinstance(self.priority, AssetPriority):
            raise InvalidAssetError("an asset requires a valid priority")
        if not isinstance(self.status, AssetStatus):
            raise InvalidAssetError("an asset requires a valid status")
        if self.owner is not None and not isinstance(self.owner, AssetOwner):
            raise InvalidAssetError("an asset owner must be canonical")

    def _validate_collections(self) -> None:
        if not isinstance(self.components, tuple):
            raise InvalidAssetError("asset decomposition collections must be tuples")
        if not isinstance(self.variants, tuple):
            raise InvalidAssetError("asset decomposition collections must be tuples")
        if not isinstance(self.states, tuple):
            raise InvalidAssetError("asset decomposition collections must be tuples")
        if any(not isinstance(item, AssetComponent) for item in self.components):
            raise InvalidAssetError("an asset contains an invalid component")
        if any(not isinstance(item, AssetVariant) for item in self.variants):
            raise InvalidAssetError("an asset contains an invalid variant")
        if any(not isinstance(item, AssetState) for item in self.states):
            raise InvalidAssetError("an asset contains an invalid state")
        self._ensure_unique_ids(
            tuple(component.id for component in self.components),
            "component",
        )
        self._ensure_unique_ids(
            tuple(variant.id for variant in self.variants),
            "variant",
        )
        self._ensure_unique_ids(
            tuple(state.id for state in self.states),
            "state",
        )

    @staticmethod
    def _ensure_unique_ids(ids: tuple[Identifier, ...], item_kind: str) -> None:
        if len(ids) != len(set(ids)):
            raise InvalidAssetError(f"asset {item_kind} IDs must be unique")

    def _validate_component_graph(self) -> None:
        parents = {component.id: component.parent_id for component in self.components}
        for component in self.components:
            if component.parent_id is not None and component.parent_id not in parents:
                raise InvalidAssetError(
                    f"component {component.id.value!r} references an unknown parent"
                )

        for component in self.components:
            visited: set[ComponentId] = set()
            current: ComponentId | None = component.id
            while current is not None:
                if current in visited:
                    raise InvalidAssetError("asset component hierarchy cannot contain cycles")
                visited.add(current)
                current = parents[current]

    @property
    def incomplete_required_items(self) -> tuple[Identifier, ...]:
        """Return required decomposed items that are not completed."""
        incomplete: list[Identifier] = []
        for component in self.components:
            if component.required and component.status is not AssetStatus.COMPLETED:
                incomplete.append(component.id)
        for variant in self.variants:
            if variant.required and variant.status is not AssetStatus.COMPLETED:
                incomplete.append(variant.id)
        for state in self.states:
            if state.required and state.status is not AssetStatus.COMPLETED:
                incomplete.append(state.id)
        return tuple(incomplete)

    @property
    def is_completion_ready(self) -> bool:
        """Return whether every required decomposed production item is completed."""
        return not self.incomplete_required_items

    def can_transition_status(self, target: AssetStatus) -> bool:
        """Return whether the aggregate can move to a target production status."""
        if not isinstance(target, AssetStatus):
            return False
        if target is self.status:
            return True
        if target is AssetStatus.COMPLETED and not self.is_completion_ready:
            return False
        return target in _STATUS_TRANSITIONS[self.status]

    def transition_status(self, target: AssetStatus) -> Self:
        """Return a new aggregate in an allowed production status."""
        if not isinstance(target, AssetStatus):
            raise InvalidAssetTransitionError("an asset target status must be valid")
        if target is self.status:
            return self
        if not self.can_transition_status(target):
            raise InvalidAssetTransitionError(
                f"cannot transition asset {self.id.value!r} from {self.status.value!r} "
                f"to {target.value!r}"
            )
        return replace(self, status=target)
