"""Published contracts for incremental document refresh requests and state."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import ContractModel, Sha256Text, Slug
from ludowright.contracts.document_templates import TemplatePath

DocumentContext = dict[str, object]


class DocumentSourceHashContract(ContractModel):
    """One deterministic source identity consumed by a document."""

    source_id: Slug
    digest: Sha256Text


class DocumentManualSectionContract(ContractModel):
    """Metadata for one manual section preserved across generated refreshes."""

    id: Slug
    approved: bool
    digest: Sha256Text


class DocumentRefreshRequestContract(ContractModel):
    """Canonical input used to render one document incrementally."""

    schema_version: Literal[1] = 1
    kind: Literal["document-refresh-request"] = "document-refresh-request"
    document_id: Slug
    template_id: Slug
    entrypoint: TemplatePath | None = None
    context: DocumentContext
    source_hashes: Annotated[
        tuple[DocumentSourceHashContract, ...],
        Field(max_length=1_024),
    ] = ()

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        _validate_context(self.context)
        _validate_unique_sorted_sources(self.source_hashes)
        return self


class DocumentRefreshStateContract(ContractModel):
    """Canonical state observed after a document refresh."""

    schema_version: Literal[1] = 1
    kind: Literal["document-refresh"] = "document-refresh"
    document_id: Slug
    template_id: Slug
    template_version: Annotated[int, Field(ge=1, le=2_147_483_647)]
    entrypoint: TemplatePath
    source_hashes: Annotated[
        tuple[DocumentSourceHashContract, ...],
        Field(max_length=1_024),
    ] = ()
    generated_digest: Sha256Text
    output_digest: Sha256Text
    status: Literal["current", "stale"] = "current"
    manual_sections: Annotated[
        tuple[DocumentManualSectionContract, ...],
        Field(max_length=1_024),
    ] = ()

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        _validate_unique_sorted_sources(self.source_hashes)
        manual_ids = tuple(section.id for section in self.manual_sections)
        if len(manual_ids) != len(set(manual_ids)):
            raise ValueError("document manual section IDs must be unique")
        if tuple(sorted(manual_ids)) != manual_ids:
            raise ValueError("document manual sections must be sorted")
        return self


def _validate_unique_sorted_sources(
    sources: tuple[DocumentSourceHashContract, ...],
) -> None:
    source_ids = tuple(source.source_id for source in sources)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("document source IDs must be unique")
    if tuple(sorted(source_ids)) != source_ids:
        raise ValueError("document source hashes must be sorted")


def _validate_context(value: object, *, depth: int = 0, nodes: list[int] | None = None) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > 100_000:
        raise ValueError("document refresh context exceeds the node limit")
    if depth > 64:
        raise ValueError("document refresh context exceeds the nesting limit")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("document refresh context cannot contain non-finite numbers")
        return
    if isinstance(value, list):
        for item in value:
            _validate_context(item, depth=depth + 1, nodes=nodes)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("document refresh context keys must be strings")
            _validate_context(item, depth=depth + 1, nodes=nodes)
        return
    raise ValueError(
        f"document refresh context values must be JSON-compatible, not {type(value).__name__}"
    )
