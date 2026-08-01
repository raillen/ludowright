"""Versioned creature and animal capture-profile contract."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.capture import CaptureProfileContract, CaptureSheetContract
from ludowright.contracts.common import ContractModel, DisplayText, ProfileGuidanceText, Slug
from ludowright.domain import (
    AssetStateId,
    CaptureViewId,
    ComponentId,
    CreatureAnatomy,
    CreatureAnatomyView,
    CreatureComponent,
    CreatureComponentKind,
    CreatureProfile,
    CreatureProfileKind,
    CreatureState,
    CreatureViewRole,
    DisplayName,
)


class CreatureAnatomyContract(ContractModel):
    """Closed creature family and its production guidance."""

    kind: CreatureProfileKind
    guidance: ProfileGuidanceText

    def to_domain(self) -> CreatureAnatomy:
        return CreatureAnatomy(kind=self.kind, guidance=self.guidance)


class CreatureAnatomyViewContract(ContractModel):
    """Anatomy-specific role bound to an existing capture view."""

    view_id: Slug
    role: CreatureViewRole
    guidance: ProfileGuidanceText

    def to_domain(self) -> CreatureAnatomyView:
        return CreatureAnatomyView(
            view_id=CaptureViewId(self.view_id),
            role=self.role,
            guidance=self.guidance,
        )


class CreatureComponentContract(ContractModel):
    """One isolated anatomical component."""

    id: Slug
    name: DisplayText
    kind: CreatureComponentKind
    required: bool = True

    def to_domain(self) -> CreatureComponent:
        return CreatureComponent(
            id=ComponentId(self.id),
            name=DisplayName(self.name),
            kind=self.kind,
            required=self.required,
        )


class CreatureStateContract(ContractModel):
    """One explicit anatomical or functional state."""

    id: Slug
    name: DisplayText
    guidance: ProfileGuidanceText
    required: bool = True

    def to_domain(self) -> CreatureState:
        return CreatureState(
            id=AssetStateId(self.id),
            name=DisplayName(self.name),
            guidance=self.guidance,
            required=self.required,
        )


class CreatureProfileContract(ContractModel):
    """Data-defined creature specialization over the capture-profile contract."""

    schema_version: Literal[1] = 1
    kind: Literal["creature-profile"] = "creature-profile"
    capture_profile: CaptureProfileContract
    anatomy: CreatureAnatomyContract
    anatomy_views: Annotated[tuple[CreatureAnatomyViewContract, ...], Field(min_length=1)]
    components: Annotated[tuple[CreatureComponentContract, ...], Field(min_length=1)]
    states: Annotated[tuple[CreatureStateContract, ...], Field(min_length=1)]
    outputs: Annotated[tuple[CaptureSheetContract, ...], Field(min_length=1)]

    def to_domain(self) -> CreatureProfile:
        return CreatureProfile(
            capture_profile=self.capture_profile.to_domain(),
            anatomy=self.anatomy.to_domain(),
            anatomy_views=tuple(view.to_domain() for view in self.anatomy_views),
            components=tuple(component.to_domain() for component in self.components),
            states=tuple(state.to_domain() for state in self.states),
            outputs=tuple(output.to_domain() for output in self.outputs),
        )

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        self.to_domain()
        return self


__all__ = [
    "CreatureAnatomyContract",
    "CreatureAnatomyViewContract",
    "CreatureComponentContract",
    "CreatureProfileContract",
    "CreatureStateContract",
]
