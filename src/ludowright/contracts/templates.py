"""Published contracts for data-defined project initialization templates."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import ContractModel, PositiveRevision, RepositoryPathText, Slug
from ludowright.contracts.project import ProjectTargetContract
from ludowright.domain import ProjectDimension

TemplatePath = RepositoryPathText


class TemplateFileContract(ContractModel):
    """One required file and its initialization role."""

    path: TemplatePath
    role: Literal["manifest", "event-log", "dependency-graph", "state-store"]

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if self.path in {".", ".."} or any(part in {".", ".."} for part in self.path.split("/")):
            raise ValueError("template file paths cannot contain dot traversal")
        return self


class TemplateProjectDefaultsContract(ContractModel):
    """Project values selected by a template without Python-specific logic."""

    dimensions: ProjectDimension
    targets: tuple[ProjectTargetContract, ...] = Field(min_length=1)


class TemplateDefinitionContract(ContractModel):
    """Versioned, data-only declaration of a project starter template."""

    schema_version: Literal[1] = 1
    kind: Literal["template"] = "template"
    id: Slug
    version: PositiveRevision
    directories: tuple[TemplatePath, ...] = Field(min_length=1)
    files: tuple[TemplateFileContract, ...] = Field(min_length=1)
    project_defaults: TemplateProjectDefaultsContract

    @model_validator(mode="after")
    def validate_layout(self) -> Self:
        directories = set(self.directories)
        if len(directories) != len(self.directories):
            raise ValueError("template directories must be unique")
        if any(
            path in {".", ".."} or any(part in {".", ".."} for part in path.split("/"))
            for path in directories
        ):
            raise ValueError("template directory paths cannot contain dot traversal")

        file_paths = {file.path for file in self.files}
        if len(file_paths) != len(self.files):
            raise ValueError("template files must be unique")

        roles = [file.role for file in self.files]
        if len(set(roles)) != len(roles) or set(roles) != {
            "manifest",
            "event-log",
            "dependency-graph",
            "state-store",
        }:
            raise ValueError("template must declare each required initialization role once")

        for path in (*directories, *file_paths):
            if not any(
                path == directory or path.startswith(f"{directory}/") for directory in directories
            ):
                raise ValueError(f"template path is outside declared directories: {path}")
        return self
