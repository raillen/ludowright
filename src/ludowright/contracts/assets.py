"""Versioned asset serialization contract."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator

from ludowright.contracts.common import ContractModel, DisplayText, Slug
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
    OwnerId,
    OwnerKind,
    VariantId,
)


class AssetOwnerContract(ContractModel):
    id: Slug
    label: DisplayText
    kind: OwnerKind

    def to_domain(self) -> AssetOwner:
        return AssetOwner(
            id=OwnerId(self.id),
            label=DisplayName(self.label),
            kind=self.kind,
        )


class AssetComponentContract(ContractModel):
    id: Slug
    name: DisplayText
    status: AssetStatus = AssetStatus.PLANNED
    required: bool = True
    parent_id: Slug | None = None
    owner: AssetOwnerContract | None = None

    def to_domain(self) -> AssetComponent:
        return AssetComponent(
            id=ComponentId(self.id),
            name=DisplayName(self.name),
            status=self.status,
            required=self.required,
            parent_id=(ComponentId(self.parent_id) if self.parent_id is not None else None),
            owner=self.owner.to_domain() if self.owner is not None else None,
        )


class AssetVariantContract(ContractModel):
    id: Slug
    name: DisplayText
    status: AssetStatus = AssetStatus.PLANNED
    required: bool = True
    owner: AssetOwnerContract | None = None

    def to_domain(self) -> AssetVariant:
        return AssetVariant(
            id=VariantId(self.id),
            name=DisplayName(self.name),
            status=self.status,
            required=self.required,
            owner=self.owner.to_domain() if self.owner is not None else None,
        )


class AssetStateContract(ContractModel):
    id: Slug
    name: DisplayText
    status: AssetStatus = AssetStatus.PLANNED
    required: bool = True
    owner: AssetOwnerContract | None = None

    def to_domain(self) -> AssetState:
        return AssetState(
            id=AssetStateId(self.id),
            name=DisplayName(self.name),
            status=self.status,
            required=self.required,
            owner=self.owner.to_domain() if self.owner is not None else None,
        )


class AssetContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["asset"] = "asset"
    id: Slug
    name: DisplayText
    family: AssetFamily
    subtype: Slug | None = None
    priority: AssetPriority = AssetPriority.NORMAL
    status: AssetStatus = AssetStatus.PLANNED
    owner: AssetOwnerContract | None = None
    components: tuple[AssetComponentContract, ...] = ()
    variants: tuple[AssetVariantContract, ...] = ()
    states: tuple[AssetStateContract, ...] = ()

    def to_domain(self) -> Asset:
        return Asset(
            id=AssetId(self.id),
            name=DisplayName(self.name),
            classification=AssetClassification(
                family=self.family,
                subtype=AssetSubtype(self.subtype) if self.subtype is not None else None,
            ),
            priority=self.priority,
            status=self.status,
            owner=self.owner.to_domain() if self.owner is not None else None,
            components=tuple(component.to_domain() for component in self.components),
            variants=tuple(variant.to_domain() for variant in self.variants),
            states=tuple(state.to_domain() for state in self.states),
        )

    @model_validator(mode="after")
    def validate_asset(self) -> Self:
        self.to_domain()
        return self
