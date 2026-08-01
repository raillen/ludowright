"""Environment and hard-surface capture-profile specializations."""

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


class HardSurfaceProfileKind(StrEnum):
    """Initial environment and hard-surface profile families."""

    PROP = "prop"
    VEHICLE = "vehicle"
    BUILDING = "building"
    MODULAR_KIT = "modular-kit"
    INTERIOR = "interior"


class HardSurfaceComponentKind(StrEnum):
    """Construction component categories that can be isolated."""

    ROOT = "root"
    STRUCTURE = "structure"
    MODULE = "module"
    PANEL = "panel"
    OPENING = "opening"
    MOVING_PART = "moving-part"
    WHEEL = "wheel"
    CONNECTOR = "connector"
    FIXTURE = "fixture"
    OTHER = "other"


class HardSurfaceViewRole(StrEnum):
    """Construction-specific purpose for one existing capture view."""

    WHOLE_ASSET = "whole-asset"
    FRONT = "front"
    SIDE = "side"
    REAR = "rear"
    TOP = "top"
    UNDERSIDE = "underside"
    EXPLODED = "exploded"
    CONNECTIONS = "connections"
    INTERIOR = "interior"
    SILHOUETTE = "silhouette"
    DETAIL = "detail"
    OTHER = "other"


class HardSurfaceConnectionKind(StrEnum):
    """Relationship types represented by a connection-matrix row."""

    ATTACHMENT = "attachment"
    HINGE = "hinge"
    SOCKET = "socket"
    EDGE = "edge"
    FLOOR = "floor"
    WALL = "wall"
    MOUNT = "mount"
    CLEARANCE = "clearance"


@dataclass(frozen=True, slots=True)
class HardSurfaceComponent:
    """One separately producible construction component."""

    id: ComponentId
    name: DisplayName
    kind: HardSurfaceComponentKind
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, ComponentId):
            raise InvalidCaptureProfileError("hard-surface component requires a component ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("hard-surface component name must be canonical")
        if not isinstance(self.kind, HardSurfaceComponentKind):
            raise InvalidCaptureProfileError("hard-surface component kind must be canonical")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("hard-surface component required flag must be boolean")


@dataclass(frozen=True, slots=True)
class HardSurfaceState:
    """One construction, operational, or damage state."""

    id: AssetStateId
    name: DisplayName
    guidance: str
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, AssetStateId):
            raise InvalidCaptureProfileError("hard-surface state requires an asset-state ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("hard-surface state name must be canonical")
        validate_profile_guidance(self.guidance, "hard-surface state guidance")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("hard-surface state required flag must be boolean")


@dataclass(frozen=True, slots=True)
class HardSurfaceView:
    """Maps a generic capture view to one construction-specific purpose."""

    view_id: CaptureViewId
    role: HardSurfaceViewRole
    guidance: str

    def __post_init__(self) -> None:
        if not isinstance(self.view_id, CaptureViewId):
            raise InvalidCaptureProfileError("hard-surface view requires a view ID")
        if not isinstance(self.role, HardSurfaceViewRole):
            raise InvalidCaptureProfileError("hard-surface view role must be canonical")
        validate_profile_guidance(self.guidance, "hard-surface view guidance")


@dataclass(frozen=True, slots=True)
class HardSurfaceConnection:
    """One directed compatibility row between two construction components."""

    source_component_id: ComponentId
    target_component_id: ComponentId
    kind: HardSurfaceConnectionKind
    guidance: str
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source_component_id, ComponentId):
            raise InvalidCaptureProfileError("connection source requires a component ID")
        if not isinstance(self.target_component_id, ComponentId):
            raise InvalidCaptureProfileError("connection target requires a component ID")
        if self.source_component_id == self.target_component_id:
            raise InvalidCaptureProfileError("a connection cannot target its source component")
        if not isinstance(self.kind, HardSurfaceConnectionKind):
            raise InvalidCaptureProfileError("connection kind must be canonical")
        validate_profile_guidance(self.guidance, "hard-surface connection guidance")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("connection required flag must be boolean")


