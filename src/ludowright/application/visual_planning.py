"""Application orchestration for deterministic visual-job planning."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass

from ludowright.contracts import VisualJobPlanContract
from ludowright.domain import (
    Asset,
    AssetComponent,
    AssetState,
    AssetStatus,
    AssetVariant,
    CaptureProfile,
    CaptureRequirement,
    CaptureRequirementKind,
    CaptureSheet,
    CaptureSubjectMode,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    DisplayName,
    FreshnessState,
    InvalidationMode,
    JobId,
    ProfileVersion,
    ReferenceId,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    RevisionVersion,
    SubjectRevision,
    VisualBatchId,
    VisualBible,
    VisualJob,
    VisualJobBatch,
    VisualJobDependency,
    VisualJobPlan,
    VisualPlanBlocker,
    VisualPlanBlockerCode,
    VisualPlanId,
    VisualPlanState,
    VisualPlanTarget,
    VisualReference,
    VisualWorkloadEstimate,
    estimate_profile_workload,
    target_for_asset,
    target_for_component,
    target_for_state,
    target_for_variant,
)
from ludowright.domain.errors import InvalidVisualPlanError
from ludowright.domain.identifiers import CaptureProfileId
from ludowright.domain.names import validate_slug

_SUBJECT_MODE_ORDER = {
    CaptureSubjectMode.ASSET: 0,
    CaptureSubjectMode.COMPONENTS: 1,
    CaptureSubjectMode.VARIANTS: 2,
    CaptureSubjectMode.STATES: 3,
}
_INACTIVE_STATUSES = frozenset({AssetStatus.CANCELLED, AssetStatus.ARCHIVED})


@dataclass(frozen=True, slots=True)
class _PlannedJob:
    job: VisualJob
    asset: Asset
    asset_id: str
    target: ReferenceTarget
    profile: CaptureProfile


class VisualJobPlanner:
    """Derive, order, batch, and estimate visual jobs without side effects."""

    def plan(
        self,
        plan_id: str | VisualPlanId,
        name: str | DisplayName,
        targets: tuple[VisualPlanTarget, ...],
        *,
        dependency_graph: DependencyGraph | None = None,
        visual_bible: VisualBible | None = None,
        references: tuple[VisualReference, ...] = (),
    ) -> VisualJobPlan:
        """Return a deterministic visual-job plan from explicit canonical inputs."""
        identifier = _plan_id(plan_id)
        plan_name = _display_name(name, "visual plan name")
        if not isinstance(targets, tuple) or not targets:
            raise InvalidVisualPlanError("visual planning requires at least one target")
        if any(not isinstance(target, VisualPlanTarget) for target in targets):
            raise InvalidVisualPlanError("visual planning targets must be canonical")
        graph = dependency_graph if dependency_graph is not None else DependencyGraph.empty()
        if not isinstance(graph, DependencyGraph):
            raise TypeError("visual planning requires DependencyGraph")
        if visual_bible is not None and not isinstance(visual_bible, VisualBible):
            raise TypeError("visual planning visual_bible must be canonical")
        reference_catalog = _reference_catalog(references)
        _validate_target_uniqueness(targets)

        planned_assets = {target.asset.id.value for target in targets}
        blockers: list[VisualPlanBlocker] = []
        for target in targets:
            blockers.extend(_dependency_blockers(target.asset, graph, planned_assets))

        planned_jobs: list[_PlannedJob] = []
        reference_counts: dict[str, set[ReferenceId]] = defaultdict(set)
        for target in sorted(targets, key=_target_sort_key):
            if target.asset.status in _INACTIVE_STATUSES:
                blockers.append(
                    _blocker(
                        VisualPlanBlockerCode.INACTIVE_ASSET,
                        target.asset.id.value,
                        f"asset status {target.asset.status.value!r} cannot be planned",
                    )
                )
                continue
            target_jobs, target_blockers, valid_references = _derive_target_jobs(
                target,
                reference_catalog,
            )
            planned_jobs.extend(target_jobs)
            blockers.extend(target_blockers)
            reference_counts[target.asset.id.value].update(valid_references)

        if visual_bible is not None:
            blockers.extend(
                _budget_blockers(
                    visual_bible,
                    job_count=len(planned_jobs),
                    output_count=sum(item.job.expected_output_count for item in planned_jobs),
                    reference_counts=reference_counts,
                )
            )

        dependencies = _derive_job_dependencies(planned_jobs, graph)
        ordered_job_ids = _ordered_job_ids(planned_jobs, dependencies)
        batches = _build_batches(planned_jobs)
        workload = _build_workload(planned_jobs, batches)
        unique_blockers = _sorted_unique_blockers(blockers)
        return VisualJobPlan(
            id=identifier,
            name=plan_name,
            state=VisualPlanState.BLOCKED if unique_blockers else VisualPlanState.READY,
            dependency_graph_revision=graph.revision,
            visual_bible_id=visual_bible.id if visual_bible is not None else None,
            visual_bible_version=visual_bible.version if visual_bible is not None else None,
            jobs=tuple(sorted((item.job for item in planned_jobs), key=lambda job: job.id.value)),
            ordered_job_ids=ordered_job_ids,
            dependencies=dependencies,
            batches=batches,
            workload=workload,
            blockers=unique_blockers,
        )

    def plan_contract(
        self,
        plan_id: str | VisualPlanId,
        name: str | DisplayName,
        targets: tuple[VisualPlanTarget, ...],
        *,
        dependency_graph: DependencyGraph | None = None,
        visual_bible: VisualBible | None = None,
        references: tuple[VisualReference, ...] = (),
    ) -> VisualJobPlanContract:
        """Return the published contract representation of a visual plan."""
        return VisualJobPlanContract.from_domain(
            self.plan(
                plan_id,
                name,
                targets,
                dependency_graph=dependency_graph,
                visual_bible=visual_bible,
                references=references,
            )
        )


def _derive_target_jobs(
    target: VisualPlanTarget,
    reference_catalog: dict[ReferenceId, VisualReference],
) -> tuple[list[_PlannedJob], list[VisualPlanBlocker], set[ReferenceId]]:
    profile = target.profile
    blockers: list[VisualPlanBlocker] = []
    jobs: list[_PlannedJob] = []
    valid_references: set[ReferenceId] = set()
    sheets = tuple(
        sorted(
            (sheet for sheet in profile.sheets if sheet.required),
            key=lambda sheet: sheet.id.value,
        )
    )
    if not sheets:
        blockers.append(
            _blocker(
                VisualPlanBlockerCode.MISSING_REQUIRED_OUTPUT,
                profile.id.value,
                "capture profile has no required technical-sheet output",
            )
        )
        return jobs, blockers, valid_references

    requirements = {
        requirement.kind: tuple(
            item for item in profile.requirements if item.kind is requirement.kind and item.required
        )
        for requirement in profile.requirements
    }
    seen: set[tuple[ReferenceTarget, str]] = set()
    for sheet in sheets:
        view_by_id = {view.id: view for view in profile.views}
        try:
            output_roles = tuple(view_by_id[view_id].role for view_id in sheet.view_ids)
        except KeyError as error:
            raise InvalidVisualPlanError(
                f"capture sheet {sheet.id.value!r} references an unknown view"
            ) from error
        if len(output_roles) > 64:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.OUTPUT_LIMIT_EXCEEDED,
                    sheet.id.value,
                    "one visual job cannot contain more than 64 outputs",
                )
            )
            continue
        for mode in sorted(sheet.subject_modes, key=_SUBJECT_MODE_ORDER.__getitem__):
            candidates, candidate_blockers = _targets_for_mode(
                target.asset,
                mode,
                requirements,
            )
            blockers.extend(candidate_blockers)
            for job_target in candidates:
                identity = (job_target, sheet.id.value)
                if identity in seen:
                    continue
                seen.add(identity)
                input_references = tuple(
                    sorted(
                        (
                            reference_id
                            for reference_id in target.reference_ids
                            if _reference_matches_target(
                                reference_catalog.get(reference_id),
                                job_target,
                            )
                        ),
                        key=lambda item: item.value,
                    )
                )
                valid_references.update(input_references)
                jobs.append(
                    _PlannedJob(
                        job=_build_job(
                            target.asset,
                            profile,
                            sheet,
                            job_target,
                            output_roles,
                            input_references,
                        ),
                        asset=target.asset,
                        asset_id=target.asset.id.value,
                        target=job_target,
                        profile=profile,
                    )
                )
    planned_targets = {planned.target for planned in jobs}
    for reference_id in target.reference_ids:
        reference = reference_catalog.get(reference_id)
        if reference is None:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.MISSING_REFERENCE,
                    reference_id.value,
                    "requested reference is not available in the catalog",
                )
            )
        elif reference.status is not ReferenceStatus.APPROVED:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.REFERENCE_NOT_APPROVED,
                    reference_id.value,
                    f"reference status {reference.status.value!r} is not approved",
                )
            )
        elif reference.target.asset_id != target.asset.id:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.REFERENCE_TARGET_MISMATCH,
                    reference_id.value,
                    "requested reference targets another asset",
                )
            )
        elif reference.target not in planned_targets:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.REFERENCE_TARGET_MISMATCH,
                    reference_id.value,
                    "requested reference does not target a planned job",
                )
            )
    return jobs, blockers, valid_references


def _targets_for_mode(
    asset: Asset,
    mode: CaptureSubjectMode,
    requirements: dict[CaptureRequirementKind, tuple[CaptureRequirement, ...]],
) -> tuple[list[ReferenceTarget], list[VisualPlanBlocker]]:
    blockers: list[VisualPlanBlocker] = []
    if mode is CaptureSubjectMode.ASSET:
        return [target_for_asset(asset)], blockers
    if mode is CaptureSubjectMode.COMPONENTS:
        return _item_targets(
            asset,
            requirements.get(CaptureRequirementKind.COMPONENT, ()),
            asset.components,
            blockers,
        )
    if mode is CaptureSubjectMode.VARIANTS:
        return _item_targets(
            asset,
            requirements.get(CaptureRequirementKind.VARIANT, ()),
            asset.variants,
            blockers,
        )
    return _item_targets(
        asset,
        requirements.get(CaptureRequirementKind.STATE, ()),
        asset.states,
        blockers,
    )


def _item_targets(
    asset: Asset,
    requirements: tuple[CaptureRequirement, ...],
    items: (tuple[AssetComponent, ...] | tuple[AssetVariant, ...] | tuple[AssetState, ...]),
    blockers: list[VisualPlanBlocker],
) -> tuple[list[ReferenceTarget], list[VisualPlanBlocker]]:
    targets: list[ReferenceTarget] = []
    for requirement in requirements:
        if (
            requirement.id.value == "subject"
            and requirement.kind is CaptureRequirementKind.COMPONENT
        ):
            targets.append(target_for_asset(asset))
            continue
        item = next((candidate for candidate in items if candidate.id == requirement.id), None)
        if item is None:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.MISSING_REQUIRED_ITEM,
                    f"{asset.id.value}:{requirement.id.value}",
                    f"required profile item {requirement.id.value!r} is missing from the asset",
                )
            )
            continue
        if item.status in _INACTIVE_STATUSES:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.INACTIVE_ITEM,
                    f"{asset.id.value}:{requirement.id.value}",
                    f"asset item status {item.status.value!r} cannot be planned",
                )
            )
            continue
        if isinstance(item, AssetComponent):
            targets.append(target_for_component(asset, item))
        elif isinstance(item, AssetVariant):
            targets.append(target_for_variant(asset, item))
        elif isinstance(item, AssetState):
            targets.append(target_for_state(asset, item))
        else:
            raise TypeError(f"unsupported visual planning item: {type(item).__name__}")
    return targets, blockers


def _build_job(
    asset: Asset,
    profile: CaptureProfile,
    sheet: CaptureSheet,
    target: ReferenceTarget,
    output_roles: tuple[ReferenceRole, ...],
    input_references: tuple[ReferenceId, ...],
) -> VisualJob:
    payload = {
        "asset_id": asset.id.value,
        "profile_id": profile.id.value,
        "profile_version": profile.version.value,
        "sheet_id": sheet.id.value,
        "target": _target_payload(target),
        "views": [
            {"id": view_id.value, "role": role.value}
            for view_id, role in zip(sheet.view_ids, output_roles, strict=True)
        ],
        "reference_ids": [item.value for item in input_references],
    }
    digest = _digest(payload)
    target_label = _target_label(target)
    job_name = f"{asset.name} - {sheet.name} - {target_label}"
    if len(job_name) > 111:
        job_name = job_name[:111].rstrip()
    return VisualJob(
        id=JobId(f"job-{digest[:48]}"),
        name=DisplayName(f"{job_name} {digest[:8]}"),
        target=target,
        profile_version=profile.version,
        request_revision=SubjectRevision(f"sha256:{digest}"),
        input_reference_ids=input_references,
        output_roles=output_roles,
        expected_output_count=len(output_roles),
    )


def _derive_job_dependencies(
    jobs: list[_PlannedJob],
    graph: DependencyGraph,
) -> tuple[VisualJobDependency, ...]:
    dependencies: set[tuple[JobId, JobId, DependencyRelation]] = set()
    grouped: dict[str, list[JobId]] = defaultdict(list)
    for planned in jobs:
        grouped[planned.asset_id].append(planned.job.id)
    jobs_by_asset = {
        asset_id: tuple(sorted(job_ids, key=lambda job_id: job_id.value))
        for asset_id, job_ids in grouped.items()
    }
    for edge in graph.edges:
        if (
            edge.relation is not DependencyRelation.REQUIRES
            or edge.source.kind is not DependencyNodeKind.ASSET
            or edge.target.kind is not DependencyNodeKind.ASSET
        ):
            continue
        for source_job_id in jobs_by_asset.get(edge.source.id, ()):
            for target_job_id in jobs_by_asset.get(edge.target.id, ()):
                if source_job_id != target_job_id:
                    dependencies.add((source_job_id, target_job_id, edge.relation))

    jobs_by_target = {planned.target: planned.job.id for planned in jobs}
    for planned in jobs:
        component_id = planned.target.component_id
        if component_id is None:
            continue
        asset = next(item.asset for item in jobs if item.asset_id == planned.asset_id)
        component = next(item for item in asset.components if item.id == component_id)
        if component.parent_id is None:
            continue
        parent_target = ReferenceTarget(asset.id, component_id=component.parent_id)
        parent_job_id = jobs_by_target.get(parent_target)
        if parent_job_id is not None and parent_job_id != planned.job.id:
            dependencies.add((parent_job_id, planned.job.id, DependencyRelation.REQUIRES))
    return tuple(
        VisualJobDependency(source, target, relation)
        for source, target, relation in sorted(
            dependencies,
            key=lambda item: (item[0].value, item[1].value, item[2].value),
        )
    )


def _ordered_job_ids(
    jobs: list[_PlannedJob],
    dependencies: tuple[VisualJobDependency, ...],
) -> tuple[JobId, ...]:
    job_by_id = {planned.job.id: planned.job for planned in jobs}
    graph = DependencyGraph.empty()
    for job_id in sorted(job_by_id, key=lambda item: item.value):
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
    return tuple(JobId(key.id) for key in graph.topological_order())


def _build_batches(jobs: list[_PlannedJob]) -> tuple[VisualJobBatch, ...]:
    grouped: dict[tuple[CaptureProfileId, int], list[_PlannedJob]] = defaultdict(list)
    for planned in jobs:
        grouped[(planned.profile.id, planned.profile.version.value)].append(planned)
    batches: list[VisualJobBatch] = []
    for (profile_id, profile_version), grouped_jobs in sorted(
        grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        ordered = tuple(sorted(grouped_jobs, key=lambda item: item.job.id.value))
        output_count = sum(item.job.expected_output_count for item in ordered)
        cost_units = 0
        workload_units = 0
        for item in ordered:
            cost, workload = estimate_profile_workload(
                item.profile,
                item.job.expected_output_count,
            )
            cost_units += cost
            workload_units += workload
        digest = _digest({"profile_id": profile_id.value, "profile_version": profile_version})
        batches.append(
            VisualJobBatch(
                id=VisualBatchId(f"batch-{digest[:48]}"),
                profile_id=profile_id,
                profile_version=ProfileVersion(profile_version),
                job_ids=tuple(item.job.id for item in ordered),
                output_count=output_count,
                estimated_cost_units=cost_units,
                estimated_workload_units=workload_units,
            )
        )
    return tuple(sorted(batches, key=lambda batch: batch.id.value))


def _build_workload(
    jobs: list[_PlannedJob],
    batches: tuple[VisualJobBatch, ...],
) -> VisualWorkloadEstimate:
    return VisualWorkloadEstimate(
        job_count=len(jobs),
        output_count=sum(item.job.expected_output_count for item in jobs),
        batch_count=len(batches),
        estimated_cost_units=sum(item.estimated_cost_units for item in batches),
        estimated_workload_units=sum(item.estimated_workload_units for item in batches),
    )


def _dependency_blockers(
    asset: Asset,
    graph: DependencyGraph,
    planned_assets: set[str],
) -> list[VisualPlanBlocker]:
    root = DependencyKey(DependencyNodeKind.ASSET, asset.id.value)
    try:
        graph.get_node(root)
    except KeyError:
        return []
    blockers: list[VisualPlanBlocker] = []
    visited: set[DependencyKey] = set()
    pending = deque([root])
    while pending:
        target = pending.popleft()
        if target in visited:
            continue
        visited.add(target)
        for edge in graph.dependencies_of(target):
            if (
                edge.relation is DependencyRelation.REQUIRES
                and edge.source.kind is DependencyNodeKind.ASSET
                and edge.source.id not in planned_assets
            ):
                blockers.append(
                    _blocker(
                        VisualPlanBlockerCode.MISSING_DEPENDENCY_JOB,
                        edge.source.token,
                        "required prerequisite asset is not included in this plan",
                    )
                )
            if edge.invalidation_mode is InvalidationMode.NONE:
                pending.append(edge.source)
                continue
            source_node = graph.get_node(edge.source)
            if source_node.freshness is not FreshnessState.FRESH:
                blockers.append(
                    _blocker(
                        VisualPlanBlockerCode.STALE_DEPENDENCY,
                        edge.source.token,
                        f"dependency freshness is {source_node.freshness.value!r}",
                    )
                )
            pending.append(edge.source)
    node = graph.get_node(root)
    if node.freshness is not FreshnessState.FRESH:
        blockers.append(
            _blocker(
                VisualPlanBlockerCode.STALE_DEPENDENCY,
                root.token,
                f"asset dependency state is {node.freshness.value!r}",
            )
        )
    return blockers


def _budget_blockers(
    visual_bible: VisualBible,
    *,
    job_count: int,
    output_count: int,
    reference_counts: dict[str, set[ReferenceId]],
) -> list[VisualPlanBlocker]:
    blockers: list[VisualPlanBlocker] = []
    subject = visual_bible.id.value
    if job_count > visual_bible.budget.max_visual_jobs:
        blockers.append(
            _blocker(
                VisualPlanBlockerCode.BUDGET_JOBS_EXCEEDED,
                subject,
                f"plan has {job_count} jobs but budget allows "
                f"{visual_bible.budget.max_visual_jobs}",
            )
        )
    if output_count > visual_bible.budget.max_generated_outputs:
        blockers.append(
            _blocker(
                VisualPlanBlockerCode.BUDGET_OUTPUTS_EXCEEDED,
                subject,
                f"plan has {output_count} outputs but budget allows "
                f"{visual_bible.budget.max_generated_outputs}",
            )
        )
    for asset_id, reference_ids in sorted(reference_counts.items()):
        if len(reference_ids) > visual_bible.budget.max_references_per_asset:
            blockers.append(
                _blocker(
                    VisualPlanBlockerCode.BUDGET_REFERENCES_EXCEEDED,
                    asset_id,
                    f"asset uses {len(reference_ids)} references but budget allows "
                    f"{visual_bible.budget.max_references_per_asset}",
                )
            )
    return blockers


def _reference_catalog(
    references: tuple[VisualReference, ...],
) -> dict[ReferenceId, VisualReference]:
    if not isinstance(references, tuple):
        raise InvalidVisualPlanError("reference catalog must be an immutable tuple")
    catalog: dict[ReferenceId, VisualReference] = {}
    for reference in references:
        if not isinstance(reference, VisualReference):
            raise InvalidVisualPlanError("reference catalog entries must be canonical")
        if reference.id in catalog:
            raise InvalidVisualPlanError("reference catalog IDs must be unique")
        catalog[reference.id] = reference
    return catalog


def _reference_matches_target(
    reference: VisualReference | None,
    target: ReferenceTarget,
) -> bool:
    return (
        reference is not None
        and reference.status is ReferenceStatus.APPROVED
        and reference.target == target
    )


def _validate_target_uniqueness(targets: tuple[VisualPlanTarget, ...]) -> None:
    keys = tuple(
        (target.asset.id.value, target.profile.id.value, target.profile.version.value)
        for target in targets
    )
    if len(keys) != len(set(keys)):
        raise InvalidVisualPlanError("visual plan targets must be unique by asset and profile")


def _target_sort_key(target: VisualPlanTarget) -> tuple[str, str, int]:
    return (target.asset.id.value, target.profile.id.value, target.profile.version.value)


def _plan_id(value: str | VisualPlanId) -> VisualPlanId:
    if isinstance(value, VisualPlanId):
        return value
    if not isinstance(value, str):
        raise TypeError("visual plan ID must be a string or VisualPlanId")
    validate_slug(value)
    return VisualPlanId(value)


def _display_name(value: str | DisplayName, field_name: str) -> DisplayName:
    if isinstance(value, DisplayName):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or DisplayName")
    return DisplayName(value)


def _blocker(code: VisualPlanBlockerCode, subject: str, message: str) -> VisualPlanBlocker:
    return VisualPlanBlocker(code=code, subject=DisplayName(subject), message=message)


def _sorted_unique_blockers(
    blockers: Iterable[VisualPlanBlocker],
) -> tuple[VisualPlanBlocker, ...]:
    unique = {(item.code.value, item.subject.value, item.message): item for item in blockers}
    return tuple(unique[key] for key in sorted(unique))


def _target_label(target: ReferenceTarget) -> str:
    if target.component_id is not None:
        return f"component-{target.component_id.value}"
    if target.variant_id is not None:
        return f"variant-{target.variant_id.value}"
    if target.state_id is not None:
        return f"state-{target.state_id.value}"
    return "asset"


def _target_payload(target: ReferenceTarget) -> dict[str, str | None]:
    return {
        "asset_id": target.asset_id.value,
        "component_id": target.component_id.value if target.component_id is not None else None,
        "variant_id": target.variant_id.value if target.variant_id is not None else None,
        "state_id": target.state_id.value if target.state_id is not None else None,
    }


def _digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["VisualJobPlanner"]
