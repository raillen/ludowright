"""Deterministic visual-job planning, batching, and readiness rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ludowright.domain.assets import (
    Asset,
    AssetComponent,
    AssetState,
    AssetVariant,
)
from ludowright.domain.capture_profiles import CaptureProfile
from ludowright.domain.dependencies import (
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    InvalidationMode,
)
from ludowright.domain.errors import InvalidVisualPlanError
from ludowright.domain.identifiers import (
    CaptureProfileId,
    JobId,
    ReferenceId,
    VisualBatchId,
    VisualBibleId,
    VisualPlanId,
)
from ludowright.domain.names import DisplayName
from ludowright.domain.references import ReferenceTarget
from ludowright.domain.versions import ProfileVersion, RevisionVersion, VisualBibleVersion
from ludowright.domain.visual_jobs import VisualJob

MAX_PLAN_JOBS = 100_000
MAX_PLAN_OUTPUTS = 1_000_000


class VisualPlanState(StrEnum):
    """Whether a visual plan can proceed to job execution."""

    READY = "ready"
    BLOCKED = "blocked"


class VisualPlanBlockerCode(StrEnum):
    """Stable reasons that prevent a plan from becoming ready."""

    INACTIVE_ASSET = "inactive-asset"
    MISSING_REQUIRED_ITEM = "missing-required-item"
    INACTIVE_ITEM = "inactive-item"
    MISSING_REQUIRED_OUTPUT = "missing-required-output"
    OUTPUT_LIMIT_EXCEEDED = "output-limit-exceeded"
    MISSING_REFERENCE = "missing-reference"
    REFERENCE_NOT_APPROVED = "reference-not-approved"
    REFERENCE_TARGET_MISMATCH = "reference-target-mismatch"
    STALE_DEPENDENCY = "stale-dependency"
    MISSING_DEPENDENCY_JOB = "missing-dependency-job"
    BUDGET_JOBS_EXCEEDED = "budget-jobs-exceeded"
    BUDGET_OUTPUTS_EXCEEDED = "budget-outputs-exceeded"
    BUDGET_REFERENCES_EXCEEDED = "budget-references-exceeded"


@dataclass(frozen=True, slots=True)
class VisualPlanTarget:
    """One asset and resolved profile supplied to the planner."""

    asset: Asset
    profile: CaptureProfile
    reference_ids: tuple[ReferenceId, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.asset, Asset):
            raise InvalidVisualPlanError("a visual plan target requires an asset")
        if not isinstance(self.profile, CaptureProfile):
            raise InvalidVisualPlanError("a visual plan target requires a capture profile")
        if self.profile.parent is not None:
            raise InvalidVisualPlanError("visual planning requires resolved capture profiles")
        if not isinstance(self.reference_ids, tuple):
            raise InvalidVisualPlanError("plan reference IDs must be an immutable tuple")
        if any(not isinstance(item, ReferenceId) for item in self.reference_ids):
            raise InvalidVisualPlanError("plan reference IDs must be typed")
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise InvalidVisualPlanError("plan reference IDs must be unique")


@dataclass(frozen=True, slots=True)
class VisualPlanBlocker:
    """One deterministic explanation for a blocked visual plan."""

    code: VisualPlanBlockerCode
    subject: DisplayName
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, VisualPlanBlockerCode):
            raise InvalidVisualPlanError("plan blocker code must be canonical")
        if not isinstance(self.subject, DisplayName):
            raise InvalidVisualPlanError("plan blocker subject must be canonical")
        if not isinstance(self.message, str) or not self.message.strip():
            raise InvalidVisualPlanError("plan blocker message cannot be empty")
        if len(self.message) > 4_000:
            raise InvalidVisualPlanError("plan blocker message cannot exceed 4000 characters")


@dataclass(frozen=True, slots=True)
class VisualJobDependency:
    """One ordering edge between two planned jobs."""

    source_job_id: JobId
    target_job_id: JobId
    relation: DependencyRelation = DependencyRelation.REQUIRES

    def __post_init__(self) -> None:
        if not isinstance(self.source_job_id, JobId):
            raise InvalidVisualPlanError("visual job dependency source must be typed")
        if not isinstance(self.target_job_id, JobId):
            raise InvalidVisualPlanError("visual job dependency target must be typed")
        if self.source_job_id == self.target_job_id:
            raise InvalidVisualPlanError("a visual job cannot depend on itself")
        if not isinstance(self.relation, DependencyRelation):
            raise InvalidVisualPlanError("visual job dependency relation must be canonical")


@dataclass(frozen=True, slots=True)
class VisualWorkloadEstimate:
    """Provider-neutral workload and cost units for one plan."""

    job_count: int
    output_count: int
    batch_count: int
    estimated_cost_units: int
    estimated_workload_units: int

    def __post_init__(self) -> None:
        values = (
            self.job_count,
            self.output_count,
            self.batch_count,
            self.estimated_cost_units,
            self.estimated_workload_units,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise InvalidVisualPlanError("visual workload values must be integers")
        if any(value < 0 for value in values):
            raise InvalidVisualPlanError("visual workload values cannot be negative")
        if self.job_count > MAX_PLAN_JOBS or self.output_count > MAX_PLAN_OUTPUTS:
            raise InvalidVisualPlanError("visual workload exceeds the published plan limits")
        if self.job_count == 0 and (self.output_count or self.batch_count):
            raise InvalidVisualPlanError("an empty plan cannot contain outputs or batches")


@dataclass(frozen=True, slots=True)
class VisualJobBatch:
    """Jobs sharing one exact capture-profile revision."""

    id: VisualBatchId
    profile_id: CaptureProfileId
    profile_version: ProfileVersion
    job_ids: tuple[JobId, ...]
    output_count: int
    estimated_cost_units: int
    estimated_workload_units: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, VisualBatchId):
            raise InvalidVisualPlanError("a visual batch requires a typed ID")
        if not isinstance(self.profile_id, CaptureProfileId):
            raise InvalidVisualPlanError("a visual batch requires a profile ID")
        if not isinstance(self.profile_version, ProfileVersion):
            raise InvalidVisualPlanError("a visual batch requires a profile version")
        if not isinstance(self.job_ids, tuple) or not self.job_ids:
            raise InvalidVisualPlanError("a visual batch requires jobs")
        if any(not isinstance(item, JobId) for item in self.job_ids):
            raise InvalidVisualPlanError("visual batch jobs must be typed")
        if len(self.job_ids) != len(set(self.job_ids)):
            raise InvalidVisualPlanError("visual batch jobs must be unique")
        values = (self.output_count, self.estimated_cost_units, self.estimated_workload_units)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise InvalidVisualPlanError("visual batch estimates must be integers")
        if any(value < 0 for value in values):
            raise InvalidVisualPlanError("visual batch estimates cannot be negative")


@dataclass(frozen=True, slots=True)
class VisualJobPlan:
    """Immutable plan of required jobs, order, batches, and readiness."""

    id: VisualPlanId
    name: DisplayName
    state: VisualPlanState
    dependency_graph_revision: RevisionVersion
    visual_bible_id: VisualBibleId | None
    visual_bible_version: VisualBibleVersion | None
    jobs: tuple[VisualJob, ...]
    ordered_job_ids: tuple[JobId, ...]
    dependencies: tuple[VisualJobDependency, ...]
    batches: tuple[VisualJobBatch, ...]
    workload: VisualWorkloadEstimate
    blockers: tuple[VisualPlanBlocker, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, VisualPlanId):
            raise InvalidVisualPlanError("a visual job plan requires a typed ID")
        if not isinstance(self.name, DisplayName):
            raise InvalidVisualPlanError("a visual job plan name must be canonical")
        if not isinstance(self.state, VisualPlanState):
            raise InvalidVisualPlanError("a visual job plan state must be canonical")
        if not isinstance(self.dependency_graph_revision, RevisionVersion):
            raise InvalidVisualPlanError("a visual job plan requires a graph revision")
        if (self.visual_bible_id is None) != (self.visual_bible_version is None):
            raise InvalidVisualPlanError("visual bible ID and version must be provided together")
        if self.visual_bible_id is not None and not isinstance(self.visual_bible_id, VisualBibleId):
            raise InvalidVisualPlanError("visual bible ID must be typed")
        if self.visual_bible_version is not None and not isinstance(
            self.visual_bible_version, VisualBibleVersion
        ):
            raise InvalidVisualPlanError("visual bible version must be typed")
        if not isinstance(self.jobs, tuple):
            raise InvalidVisualPlanError("visual plan jobs must be immutable")
        if any(not isinstance(job, VisualJob) for job in self.jobs):
            raise InvalidVisualPlanError("visual plan jobs must be canonical")
        job_ids = tuple(job.id for job in self.jobs)
        if len(job_ids) != len(set(job_ids)):
            raise InvalidVisualPlanError("visual plan job IDs must be unique")
        if job_ids != tuple(sorted(job_ids, key=lambda item: item.value)):
            raise InvalidVisualPlanError("visual plan jobs must be sorted")
        if not isinstance(self.ordered_job_ids, tuple):
            raise InvalidVisualPlanError("visual plan order must be immutable")
        if len(self.ordered_job_ids) != len(set(self.ordered_job_ids)) or set(
            self.ordered_job_ids
        ) != set(job_ids):
            raise InvalidVisualPlanError("visual plan order must contain every job exactly once")
        if not isinstance(self.dependencies, tuple):
            raise InvalidVisualPlanError("visual plan dependencies must be immutable")
        if any(not isinstance(item, VisualJobDependency) for item in self.dependencies):
            raise InvalidVisualPlanError("visual plan dependencies must be canonical")
        dependency_keys = tuple(
            (item.source_job_id.value, item.target_job_id.value, item.relation.value)
            for item in self.dependencies
        )
        if len(dependency_keys) != len(set(dependency_keys)):
            raise InvalidVisualPlanError("visual plan dependencies must be unique")
        known_job_ids = set(job_ids)
        if any(
            item.source_job_id not in known_job_ids or item.target_job_id not in known_job_ids
            for item in self.dependencies
        ):
            raise InvalidVisualPlanError("visual plan dependencies must reference planned jobs")
        if dependency_keys != tuple(sorted(dependency_keys)):
            raise InvalidVisualPlanError("visual plan dependencies must be sorted")
        _validate_order(job_ids, self.ordered_job_ids, self.dependencies)
        self._validate_batches(known_job_ids)
        if not isinstance(self.workload, VisualWorkloadEstimate):
            raise InvalidVisualPlanError("visual plan workload must be canonical")
        if self.workload.job_count != len(self.jobs):
            raise InvalidVisualPlanError("visual workload job count must match the plan")
        if self.workload.batch_count != len(self.batches):
            raise InvalidVisualPlanError("visual workload batch count must match the plan")
        if self.workload.output_count != sum(job.expected_output_count for job in self.jobs):
            raise InvalidVisualPlanError("visual workload output count must match the plan")
        if self.workload.estimated_cost_units != sum(
            batch.estimated_cost_units for batch in self.batches
        ):
            raise InvalidVisualPlanError("visual workload cost must match its batches")
        if self.workload.estimated_workload_units != sum(
            batch.estimated_workload_units for batch in self.batches
        ):
            raise InvalidVisualPlanError("visual workload estimate must match its batches")
        if not isinstance(self.blockers, tuple):
            raise InvalidVisualPlanError("visual plan blockers must be immutable")
        if any(not isinstance(item, VisualPlanBlocker) for item in self.blockers):
            raise InvalidVisualPlanError("visual plan blockers must be canonical")
        blocker_keys = tuple(
            (item.code.value, item.subject.value, item.message) for item in self.blockers
        )
        if len(blocker_keys) != len(set(blocker_keys)):
            raise InvalidVisualPlanError("visual plan blockers must be unique")
        if blocker_keys != tuple(sorted(blocker_keys)):
            raise InvalidVisualPlanError("visual plan blockers must be sorted")
        if self.state is VisualPlanState.READY and self.blockers:
            raise InvalidVisualPlanError("a ready visual plan cannot contain blockers")
        if self.state is VisualPlanState.BLOCKED and not self.blockers:
            raise InvalidVisualPlanError("a blocked visual plan requires blockers")

    def _validate_batches(self, known_job_ids: set[JobId]) -> None:
        if not isinstance(self.batches, tuple):
            raise InvalidVisualPlanError("visual plan batches must be immutable")
        if any(not isinstance(item, VisualJobBatch) for item in self.batches):
            raise InvalidVisualPlanError("visual plan batches must be canonical")
        batch_ids = tuple(item.id for item in self.batches)
        if len(batch_ids) != len(set(batch_ids)):
            raise InvalidVisualPlanError("visual plan batch IDs must be unique")
        assigned: set[JobId] = set()
        job_by_id = {job.id: job for job in self.jobs}
        for batch in self.batches:
            if any(job_id not in known_job_ids for job_id in batch.job_ids):
                raise InvalidVisualPlanError("visual batch must reference planned jobs")
            if assigned.intersection(batch.job_ids):
                raise InvalidVisualPlanError("each planned job must belong to one batch")
            if batch.job_ids != tuple(sorted(batch.job_ids, key=lambda item: item.value)):
                raise InvalidVisualPlanError("visual batch jobs must be sorted")
            assigned.update(batch.job_ids)
            expected_outputs = sum(
                job_by_id[job_id].expected_output_count for job_id in batch.job_ids
            )
            if batch.output_count != expected_outputs:
                raise InvalidVisualPlanError("visual batch output count must match its jobs")
        if assigned != known_job_ids:
            raise InvalidVisualPlanError("every planned job must belong to a batch")
        expected_order = tuple(sorted(batch_ids, key=lambda item: item.value))
        if batch_ids != expected_order:
            raise InvalidVisualPlanError("visual plan batches must be sorted")


def estimate_profile_workload(
    profile: CaptureProfile,
    output_count: int,
) -> tuple[int, int]:
    """Return provider-neutral cost and pixel-weighted workload units."""
    if not isinstance(profile, CaptureProfile) or profile.validation is None:
        raise InvalidVisualPlanError("workload estimation requires a resolved profile")
    if isinstance(output_count, bool) or not isinstance(output_count, int) or output_count < 1:
        raise InvalidVisualPlanError("workload estimation requires positive outputs")
    pixels = profile.validation.dimensions.width * profile.validation.dimensions.height
    megapixel_units = max(1, (pixels + 1_048_575) // 1_048_576)
    return output_count, output_count * megapixel_units


def _validate_order(
    job_ids: tuple[JobId, ...],
    ordered_job_ids: tuple[JobId, ...],
    dependencies: tuple[VisualJobDependency, ...],
) -> None:
    positions = {job_id: index for index, job_id in enumerate(ordered_job_ids)}
    if set(positions) != set(job_ids):
        raise InvalidVisualPlanError("visual plan order must contain known jobs")
    if any(positions[item.source_job_id] >= positions[item.target_job_id] for item in dependencies):
        raise InvalidVisualPlanError("visual plan order must respect dependencies")
    graph = DependencyGraph.empty()
    for job_id in sorted(job_ids, key=lambda item: item.value):
        graph = graph.add_node(
            DependencyNode(
                key=DependencyKey(DependencyNodeKind.VISUAL_JOB, job_id.value),
                revision=RevisionVersion(1),
            )
        )
    for dependency in dependencies:
        graph = graph.connect(
            DependencyKey(DependencyNodeKind.VISUAL_JOB, dependency.source_job_id.value),
            DependencyKey(DependencyNodeKind.VISUAL_JOB, dependency.target_job_id.value),
            dependency.relation,
            InvalidationMode.NONE,
        )
    expected = tuple(JobId(key.id) for key in graph.topological_order())
    if expected != ordered_job_ids:
        raise InvalidVisualPlanError("visual plan order must be deterministic")


def target_for_asset(asset: Asset) -> ReferenceTarget:
    """Return the root target used for a complete asset capture."""
    if not isinstance(asset, Asset):
        raise TypeError("asset target derivation requires Asset")
    return ReferenceTarget(asset.id)


def target_for_component(asset: Asset, component: AssetComponent) -> ReferenceTarget:
    """Return a typed target for one asset component."""
    if not isinstance(asset, Asset) or not isinstance(component, AssetComponent):
        raise TypeError("component target derivation requires canonical asset values")
    return ReferenceTarget(asset.id, component_id=component.id)


def target_for_variant(asset: Asset, variant: AssetVariant) -> ReferenceTarget:
    """Return a typed target for one asset variant."""
    if not isinstance(asset, Asset) or not isinstance(variant, AssetVariant):
        raise TypeError("variant target derivation requires canonical asset values")
    return ReferenceTarget(asset.id, variant_id=variant.id)


def target_for_state(asset: Asset, state: AssetState) -> ReferenceTarget:
    """Return a typed target for one asset state."""
    if not isinstance(asset, Asset) or not isinstance(state, AssetState):
        raise TypeError("state target derivation requires canonical asset values")
    return ReferenceTarget(asset.id, state_id=state.id)


def dependency_key_for_target(target: ReferenceTarget) -> DependencyKey:
    """Map a visual target to the most specific graph key available to callers."""
    if target.component_id is not None:
        return DependencyKey(DependencyNodeKind.COMPONENT, target.component_id.value)
    if target.variant_id is not None:
        return DependencyKey(DependencyNodeKind.VARIANT, target.variant_id.value)
    if target.state_id is not None:
        return DependencyKey(DependencyNodeKind.ASSET_STATE, target.state_id.value)
    return DependencyKey(DependencyNodeKind.ASSET, target.asset_id.value)


__all__ = [
    "MAX_PLAN_JOBS",
    "MAX_PLAN_OUTPUTS",
    "VisualJobBatch",
    "VisualJobDependency",
    "VisualJobPlan",
    "VisualPlanBlocker",
    "VisualPlanBlockerCode",
    "VisualPlanState",
    "VisualPlanTarget",
    "VisualWorkloadEstimate",
    "dependency_key_for_target",
    "estimate_profile_workload",
    "target_for_asset",
    "target_for_component",
    "target_for_state",
    "target_for_variant",
]
