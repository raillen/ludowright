"""Published contracts for deterministic documentation audits."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.atlas import (
    AtlasBrokenLinkContract,
    AtlasDocumentPath,
)
from ludowright.contracts.common import ContractModel, DisplayText, ReviewText, Sha256Text, Slug

AuditPhrase = Annotated[
    str, StringConstraints(min_length=1, max_length=256, pattern=r"^\S(?:.*\S)?$")
]


class DocumentationTopicContract(ContractModel):
    """One required documentation topic and its canonical source."""

    id: Slug
    title: DisplayText
    canonical_source: AtlasDocumentPath


class DocumentationPhraseContract(ContractModel):
    """One exact, case-insensitive phrase used by a contradiction rule."""

    path: AtlasDocumentPath
    phrase: AuditPhrase


class DocumentationContradictionRuleContract(ContractModel):
    """Two phrases that must not both be present in their named documents."""

    id: Slug
    title: DisplayText
    left: DocumentationPhraseContract
    right: DocumentationPhraseContract


class DocumentationDeprecatedReferenceContract(ContractModel):
    """A stale documentation path and its replacement canonical source."""

    path: AtlasDocumentPath
    replacement: AtlasDocumentPath

    @model_validator(mode="after")
    def validate_distinct_paths(self) -> Self:
        if self.path == self.replacement:
            raise ValueError("deprecated reference path must differ from its replacement")
        return self


class DocumentationAuditPolicyContract(ContractModel):
    """Versioned, repository-local policy for the documentation audit."""

    schema_version: Literal[1] = 1
    kind: Literal["documentation-audit-policy"] = "documentation-audit-policy"
    version: int = Field(ge=1, le=2_147_483_647)
    topics: Annotated[tuple[DocumentationTopicContract, ...], Field(max_length=1_000)] = ()
    contradictions: Annotated[
        tuple[DocumentationContradictionRuleContract, ...], Field(max_length=1_000)
    ] = ()
    deprecated_references: Annotated[
        tuple[DocumentationDeprecatedReferenceContract, ...], Field(max_length=1_000)
    ] = ()

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        ids = tuple(topic.id for topic in self.topics)
        if len(ids) != len(set(ids)):
            raise ValueError("documentation audit topic IDs must be unique")
        topic_sources = tuple(topic.canonical_source for topic in self.topics)
        if len(topic_sources) != len(set(topic_sources)):
            raise ValueError("documentation audit topic sources must be unique")
        rule_ids = tuple(rule.id for rule in self.contradictions)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("documentation contradiction rule IDs must be unique")
        deprecated_paths = tuple(item.path for item in self.deprecated_references)
        if len(deprecated_paths) != len(set(deprecated_paths)):
            raise ValueError("deprecated documentation paths must be unique")
        if tuple(sorted(ids)) != ids:
            raise ValueError("documentation audit topics must be sorted by ID")
        if tuple(sorted(rule_ids)) != rule_ids:
            raise ValueError("documentation contradiction rules must be sorted by ID")
        if tuple(sorted(deprecated_paths)) != deprecated_paths:
            raise ValueError("deprecated documentation paths must be sorted")
        return self


DocumentationFindingCode = Literal[
    "missing-canonical-topic",
    "duplicate-canonical-source",
    "contradictory-claim",
    "stale-reference",
]


class DocumentationFindingContract(ContractModel):
    """One deterministic audit finding requiring review."""

    code: DocumentationFindingCode
    subject: str = Field(min_length=1, max_length=1_024)
    message: ReviewText
    related_paths: Annotated[tuple[AtlasDocumentPath, ...], Field(max_length=100)] = ()
    replacement: AtlasDocumentPath | None = None


class DocumentationAuditReportContract(ContractModel):
    """ATLAS integrity plus policy findings for one documentation tree."""

    schema_version: Literal[1] = 1
    kind: Literal["documentation-audit"] = "documentation-audit"
    version: int = Field(ge=1, le=2_147_483_647)
    metadata_digest: Sha256Text
    policy_digest: Sha256Text
    atlas_valid: bool
    broken_links: Annotated[tuple[AtlasBrokenLinkContract, ...], Field(max_length=100_000)]
    orphan_documents: Annotated[tuple[AtlasDocumentPath, ...], Field(max_length=10_000)]
    findings: Annotated[tuple[DocumentationFindingContract, ...], Field(max_length=100_000)]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if tuple(sorted(self.orphan_documents)) != self.orphan_documents:
            raise ValueError("documentation audit orphan documents must be sorted")
        if tuple(sorted(self.findings, key=_finding_sort_key)) != self.findings:
            raise ValueError("documentation audit findings must be sorted")
        return self

    @property
    def valid(self) -> bool:
        """Return whether ATLAS and all policy checks passed."""
        return self.atlas_valid and not self.findings


def _finding_sort_key(finding: DocumentationFindingContract) -> tuple[str, str, tuple[str, ...]]:
    return finding.code, finding.subject, finding.related_paths
