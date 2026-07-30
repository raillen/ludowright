"""Published contracts for deterministic documentation atlas generation."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    Sha256Text,
    Slug,
)

AtlasDocumentPath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=1_024,
        pattern=r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$",
    ),
]
LinkTarget = Annotated[str, StringConstraints(min_length=1, max_length=2_048)]
LinkFragment = Annotated[str, StringConstraints(min_length=1, max_length=256)]

_DOCUMENT_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_RESERVED_WINDOWS_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class AtlasDocumentMetadataContract(ContractModel):
    """Canonical metadata for one Markdown document in the atlas."""

    path: AtlasDocumentPath
    title: DisplayText
    section: Slug
    canonical_source: AtlasDocumentPath

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        _validate_document_path(self.path)
        _validate_document_path(self.canonical_source)
        return self


class AtlasMetadataContract(ContractModel):
    """Versioned sidecar describing canonical documentation sources."""

    schema_version: Literal[1] = 1
    kind: Literal["atlas-metadata"] = "atlas-metadata"
    version: PositiveRevision
    documents: Annotated[
        tuple[AtlasDocumentMetadataContract, ...],
        Field(min_length=1, max_length=10_000),
    ]

    @model_validator(mode="after")
    def validate_documents(self) -> Self:
        paths = tuple(document.path for document in self.documents)
        if len(paths) != len(set(paths)):
            raise ValueError("atlas metadata document paths must be unique")
        return self


class AtlasLinkContract(ContractModel):
    """One relative Markdown link discovered while building the atlas."""

    source: AtlasDocumentPath
    target: LinkTarget
    fragment: LinkFragment | None = None


class AtlasBrokenLinkContract(ContractModel):
    """One link or canonical-source reference that cannot be resolved."""

    source: AtlasDocumentPath
    target: LinkTarget
    reason: Literal[
        "missing-file",
        "missing-anchor",
        "unsafe-path",
        "missing-canonical-source",
    ]
    fragment: LinkFragment | None = None


class AtlasReportContract(ContractModel):
    """Deterministic document index and integrity report."""

    schema_version: Literal[1] = 1
    kind: Literal["atlas-report"] = "atlas-report"
    version: PositiveRevision
    metadata_digest: Sha256Text
    documents: Annotated[tuple[AtlasDocumentMetadataContract, ...], Field(max_length=10_000)]
    links: Annotated[tuple[AtlasLinkContract, ...], Field(max_length=100_000)]
    broken_links: Annotated[tuple[AtlasBrokenLinkContract, ...], Field(max_length=100_000)]
    orphan_documents: Annotated[tuple[AtlasDocumentPath, ...], Field(max_length=10_000)]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        paths = tuple(document.path for document in self.documents)
        if len(paths) != len(set(paths)):
            raise ValueError("atlas report document paths must be unique")
        if tuple(sorted(self.orphan_documents)) != self.orphan_documents:
            raise ValueError("atlas orphan documents must be sorted")
        return self


def _validate_document_path(value: str) -> None:
    if "\\" in value or value.startswith("/"):
        raise ValueError("atlas document paths must be relative POSIX paths")
    for segment in value.split("/"):
        if (
            not _DOCUMENT_SEGMENT_PATTERN.fullmatch(segment)
            or segment in {".", ".."}
            or segment.casefold().split(".", maxsplit=1)[0] in _RESERVED_WINDOWS_NAMES
        ):
            raise ValueError("atlas document paths contain an unsafe segment")
