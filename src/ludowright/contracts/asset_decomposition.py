"""Published contracts for asset decomposition and guided recommendations."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.assets import (
    AssetComponentContract,
    AssetContract,
    AssetStateContract,
    AssetVariantContract,
)
from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    RepositoryPathText,
    ReviewText,
    Slug,
)
from ludowright.domain import AssetFamily, CaptureSubjectMode, InvalidationMode

DecompositionState = Literal["current", "planned", "updated", "invalid"]
CorrectionSeverity = Literal["error", "warning", "info"]
CorrectionCode = Literal[
    "missing-input",
    "invalid-decomposition",
    "unknown-dependency",
    "self-dependency",
    "duplicate-dependency",
    "input-asset-mismatch",
    "graph-reconciliation-required",
    "profile-review",
    "required-item-blocks-completion",
]
RecommendationState = Literal["recommended", "needs-review", "unavailable"]
_SUBJECT_MODE_ORDER = {
    CaptureSubjectMode.ASSET: 0,
    CaptureSubjectMode.COMPONENTS: 1,
    CaptureSubjectMode.VARIANTS: 2,
    CaptureSubjectMode.STATES: 3,
}


class AssetDependencyContract(ContractModel):
    """One explicit prerequisite asset for the decomposed aggregate."""

    depends_on: Slug
    invalidation_mode: InvalidationMode = InvalidationMode.STALE


class AssetDecompositionContract(ContractModel):
    """Complete replacement payload for one asset's decomposition."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-decomposition"] = "asset-decomposition"
    asset_id: Slug
    components: tuple[AssetComponentContract, ...] = ()
    variants: tuple[AssetVariantContract, ...] = ()
    states: tuple[AssetStateContract, ...] = ()
    dependencies: Annotated[tuple[AssetDependencyContract, ...], Field(max_length=256)] = ()

    @model_validator(mode="after")
    def validate_order_and_dependencies(self) -> Self:
        component_ids = tuple(item.id for item in self.components)
        variant_ids = tuple(item.id for item in self.variants)
        state_ids = tuple(item.id for item in self.states)
        dependency_ids = tuple(item.depends_on for item in self.dependencies)
        if component_ids != tuple(sorted(component_ids)):
            raise ValueError("asset decomposition components must be sorted")
        if variant_ids != tuple(sorted(variant_ids)):
            raise ValueError("asset decomposition variants must be sorted")
        if state_ids != tuple(sorted(state_ids)):
            raise ValueError("asset decomposition states must be sorted")
        if dependency_ids != tuple(sorted(dependency_ids)):
            raise ValueError("asset decomposition dependencies must be sorted")
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("asset decomposition dependencies must be unique")
        if self.asset_id in dependency_ids:
            raise ValueError("an asset cannot depend on itself")
        return self


class CaptureProfileRecommendationContract(ContractModel):
    """A deterministic, non-executable capture-profile recommendation."""

    state: RecommendationState
    profile_id: Slug | None = None
    profile_version: PositiveRevision | None = None
    family: AssetFamily
    subtype: Slug | None = None
    subject_modes: tuple[CaptureSubjectMode, ...] = ()
    required_item_ids: Annotated[tuple[Slug, ...], Field(max_length=512)] = ()
    reason: ReviewText

    @model_validator(mode="after")
    def validate_recommendation(self) -> Self:
        if self.state == "recommended" and (
            self.profile_id is None or self.profile_version is None
        ):
            raise ValueError("a recommended profile requires an ID and version")
        if (
            tuple(sorted(self.subject_modes, key=_SUBJECT_MODE_ORDER.__getitem__))
            != self.subject_modes
        ):
            raise ValueError("capture profile subject modes must be sorted")
        if tuple(sorted(self.required_item_ids)) != self.required_item_ids:
            raise ValueError("capture profile required item IDs must be sorted")
        if len(self.required_item_ids) != len(set(self.required_item_ids)):
            raise ValueError("capture profile required item IDs must be unique")
        return self


class AssetDecompositionCorrectionContract(ContractModel):
    """One actionable validation or review message for a decomposition."""

    code: CorrectionCode
    severity: CorrectionSeverity
    subject: DisplayText
    message: ReviewText
    suggestion: ReviewText


class AssetDecompositionReportContract(ContractModel):
    """Stable result returned by the decomposition command."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-decomposition-report"] = "asset-decomposition-report"
    state: DecompositionState
    dry_run: bool
    asset_id: Slug
    asset: AssetContract
    decomposition: AssetDecompositionContract
    corrections: Annotated[
        tuple[AssetDecompositionCorrectionContract, ...], Field(max_length=256)
    ] = ()
    capture_profile: CaptureProfileRecommendationContract
    registry_path: RepositoryPathText
    registry_version: PositiveRevision
    dependency_graph_path: RepositoryPathText
    dependency_graph_revision: PositiveRevision
    valid: bool = True

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.asset.id != self.asset_id:
            raise ValueError("decomposition report asset ID must match its asset")
        if self.decomposition.asset_id != self.asset_id:
            raise ValueError("decomposition report asset ID must match its payload")
        correction_keys = tuple(
            (correction.severity, correction.code, correction.subject)
            for correction in self.corrections
        )
        if correction_keys != tuple(sorted(correction_keys)):
            raise ValueError("decomposition report corrections must be sorted")
        return self


class AssetDecompositionRecommendationRuleContract(ContractModel):
    """Packaged data rule used to derive a capture-profile recommendation."""

    family: AssetFamily
    subtype: Slug | None = None
    profile_id: Slug
    profile_version: PositiveRevision
    subject_modes: tuple[CaptureSubjectMode, ...]
    rationale: ReviewText

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        if not self.subject_modes:
            raise ValueError("a recommendation rule requires at least one subject mode")
        if len(self.subject_modes) != len(set(self.subject_modes)):
            raise ValueError("recommendation subject modes must be unique")
        if (
            tuple(sorted(self.subject_modes, key=_SUBJECT_MODE_ORDER.__getitem__))
            != self.subject_modes
        ):
            raise ValueError("recommendation subject modes must be sorted")
        return self


class AssetDecompositionRecommendationCatalogContract(ContractModel):
    """Versioned packaged recommendation data, not a persisted project file."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-decomposition-recommendations"] = "asset-decomposition-recommendations"
    rules: tuple[AssetDecompositionRecommendationRuleContract, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        rule_keys = tuple((rule.family.value, rule.subtype or "") for rule in self.rules)
        if rule_keys != tuple(sorted(rule_keys)):
            raise ValueError("recommendation catalog rules must be sorted")
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("recommendation catalog rules must be unique")
        return self
