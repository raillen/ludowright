"""Canonical registry for published LudoWright JSON Schemas."""

from __future__ import annotations

from dataclasses import dataclass

from ludowright.contracts.assets import AssetContract
from ludowright.contracts.atlas import AtlasMetadataContract, AtlasReportContract
from ludowright.contracts.capture import CaptureProfileContract
from ludowright.contracts.cli import CliResponseContract
from ludowright.contracts.common import ContractModel
from ludowright.contracts.dependencies import DependencyGraphContract
from ludowright.contracts.document_templates import DocumentTemplateManifestContract
from ludowright.contracts.governance import ApprovalContract, DecisionContract
from ludowright.contracts.interviews import (
    InterviewInteractionContract,
    InterviewSessionContract,
    QuestionnaireContract,
)
from ludowright.contracts.migrations import MigrationReceiptContract
from ludowright.contracts.project import ProjectContract
from ludowright.contracts.visual import (
    GenerationReceiptContract,
    VisualJobContract,
    VisualReferenceContract,
    VisualReviewContract,
)

SCHEMA_VERSION = 1
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE_URI = "https://schemas.ludowright.dev/v1"


@dataclass(frozen=True, slots=True)
class ContractDefinition:
    """One stable public contract and its publication metadata."""

    name: str
    filename: str
    title: str
    model: type[ContractModel]

    @property
    def schema_id(self) -> str:
        return f"{SCHEMA_BASE_URI}/{self.filename}"


CONTRACTS: tuple[ContractDefinition, ...] = (
    ContractDefinition("project", "project.schema.json", "LudoWright Project", ProjectContract),
    ContractDefinition("decision", "decision.schema.json", "LudoWright Decision", DecisionContract),
    ContractDefinition("approval", "approval.schema.json", "LudoWright Approval", ApprovalContract),
    ContractDefinition("asset", "asset.schema.json", "LudoWright Asset", AssetContract),
    ContractDefinition(
        "visual-reference",
        "visual-reference.schema.json",
        "LudoWright Visual Reference",
        VisualReferenceContract,
    ),
    ContractDefinition(
        "visual-job",
        "visual-job.schema.json",
        "LudoWright Visual Job",
        VisualJobContract,
    ),
    ContractDefinition(
        "generation-receipt",
        "generation-receipt.schema.json",
        "LudoWright Generation Receipt",
        GenerationReceiptContract,
    ),
    ContractDefinition(
        "visual-review",
        "visual-review.schema.json",
        "LudoWright Visual Review",
        VisualReviewContract,
    ),
    ContractDefinition(
        "capture-profile",
        "capture-profile.schema.json",
        "LudoWright Capture Profile",
        CaptureProfileContract,
    ),
    ContractDefinition(
        "migration-receipt",
        "migration-receipt.schema.json",
        "LudoWright Migration Receipt",
        MigrationReceiptContract,
    ),
    ContractDefinition(
        "dependency-graph",
        "dependency-graph.schema.json",
        "LudoWright Dependency Graph",
        DependencyGraphContract,
    ),
    ContractDefinition(
        "document-template",
        "document-template.schema.json",
        "LudoWright Document Template",
        DocumentTemplateManifestContract,
    ),
    ContractDefinition(
        "atlas-metadata",
        "atlas-metadata.schema.json",
        "LudoWright Atlas Metadata",
        AtlasMetadataContract,
    ),
    ContractDefinition(
        "atlas-report",
        "atlas-report.schema.json",
        "LudoWright Atlas Report",
        AtlasReportContract,
    ),
    ContractDefinition(
        "cli-response",
        "cli-response.schema.json",
        "LudoWright CLI Response",
        CliResponseContract,
    ),
    ContractDefinition(
        "interview-questionnaire",
        "interview-questionnaire.schema.json",
        "LudoWright Interview Questionnaire",
        QuestionnaireContract,
    ),
    ContractDefinition(
        "interview-session",
        "interview-session.schema.json",
        "LudoWright Interview Session",
        InterviewSessionContract,
    ),
    ContractDefinition(
        "interview-interaction",
        "interview-interaction.schema.json",
        "LudoWright Interview Interaction",
        InterviewInteractionContract,
    ),
)

CONTRACT_BY_NAME = {definition.name: definition for definition in CONTRACTS}
