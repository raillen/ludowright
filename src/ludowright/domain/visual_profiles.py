"""Foliage, UI, VFX, and animation capture-profile specializations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ludowright.domain.assets import AssetFamily, AssetSubtype
from ludowright.domain.capture_profiles import (
    CaptureProfile,
    CaptureRequirement,
    CaptureRequirementKind,
    CaptureSheet,
)
from ludowright.domain.errors import InvalidCaptureProfileError
from ludowright.domain.identifiers import (
    AssetStateId,
    CaptureProfileId,
    CaptureViewId,
    ComponentId,
    Identifier,
    VariantId,
)
from ludowright.domain.names import DisplayName
from ludowright.domain.profile_guidance import validate_profile_guidance
from ludowright.domain.versions import ProfileVersion


class VisualProfileKind(StrEnum):
    """Initial foliage, interface, effect, and motion profile families."""

    TREE = "tree"
    PLANT = "plant"
    INTERFACE_ICON = "interface-icon"
    MENU = "menu"
    PARTICLE_EFFECT = "particle-effect"
    SHADER_EFFECT = "shader-effect"
    LOCOMOTION = "locomotion"
    MOTION_SET = "motion-set"


class VisualComponentKind(StrEnum):
    """Component categories that can be isolated from a visual subject."""

    SUBJECT = "subject"
    TRUNK = "trunk"
    CANOPY = "canopy"
    STEM = "stem"
    LEAF = "leaf"
    FLOWER = "flower"
    PANEL = "panel"
    ICON = "icon"
    LABEL = "label"
    ITEM = "item"
    EMITTER = "emitter"
    PARTICLE = "particle"
    IMPACT = "impact"
    SURFACE = "surface"
    MASK = "mask"
    RIG = "rig"
    POSE = "pose"
    CONTACT = "contact"
    OTHER = "other"


class VisualViewRole(StrEnum):
    """Purpose for one existing generic capture view."""

    WHOLE_SUBJECT = "whole-subject"
    FRONT = "front"
    SIDE = "side"
    REAR = "rear"
    TOP = "top"
    SILHOUETTE = "silhouette"
    DETAIL = "detail"
    STATE = "state"
    VARIANT = "variant"
    ICON = "icon"
    PANEL = "panel"
    EMITTER = "emitter"
    IMPACT = "impact"
    START = "start"
    LOOP = "loop"
    END = "end"
    CONTACT = "contact"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class VisualComponent:
    """One separately producible visual component."""

    id: ComponentId
    name: DisplayName
    kind: VisualComponentKind
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, ComponentId):
            raise InvalidCaptureProfileError("visual component requires a component ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("visual component name must be canonical")
        if not isinstance(self.kind, VisualComponentKind):
            raise InvalidCaptureProfileError("visual component kind must be canonical")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("visual component required flag must be boolean")


@dataclass(frozen=True, slots=True)
class VisualVariant:
    """One named visual configuration or presentation variant."""

    id: VariantId
    name: DisplayName
    guidance: str
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, VariantId):
            raise InvalidCaptureProfileError("visual variant requires a variant ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("visual variant name must be canonical")
        validate_profile_guidance(self.guidance, "visual variant guidance")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("visual variant required flag must be boolean")


@dataclass(frozen=True, slots=True)
class VisualState:
    """One functional, lifecycle, or presentation state."""

    id: AssetStateId
    name: DisplayName
    guidance: str
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, AssetStateId):
            raise InvalidCaptureProfileError("visual state requires an asset-state ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("visual state name must be canonical")
        validate_profile_guidance(self.guidance, "visual state guidance")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("visual state required flag must be boolean")


@dataclass(frozen=True, slots=True)
class VisualView:
    """Maps a generic capture view to one visual-specialty role."""

    view_id: CaptureViewId
    role: VisualViewRole
    guidance: str

    def __post_init__(self) -> None:
        if not isinstance(self.view_id, CaptureViewId):
            raise InvalidCaptureProfileError("visual view requires a view ID")
        if not isinstance(self.role, VisualViewRole):
            raise InvalidCaptureProfileError("visual view role must be canonical")
        validate_profile_guidance(self.guidance, "visual view guidance")


@dataclass(frozen=True, slots=True)
class VisualProfile:
    """Data-defined foliage, UI, VFX, or animation specialization."""

    capture_profile: CaptureProfile
    kind: VisualProfileKind
    guidance: str
    views: tuple[VisualView, ...]
    components: tuple[VisualComponent, ...]
    variants: tuple[VisualVariant, ...]
    states: tuple[VisualState, ...]
    outputs: tuple[CaptureSheet, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capture_profile, CaptureProfile):
            raise InvalidCaptureProfileError("visual profile requires a capture profile")
        if self.capture_profile.parent is not None:
            raise InvalidCaptureProfileError("visual profiles require a resolved capture profile")
        if self.capture_profile.sheets:
            raise InvalidCaptureProfileError(
                "visual outputs must be the sole source of capture sheets"
            )
        if not isinstance(self.kind, VisualProfileKind):
            raise InvalidCaptureProfileError("visual profile kind must be canonical")
        expected_family, expected_subtype = _expected_classification(self.kind)
        if self.capture_profile.family is not expected_family:
            raise InvalidCaptureProfileError(
                "visual profile family does not match its profile kind"
            )
        if self.capture_profile.subtype != expected_subtype:
            raise InvalidCaptureProfileError(
                "visual profile subtype does not match its profile kind"
            )
        validate_profile_guidance(self.guidance, "visual profile guidance")
        self._validate_typed_collections()
        self._validate_requirements()
        self._validate_views()
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
        """Derive the generic capture profile with specialized output sheets."""
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

    def _validate_typed_collections(self) -> None:
        if not isinstance(self.views, tuple) or not self.views:
            raise InvalidCaptureProfileError("visual profiles require views")
        if any(not isinstance(view, VisualView) for view in self.views):
            raise InvalidCaptureProfileError("visual views must be canonical")
        if not isinstance(self.components, tuple) or not self.components:
            raise InvalidCaptureProfileError("visual profiles require components")
        if any(not isinstance(component, VisualComponent) for component in self.components):
            raise InvalidCaptureProfileError("visual components must be canonical")
        if not isinstance(self.variants, tuple):
            raise InvalidCaptureProfileError("visual variants must be a tuple")
        if any(not isinstance(variant, VisualVariant) for variant in self.variants):
            raise InvalidCaptureProfileError("visual variants must be canonical")
        if not isinstance(self.states, tuple) or not self.states:
            raise InvalidCaptureProfileError("visual profiles require states")
        if any(not isinstance(state, VisualState) for state in self.states):
            raise InvalidCaptureProfileError("visual states must be canonical")
        if not isinstance(self.outputs, tuple) or not self.outputs:
            raise InvalidCaptureProfileError("visual profiles require outputs")
        if any(not isinstance(output, CaptureSheet) for output in self.outputs):
            raise InvalidCaptureProfileError("visual outputs must be capture sheets")

    def _validate_requirements(self) -> None:
        components_by_id = {component.id: component for component in self.components}
        if len(components_by_id) != len(self.components):
            raise InvalidCaptureProfileError("visual component IDs must be unique")
        subject_components = [
            component
            for component in self.components
            if component.kind is VisualComponentKind.SUBJECT
        ]
        if len(subject_components) != 1 or not subject_components[0].required:
            raise InvalidCaptureProfileError(
                "visual profiles require exactly one required subject component"
            )
        variants_by_id = {variant.id: variant for variant in self.variants}
        if len(variants_by_id) != len(self.variants):
            raise InvalidCaptureProfileError("visual variant IDs must be unique")
        states_by_id = {state.id: state for state in self.states}
        if len(states_by_id) != len(self.states):
            raise InvalidCaptureProfileError("visual state IDs must be unique")
        requirements = {
            requirement.id: requirement for requirement in self.capture_profile.requirements
        }
        if set(requirements) != {*components_by_id, *variants_by_id, *states_by_id}:
            raise InvalidCaptureProfileError("visual profile IDs must match capture requirements")
        for component in self.components:
            _validate_requirement(
                requirements[component.id],
                component.id,
                component.name,
                component.required,
                CaptureRequirementKind.COMPONENT,
            )
        for variant in self.variants:
            _validate_requirement(
                requirements[variant.id],
                variant.id,
                variant.name,
                variant.required,
                CaptureRequirementKind.VARIANT,
            )
        for state in self.states:
            _validate_requirement(
                requirements[state.id],
                state.id,
                state.name,
                state.required,
                CaptureRequirementKind.STATE,
            )

    def _validate_views(self) -> None:
        view_ids = tuple(view.view_id for view in self.views)
        if len(view_ids) != len(set(view_ids)):
            raise InvalidCaptureProfileError("visual view IDs must be unique")
        known_views = {view.id for view in self.capture_profile.views}
        if set(view_ids) - known_views:
            raise InvalidCaptureProfileError("visual views must reference profile views")
        whole_subject = [view for view in self.views if view.role is VisualViewRole.WHOLE_SUBJECT]
        if len(whole_subject) != 1:
            raise InvalidCaptureProfileError(
                "visual profiles require exactly one whole-subject view"
            )

    def _validate_outputs(self) -> None:
        output_ids = tuple(output.id for output in self.outputs)
        if len(output_ids) != len(set(output_ids)):
            raise InvalidCaptureProfileError("visual output IDs must be unique")
        if not any(output.assembled_sheet for output in self.outputs):
            raise InvalidCaptureProfileError("visual profiles require an assembled output")
        known_views = {view.id for view in self.capture_profile.views}
        if any(set(output.view_ids) - known_views for output in self.outputs):
            raise InvalidCaptureProfileError("visual outputs must reference profile views")


def _expected_classification(
    kind: VisualProfileKind,
) -> tuple[AssetFamily, AssetSubtype]:
    classifications = {
        VisualProfileKind.TREE: (AssetFamily.VEGETATION, AssetSubtype("large-tree")),
        VisualProfileKind.PLANT: (AssetFamily.VEGETATION, AssetSubtype("plant")),
        VisualProfileKind.INTERFACE_ICON: (
            AssetFamily.UI,
            AssetSubtype("interface-icon"),
        ),
        VisualProfileKind.MENU: (AssetFamily.UI, AssetSubtype("menu")),
        VisualProfileKind.PARTICLE_EFFECT: (
            AssetFamily.VFX,
            AssetSubtype("particle-effect"),
        ),
        VisualProfileKind.SHADER_EFFECT: (
            AssetFamily.VFX,
            AssetSubtype("shader-effect"),
        ),
        VisualProfileKind.LOCOMOTION: (
            AssetFamily.ANIMATION,
            AssetSubtype("locomotion"),
        ),
        VisualProfileKind.MOTION_SET: (
            AssetFamily.ANIMATION,
            AssetSubtype("motion-set"),
        ),
    }
    return classifications[kind]


def _validate_requirement(
    requirement: CaptureRequirement,
    identifier: Identifier,
    name: DisplayName,
    required: bool,
    expected_kind: CaptureRequirementKind,
) -> None:
    if requirement.kind is not expected_kind:
        raise InvalidCaptureProfileError(f"visual requirement kind does not match {identifier}")
    if requirement.name != name or requirement.required != required:
        raise InvalidCaptureProfileError(f"visual requirement does not match {identifier}")


__all__ = [
    "VisualComponent",
    "VisualComponentKind",
    "VisualProfile",
    "VisualProfileKind",
    "VisualState",
    "VisualVariant",
    "VisualView",
    "VisualViewRole",
]
