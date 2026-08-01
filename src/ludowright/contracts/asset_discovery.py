"""Published contracts for deterministic asset discovery from Markdown."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    ReviewText,
    Slug,
)
from ludowright.domain import AssetFamily, AssetPriority

RepositoryPathText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=1_024,
        pattern=r"^[a-z0-9._-]+(?:/[a-z0-9._-]+)*$",
    ),
]
DiscoverySubject = Annotated[str, StringConstraints(min_length=1, max_length=1_024)]
AssetDiscoveryState = Literal["empty", "pending", "ambiguous", "invalid", "planned", "confirmed"]
AssetDiscoveryIssueCode = Literal[
    "invalid-declaration",
    "duplicate-candidate",
    "duplicate-asset-id",
    "existing-asset-id",
    "candidate-not-found",
    "confirmation-blocked",
]


class AssetDiscoveryCandidateContract(ContractModel):
    """One explicit candidate extracted from a project Markdown document."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-discovery-candidate"] = "asset-discovery-candidate"
    candidate_id: Slug
    asset_id: Slug
    name: DisplayText
    family: AssetFamily
    subtype: Slug | None = None
    priority: AssetPriority = AssetPriority.NORMAL
    source_path: RepositoryPathText
    source_line: PositiveRevision
    evidence: ReviewText
    state: Literal["pending", "ambiguous", "confirmed", "rejected"] = "pending"


class AssetDiscoveryIssueContract(ContractModel):
    """One deterministic extraction or confirmation issue."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-discovery-issue"] = "asset-discovery-issue"
    code: AssetDiscoveryIssueCode
    subject: DiscoverySubject
    message: ReviewText
    candidate_ids: Annotated[tuple[Slug, ...], Field(max_length=256)] = ()
    source_paths: Annotated[tuple[RepositoryPathText, ...], Field(max_length=256)] = ()

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if tuple(sorted(self.candidate_ids)) != self.candidate_ids:
            raise ValueError("asset discovery candidate IDs must be sorted")
        if tuple(sorted(self.source_paths)) != self.source_paths:
            raise ValueError("asset discovery source paths must be sorted")
        return self


class AssetDiscoveryReportContract(ContractModel):
    """Stable report returned by the discovery and confirmation workflow."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-discovery-report"] = "asset-discovery-report"
    state: AssetDiscoveryState
    dry_run: bool
    source_paths: Annotated[tuple[RepositoryPathText, ...], Field(max_length=10_000)] = ()
    candidates: Annotated[
        tuple[AssetDiscoveryCandidateContract, ...], Field(max_length=10_000)
    ] = ()
    issues: Annotated[tuple[AssetDiscoveryIssueContract, ...], Field(max_length=10_000)] = ()
    confirmed_asset_ids: Annotated[tuple[Slug, ...], Field(max_length=256)] = ()
    registry_path: RepositoryPathText
    registry_version: PositiveRevision
    valid: bool = True

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if tuple(sorted(self.source_paths)) != self.source_paths:
            raise ValueError("asset discovery source paths must be sorted")
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("asset discovery candidate IDs must be unique")
        if tuple(sorted(candidate_ids)) != candidate_ids:
            raise ValueError("asset discovery candidates must be sorted")
        if tuple(sorted(self.confirmed_asset_ids)) != self.confirmed_asset_ids:
            raise ValueError("confirmed asset IDs must be sorted")
        return self
