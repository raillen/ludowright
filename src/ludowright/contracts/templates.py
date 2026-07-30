"""Contracts for versioned, data-driven project templates."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import ContractModel, PositiveRevision, Slug
from ludowright.contracts.project import ProjectTargetContract
from ludowright.domain import ProjectDimension

TemplatePath = Annotated[
    str,
    Field(
        min_length=1,
        max_length=1_024,
        pattern=r"^[a-z0-9._-]+(?:/[a-z0-9._-]+)*$",
    ),
]


class TemplateFileContract(ContractModel):
    """One file declared by a template without embedding generation logic."""

    path: TemplatePath
    role: Literal["manifest", "event-log", "dependency-graph", "state-store"]

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if any(segment in {".", ".."} for segment in self.path.split("/")):
            raise ValueError("template paths cannot contain dot traversal")
        return self


class TemplateProjectDefaultsContract(ContractModel):
    """Default project facts selected by a template."""

    dimensions: ProjectDimension
    targets: Annotated[tuple[ProjectTargetContract, ...], Field(min_length=1)]


class TemplateDefinitionContract(ContractModel):
    """Versioned data consumed by the generic project initializer."""

    schema_version: Literal[1] = 1
    kind: Literal["template"] = "template"
    id: Slug
    version: PositiveRevision
    directories: Annotated[tuple[TemplatePath, ...], Field(min_length=1)]
    files: Annotated[tuple[TemplateFileContract, ...], Field(min_length=1)]
    project_defaults: TemplateProjectDefaultsContract

    @model_validator(mode="after")
    def validate_layout(self) -> Self:
        directories = set(self.directories)
        files = {item.path for item in self.files}
        if len(directories) != len(self.directories):
            raise ValueError("template directories must be unique")
        if len(files) != len(self.files):
            raise ValueError("template files must be unique")
        roles = {item.role for item in self.files}
        if len(roles) != len(self.files):
            raise ValueError("template file roles must be unique")
        if roles != {"manifest", "event-log", "dependency-graph", "state-store"}:
            raise ValueError("template must declare every initialization file role")
        if not all(
            any(path == directory or path.startswith(f"{directory}/") for directory in directories)
            for path in files
        ):
            raise ValueError("every template file must belong to a declared directory")
        return self
