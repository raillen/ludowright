"""Versioned contract for deterministic visual-job plans."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    NonNegativeRevision,
    PositiveRevision,
    ReviewText,
    Slug,
)
from ludowright.contracts.visual import VisualJobContract
from ludowright.domain import (
    CaptureProfileId,
    DependencyRelation,
    DisplayName,
    JobId,
    ProfileVersion,
    RevisionVersion,
    VisualBatchId,
    VisualBibleId,
    VisualBibleVersion,
    VisualJobBatch,
    VisualJobDependency,
    VisualJobPlan,
    VisualPlanBlocker,
    VisualPlanBlockerCode,
    VisualPlanId,
    VisualPlanState,
    VisualWorkloadEstimate,
)


class VisualPlanBlockerContract(ContractModel):
    """One stable reason a visual-job plan cannot execute."""

    code: VisualPlanBlockerCode
    subject: DisplayText
    message: ReviewText

    def to_domain(self) -> VisualPlanBlocker:
        return VisualPlanBlocker(
            code=self.code,
            subject=DisplayName(self.subject),
            message=self.message,
        )

    @classmethod
    def from_domain(cls, value: VisualPlanBlocker) -> Self:
        return cls(code=value.code, subject=value.subject.value, message=value.message)


class VisualJobDependencyContract(ContractModel):
    """One deterministic ordering edge between two visual jobs."""

    source_job_id: Slug
    target_job_id: Slug
    relation: DependencyRelation = DependencyRelation.REQUIRES

    def to_domain(self) -> VisualJobDependency:
        return VisualJobDependency(
            source_job_id=JobId(self.source_job_id),
            target_job_id=JobId(self.target_job_id),
            relation=self.relation,
        )

    @classmethod
    def from_domain(cls, value: VisualJobDependency) -> Self:
        return cls(
            source_job_id=value.source_job_id.value,
            target_job_id=value.target_job_id.value,
            relation=value.relation,
        )


class VisualJobBatchContract(ContractModel):
    """A group of jobs sharing an exact capture-profile revision."""

    id: Slug
    profile_id: Slug
    profile_version: PositiveRevision
    job_ids: Annotated[tuple[Slug, ...], Field(min_length=1)]
    output_count: NonNegativeRevision
    estimated_cost_units: NonNegativeRevision
    estimated_workload_units: NonNegativeRevision

    def to_domain(self) -> VisualJobBatch:
        return VisualJobBatch(
            id=VisualBatchId(self.id),
            profile_id=CaptureProfileId(self.profile_id),
            profile_version=ProfileVersion(self.profile_version),
            job_ids=tuple(JobId(item) for item in self.job_ids),
            output_count=self.output_count,
            estimated_cost_units=self.estimated_cost_units,
            estimated_workload_units=self.estimated_workload_units,
        )

    @classmethod
    def from_domain(cls, value: VisualJobBatch) -> Self:
        return cls(
            id=value.id.value,
            profile_id=value.profile_id.value,
            profile_version=value.profile_version.value,
            job_ids=tuple(item.value for item in value.job_ids),
            output_count=value.output_count,
            estimated_cost_units=value.estimated_cost_units,
            estimated_workload_units=value.estimated_workload_units,
        )


class VisualWorkloadEstimateContract(ContractModel):
    """Provider-neutral workload totals for a visual-job plan."""

    job_count: NonNegativeRevision
    output_count: NonNegativeRevision
    batch_count: NonNegativeRevision
    estimated_cost_units: NonNegativeRevision
    estimated_workload_units: NonNegativeRevision

    def to_domain(self) -> VisualWorkloadEstimate:
        return VisualWorkloadEstimate(
            job_count=self.job_count,
            output_count=self.output_count,
            batch_count=self.batch_count,
            estimated_cost_units=self.estimated_cost_units,
            estimated_workload_units=self.estimated_workload_units,
        )

    @classmethod
    def from_domain(cls, value: VisualWorkloadEstimate) -> Self:
        return cls(
            job_count=value.job_count,
            output_count=value.output_count,
            batch_count=value.batch_count,
            estimated_cost_units=value.estimated_cost_units,
            estimated_workload_units=value.estimated_workload_units,
        )


class VisualJobPlanContract(ContractModel):
    """Published v1 representation of a deterministic visual-job plan."""

    schema_version: Literal[1] = 1
    kind: Literal["visual-job-plan"] = "visual-job-plan"
    id: Slug
    name: DisplayText
    state: VisualPlanState
    dependency_graph_revision: PositiveRevision
    visual_bible_id: Slug | None = None
    visual_bible_version: PositiveRevision | None = None
    jobs: tuple[VisualJobContract, ...]
    ordered_job_ids: tuple[Slug, ...]
    dependencies: tuple[VisualJobDependencyContract, ...]
    batches: tuple[VisualJobBatchContract, ...]
    workload: VisualWorkloadEstimateContract
    blockers: tuple[VisualPlanBlockerContract, ...] = ()

    def to_domain(self) -> VisualJobPlan:
        return VisualJobPlan(
            id=VisualPlanId(self.id),
            name=DisplayName(self.name),
            state=self.state,
            dependency_graph_revision=RevisionVersion(self.dependency_graph_revision),
            visual_bible_id=(
                VisualBibleId(self.visual_bible_id) if self.visual_bible_id is not None else None
            ),
            visual_bible_version=(
                VisualBibleVersion(self.visual_bible_version)
                if self.visual_bible_version is not None
                else None
            ),
            jobs=tuple(job.to_domain() for job in self.jobs),
            ordered_job_ids=tuple(JobId(item) for item in self.ordered_job_ids),
            dependencies=tuple(item.to_domain() for item in self.dependencies),
            batches=tuple(item.to_domain() for item in self.batches),
            workload=self.workload.to_domain(),
            blockers=tuple(item.to_domain() for item in self.blockers),
        )

    @classmethod
    def from_domain(cls, value: VisualJobPlan) -> Self:
        return cls(
            id=value.id.value,
            name=value.name.value,
            state=value.state,
            dependency_graph_revision=value.dependency_graph_revision.value,
            visual_bible_id=value.visual_bible_id.value if value.visual_bible_id else None,
            visual_bible_version=(
                value.visual_bible_version.value if value.visual_bible_version else None
            ),
            jobs=tuple(VisualJobContract.from_domain(item) for item in value.jobs),
            ordered_job_ids=tuple(item.value for item in value.ordered_job_ids),
            dependencies=tuple(
                VisualJobDependencyContract.from_domain(item) for item in value.dependencies
            ),
            batches=tuple(VisualJobBatchContract.from_domain(item) for item in value.batches),
            workload=VisualWorkloadEstimateContract.from_domain(value.workload),
            blockers=tuple(VisualPlanBlockerContract.from_domain(item) for item in value.blockers),
        )

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if (self.visual_bible_id is None) != (self.visual_bible_version is None):
            raise ValueError("visual bible ID and version must be provided together")
        self.to_domain()
        return self


__all__ = [
    "VisualJobBatchContract",
    "VisualJobDependencyContract",
    "VisualJobPlanContract",
    "VisualPlanBlockerContract",
    "VisualWorkloadEstimateContract",
]
