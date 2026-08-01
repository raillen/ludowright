"""Versioned environment and hard-surface capture-profile contract."""

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
    HardSurfaceComponent,
    HardSurfaceComponentKind,
    HardSurfaceConnection,
    HardSurfaceConnectionKind,
    HardSurfaceProfile,
    HardSurfaceProfileKind,
    HardSurfaceState,
    HardSurfaceView,
    HardSurfaceViewRole,
)


class HardSurfaceComponentContract(ContractModel):
    """One separately producible construction component."""

    id: Slug
    name: DisplayText
    kind: HardSurfaceComponentKind
    required: bool = True

    def to_domain(self) -> HardSurfaceComponent:
        return HardSurfaceComponent(
            id=ComponentId(self.id),
            name=DisplayName(self.name),
            kind=self.kind,
            required=self.required,
        )


class HardSurfaceViewContract(ContractModel):
    """Construction-specific role bound to an existing capture view."""

    view_id: Slug
    role: HardSurfaceViewRole
    guidance: ProfileGuidanceText

    def to_domain(self) -> HardSurfaceView:
        return HardSurfaceView(
            view_id=CaptureViewId(self.view_id),
            role=self.role,
            guidance=self.guidance,
        )


class HardSurfaceConnectionContract(ContractModel):
    """One directed connection-matrix compatibility row."""

    source_component_id: Slug
    target_component_id: Slug
    kind: HardSurfaceConnectionKind
    guidance: ProfileGuidanceText
    required: bool = True

    def to_domain(self) -> HardSurfaceConnection:
        return HardSurfaceConnection(
            source_component_id=ComponentId(self.source_component_id),
            target_component_id=ComponentId(self.target_component_id),
            kind=self.kind,
            guidance=self.guidance,
            required=self.required,
        )


class HardSurfaceStateContract(ContractModel):
    """One construction, operational, or damage state."""

    id: Slug
    name: DisplayText
    guidance: ProfileGuidanceText
    required: bool = True

    def to_domain(self) -> HardSurfaceState:
        return HardSurfaceState(
            id=AssetStateId(self.id),
            name=DisplayName(self.name),
            guidance=self.guidance,
            required=self.required,
        )


class HardSurfaceProfileContract(ContractModel):
    """Data-defined environment and hard-surface specialization."""

    schema_version: Literal[1] = 1
    kind: Literal["hard-surface-profile"] = "hard-surface-profile"
    capture_profile: CaptureProfileContract
    profile_kind: HardSurfaceProfileKind
    construction_views: Annotated[tuple[HardSurfaceViewContract, ...], Field(min_length=1)]
    components: Annotated[tuple[HardSurfaceComponentContract, ...], Field(min_length=1)]
    connection_matrix: Annotated[tuple[HardSurfaceConnectionContract, ...], Field(min_length=1)]
    states: Annotated[tuple[HardSurfaceStateContract, ...], Field(min_length=1)]
    outputs: Annotated[tuple[CaptureSheetContract, ...], Field(min_length=1)]

    def to_domain(self) -> HardSurfaceProfile:
        return HardSurfaceProfile(
            capture_profile=self.capture_profile.to_domain(),
            kind=self.profile_kind,
            construction_views=tuple(view.to_domain() for view in self.construction_views),
            components=tuple(component.to_domain() for component in self.components),
            connection_matrix=tuple(
                connection.to_domain() for connection in self.connection_matrix
            ),
            states=tuple(state.to_domain() for state in self.states),
            outputs=tuple(output.to_domain() for output in self.outputs),
        )

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        self.to_domain()
        return self


__all__ = [
    "HardSurfaceComponentContract",
    "HardSurfaceConnectionContract",
    "HardSurfaceProfileContract",
    "HardSurfaceStateContract",
    "HardSurfaceViewContract",
]
