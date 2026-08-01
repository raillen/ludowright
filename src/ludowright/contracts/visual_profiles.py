"""Versioned foliage, UI, VFX, and animation profile contract."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.capture import CaptureProfileContract, CaptureSheetContract
from ludowright.contracts.common import ContractModel, DisplayText, ProfileGuidanceText, Slug
from ludowright.domain import (
    AssetStateId,
    CaptureViewId,
    ComponentId,
    DisplayName,
    VariantId,
    VisualComponent,
    VisualComponentKind,
    VisualProfile,
    VisualProfileKind,
    VisualState,
    VisualVariant,
    VisualView,
    VisualViewRole,
)


class VisualComponentContract(ContractModel):
    """One separately producible visual component."""

    id: Slug
    name: DisplayText
    kind: VisualComponentKind
    required: bool = True

    def to_domain(self) -> VisualComponent:
        return VisualComponent(
            id=ComponentId(self.id),
            name=DisplayName(self.name),
            kind=self.kind,
            required=self.required,
        )


class VisualVariantContract(ContractModel):
    """One named visual configuration or presentation variant."""

    id: Slug
    name: DisplayText
    guidance: ProfileGuidanceText
    required: bool = True

    def to_domain(self) -> VisualVariant:
        return VisualVariant(
            id=VariantId(self.id),
            name=DisplayName(self.name),
            guidance=self.guidance,
            required=self.required,
        )


class VisualStateContract(ContractModel):
    """One functional, lifecycle, or presentation state."""

    id: Slug
    name: DisplayText
    guidance: ProfileGuidanceText
    required: bool = True

    def to_domain(self) -> VisualState:
        return VisualState(
            id=AssetStateId(self.id),
            name=DisplayName(self.name),
            guidance=self.guidance,
            required=self.required,
        )


class VisualViewContract(ContractModel):
    """Specialized role bound to an existing capture view."""

    view_id: Slug
    role: VisualViewRole
    guidance: ProfileGuidanceText

    def to_domain(self) -> VisualView:
        return VisualView(
            view_id=CaptureViewId(self.view_id),
            role=self.role,
            guidance=self.guidance,
        )


class VisualProfileContract(ContractModel):
    """Data-defined foliage, UI, VFX, or animation specialization."""

    schema_version: Literal[1] = 1
    kind: Literal["visual-profile"] = "visual-profile"
    capture_profile: CaptureProfileContract
    profile_kind: VisualProfileKind
    guidance: ProfileGuidanceText
    views: Annotated[tuple[VisualViewContract, ...], Field(min_length=1)]
    components: Annotated[tuple[VisualComponentContract, ...], Field(min_length=1)]
    variants: tuple[VisualVariantContract, ...] = ()
    states: Annotated[tuple[VisualStateContract, ...], Field(min_length=1)]
    outputs: Annotated[tuple[CaptureSheetContract, ...], Field(min_length=1)]

    def to_domain(self) -> VisualProfile:
        return VisualProfile(
            capture_profile=self.capture_profile.to_domain(),
            kind=self.profile_kind,
            guidance=self.guidance,
            views=tuple(view.to_domain() for view in self.views),
            components=tuple(component.to_domain() for component in self.components),
            variants=tuple(variant.to_domain() for variant in self.variants),
            states=tuple(state.to_domain() for state in self.states),
            outputs=tuple(output.to_domain() for output in self.outputs),
        )

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        self.to_domain()
        return self


__all__ = [
    "VisualComponentContract",
    "VisualProfileContract",
    "VisualStateContract",
    "VisualVariantContract",
    "VisualViewContract",
]
