"""Humanoid capture-profile specializations and wearable requirements."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from ludowright.domain.assets import AssetFamily, AssetSubtype
from ludowright.domain.capture_profiles import (
    CaptureProfile,
    CaptureRequirementKind,
    CaptureSheet,
)
from ludowright.domain.errors import InvalidCaptureProfileError
from ludowright.domain.identifiers import CaptureProfileId, ComponentId
from ludowright.domain.names import DisplayName
from ludowright.domain.versions import ProfileVersion

MAX_HUMANOID_PROFILE_GUIDANCE_LENGTH = 1_000


class NeutralRepresentationMode(StrEnum):
    """Approved body-base presentation modes for humanoid references."""

    NEUTRAL_BODYSUIT = "neutral-bodysuit"
    FITTED_NEUTRAL_CLOTHING = "fitted-neutral-clothing"
    TECHNICAL_MANNEQUIN = "technical-mannequin"


class HumanoidWearableKind(StrEnum):
    """Categories that can be isolated from a humanoid body base."""

    HAIR = "hair"
    GARMENT = "garment"
    FOOTWEAR = "footwear"
    ACCESSORY = "accessory"
    PROP = "prop"
    DETAIL = "detail"


@dataclass(frozen=True, slots=True)
class NeutralRepresentationPolicy:
    """Explicit, provider-neutral policy for the body-base representation."""

    mode: NeutralRepresentationMode
    guidance: str

    def __post_init__(self) -> None:
        if not isinstance(self.mode, NeutralRepresentationMode):
            raise InvalidCaptureProfileError("neutral representation mode must be canonical")
        _validate_guidance(self.guidance, "neutral representation guidance")


@dataclass(frozen=True, slots=True)
class HumanoidBodyBase:
    """The required neutral body component in a humanoid profile."""

    id: ComponentId
    name: DisplayName

    def __post_init__(self) -> None:
        if not isinstance(self.id, ComponentId):
            raise InvalidCaptureProfileError("humanoid body base requires a component ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("humanoid body base name must be canonical")


@dataclass(frozen=True, slots=True)
class HumanoidWearable:
    """One data-defined, optionally isolated wearable or detail component."""

    id: ComponentId
    name: DisplayName
    kind: HumanoidWearableKind
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, ComponentId):
            raise InvalidCaptureProfileError("humanoid wearable requires a component ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("humanoid wearable name must be canonical")
        if not isinstance(self.kind, HumanoidWearableKind):
            raise InvalidCaptureProfileError("humanoid wearable kind must be canonical")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("humanoid wearable required flag must be boolean")


@dataclass(frozen=True, slots=True)
class HumanoidProfile:
    """Specialized humanoid data that derives the existing capture profile."""

    capture_profile: CaptureProfile
    neutral_representation: NeutralRepresentationPolicy
    body_base: HumanoidBodyBase
    wearables: tuple[HumanoidWearable, ...]
    outputs: tuple[CaptureSheet, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capture_profile, CaptureProfile):
            raise InvalidCaptureProfileError("humanoid profile requires a capture profile")
        if self.capture_profile.parent is not None:
            raise InvalidCaptureProfileError("humanoid profiles require a resolved capture profile")
        if self.capture_profile.sheets:
            raise InvalidCaptureProfileError(
                "humanoid outputs must be the sole source of capture sheets"
            )
        if self.capture_profile.family is not AssetFamily.CHARACTER:
            raise InvalidCaptureProfileError("humanoid profiles require the character family")
        if self.capture_profile.subtype != AssetSubtype("humanoid"):
            raise InvalidCaptureProfileError("humanoid profiles require the humanoid subtype")
        if not isinstance(self.neutral_representation, NeutralRepresentationPolicy):
            raise InvalidCaptureProfileError("humanoid profile requires a neutral policy")
        if not isinstance(self.body_base, HumanoidBodyBase):
            raise InvalidCaptureProfileError("humanoid profile requires a body base")
        if not isinstance(self.wearables, tuple):
            raise InvalidCaptureProfileError("humanoid wearables must be an immutable tuple")
        if any(not isinstance(item, HumanoidWearable) for item in self.wearables):
            raise InvalidCaptureProfileError("humanoid wearables must be canonical")
        if not isinstance(self.outputs, tuple) or not self.outputs:
            raise InvalidCaptureProfileError("humanoid profiles require at least one output")
        if any(not isinstance(output, CaptureSheet) for output in self.outputs):
            raise InvalidCaptureProfileError("humanoid outputs must be capture sheets")
        self._validate_component_requirements()
        self._validate_outputs()

    @property
    def id(self) -> CaptureProfileId:
        """Return the stable capture-profile lineage ID."""
        return self.capture_profile.id

    @property
    def version(self) -> ProfileVersion:
        """Return the immutable capture-profile revision."""
        return self.capture_profile.version

    @property
    def name(self) -> DisplayName:
        """Return the human-facing profile name."""
        return self.capture_profile.name

    @property
    def wearable_ids_by_kind(self) -> dict[HumanoidWearableKind, tuple[ComponentId, ...]]:
        """Return deterministic component IDs grouped by wearable category."""
        return {
            kind: tuple(item.id for item in self.wearables if item.kind is kind)
            for kind in HumanoidWearableKind
        }

    def to_capture_profile(self) -> CaptureProfile:
        """Derive the generic capture profile with this profile's output sheets."""
        return CaptureProfile(
            id=self.capture_profile.id,
            version=self.capture_profile.version,
            name=self.capture_profile.name,
            family=self.capture_profile.family,
            subtype=self.capture_profile.subtype,
            camera=self.capture_profile.camera,
            background=self.capture_profile.background,
            lighting=self.capture_profile.lighting,
            validation=self.capture_profile.validation,
            views=self.capture_profile.views,
            requirements=self.capture_profile.requirements,
            sheets=self.outputs,
        )

    def _validate_component_requirements(self) -> None:
        requirements = {
            requirement.id: requirement
            for requirement in self.capture_profile.requirements
            if requirement.kind is CaptureRequirementKind.COMPONENT
        }
        if len(requirements) != sum(
            requirement.kind is CaptureRequirementKind.COMPONENT
            for requirement in self.capture_profile.requirements
        ):
            raise InvalidCaptureProfileError("humanoid component requirements must be unique")
        if self.body_base.id in {item.id for item in self.wearables}:
            raise InvalidCaptureProfileError("body base and wearable IDs must be unique")
        wearable_ids = tuple(item.id for item in self.wearables)
        if len(wearable_ids) != len(set(wearable_ids)):
            raise InvalidCaptureProfileError("humanoid wearable IDs must be unique")
        expected_ids = {self.body_base.id, *wearable_ids}
        if set(requirements) != expected_ids:
            raise InvalidCaptureProfileError(
                "humanoid body base and wearable IDs must match component requirements"
            )
        body_requirement = requirements.get(self.body_base.id)
        if body_requirement is None or not body_requirement.required:
            raise InvalidCaptureProfileError("humanoid body base must be a required component")
        for wearable in self.wearables:
            requirement = requirements[wearable.id]
            if requirement.required != wearable.required:
                raise InvalidCaptureProfileError(
                    f"wearable requirement flag does not match {wearable.id}"
                )

    def _validate_outputs(self) -> None:
        output_ids = tuple(output.id for output in self.outputs)
        if len(output_ids) != len(set(output_ids)):
            raise InvalidCaptureProfileError("humanoid output IDs must be unique")
        if not any(output.assembled_sheet for output in self.outputs):
            raise InvalidCaptureProfileError("humanoid profiles require an assembled output")
        if any(
            set(output.view_ids) - {view.id for view in self.capture_profile.views}
            for output in self.outputs
        ):
            raise InvalidCaptureProfileError("humanoid outputs must reference profile views")


def _validate_guidance(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise InvalidCaptureProfileError(f"{field_name} cannot be empty")
    if len(value) > MAX_HUMANOID_PROFILE_GUIDANCE_LENGTH:
        raise InvalidCaptureProfileError(
            f"{field_name} cannot exceed {MAX_HUMANOID_PROFILE_GUIDANCE_LENGTH} characters"
        )
    if unicodedata.normalize("NFC", value) != value:
        raise InvalidCaptureProfileError(f"{field_name} must use Unicode NFC")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise InvalidCaptureProfileError(f"{field_name} cannot contain control characters")


__all__ = [
    "MAX_HUMANOID_PROFILE_GUIDANCE_LENGTH",
    "HumanoidBodyBase",
    "HumanoidProfile",
    "HumanoidWearable",
    "HumanoidWearableKind",
    "NeutralRepresentationMode",
    "NeutralRepresentationPolicy",
]
