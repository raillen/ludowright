"""Versioned project serialization contract."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    EngineVersionText,
    PositiveRevision,
    Slug,
)
from ludowright.domain import (
    DisplayName,
    EngineSpec,
    PlatformFamily,
    Project,
    ProjectDimension,
    ProjectId,
    ProjectIdentity,
    ProjectLifecycle,
    ProjectStage,
    ProjectTarget,
)


class ProjectTargetContract(ContractModel):
    platform: PlatformFamily
    label: DisplayText | None = None

    def to_domain(self) -> ProjectTarget:
        return ProjectTarget(
            platform=self.platform,
            label=DisplayName(self.label) if self.label is not None else None,
        )

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        self.to_domain()
        return self


class EngineContract(ContractModel):
    name: DisplayText
    version: EngineVersionText | None = None

    def to_domain(self) -> EngineSpec:
        return EngineSpec(name=DisplayName(self.name), version=self.version)

    @model_validator(mode="after")
    def validate_engine(self) -> Self:
        self.to_domain()
        return self


class TemplateSelectionContract(ContractModel):
    """Template provenance recorded in a generated project manifest."""

    id: Slug
    version: PositiveRevision


class ProjectContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["project"] = "project"
    id: Slug
    name: DisplayText
    codename: DisplayText | None = None
    dimensions: ProjectDimension
    targets: Annotated[tuple[ProjectTargetContract, ...], Field(min_length=1)]
    stage: ProjectStage = ProjectStage.CONCEPT
    lifecycle: ProjectLifecycle = ProjectLifecycle.ACTIVE
    engine: EngineContract | None = None
    template: TemplateSelectionContract | None = None

    def to_domain(self) -> Project:
        return Project(
            identity=ProjectIdentity(
                id=ProjectId(self.id),
                name=DisplayName(self.name),
                codename=(DisplayName(self.codename) if self.codename is not None else None),
            ),
            dimensions=self.dimensions,
            targets=frozenset(target.to_domain() for target in self.targets),
            stage=self.stage,
            lifecycle=self.lifecycle,
            engine=self.engine.to_domain() if self.engine is not None else None,
        )

    @model_validator(mode="after")
    def validate_project(self) -> Self:
        self.to_domain()
        return self
