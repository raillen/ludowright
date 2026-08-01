"""Creature and animal capture-profile specializations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ludowright.domain.assets import AssetFamily, AssetSubtype
from ludowright.domain.capture_profiles import (
    CaptureProfile,
    CaptureRequirementKind,
    CaptureSheet,
)
from ludowright.domain.errors import InvalidCaptureProfileError
from ludowright.domain.identifiers import (
    AssetStateId,
    CaptureProfileId,
    CaptureViewId,
    ComponentId,
)
from ludowright.domain.names import DisplayName
from ludowright.domain.profile_guidance import validate_profile_guidance
from ludowright.domain.versions import ProfileVersion


class CreatureProfileKind(StrEnum):
    """Initial anatomy families covered by the creature profile catalog."""

    QUADRUPED = "quadruped"
    BIRD = "bird"
    FISH = "fish"
    INSECT = "insect"
    FANTASY_CREATURE = "fantasy-creature"


class CreatureComponentKind(StrEnum):
    """Anatomical component categories that can be isolated."""

    BODY = "body"
    HEAD = "head"
    LIMB = "limb"
    WING = "wing"
    FIN = "fin"
    TAIL = "tail"
    SHELL = "shell"
    ANTENNAE = "antennae"
    HORN = "horn"
    OTHER = "other"


class CreatureViewRole(StrEnum):
    """Anatomy-specific purpose for one existing capture view."""

    WHOLE_BODY = "whole-body"
    HEAD = "head"
    LIMB = "limb"
    WING = "wing"
    FIN = "fin"
    TAIL = "tail"
    SHELL = "shell"
    ANTENNAE = "antennae"
    UNDERSIDE = "underside"
    SILHOUETTE = "silhouette"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class CreatureAnatomy:
    """Closed anatomy family and bounded production guidance."""

    kind: CreatureProfileKind
    guidance: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CreatureProfileKind):
            raise InvalidCaptureProfileError("creature anatomy kind must be canonical")
        validate_profile_guidance(self.guidance, "creature anatomy guidance")


@dataclass(frozen=True, slots=True)
class CreatureComponent:
    """One anatomical component represented by a typed asset component ID."""

    id: ComponentId
    name: DisplayName
    kind: CreatureComponentKind
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, ComponentId):
            raise InvalidCaptureProfileError("creature component requires a component ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("creature component name must be canonical")
        if not isinstance(self.kind, CreatureComponentKind):
            raise InvalidCaptureProfileError("creature component kind must be canonical")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("creature component required flag must be boolean")


@dataclass(frozen=True, slots=True)
class CreatureState:
    """One anatomical or functional state required by the profile."""

    id: AssetStateId
    name: DisplayName
    guidance: str
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, AssetStateId):
            raise InvalidCaptureProfileError("creature state requires an asset-state ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("creature state name must be canonical")
        validate_profile_guidance(self.guidance, "creature state guidance")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("creature state required flag must be boolean")


@dataclass(frozen=True, slots=True)
class CreatureAnatomyView:
    """Maps a generic capture view to one anatomy-specific purpose."""

    view_id: CaptureViewId
    role: CreatureViewRole
    guidance: str

    def __post_init__(self) -> None:
        if not isinstance(self.view_id, CaptureViewId):
            raise InvalidCaptureProfileError("creature anatomy view requires a view ID")
        if not isinstance(self.role, CreatureViewRole):
            raise InvalidCaptureProfileError("creature anatomy view role must be canonical")
        validate_profile_guidance(self.guidance, "creature anatomy view guidance")


@dataclass(frozen=True, slots=True)
class CreatureProfile:
    """Data-defined creature specialization over the generic capture profile."""

    capture_profile: CaptureProfile
    anatomy: CreatureAnatomy
    anatomy_views: tuple[CreatureAnatomyView, ...]
    components: tuple[CreatureComponent, ...]
    states: tuple[CreatureState, ...]
    outputs: tuple[CaptureSheet, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capture_profile, CaptureProfile):
            raise InvalidCaptureProfileError("creature profile requires a capture profile")
        if self.capture_profile.parent is not None:
            raise InvalidCaptureProfileError("creature profiles require a resolved capture profile")
        if self.capture_profile.sheets:
            raise InvalidCaptureProfileError(
                "creature outputs must be the sole source of capture sheets"
            )
        if self.capture_profile.family is not AssetFamily.CREATURE:
            raise InvalidCaptureProfileError("creature profiles require the creature family")
        if not isinstance(self.anatomy, CreatureAnatomy):
            raise InvalidCaptureProfileError("creature profile requires anatomy data")
        expected_subtype = AssetSubtype(self.anatomy.kind.value)
        if self.capture_profile.subtype != expected_subtype:
            raise InvalidCaptureProfileError("creature profile subtype must match its anatomy kind")
        if not isinstance(self.anatomy_views, tuple) or not self.anatomy_views:
            raise InvalidCaptureProfileError("creature profiles require anatomy-specific views")
        if any(not isinstance(view, CreatureAnatomyView) for view in self.anatomy_views):
            raise InvalidCaptureProfileError("creature anatomy views must be canonical")
        if not isinstance(self.components, tuple) or not self.components:
            raise InvalidCaptureProfileError("creature profiles require components")
        if any(not isinstance(component, CreatureComponent) for component in self.components):
            raise InvalidCaptureProfileError("creature components must be canonical")
        if not isinstance(self.states, tuple) or not self.states:
            raise InvalidCaptureProfileError("creature profiles require at least one state")
        if any(not isinstance(state, CreatureState) for state in self.states):
            raise InvalidCaptureProfileError("creature states must be canonical")
        if not isinstance(self.outputs, tuple) or not self.outputs:
            raise InvalidCaptureProfileError("creature profiles require at least one output")
        if any(not isinstance(output, CaptureSheet) for output in self.outputs):
            raise InvalidCaptureProfileError("creature outputs must be capture sheets")
        self._validate_component_requirements()
        self._validate_state_requirements()
        self._validate_anatomy_views()
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

    def to_capture_profile(self) -> CaptureProfile:
        """Derive the generic capture profile with creature output sheets."""
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
        components_by_id = {component.id: component for component in self.components}
        if len(components_by_id) != len(self.components):
            raise InvalidCaptureProfileError("creature component IDs must be unique")
        body_components = [
            component
            for component in self.components
            if component.kind is CreatureComponentKind.BODY
        ]
        if len(body_components) != 1 or not body_components[0].required:
            raise InvalidCaptureProfileError(
                "creature profiles require exactly one required body component"
            )
        requirements = {
            requirement.id: requirement
            for requirement in self.capture_profile.requirements
            if requirement.kind is CaptureRequirementKind.COMPONENT
        }
        if set(requirements) != set(components_by_id):
            raise InvalidCaptureProfileError(
                "creature component IDs must match component requirements"
            )
        for component in self.components:
            requirement = requirements[component.id]
            if requirement.name != component.name or requirement.required != component.required:
                raise InvalidCaptureProfileError(
                    f"creature component requirement does not match {component.id}"
                )

    def _validate_state_requirements(self) -> None:
        states_by_id = {state.id: state for state in self.states}
        if len(states_by_id) != len(self.states):
            raise InvalidCaptureProfileError("creature state IDs must be unique")
        requirements = {
            requirement.id: requirement
            for requirement in self.capture_profile.requirements
            if requirement.kind is CaptureRequirementKind.STATE
        }
        if set(requirements) != set(states_by_id):
            raise InvalidCaptureProfileError("creature state IDs must match state requirements")
        for state in self.states:
            requirement = requirements[state.id]
            if requirement.name != state.name or requirement.required != state.required:
                raise InvalidCaptureProfileError(
                    f"creature state requirement does not match {state.id}"
                )
        if any(
            requirement.kind
            not in {
                CaptureRequirementKind.COMPONENT,
                CaptureRequirementKind.STATE,
            }
            for requirement in self.capture_profile.requirements
        ):
            raise InvalidCaptureProfileError(
                "creature profiles support component and state requirements only"
            )

    def _validate_anatomy_views(self) -> None:
        view_ids = tuple(view.view_id for view in self.anatomy_views)
        if len(view_ids) != len(set(view_ids)):
            raise InvalidCaptureProfileError("creature anatomy view IDs must be unique")
        known_views = {view.id for view in self.capture_profile.views}
        if set(view_ids) - known_views:
            raise InvalidCaptureProfileError("creature anatomy views must reference profile views")
        if not any(view.role is CreatureViewRole.WHOLE_BODY for view in self.anatomy_views):
            raise InvalidCaptureProfileError("creature profiles require a whole-body view")

    def _validate_outputs(self) -> None:
        output_ids = tuple(output.id for output in self.outputs)
        if len(output_ids) != len(set(output_ids)):
            raise InvalidCaptureProfileError("creature output IDs must be unique")
        if not any(output.assembled_sheet for output in self.outputs):
            raise InvalidCaptureProfileError("creature profiles require an assembled output")
        known_views = {view.id for view in self.capture_profile.views}
        if any(set(output.view_ids) - known_views for output in self.outputs):
            raise InvalidCaptureProfileError("creature outputs must reference profile views")


__all__ = [
    "CreatureAnatomy",
    "CreatureAnatomyView",
    "CreatureComponent",
    "CreatureComponentKind",
    "CreatureProfile",
    "CreatureProfileKind",
    "CreatureState",
    "CreatureViewRole",
]
