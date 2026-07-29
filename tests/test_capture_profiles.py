"""Tests for reusable capture profiles and exact inheritance."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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
    InvalidCaptureProfileError,
    InvalidCaptureProfileInheritanceError,
    LightingMode,
    LightingSpec,
    PixelDimensions,
    ProfileVersion,
    ReferenceRole,
    ShadowMode,
    SheetLayout,
    VariantId,
)


def front_view(*, required: bool = True) -> CaptureView:
    return CaptureView(
        id=CaptureViewId("front"),
        name=DisplayName("Front"),
        azimuth_degrees=0,
        elevation_degrees=0,
        role=ReferenceRole.IDENTITY,
        required=required,
    )


def side_view() -> CaptureView:
    return CaptureView(
        id=CaptureViewId("side"),
        name=DisplayName("Side"),
        azimuth_degrees=90,
        elevation_degrees=0,
    )


def base_profile() -> CaptureProfile:
    front = front_view()
    side = side_view()
    component = CaptureRequirement(
        ComponentId("base-body"),
        DisplayName("Base Body"),
        CaptureRequirementKind.COMPONENT,
    )
    state = CaptureRequirement(
        AssetStateId("neutral"),
        DisplayName("Neutral"),
        CaptureRequirementKind.STATE,
    )
    sheet = CaptureSheet(
        id=CaptureSheetId("character-turnaround"),
        name=DisplayName("Character Turnaround"),
        layout=SheetLayout.TURNAROUND,
        view_ids=(front.id, side.id),
        subject_modes=frozenset(
            {
                CaptureSubjectMode.ASSET,
                CaptureSubjectMode.COMPONENTS,
                CaptureSubjectMode.STATES,
            }
        ),
    )
    return CaptureProfile(
        id=CaptureProfileId("character-base"),
        version=ProfileVersion(1),
        name=DisplayName("Character Base"),
        family=AssetFamily.CHARACTER,
        camera=CameraSpec(CameraProjection.ORTHOGRAPHIC),
        background=BackgroundSpec(BackgroundMode.TRANSPARENT),
        lighting=LightingSpec(LightingMode.STUDIO, ShadowMode.SOFT),
        validation=CaptureValidation(
            PixelDimensions(2048, 2048),
            require_neutral_pose=True,
        ),
        views=(front, side),
        requirements=(component, state),
        sheets=(sheet,),
    )


def test_root_profile_preserves_complete_capture_contract() -> None:
    profile = base_profile()

    assert profile.family is AssetFamily.CHARACTER
    assert profile.camera == CameraSpec(CameraProjection.ORTHOGRAPHIC)
    assert profile.required_view_ids == (
        CaptureViewId("front"),
        CaptureViewId("side"),
    )
    assert profile.reference == CaptureProfileRef(
        CaptureProfileId("character-base"),
        ProfileVersion(1),
    )


def test_profile_is_immutable() -> None:
    profile = base_profile()

    with pytest.raises(FrozenInstanceError):
        profile.family = AssetFamily.PROP  # type: ignore[misc]


@pytest.mark.parametrize("value", ["#ffffff", "FFFFFF", "#FFFF", "#GGGGGG", 123])
def test_hex_color_requires_canonical_uppercase_rgb(value: object) -> None:
    with pytest.raises(InvalidCaptureProfileError):
        HexColor(value)  # type: ignore[arg-type]


def test_pixel_dimensions_are_bounded_integers() -> None:
    assert PixelDimensions(1024, 2048).height == 2048

    with pytest.raises(InvalidCaptureProfileError):
        PixelDimensions(True, 1024)  # type: ignore[arg-type]
    with pytest.raises(InvalidCaptureProfileError):
        PixelDimensions(32, 1024)


def test_perspective_camera_requires_bounded_focal_length() -> None:
    camera = CameraSpec(CameraProjection.PERSPECTIVE, focal_length_mm=50)
    assert camera.focal_length_mm == 50

    with pytest.raises(InvalidCaptureProfileError, match="requires"):
        CameraSpec(CameraProjection.PERSPECTIVE)
    with pytest.raises(InvalidCaptureProfileError, match="only perspective"):
        CameraSpec(CameraProjection.ORTHOGRAPHIC, focal_length_mm=50)


def test_solid_background_requires_color_and_other_modes_forbid_it() -> None:
    background = BackgroundSpec(BackgroundMode.SOLID, HexColor("#FFFFFF"))
    assert str(background.color) == "#FFFFFF"

    with pytest.raises(InvalidCaptureProfileError, match="requires a color"):
        BackgroundSpec(BackgroundMode.SOLID)
    with pytest.raises(InvalidCaptureProfileError, match="only solid"):
        BackgroundSpec(BackgroundMode.TRANSPARENT, HexColor("#FFFFFF"))


def test_custom_lighting_requires_label() -> None:
    lighting = LightingSpec(
        LightingMode.CUSTOM,
        ShadowMode.CONTACT,
        DisplayName("Approved Three-Point Rig"),
    )
    assert lighting.custom_label == DisplayName("Approved Three-Point Rig")

    with pytest.raises(InvalidCaptureProfileError, match="requires"):
        LightingSpec(LightingMode.CUSTOM, ShadowMode.NONE)


def test_full_subject_validation_cannot_allow_occlusion() -> None:
    with pytest.raises(InvalidCaptureProfileError, match="cannot allow"):
        CaptureValidation(PixelDimensions(1024, 1024), allow_occlusion=True)


def test_capture_view_validates_angles() -> None:
    with pytest.raises(InvalidCaptureProfileError, match="azimuth"):
        CaptureView(
            CaptureViewId("invalid"),
            DisplayName("Invalid"),
            azimuth_degrees=360,
            elevation_degrees=0,
        )
    with pytest.raises(InvalidCaptureProfileError, match="elevation"):
        CaptureView(
            CaptureViewId("invalid"),
            DisplayName("Invalid"),
            azimuth_degrees=0,
            elevation_degrees=91,
        )


@pytest.mark.parametrize(
    ("identifier", "kind"),
    [
        (VariantId("winter"), CaptureRequirementKind.COMPONENT),
        (ComponentId("body"), CaptureRequirementKind.STATE),
        (AssetStateId("open"), CaptureRequirementKind.VARIANT),
    ],
)
def test_capture_requirement_id_must_match_kind(
    identifier: object,
    kind: CaptureRequirementKind,
) -> None:
    with pytest.raises(InvalidCaptureProfileError, match="must match"):
        CaptureRequirement(
            identifier,  # type: ignore[arg-type]
            DisplayName("Mismatched"),
            kind,
        )


def test_capture_sheet_requires_output_form_and_unique_views() -> None:
    view_id = CaptureViewId("front")
    with pytest.raises(InvalidCaptureProfileError, match="must request"):
        CaptureSheet(
            CaptureSheetId("invalid"),
            DisplayName("Invalid"),
            SheetLayout.GRID,
            (view_id,),
            frozenset({CaptureSubjectMode.ASSET}),
            separate_files=False,
            assembled_sheet=False,
        )
    with pytest.raises(InvalidCaptureProfileError, match="must be unique"):
        CaptureSheet(
            CaptureSheetId("duplicate"),
            DisplayName("Duplicate"),
            SheetLayout.GRID,
            (view_id, view_id),
            frozenset({CaptureSubjectMode.ASSET}),
        )


def test_root_profile_requires_complete_environment_and_view() -> None:
    with pytest.raises(InvalidCaptureProfileError, match="requires camera"):
        CaptureProfile(
            CaptureProfileId("incomplete"),
            ProfileVersion(1),
            DisplayName("Incomplete"),
            AssetFamily.PROP,
            background=BackgroundSpec(BackgroundMode.TRANSPARENT),
            lighting=LightingSpec(LightingMode.FLAT, ShadowMode.NONE),
            validation=CaptureValidation(PixelDimensions(1024, 1024)),
            views=(front_view(),),
        )


def test_profile_rejects_duplicate_requirement_ids() -> None:
    duplicate_a = CaptureRequirement(
        ComponentId("body"),
        DisplayName("Body"),
        CaptureRequirementKind.COMPONENT,
    )
    duplicate_b = CaptureRequirement(
        ComponentId("body"),
        DisplayName("Body Duplicate"),
        CaptureRequirementKind.COMPONENT,
    )
    profile = base_profile()

    with pytest.raises(InvalidCaptureProfileError, match="IDs must be unique"):
        CaptureProfile(
            id=profile.id,
            version=profile.version,
            name=profile.name,
            family=profile.family,
            camera=profile.camera,
            background=profile.background,
            lighting=profile.lighting,
            validation=profile.validation,
            views=profile.views,
            requirements=(duplicate_a, duplicate_b),
        )


def test_sheet_must_reference_known_views() -> None:
    profile = base_profile()
    sheet = CaptureSheet(
        CaptureSheetId("unknown-view"),
        DisplayName("Unknown View"),
        SheetLayout.GRID,
        (CaptureViewId("rear"),),
        frozenset({CaptureSubjectMode.ASSET}),
    )

    with pytest.raises(InvalidCaptureProfileError, match="not present"):
        CaptureProfile(
            id=profile.id,
            version=profile.version,
            name=profile.name,
            family=profile.family,
            camera=profile.camera,
            background=profile.background,
            lighting=profile.lighting,
            validation=profile.validation,
            views=profile.views,
            requirements=profile.requirements,
            sheets=(sheet,),
        )


def test_sheet_subject_mode_requires_matching_requirement() -> None:
    profile = base_profile()
    sheet = CaptureSheet(
        CaptureSheetId("variant-sheet"),
        DisplayName("Variant Sheet"),
        SheetLayout.GRID,
        (CaptureViewId("front"),),
        frozenset({CaptureSubjectMode.VARIANTS}),
    )

    with pytest.raises(InvalidCaptureProfileError, match="matching"):
        CaptureProfile(
            id=profile.id,
            version=profile.version,
            name=profile.name,
            family=profile.family,
            camera=profile.camera,
            background=profile.background,
            lighting=profile.lighting,
            validation=profile.validation,
            views=profile.views,
            requirements=profile.requirements,
            sheets=(sheet,),
        )


def test_child_profile_resolves_exact_parent_and_overrides_by_id() -> None:
    parent = base_profile()
    overridden_front = CaptureView(
        CaptureViewId("front"),
        DisplayName("Front Identity"),
        0,
        0,
        ReferenceRole.IDENTITY,
        False,
    )
    rear = CaptureView(CaptureViewId("rear"), DisplayName("Rear"), 180, 0)
    variant = CaptureRequirement(
        VariantId("winter"),
        DisplayName("Winter"),
        CaptureRequirementKind.VARIANT,
    )
    child = CaptureProfile(
        id=CaptureProfileId("humanoid-character"),
        version=ProfileVersion(2),
        name=DisplayName("Humanoid Character"),
        family=None,
        subtype=AssetSubtype("humanoid"),
        parent=parent.reference,
        background=BackgroundSpec(BackgroundMode.NEUTRAL),
        views=(overridden_front, rear),
        requirements=(variant,),
    )

    resolved = child.resolve(parent)

    assert resolved.parent is None
    assert resolved.family is AssetFamily.CHARACTER
    assert resolved.subtype == AssetSubtype("humanoid")
    assert resolved.background == BackgroundSpec(BackgroundMode.NEUTRAL)
    assert tuple(view.id for view in resolved.views) == (
        CaptureViewId("front"),
        CaptureViewId("side"),
        CaptureViewId("rear"),
    )
    assert resolved.views[0].required is False
    assert resolved.requirements[-1] == variant


def test_inheritance_requires_exact_parent_version() -> None:
    parent = base_profile()
    child = CaptureProfile(
        CaptureProfileId("child"),
        ProfileVersion(1),
        DisplayName("Child"),
        None,
        parent=CaptureProfileRef(parent.id, ProfileVersion(2)),
    )

    with pytest.raises(InvalidCaptureProfileInheritanceError, match="exactly"):
        child.resolve(parent)


def test_child_cannot_change_parent_family() -> None:
    parent = base_profile()
    child = CaptureProfile(
        CaptureProfileId("prop-child"),
        ProfileVersion(1),
        DisplayName("Prop Child"),
        AssetFamily.PROP,
        parent=parent.reference,
    )

    with pytest.raises(InvalidCaptureProfileInheritanceError, match="cannot change"):
        child.resolve(parent)


def test_root_profile_does_not_resolve_again() -> None:
    profile = base_profile()

    with pytest.raises(InvalidCaptureProfileInheritanceError, match="root"):
        profile.resolve(profile)
