"""Canonical visual-bible values and validation rules."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from ludowright.domain.capture_profiles import CameraSpec, LightingSpec
from ludowright.domain.errors import InvalidVisualBibleError
from ludowright.domain.identifiers import ProjectId, VisualBibleId
from ludowright.domain.names import DisplayName, validate_slug
from ludowright.domain.versions import VisualBibleVersion

MAX_VISUAL_TEXT_LENGTH = 1_000
MAX_VISUAL_BUDGET = 1_000_000


class PaletteRole(StrEnum):
    """Semantic role for a color in the shared visual palette."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    ACCENT = "accent"
    NEUTRAL = "neutral"
    BACKGROUND = "background"
    HIGHLIGHT = "highlight"


class MaterialFinish(StrEnum):
    """Controlled surface finish vocabulary for material guidance."""

    MATTE = "matte"
    SATIN = "satin"
    SEMI_GLOSS = "semi-gloss"
    GLOSSY = "glossy"
    METALLIC = "metallic"
    TRANSLUCENT = "translucent"
    EMISSIVE = "emissive"
    STYLIZED = "stylized"


class DetailLevel(StrEnum):
    """Production detail bands shared by visual jobs and future profiles."""

    PROXY = "proxy"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HERO = "hero"


@dataclass(frozen=True, slots=True)
class VisualText:
    """A bounded, normalized one-line visual direction statement."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise InvalidVisualBibleError("visual guidance text cannot be empty")
        if len(self.value) > MAX_VISUAL_TEXT_LENGTH:
            raise InvalidVisualBibleError(
                f"visual guidance text cannot exceed {MAX_VISUAL_TEXT_LENGTH} characters"
            )
        if unicodedata.normalize("NFC", self.value) != self.value:
            raise InvalidVisualBibleError("visual guidance text must use Unicode NFC")
        if any(unicodedata.category(character).startswith("C") for character in self.value):
            raise InvalidVisualBibleError("visual guidance text cannot contain control characters")

    def __str__(self) -> str:
        return self.value


def _require_tuple(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise InvalidVisualBibleError(f"{field_name} must be an immutable tuple")
    return value


def _require_unique(values: tuple[object, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise InvalidVisualBibleError(f"{field_name} must contain unique values")


def _validate_entry_id(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise InvalidVisualBibleError(f"{field_name} must be a canonical slug")
    try:
        validate_slug(value)
    except ValueError as error:
        raise InvalidVisualBibleError(f"{field_name} must be a canonical slug") from error


@dataclass(frozen=True, slots=True)
class ShapeLanguage:
    """Primary, supporting, and explicitly avoided shape descriptors."""

    primary: VisualText
    secondary: tuple[VisualText, ...] = ()
    avoid: tuple[VisualText, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.primary, VisualText):
            raise InvalidVisualBibleError("shape-language primary descriptor must be canonical")
        secondary = _require_tuple(self.secondary, "shape-language secondary descriptors")
        avoid = _require_tuple(self.avoid, "shape-language avoided descriptors")
        if any(not isinstance(value, VisualText) for value in secondary + avoid):
            raise InvalidVisualBibleError("shape-language descriptors must be canonical")
        _require_unique(secondary, "shape-language secondary descriptors")
        _require_unique(avoid, "shape-language avoided descriptors")
        if self.primary in secondary or self.primary in avoid:
            raise InvalidVisualBibleError(
                "shape-language primary descriptor cannot be repeated in secondary or avoid"
            )


@dataclass(frozen=True, slots=True)
class ProportionRule:
    """Named proportional guidance without provider-specific geometry claims."""

    id: str
    name: DisplayName
    guidance: VisualText

    def __post_init__(self) -> None:
        _validate_entry_id(self.id, "proportion rule ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidVisualBibleError("proportion rule name must be canonical")
        if not isinstance(self.guidance, VisualText):
            raise InvalidVisualBibleError("proportion rule guidance must be canonical")


@dataclass(frozen=True, slots=True)
class PaletteColor:
    """One named color in the shared visual palette."""

    id: str
    name: DisplayName
    color: str
    role: PaletteRole

    def __post_init__(self) -> None:
        _validate_entry_id(self.id, "palette color ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidVisualBibleError("palette color name must be canonical")
        if not isinstance(self.color, str):
            raise InvalidVisualBibleError("palette color must be text")
        if (
            len(self.color) != 7
            or self.color[0] != "#"
            or any(character not in "0123456789ABCDEF" for character in self.color[1:])
        ):
            raise InvalidVisualBibleError("palette colors must use uppercase #RRGGBB notation")
        if not isinstance(self.role, PaletteRole):
            raise InvalidVisualBibleError("palette color role must be canonical")


@dataclass(frozen=True, slots=True)
class MaterialRule:
    """Named material guidance shared by visual jobs."""

    id: str
    name: DisplayName
    finish: MaterialFinish
    guidance: VisualText

    def __post_init__(self) -> None:
        _validate_entry_id(self.id, "material rule ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidVisualBibleError("material rule name must be canonical")
        if not isinstance(self.finish, MaterialFinish):
            raise InvalidVisualBibleError("material finish must be canonical")
        if not isinstance(self.guidance, VisualText):
            raise InvalidVisualBibleError("material rule guidance must be canonical")


@dataclass(frozen=True, slots=True)
class DetailLevelRule:
    """Guidance for one shared level-of-detail band."""

    level: DetailLevel
    guidance: VisualText

    def __post_init__(self) -> None:
        if not isinstance(self.level, DetailLevel):
            raise InvalidVisualBibleError("detail level must be canonical")
        if not isinstance(self.guidance, VisualText):
            raise InvalidVisualBibleError("detail level guidance must be canonical")


@dataclass(frozen=True, slots=True)
class LevelOfDetail:
    """Ordered detail bands and the project's default band."""

    default_level: DetailLevel
    levels: tuple[DetailLevelRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.default_level, DetailLevel):
            raise InvalidVisualBibleError("default detail level must be canonical")
        levels = _require_tuple(self.levels, "level-of-detail rules")
        if not levels:
            raise InvalidVisualBibleError("level-of-detail requires at least one rule")
        if any(not isinstance(rule, DetailLevelRule) for rule in levels):
            raise InvalidVisualBibleError("level-of-detail rules must be canonical")
        _require_unique(tuple(rule.level for rule in self.levels), "level-of-detail bands")
        if self.default_level not in tuple(rule.level for rule in self.levels):
            raise InvalidVisualBibleError("default detail level must have a matching rule")


