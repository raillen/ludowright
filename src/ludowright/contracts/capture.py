"""Versioned capture-profile serialization contract."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    Slug,
)
from ludowright.domain import (
    AssetFamily,
    AssetStateId,
    AssetSubtype,
    BackgroundMode,
    BackgroundSpec,
    CameraProjection,
    CameraSpec,
    CaptureProfile,
    CaptureProfileId,
    CaptureProfileRef,
    CaptureRequirement,
    CaptureRequirementKind,
    CaptureSheet,
    CaptureSheetId,
    CaptureSubjectMode,
    CaptureValidation,
    CaptureView,
    CaptureViewId,
    ComponentId,
    DisplayName,
    HexColor,
    LightingMode,
    LightingSpec,
    PixelDimensions,
    ProfileVersion,
    ReferenceRole,
    ShadowMode,
    SheetLayout,
    VariantId,
)

HexColorText = Annotated[str, StringConstraints(pattern=r"^#[0-9A-F]{6}$")]


class CameraContract(ContractModel):
    projection: CameraProjection
    focal_length_mm: Annotated[int, Field(ge=10, le=300)] | None = None
    framing_margin_percent: Annotated[int, Field(ge=0, le=50)] = 10

    def to_domain(self) -> CameraSpec:
        return CameraSpec(
            projection=self.projection,
            focal_length_mm=self.focal_length_mm,
            framing_margin_percent=self.framing_margin_percent,
        )

    @model_validator(mode="after")
    def validate_camera(self) -> Self:
        self.to_domain()
        return self


class BackgroundContract(ContractModel):
    mode: BackgroundMode
    color: HexColorText | None = None

    def to_domain(self) -> BackgroundSpec:
        return BackgroundSpec(
            mode=self.mode,
            color=HexColor(self.color) if self.color is not None else None,
        )

    @model_validator(mode="after")
    def validate_background(self) -> Self:
        self.to_domain()
        return self


class LightingContract(ContractModel):
    mode: LightingMode
    shadows: ShadowMode
    custom_label: DisplayText | None = None

    def to_domain(self) -> LightingSpec:
        return LightingSpec(
            mode=self.mode,
            shadows=self.shadows,
            custom_label=(
                DisplayName(self.custom_label)
                if self.custom_label is not None
                else None
            ),
        )

    @model_validator(mode="after")
    def validate_lighting(self) -> Self:
        self.to_domain()
        return self


class CaptureValidationContract(ContractModel):
    width: Annotated[int, Field(ge=64, le=16_384)]
    height: Annotated[int, Field(ge=64, le=16_384)]
    require_full_subject: bool = True
    require_consistent_scale: bool = True
    require_neutral_pose: bool = False
    allow_occlusion: bool = False

    def to_domain(self) -> CaptureValidation:
        return CaptureValidation(
            dimensions=PixelDimensions(self.width, self.height),
            require_full_subject=self.require_full_subject,
            require_consistent_scale=self.require_consistent_scale,
            require_neutral_pose=self.require_neutral_pose,
            allow_occlusion=self.allow_occlusion,
        )

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        self.to_domain()
        return self


class CaptureViewContract(ContractModel):
    id: Slug
    name: DisplayText
    azimuth_degrees: Annotated[int, Field(ge=0, le=359)]
    elevation_degrees: Annotated[int, Field(ge=-90, le=90)]
    role: ReferenceRole = ReferenceRole.CONSTRUCTION
    required: bool = True

    def to_domain(self) -> CaptureView:
        return CaptureView(
            id=CaptureViewId(self.id),
            name=DisplayName(self.name),
            azimuth_degrees=self.azimuth_degrees,
            elevation_degrees=self.elevation_degrees,
            role=self.role,
            required=self.required,
        )


class CaptureRequirementContract(ContractModel):
    id: Slug
    name: DisplayText
    requirement_kind: CaptureRequirementKind
    required: bool = True

    def to_domain(self) -> CaptureRequirement:
        identifier_types = {
            CaptureRequirementKind.COMPONENT: ComponentId,
            CaptureRequirementKind.VARIANT: VariantId,
            CaptureRequirementKind.STATE: AssetStateId,
        }
        identifier_type = identifier_types[self.requirement_kind]
        return CaptureRequirement(
            id=identifier_type(self.id),
            name=DisplayName(self.name),
            kind=self.requirement_kind,
            required=self.required,
        )


class CaptureSheetContract(ContractModel):
    id: Slug
    name: DisplayText
    layout: SheetLayout
    view_ids: Annotated[tuple[Slug, ...], Field(min_length=1)]
    subject_modes: Annotated[frozenset[CaptureSubjectMode], Field(min_length=1)]
    separate_files: bool = True
    assembled_sheet: bool = True
    required: bool = True

    def to_domain(self) -> CaptureSheet:
        return CaptureSheet(
            id=CaptureSheetId(self.id),
            name=DisplayName(self.name),
            layout=self.layout,
            view_ids=tuple(CaptureViewId(view_id) for view_id in self.view_ids),
            subject_modes=self.subject_modes,
            separate_files=self.separate_files,
            assembled_sheet=self.assembled_sheet,
            required=self.required,
        )


class CaptureProfileRefContract(ContractModel):
    id: Slug
    version: PositiveRevision

    def to_domain(self) -> CaptureProfileRef:
        return CaptureProfileRef(
            id=CaptureProfileId(self.id),
            version=ProfileVersion(self.version),
        )


class CaptureProfileContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["capture-profile"] = "capture-profile"
    id: Slug
    version: PositiveRevision
    name: DisplayText
    family: AssetFamily | None
    subtype: Slug | None = None
    parent: CaptureProfileRefContract | None = None
    camera: CameraContract | None = None
    background: BackgroundContract | None = None
    lighting: LightingContract | None = None
    validation: CaptureValidationContract | None = None
    views: tuple[CaptureViewContract, ...] = ()
    requirements: tuple[CaptureRequirementContract, ...] = ()
    sheets: tuple[CaptureSheetContract, ...] = ()

    def to_domain(self) -> CaptureProfile:
        return CaptureProfile(
            id=CaptureProfileId(self.id),
            version=ProfileVersion(self.version),
            name=DisplayName(self.name),
            family=self.family,
            subtype=AssetSubtype(self.subtype) if self.subtype is not None else None,
            parent=self.parent.to_domain() if self.parent is not None else None,
            camera=self.camera.to_domain() if self.camera is not None else None,
            background=(
                self.background.to_domain()
                if self.background is not None
                else None
            ),
            lighting=self.lighting.to_domain() if self.lighting is not None else None,
            validation=(
                self.validation.to_domain()
                if self.validation is not None
                else None
            ),
            views=tuple(view.to_domain() for view in self.views),
            requirements=tuple(
                requirement.to_domain() for requirement in self.requirements
            ),
            sheets=tuple(sheet.to_domain() for sheet in self.sheets),
        )

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        self.to_domain()
        return self
