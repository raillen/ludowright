"""Versioned humanoid and wearable capture-profile contract."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.capture import CaptureProfileContract, CaptureSheetContract
from ludowright.contracts.common import ContractModel, DisplayText, Slug
from ludowright.domain import (
    ComponentId,
    DisplayName,
    HumanoidBodyBase,
    HumanoidProfile,
    HumanoidWearable,
    HumanoidWearableKind,
    NeutralRepresentationMode,
    NeutralRepresentationPolicy,
)

ProfileGuidanceText = Annotated[str, StringConstraints(min_length=1, max_length=1_000)]


class NeutralRepresentationPolicyContract(ContractModel):
    """Explicit body-base representation policy."""

    mode: NeutralRepresentationMode
    guidance: ProfileGuidanceText

    def to_domain(self) -> NeutralRepresentationPolicy:
        return NeutralRepresentationPolicy(mode=self.mode, guidance=self.guidance)


class HumanoidBodyBaseContract(ContractModel):
    """Required body-base component."""

    id: Slug
    name: DisplayText

    def to_domain(self) -> HumanoidBodyBase:
        return HumanoidBodyBase(id=ComponentId(self.id), name=DisplayName(self.name))


class HumanoidWearableContract(ContractModel):
    """One categorized wearable, prop, or detail component."""

    id: Slug
    name: DisplayText
    kind: HumanoidWearableKind
    required: bool = True

    def to_domain(self) -> HumanoidWearable:
        return HumanoidWearable(
            id=ComponentId(self.id),
            name=DisplayName(self.name),
            kind=self.kind,
            required=self.required,
        )


class HumanoidProfileContract(ContractModel):
    """Data-defined humanoid specialization over the capture-profile contract."""

    schema_version: Literal[1] = 1
    kind: Literal["humanoid-profile"] = "humanoid-profile"
    capture_profile: CaptureProfileContract
    neutral_representation: NeutralRepresentationPolicyContract
    body_base: HumanoidBodyBaseContract
    wearables: tuple[HumanoidWearableContract, ...] = ()
    outputs: Annotated[tuple[CaptureSheetContract, ...], Field(min_length=1)]

    def to_domain(self) -> HumanoidProfile:
        return HumanoidProfile(
            capture_profile=self.capture_profile.to_domain(),
            neutral_representation=self.neutral_representation.to_domain(),
            body_base=self.body_base.to_domain(),
            wearables=tuple(item.to_domain() for item in self.wearables),
            outputs=tuple(output.to_domain() for output in self.outputs),
        )

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        self.to_domain()
        return self


__all__ = [
    "HumanoidBodyBaseContract",
    "HumanoidProfileContract",
    "HumanoidWearableContract",
    "NeutralRepresentationPolicyContract",
]