@dataclass(frozen=True, slots=True)
class VisualBudget:
    """Provider-neutral workload ceilings for visual production planning."""

    max_visual_jobs: int
    max_generated_outputs: int
    max_references_per_asset: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_visual_jobs", self.max_visual_jobs),
            ("max_generated_outputs", self.max_generated_outputs),
            ("max_references_per_asset", self.max_references_per_asset),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidVisualBibleError(f"{field_name} must be an integer")
            if not 1 <= value <= MAX_VISUAL_BUDGET:
                raise InvalidVisualBibleError(
                    f"{field_name} must be between 1 and {MAX_VISUAL_BUDGET}"
                )


@dataclass(frozen=True, slots=True)
class VisualBible:
    """Immutable project-level visual direction contract."""

    id: VisualBibleId
    version: VisualBibleVersion
    name: DisplayName
    project_id: ProjectId
    shape_language: ShapeLanguage
    proportions: tuple[ProportionRule, ...]
    palette: tuple[PaletteColor, ...]
    materials: tuple[MaterialRule, ...]
    lighting: LightingSpec
    camera: CameraSpec
    level_of_detail: LevelOfDetail
    budget: VisualBudget
    prompt_constraints: tuple[VisualText, ...]
    negative_constraints: tuple[VisualText, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, VisualBibleId):
            raise InvalidVisualBibleError("visual bible requires a typed ID")
        if not isinstance(self.version, VisualBibleVersion):
            raise InvalidVisualBibleError("visual bible requires a version")
        if not isinstance(self.name, DisplayName):
            raise InvalidVisualBibleError("visual bible name must be canonical")
        if not isinstance(self.project_id, ProjectId):
            raise InvalidVisualBibleError("visual bible requires a typed project ID")
        if not isinstance(self.shape_language, ShapeLanguage):
            raise InvalidVisualBibleError("visual bible shape language must be canonical")
        if not isinstance(self.lighting, LightingSpec):
            raise InvalidVisualBibleError("visual bible lighting must be canonical")
        if not isinstance(self.camera, CameraSpec):
            raise InvalidVisualBibleError("visual bible camera must be canonical")
        if not isinstance(self.level_of_detail, LevelOfDetail):
            raise InvalidVisualBibleError("visual bible detail levels must be canonical")
        if not isinstance(self.budget, VisualBudget):
            raise InvalidVisualBibleError("visual bible budget must be canonical")
        proportions = _require_tuple(self.proportions, "proportion rules")
        palette = _require_tuple(self.palette, "palette colors")
        materials = _require_tuple(self.materials, "material rules")
        prompt_constraints = _require_tuple(self.prompt_constraints, "prompt constraints")
        negative_constraints = _require_tuple(self.negative_constraints, "negative constraints")

        if not proportions:
            raise InvalidVisualBibleError("visual bible requires at least one proportion rule")
        if not palette:
            raise InvalidVisualBibleError("visual bible requires at least one palette color")
        if not materials:
            raise InvalidVisualBibleError("visual bible requires at least one material rule")
        if not prompt_constraints:
            raise InvalidVisualBibleError("visual bible requires at least one prompt constraint")
        if not negative_constraints:
            raise InvalidVisualBibleError("visual bible requires at least one negative constraint")
        if any(not isinstance(rule, ProportionRule) for rule in proportions):
            raise InvalidVisualBibleError("proportion rules must be canonical")
        if any(not isinstance(color, PaletteColor) for color in palette):
            raise InvalidVisualBibleError("palette colors must be canonical")
        if any(not isinstance(rule, MaterialRule) for rule in materials):
            raise InvalidVisualBibleError("material rules must be canonical")
        if any(
            not isinstance(value, VisualText) for value in prompt_constraints + negative_constraints
        ):
            raise InvalidVisualBibleError("visual constraints must be canonical")

        _require_unique(tuple(rule.id for rule in self.proportions), "proportion rule IDs")
        _require_unique(tuple(color.id for color in self.palette), "palette color IDs")
        _require_unique(tuple(rule.id for rule in self.materials), "material rule IDs")
        _require_unique(prompt_constraints, "prompt constraints")
        _require_unique(negative_constraints, "negative constraints")
        if set(prompt_constraints) & set(negative_constraints):
            raise InvalidVisualBibleError(
                "prompt and negative constraints cannot contain the same statement"
            )