@dataclass(frozen=True, slots=True)
class HardSurfaceProfile:
    """Data-defined environment or hard-surface specialization."""

    capture_profile: CaptureProfile
    kind: HardSurfaceProfileKind
    construction_views: tuple[HardSurfaceView, ...]
    components: tuple[HardSurfaceComponent, ...]
    connection_matrix: tuple[HardSurfaceConnection, ...]
    states: tuple[HardSurfaceState, ...]
    outputs: tuple[CaptureSheet, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capture_profile, CaptureProfile):
            raise InvalidCaptureProfileError("hard-surface profile requires a capture profile")
        if self.capture_profile.parent is not None:
            raise InvalidCaptureProfileError(
                "hard-surface profiles require a resolved capture profile"
            )
        if self.capture_profile.sheets:
            raise InvalidCaptureProfileError(
                "hard-surface outputs must be the sole source of capture sheets"
            )
        if not isinstance(self.kind, HardSurfaceProfileKind):
            raise InvalidCaptureProfileError("hard-surface profile kind must be canonical")
        expected_family, expected_subtype = _expected_classification(self.kind)
        if self.capture_profile.family is not expected_family:
            raise InvalidCaptureProfileError(
                "hard-surface profile family does not match its construction kind"
            )
        if self.capture_profile.subtype != expected_subtype:
            raise InvalidCaptureProfileError(
                "hard-surface profile subtype does not match its construction kind"
            )
        if not isinstance(self.construction_views, tuple) or not self.construction_views:
            raise InvalidCaptureProfileError("hard-surface profiles require construction views")
        if any(not isinstance(view, HardSurfaceView) for view in self.construction_views):
            raise InvalidCaptureProfileError("hard-surface views must be canonical")
        if not isinstance(self.components, tuple) or not self.components:
            raise InvalidCaptureProfileError("hard-surface profiles require components")
        if any(not isinstance(component, HardSurfaceComponent) for component in self.components):
            raise InvalidCaptureProfileError("hard-surface components must be canonical")
        if not isinstance(self.connection_matrix, tuple) or not self.connection_matrix:
            raise InvalidCaptureProfileError("hard-surface profiles require a connection matrix")
        if any(
            not isinstance(connection, HardSurfaceConnection)
            for connection in self.connection_matrix
        ):
            raise InvalidCaptureProfileError("hard-surface connections must be canonical")
        if not isinstance(self.states, tuple) or not self.states:
            raise InvalidCaptureProfileError("hard-surface profiles require at least one state")
        if any(not isinstance(state, HardSurfaceState) for state in self.states):
            raise InvalidCaptureProfileError("hard-surface states must be canonical")
        if not isinstance(self.outputs, tuple) or not self.outputs:
            raise InvalidCaptureProfileError("hard-surface profiles require at least one output")
        if any(not isinstance(output, CaptureSheet) for output in self.outputs):
            raise InvalidCaptureProfileError("hard-surface outputs must be capture sheets")
        self._validate_component_requirements()
        self._validate_state_requirements()
        self._validate_construction_views()
        self._validate_connection_matrix()
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
        """Derive the generic capture profile with hard-surface output sheets."""
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
            raise InvalidCaptureProfileError("hard-surface component IDs must be unique")
        root_components = [
            component
            for component in self.components
            if component.kind is HardSurfaceComponentKind.ROOT
        ]
        if len(root_components) != 1 or not root_components[0].required:
            raise InvalidCaptureProfileError(
                "hard-surface profiles require exactly one required root component"
            )
        requirements = {
            requirement.id: requirement
            for requirement in self.capture_profile.requirements
            if requirement.kind is CaptureRequirementKind.COMPONENT
        }
        if set(requirements) != set(components_by_id):
            raise InvalidCaptureProfileError(
                "hard-surface component IDs must match component requirements"
            )
        for component in self.components:
            requirement = requirements[component.id]
            if requirement.name != component.name or requirement.required != component.required:
                raise InvalidCaptureProfileError(
                    f"hard-surface component requirement does not match {component.id}"
                )

    def _validate_state_requirements(self) -> None:
        states_by_id = {state.id: state for state in self.states}
        if len(states_by_id) != len(self.states):
            raise InvalidCaptureProfileError("hard-surface state IDs must be unique")
        requirements = {
            requirement.id: requirement
            for requirement in self.capture_profile.requirements
            if requirement.kind is CaptureRequirementKind.STATE
        }
        if set(requirements) != set(states_by_id):
            raise InvalidCaptureProfileError("hard-surface state IDs must match state requirements")
        for state in self.states:
            requirement = requirements[state.id]
            if requirement.name != state.name or requirement.required != state.required:
                raise InvalidCaptureProfileError(
                    f"hard-surface state requirement does not match {state.id}"
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
                "hard-surface profiles support component and state requirements only"
            )

    def _validate_construction_views(self) -> None:
        view_ids = tuple(view.view_id for view in self.construction_views)
        if len(view_ids) != len(set(view_ids)):
            raise InvalidCaptureProfileError("hard-surface view IDs must be unique")
        known_views = {view.id for view in self.capture_profile.views}
        if set(view_ids) - known_views:
            raise InvalidCaptureProfileError("hard-surface views must reference profile views")
        if not any(
            view.role is HardSurfaceViewRole.WHOLE_ASSET for view in self.construction_views
        ):
            raise InvalidCaptureProfileError("hard-surface profiles require a whole-asset view")

    def _validate_connection_matrix(self) -> None:
        component_ids = {component.id for component in self.components}
        connection_keys = tuple(
            (
                connection.source_component_id,
                connection.target_component_id,
                connection.kind,
            )
            for connection in self.connection_matrix
        )
        if len(connection_keys) != len(set(connection_keys)):
            raise InvalidCaptureProfileError("hard-surface connection rows must be unique")
        if any(
            connection.source_component_id not in component_ids
            or connection.target_component_id not in component_ids
            for connection in self.connection_matrix
        ):
            raise InvalidCaptureProfileError(
                "hard-surface connections must reference profile components"
            )

    def _validate_outputs(self) -> None:
        output_ids = tuple(output.id for output in self.outputs)
        if len(output_ids) != len(set(output_ids)):
            raise InvalidCaptureProfileError("hard-surface output IDs must be unique")
        if not any(output.assembled_sheet for output in self.outputs):
            raise InvalidCaptureProfileError("hard-surface profiles require an assembled output")
        known_views = {view.id for view in self.capture_profile.views}
        if any(set(output.view_ids) - known_views for output in self.outputs):
            raise InvalidCaptureProfileError("hard-surface outputs must reference profile views")


def _expected_classification(
    kind: HardSurfaceProfileKind,
) -> tuple[AssetFamily, AssetSubtype | None]:
    classifications = {
        HardSurfaceProfileKind.PROP: (AssetFamily.PROP, None),
        HardSurfaceProfileKind.VEHICLE: (AssetFamily.VEHICLE, AssetSubtype("vehicle")),
        HardSurfaceProfileKind.BUILDING: (
            AssetFamily.ARCHITECTURE,
            AssetSubtype("building"),
        ),
        HardSurfaceProfileKind.MODULAR_KIT: (
            AssetFamily.ENVIRONMENT,
            AssetSubtype("modular-environment"),
        ),
        HardSurfaceProfileKind.INTERIOR: (
            AssetFamily.ENVIRONMENT,
            AssetSubtype("interior"),
        ),
    }
    return classifications[kind]


__all__ = [
    "HardSurfaceComponent",
    "HardSurfaceComponentKind",
    "HardSurfaceConnection",
    "HardSurfaceConnectionKind",
    "HardSurfaceProfile",
    "HardSurfaceProfileKind",
    "HardSurfaceState",
    "HardSurfaceView",
    "HardSurfaceViewRole",
]
