"""Versioned visual-bible serialization contract."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.capture import CameraContract, LightingContract
from ludowright.contracts.common import ContractModel, DisplayText, PositiveRevision, Slug
from ludowright.domain import (
    DetailLevel,
    DetailLevelRule,
    DisplayName,
    LevelOfDetail,
    MaterialFinish,
    MaterialRule,
    PaletteColor,
    PaletteRole,
    ProjectId,
    ProportionRule,
    ShapeLanguage,
    VisualBible,
    VisualBibleId,
    VisualBibleVersion,
    VisualBudget,
    VisualText,
)

VisualGuidanceText = Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
PositiveVisualBudget = Annotated[int, Field(ge=1, le=1_000_000)]


class ShapeLanguageContract(ContractModel):
    primary: DisplayText
    secondary: tuple[DisplayText, ...] = ()
    avoid: tuple[DisplayText, ...] = ()

    def to_domain(self) -> ShapeLanguage:
        return ShapeLanguage(
            primary=VisualText(self.primary),
            secondary=tuple(VisualText(value) for value in self.secondary),
            avoid=tuple(VisualText(value) for value in self.avoid),
        )


class ProportionRuleContract(ContractModel):
    id: Slug
    name: DisplayText
    guidance: VisualGuidanceText

    def to_domain(self) -> ProportionRule:
        return ProportionRule(
            id=self.id,
            name=DisplayName(self.name),
            guidance=VisualText(self.guidance),
        )


class PaletteColorContract(ContractModel):
    id: Slug
    name: DisplayText
    color: Annotated[str, StringConstraints(pattern=r"^#[0-9A-F]{6}$")]
    role: PaletteRole

    def to_domain(self) -> PaletteColor:
        return PaletteColor(
            id=self.id,
            name=DisplayName(self.name),
            color=self.color,
            role=self.role,
        )


class MaterialRuleContract(ContractModel):
    id: Slug
    name: DisplayText
    finish: MaterialFinish
    guidance: VisualGuidanceText

    def to_domain(self) -> MaterialRule:
        return MaterialRule(
            id=self.id,
            name=DisplayName(self.name),
            finish=self.finish,
            guidance=VisualText(self.guidance),
        )


class DetailLevelRuleContract(ContractModel):
    level: DetailLevel
    guidance: VisualGuidanceText

    def to_domain(self) -> DetailLevelRule:
        return DetailLevelRule(level=self.level, guidance=VisualText(self.guidance))


class LevelOfDetailContract(ContractModel):
    default_level: DetailLevel
    levels: Annotated[tuple[DetailLevelRuleContract, ...], Field(min_length=1)]

    def to_domain(self) -> LevelOfDetail:
        return LevelOfDetail(
            default_level=self.default_level,
            levels=tuple(level.to_domain() for level in self.levels),
        )

    @model_validator(mode="after")
    def validate_levels(self) -> Self:
        self.to_domain()
        return self


class VisualBudgetContract(ContractModel):
    max_visual_jobs: PositiveVisualBudget
    max_generated_outputs: PositiveVisualBudget
    max_references_per_asset: PositiveVisualBudget

    def to_domain(self) -> VisualBudget:
        return VisualBudget(
            max_visual_jobs=self.max_visual_jobs,
            max_generated_outputs=self.max_generated_outputs,
            max_references_per_asset=self.max_references_per_asset,
        )


class VisualBibleContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["visual-bible"] = "visual-bible"
    id: Slug
    version: PositiveRevision
    name: DisplayText
    project_id: Slug
    shape_language: ShapeLanguageContract
    proportions: Annotated[tuple[ProportionRuleContract, ...], Field(min_length=1)]
    palette: Annotated[tuple[PaletteColorContract, ...], Field(min_length=1)]
    materials: Annotated[tuple[MaterialRuleContract, ...], Field(min_length=1)]
    lighting: LightingContract
    camera: CameraContract
    level_of_detail: LevelOfDetailContract
    budget: VisualBudgetContract
    prompt_constraints: Annotated[tuple[VisualGuidanceText, ...], Field(min_length=1)]
    negative_constraints: Annotated[tuple[VisualGuidanceText, ...], Field(min_length=1)]

    def to_domain(self) -> VisualBible:
        return VisualBible(
            id=VisualBibleId(self.id),
            version=VisualBibleVersion(self.version),
            name=DisplayName(self.name),
            project_id=ProjectId(self.project_id),
            shape_language=self.shape_language.to_domain(),
            proportions=tuple(rule.to_domain() for rule in self.proportions),
            palette=tuple(color.to_domain() for color in self.palette),
            materials=tuple(rule.to_domain() for rule in self.materials),
            lighting=self.lighting.to_domain(),
            camera=self.camera.to_domain(),
            level_of_detail=self.level_of_detail.to_domain(),
            budget=self.budget.to_domain(),
            prompt_constraints=tuple(VisualText(value) for value in self.prompt_constraints),
            negative_constraints=tuple(VisualText(value) for value in self.negative_constraints),
        )

    @model_validator(mode="after")
    def validate_visual_bible(self) -> Self:
        self.to_domain()
        return self
