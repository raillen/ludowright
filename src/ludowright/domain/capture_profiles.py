"""Reusable capture profiles, technical sheets, and inheritance rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, Self, TypeVar

from ludowright.domain.assets import AssetFamily, AssetSubtype
from ludowright.domain.errors import (
    InvalidCaptureProfileError,
    InvalidCaptureProfileInheritanceError,
)
from ludowright.domain.identifiers import (
    AssetStateId,
    CaptureProfileId,
    CaptureSheetId,
    CaptureViewId,
    ComponentId,
    Identifier,
    VariantId,
)
from ludowright.domain.names import DisplayName
from ludowright.domain.references import ReferenceRole
from ludowright.domain.versions import ProfileVersion

_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")


class CameraProjection(StrEnum):
    ORTHOGRAPHIC = "orthographic"
    PERSPECTIVE = "perspective"
    ISOMETRIC = "isometric"


class BackgroundMode(StrEnum):
    TRANSPARENT = "transparent"
    SOLID = "solid"
    NEUTRAL = "neutral"
    ENVIRONMENT = "environment"


class LightingMode(StrEnum):
    FLAT = "flat"
    STUDIO = "studio"
    NATURAL = "natural"
    DRAMATIC = "dramatic"
    UNLIT = "unlit"
    CUSTOM = "custom"


class ShadowMode(StrEnum):
    NONE = "none"
    CONTACT = "contact"
    SOFT = "soft"
    FULL = "full"


class SheetLayout(StrEnum):
    GRID = "grid"
    TURNAROUND = "turnaround"
    EXPLODED = "exploded"
    CONTACT_SHEET = "contact-sheet"


class CaptureSubjectMode(StrEnum):
    ASSET = "asset"
    COMPONENTS = "components"
    VARIANTS = "variants"
    STATES = "states"


class CaptureRequirementKind(StrEnum):
    COMPONENT = "component"
    VARIANT = "variant"
    STATE = "state"


@dataclass(frozen=True, slots=True)
class HexColor:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _HEX_COLOR_PATTERN.fullmatch(self.value) is None:
            raise InvalidCaptureProfileError(
                "a capture color must use canonical uppercase #RRGGBB notation"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PixelDimensions:
    width: int
    height: int

    def __post_init__(self) -> None:
        for value in (self.width, self.height):
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidCaptureProfileError("pixel dimensions must be integers")
            if not 64 <= value <= 16_384:
                raise InvalidCaptureProfileError(
                    "pixel dimensions must be between 64 and 16384 pixels"
                )


@dataclass(frozen=True, slots=True)
class CameraSpec:
    projection: CameraProjection
    focal_length_mm: int | None = None
    framing_margin_percent: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.projection, CameraProjection):
            raise InvalidCaptureProfileError("camera projection must be canonical")
        if isinstance(self.framing_margin_percent, bool) or not isinstance(
            self.framing_margin_percent, int
        ):
            raise InvalidCaptureProfileError("camera framing margin must be an integer")
        if not 0 <= self.framing_margin_percent <= 50:
            raise InvalidCaptureProfileError(
                "camera framing margin must be between 0 and 50 percent"
            )
        if self.projection is CameraProjection.PERSPECTIVE:
            if isinstance(self.focal_length_mm, bool) or not isinstance(
                self.focal_length_mm, int
            ):
                raise InvalidCaptureProfileError(
                    "perspective camera requires an integer focal length"
                )
            if not 10 <= self.focal_length_mm <= 300:
                raise InvalidCaptureProfileError(
                    "perspective focal length must be between 10 and 300 mm"
                )
        elif self.focal_length_mm is not None:
            raise InvalidCaptureProfileError(
                "only perspective cameras may define a focal length"
            )


@dataclass(frozen=True, slots=True)
class BackgroundSpec:
    mode: BackgroundMode
    color: HexColor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, BackgroundMode):
            raise InvalidCaptureProfileError("background mode must be canonical")
        if self.mode is BackgroundMode.SOLID:
            if not isinstance(self.color, HexColor):
                raise InvalidCaptureProfileError("solid background requires a color")
        elif self.color is not None:
            raise InvalidCaptureProfileError(
                "only solid backgrounds may define a color"
            )


@dataclass(frozen=True, slots=True)
class LightingSpec:
    mode: LightingMode
    shadows: ShadowMode
    custom_label: DisplayName | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, LightingMode):
            raise InvalidCaptureProfileError("lighting mode must be canonical")
        if not isinstance(self.shadows, ShadowMode):
            raise InvalidCaptureProfileError("shadow mode must be canonical")
        if self.mode is LightingMode.CUSTOM:
            if not isinstance(self.custom_label, DisplayName):
                raise InvalidCaptureProfileError(
                    "custom lighting requires a descriptive label"
                )
        elif self.custom_label is not None:
            raise InvalidCaptureProfileError(
                "only custom lighting may define a custom label"
            )


@dataclass(frozen=True, slots=True)
class CaptureValidation:
    dimensions: PixelDimensions
    require_full_subject: bool = True
    require_consistent_scale: bool = True
    require_neutral_pose: bool = False
    allow_occlusion: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, PixelDimensions):
            raise InvalidCaptureProfileError(
                "capture validation requires pixel dimensions"
            )
        flags = (
            self.require_full_subject,
            self.require_consistent_scale,
            self.require_neutral_pose,
            self.allow_occlusion,
        )
        if any(not isinstance(flag, bool) for flag in flags):
            raise InvalidCaptureProfileError(
                "capture validation flags must be boolean"
            )
        if self.require_full_subject and self.allow_occlusion:
            raise InvalidCaptureProfileError(
                "full-subject validation cannot allow occlusion"
            )


@dataclass(frozen=True, slots=True)
class CaptureView:
    id: CaptureViewId
    name: DisplayName
    azimuth_degrees: int
    elevation_degrees: int
    role: ReferenceRole = ReferenceRole.CONSTRUCTION
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, CaptureViewId):
            raise InvalidCaptureProfileError("capture view requires a typed ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("capture view name must be canonical")
        if isinstance(self.azimuth_degrees, bool) or not isinstance(
            self.azimuth_degrees, int
        ):
            raise InvalidCaptureProfileError("view azimuth must be an integer")
        if not 0 <= self.azimuth_degrees <= 359:
            raise InvalidCaptureProfileError("view azimuth must be between 0 and 359")
        if isinstance(self.elevation_degrees, bool) or not isinstance(
            self.elevation_degrees, int
        ):
            raise InvalidCaptureProfileError("view elevation must be an integer")
        if not -90 <= self.elevation_degrees <= 90:
            raise InvalidCaptureProfileError(
                "view elevation must be between -90 and 90"
            )
        if not isinstance(self.role, ReferenceRole):
            raise InvalidCaptureProfileError("capture view role must be canonical")
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError("capture view required flag must be boolean")


@dataclass(frozen=True, slots=True)
class CaptureRequirement:
    id: Identifier
    name: DisplayName
    kind: CaptureRequirementKind
    required: bool = True

    def __post_init__(self) -> None:
        expected_types = {
            CaptureRequirementKind.COMPONENT: ComponentId,
            CaptureRequirementKind.VARIANT: VariantId,
            CaptureRequirementKind.STATE: AssetStateId,
        }
        if not isinstance(self.kind, CaptureRequirementKind):
            raise InvalidCaptureProfileError("capture requirement kind must be canonical")
        if not isinstance(self.id, expected_types[self.kind]):
            raise InvalidCaptureProfileError(
                "capture requirement ID must match its requirement kind"
            )
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError(
                "capture requirement name must be canonical"
            )
        if not isinstance(self.required, bool):
            raise InvalidCaptureProfileError(
                "capture requirement required flag must be boolean"
            )


@dataclass(frozen=True, slots=True)
class CaptureSheet:
    id: CaptureSheetId
    name: DisplayName
    layout: SheetLayout
    view_ids: tuple[CaptureViewId, ...]
    subject_modes: frozenset[CaptureSubjectMode]
    separate_files: bool = True
    assembled_sheet: bool = True
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, CaptureSheetId):
            raise InvalidCaptureProfileError("capture sheet requires a typed ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("capture sheet name must be canonical")
        if not isinstance(self.layout, SheetLayout):
            raise InvalidCaptureProfileError("capture sheet layout must be canonical")
        if not isinstance(self.view_ids, tuple) or not self.view_ids:
            raise InvalidCaptureProfileError(
                "capture sheet requires an immutable non-empty view tuple"
            )
        if any(not isinstance(view_id, CaptureViewId) for view_id in self.view_ids):
            raise InvalidCaptureProfileError("capture sheet view IDs must be typed")
        if len(self.view_ids) != len(set(self.view_ids)):
            raise InvalidCaptureProfileError("capture sheet view IDs must be unique")
        if not isinstance(self.subject_modes, frozenset) or not self.subject_modes:
            raise InvalidCaptureProfileError(
                "capture sheet requires immutable subject modes"
            )
        if any(
            not isinstance(mode, CaptureSubjectMode) for mode in self.subject_modes
        ):
            raise InvalidCaptureProfileError(
                "capture sheet subject modes must be canonical"
            )
        for flag in (self.separate_files, self.assembled_sheet, self.required):
            if not isinstance(flag, bool):
                raise InvalidCaptureProfileError(
                    "capture sheet output flags must be boolean"
                )
        if not self.separate_files and not self.assembled_sheet:
            raise InvalidCaptureProfileError(
                "capture sheet must request separate files or an assembled sheet"
            )


@dataclass(frozen=True, slots=True)
class CaptureProfileRef:
    id: CaptureProfileId
    version: ProfileVersion

    def __post_init__(self) -> None:
        if not isinstance(self.id, CaptureProfileId):
            raise InvalidCaptureProfileError("profile reference requires a typed ID")
        if not isinstance(self.version, ProfileVersion):
            raise InvalidCaptureProfileError(
                "profile reference requires a profile version"
            )


class _Identified(Protocol):
    @property
    def id(self) -> Identifier: ...


_T = TypeVar("_T", bound=_Identified)


@dataclass(frozen=True, slots=True)
class CaptureProfile:
    id: CaptureProfileId
    version: ProfileVersion
    name: DisplayName
    family: AssetFamily | None
    subtype: AssetSubtype | None = None
    parent: CaptureProfileRef | None = None
    camera: CameraSpec | None = None
    background: BackgroundSpec | None = None
    lighting: LightingSpec | None = None
    validation: CaptureValidation | None = None
    views: tuple[CaptureView, ...] = ()
    requirements: tuple[CaptureRequirement, ...] = ()
    sheets: tuple[CaptureSheet, ...] = ()

    def __post_init__(self) -> None:
        self._validate_identity()
        self._validate_collections()
        if self.parent is None:
            self._validate_resolved_contract()
        elif not isinstance(self.parent, CaptureProfileRef):
            raise InvalidCaptureProfileError(
                "capture profile parent must be an exact profile reference"
            )

    def _validate_identity(self) -> None:
        if not isinstance(self.id, CaptureProfileId):
            raise InvalidCaptureProfileError("capture profile requires a typed ID")
        if not isinstance(self.version, ProfileVersion):
            raise InvalidCaptureProfileError("capture profile requires a version")
        if not isinstance(self.name, DisplayName):
            raise InvalidCaptureProfileError("capture profile name must be canonical")
        if self.family is not None and not isinstance(self.family, AssetFamily):
            raise InvalidCaptureProfileError("capture profile family must be canonical")
        if self.subtype is not None and not isinstance(self.subtype, AssetSubtype):
            raise InvalidCaptureProfileError("capture profile subtype must be canonical")
        if self.family is AssetFamily.OTHER and self.subtype is None:
            raise InvalidCaptureProfileError(
                "the 'other' profile family requires a subtype"
            )

    def _validate_collections(self) -> None:
        collections = (self.views, self.requirements, self.sheets)
        if any(not isinstance(collection, tuple) for collection in collections):
            raise InvalidCaptureProfileError(
                "capture profile requirement collections must be tuples"
            )
        self._validate_items(self.views, CaptureView, "view")
        self._validate_items(self.requirements, CaptureRequirement, "requirement")
        self._validate_items(self.sheets, CaptureSheet, "sheet")

    @staticmethod
    def _validate_items(items: tuple[_T, ...], expected: type[_T], label: str) -> None:
        if any(not isinstance(item, expected) for item in items):
            raise InvalidCaptureProfileError(
                f"capture profile contains an invalid {label}"
            )
        ids = tuple(item.id for item in items)
        if len(ids) != len(set(ids)):
            raise InvalidCaptureProfileError(
                f"capture profile {label} IDs must be unique"
            )

    def _validate_resolved_contract(self) -> None:
        if self.family is None:
            raise InvalidCaptureProfileError(
                "resolved capture profile requires an asset family"
            )
        for value, label in (
            (self.camera, "camera"),
            (self.background, "background"),
            (self.lighting, "lighting"),
            (self.validation, "validation rules"),
        ):
            if value is None:
                raise InvalidCaptureProfileError(
                    f"resolved capture profile requires {label}"
                )
        if not self.views:
            raise InvalidCaptureProfileError(
                "resolved capture profile requires at least one view"
            )
        self._validate_sheet_references()

    def _validate_sheet_references(self) -> None:
        known_views = {view.id for view in self.views}
        kinds = {requirement.kind for requirement in self.requirements}
        required_kinds = {
            CaptureSubjectMode.COMPONENTS: CaptureRequirementKind.COMPONENT,
            CaptureSubjectMode.VARIANTS: CaptureRequirementKind.VARIANT,
            CaptureSubjectMode.STATES: CaptureRequirementKind.STATE,
        }
        for sheet in self.sheets:
            if set(sheet.view_ids) - known_views:
                raise InvalidCaptureProfileError(
                    "capture sheet references views not present in the profile"
                )
            for mode, kind in required_kinds.items():
                if mode in sheet.subject_modes and kind not in kinds:
                    raise InvalidCaptureProfileError(
                        f"{mode.value} sheet mode requires matching capture requirements"
                    )

    @property
    def reference(self) -> CaptureProfileRef:
        return CaptureProfileRef(self.id, self.version)

    @property
    def required_view_ids(self) -> tuple[CaptureViewId, ...]:
        return tuple(view.id for view in self.views if view.required)

    def resolve(self, parent: CaptureProfile) -> Self:
        if self.parent is None:
            raise InvalidCaptureProfileInheritanceError(
                "a root capture profile does not require inheritance resolution"
            )
        if not isinstance(parent, CaptureProfile):
            raise InvalidCaptureProfileInheritanceError(
                "capture profile inheritance requires a parent profile"
            )
        if parent.parent is not None:
            raise InvalidCaptureProfileInheritanceError(
                "capture profile parent must be resolved before inheritance"
            )
        if self.parent != parent.reference:
            raise InvalidCaptureProfileInheritanceError(
                "capture profile parent ID and version must match exactly"
            )
        if self.family is not None and self.family is not parent.family:
            raise InvalidCaptureProfileInheritanceError(
                "child capture profile cannot change the parent asset family"
            )
        return replace(
            self,
            parent=None,
            family=self.family or parent.family,
            subtype=self.subtype or parent.subtype,
            camera=self.camera or parent.camera,
            background=self.background or parent.background,
            lighting=self.lighting or parent.lighting,
            validation=self.validation or parent.validation,
            views=_merge_requirements(parent.views, self.views),
            requirements=_merge_requirements(parent.requirements, self.requirements),
            sheets=_merge_requirements(parent.sheets, self.sheets),
        )


def _merge_requirements(base: tuple[_T, ...], overrides: tuple[_T, ...]) -> tuple[_T, ...]:
    override_by_id = {item.id: item for item in overrides}
    merged = [override_by_id.pop(item.id, item) for item in base]
    merged.extend(override_by_id.values())
    return tuple(merged)
