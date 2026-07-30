"""Versioned contracts for data-driven document template manifests."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import ContractModel, PositiveRevision, Slug

TemplatePath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=1_024,
        pattern=r"^[a-z0-9._-]+(?:/[a-z0-9._-]+)*$",
    ),
]


class DocumentTemplateManifestContract(ContractModel):
    """Metadata needed to load one deterministic Jinja document template."""

    schema_version: Literal[1] = 1
    kind: Literal["document-template"] = "document-template"
    id: Slug
    version: PositiveRevision
    entrypoint: TemplatePath
    files: Annotated[tuple[TemplatePath, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_files(self) -> Self:
        paths = tuple(self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("document template files must be unique")
        if self.entrypoint not in paths:
            raise ValueError("document template entrypoint must be declared in files")
        if any(_has_unsafe_segment(path) for path in paths):
            raise ValueError("document template paths cannot contain dot traversal")
        return self


def _has_unsafe_segment(path: str) -> bool:
    return any(segment in {".", ".."} for segment in path.split("/"))
