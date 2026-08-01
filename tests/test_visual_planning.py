"""Tests for deterministic visual-job planning and its published contract."""

from __future__ import annotations

import json
from pathlib import Path

from ludowright.application import VisualJobPlanner
from ludowright.contracts import VisualJobPlanContract
from ludowright.domain import (
    APPROVAL_REVOKED,
    ApprovalId,
    Asset,
    AssetClassification,
    AssetComponent,
    AssetFamily,
    AssetId,
    AssetPriority,
    AssetStatus,
    AssetSubtype,
    BackgroundMode,
    BackgroundSpec,
    CameraProjection,
    CameraSpec,
    CaptureProfile,
    CaptureProfileId,
    CaptureRequirement,
    CaptureRequirementKind,
    CaptureSheet,
    CaptureSheetId,
    CaptureSubjectMode,
    CaptureValidation,
    CaptureView,
    CaptureViewId,
    ComponentId,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    DetailLevel,
    DetailLevelRule,
    DisplayName,
    InvalidationMode,
    LevelOfDetail,
    LightingMode,
    LightingSpec,
    MaterialFinish,
    MaterialRule,
    PaletteColor,
    PaletteRole,
    PixelDimensions,
    ProfileVersion,
    ProjectId,
    ProportionRule,
    ReferenceId,
    ReferenceOrigin,
    ReferenceProvenance,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    RevisionVersion,
    ShadowMode,
    ShapeLanguage,
    SheetLayout,
    SourceUri,
    SubjectRevision,
    VisualBible,
    VisualBibleId,
    VisualBibleVersion,
    VisualBudget,
    VisualJobPlan,
    VisualPlanBlockerCode,
    VisualPlanState,
    VisualPlanTarget,
    VisualReference,
    VisualText,
)

FIXTURE = Path("tests/fixtures/contracts/v1/visual-job-plan.json")


def make_asset(
    asset_id: str = "prop-lantern",
    *,
    status: AssetStatus = AssetStatus.PLANNED,
    components: tuple[AssetComponent, ...] = (),
) -> Asset:
    return Asset(
        id=AssetId(asset_id),
        name=DisplayName("Lantern"),
        classification=AssetClassification(AssetFamily.PROP, AssetSubtype("lantern")),
        priority=AssetPriority.NORMAL,
        status=status,
        components=components,
    )


def make_profile(
    *,
    profile_id: str = "prop-capture",
    requirements: tuple[CaptureRequirement, ...] = (),
    required_sheet: bool = True,
    include_optional_sheet: bool = False,
    subject_modes: frozenset[CaptureSubjectMode] = frozenset({CaptureSubjectMode.ASSET}),
) -> CaptureProfile:
    front = CaptureView(
        id=CaptureViewId("front"),
        name=DisplayName("Front"),
        azimuth_degrees=0,
        elevation_degrees=0,
        role=ReferenceRole.IDENTITY,
    )
    side = CaptureView(
        id=CaptureViewId("side"),
        name=DisplayName("Side"),
        azimuth_degrees=90,
        elevation_degrees=0,
        role=ReferenceRole.CONSTRUCTION,
    )
    main_sheet = CaptureSheet(
        id=CaptureSheetId("main-sheet"),
        name=DisplayName("Main Sheet"),
        layout=SheetLayout.TURNAROUND,
        view_ids=(front.id, side.id),
        subject_modes=subject_modes,
        required=required_sheet,
    )
    sheets = [main_sheet]
    if include_optional_sheet:
        sheets.append(
            CaptureSheet(
                id=CaptureSheetId("optional-components"),
                name=DisplayName("Optional Components"),
                layout=SheetLayout.EXPLODED,
                view_ids=(front.id,),
                subject_modes=frozenset({CaptureSubjectMode.COMPONENTS}),
                required=False,
            )
        )
    return CaptureProfile(
        id=CaptureProfileId(profile_id),
        version=ProfileVersion(1),
        name=DisplayName("Prop Capture"),
        family=AssetFamily.PROP,
        camera=CameraSpec(CameraProjection.ORTHOGRAPHIC),
        background=BackgroundSpec(BackgroundMode.TRANSPARENT),
        lighting=LightingSpec(LightingMode.STUDIO, ShadowMode.SOFT),
        validation=CaptureValidation(PixelDimensions(1024, 1024)),
        views=(front, side),
        requirements=requirements,
        sheets=tuple(sheets),
    )


def make_reference(
    reference_id: str,
    target: ReferenceTarget,
    *,
    status: ReferenceStatus = ReferenceStatus.APPROVED,
) -> VisualReference:
    return VisualReference(
        id=ReferenceId(reference_id),
        name=DisplayName("Lantern Reference"),
        target=target,
        role=ReferenceRole.IDENTITY,
        provenance=ReferenceProvenance(
            origin=ReferenceOrigin.EXTERNAL,
            content_revision=SubjectRevision("sha256:reference"),
            source_uri=SourceUri("https://example.com/lantern"),
        ),
        status=status,
        approval_id=ApprovalId("approval-reference")
        if status is ReferenceStatus.APPROVED
        else None,
    )


def make_bible(*, max_jobs: int = 100, max_outputs: int = 100) -> VisualBible:
    return VisualBible(
        id=VisualBibleId("visual-bible-main"),
        version=VisualBibleVersion(1),
        name=DisplayName("Main Bible"),
        project_id=ProjectId("game"),
        shape_language=ShapeLanguage(VisualText("simple angular forms")),
        proportions=(ProportionRule("default", DisplayName("Default"), VisualText("balanced")),),
        palette=(PaletteColor("primary", DisplayName("Primary"), "#FFFFFF", PaletteRole.PRIMARY),),
        materials=(
            MaterialRule(
                "default",
                DisplayName("Default"),
                MaterialFinish.MATTE,
                VisualText("matte painted surface"),
            ),
        ),
        lighting=LightingSpec(LightingMode.STUDIO, ShadowMode.SOFT),
        camera=CameraSpec(CameraProjection.ORTHOGRAPHIC),
        level_of_detail=LevelOfDetail(
            DetailLevel.MEDIUM,
            (DetailLevelRule(DetailLevel.MEDIUM, VisualText("medium detail")),),
        ),
        budget=VisualBudget(max_jobs, max_outputs, 1),
        prompt_constraints=(VisualText("preserve the silhouette"),),
        negative_constraints=(VisualText("no text overlays"),),
    )


def plan_for(
    asset: Asset,
    profile: CaptureProfile,
    *,
    dependency_graph: DependencyGraph | None = None,
    visual_bible: VisualBible | None = None,
) -> VisualJobPlan:
    return VisualJobPlanner().plan(
        "lantern-plan",
        "Lantern Plan",
        (VisualPlanTarget(asset, profile),),
        dependency_graph=dependency_graph,
        visual_bible=visual_bible,
    )


def test_minimal_plan_is_ready_and_deterministic() -> None:
    asset = make_asset()
    profile = make_profile()

    first = plan_for(asset, profile)
    second = plan_for(asset, profile)

    assert first.state is VisualPlanState.READY
    assert first == second
    assert len(first.jobs) == 1
    assert first.workload.job_count == 1
    assert first.workload.output_count == 2
    assert first.workload.estimated_cost_units == 2
    assert first.workload.estimated_workload_units == 2
    assert first.ordered_job_ids == (first.jobs[0].id,)
    assert first.batches[0].profile_version == ProfileVersion(1)


def test_required_components_are_planned_and_parent_precedes_child() -> None:
    body = AssetComponent(ComponentId("body"), DisplayName("Body"))
    hand = AssetComponent(
        ComponentId("hand"),
        DisplayName("Hand"),
        parent_id=body.id,
    )
    profile = make_profile(
        requirements=(
            CaptureRequirement(
                body.id,
                DisplayName("Body"),
                CaptureRequirementKind.COMPONENT,
            ),
            CaptureRequirement(
                hand.id,
                DisplayName("Hand"),
                CaptureRequirementKind.COMPONENT,
            ),
        )
    )
    profile = CaptureProfile(
        id=profile.id,
        version=profile.version,
        name=profile.name,
        family=profile.family,
        camera=profile.camera,
        background=profile.background,
        lighting=profile.lighting,
        validation=profile.validation,
        views=profile.views,
        requirements=profile.requirements,
        sheets=(
            CaptureSheet(
                id=CaptureSheetId("main-sheet"),
                name=DisplayName("Main Sheet"),
                layout=SheetLayout.EXPLODED,
                view_ids=(CaptureViewId("front"),),
                subject_modes=frozenset({CaptureSubjectMode.COMPONENTS}),
            ),
        ),
    )
    plan = plan_for(make_asset(components=(body, hand)), profile)

    assert plan.state is VisualPlanState.READY
    assert len(plan.jobs) == 2
    body_job = next(job for job in plan.jobs if job.target.component_id == body.id)
    hand_job = next(job for job in plan.jobs if job.target.component_id == hand.id)
    assert plan.ordered_job_ids.index(body_job.id) < plan.ordered_job_ids.index(hand_job.id)
    assert any(
        dependency.source_job_id == body_job.id and dependency.target_job_id == hand_job.id
        for dependency in plan.dependencies
    )


def test_missing_and_inactive_items_block_without_fake_jobs() -> None:
    requirement = CaptureRequirement(
        ComponentId("body"),
        DisplayName("Body"),
        CaptureRequirementKind.COMPONENT,
    )
    profile = make_profile(
        requirements=(requirement,),
        subject_modes=frozenset({CaptureSubjectMode.COMPONENTS}),
    )
    missing = plan_for(make_asset(), profile)
    assert missing.state is VisualPlanState.BLOCKED
    assert VisualPlanBlockerCode.MISSING_REQUIRED_ITEM in {item.code for item in missing.blockers}

    archived = make_asset(
        components=(
            AssetComponent(ComponentId("body"), DisplayName("Body"), status=AssetStatus.ARCHIVED),
        )
    )
    inactive = plan_for(archived, profile)
    assert inactive.state is VisualPlanState.BLOCKED
    assert VisualPlanBlockerCode.INACTIVE_ITEM in {item.code for item in inactive.blockers}


def test_inactive_asset_and_missing_required_sheet_block() -> None:
    inactive = plan_for(make_asset(status=AssetStatus.ARCHIVED), make_profile())
    assert inactive.state is VisualPlanState.BLOCKED
    assert VisualPlanBlockerCode.INACTIVE_ASSET in {item.code for item in inactive.blockers}

    no_required_sheet = plan_for(make_asset(), make_profile(required_sheet=False))
    assert no_required_sheet.state is VisualPlanState.BLOCKED
    assert VisualPlanBlockerCode.MISSING_REQUIRED_OUTPUT in {
        item.code for item in no_required_sheet.blockers
    }
    assert not no_required_sheet.jobs


def test_optional_sheet_is_not_planned() -> None:
    requirement = CaptureRequirement(
        ComponentId("body"),
        DisplayName("Body"),
        CaptureRequirementKind.COMPONENT,
    )
    profile = make_profile(
        requirements=(requirement,),
        include_optional_sheet=True,
    )
    plan = plan_for(make_asset(), profile)
    assert plan.state is VisualPlanState.READY
    assert len(plan.jobs) == 1


def test_references_are_exact_approved_inputs() -> None:
    asset = make_asset()
    target = ReferenceTarget(asset.id)
    approved = make_reference("ref-approved", target)
    plan = VisualJobPlanner().plan(
        "lantern-plan",
        "Lantern Plan",
        (VisualPlanTarget(asset, make_profile(), (approved.id,)),),
        references=(approved,),
    )
    assert plan.jobs[0].input_reference_ids == (approved.id,)

    missing = VisualJobPlanner().plan(
        "lantern-plan",
        "Lantern Plan",
        (VisualPlanTarget(asset, make_profile(), (ReferenceId("ref-missing"),)),),
    )
    assert VisualPlanBlockerCode.MISSING_REFERENCE in {item.code for item in missing.blockers}

    candidate = make_reference("ref-candidate", target, status=ReferenceStatus.CANDIDATE)
    not_approved = VisualJobPlanner().plan(
        "lantern-plan",
        "Lantern Plan",
        (VisualPlanTarget(asset, make_profile(), (candidate.id,)),),
        references=(candidate,),
    )
    assert VisualPlanBlockerCode.REFERENCE_NOT_APPROVED in {
        item.code for item in not_approved.blockers
    }

    other = make_reference("ref-other", ReferenceTarget(AssetId("other-prop")))
    mismatched = VisualJobPlanner().plan(
        "lantern-plan",
        "Lantern Plan",
        (VisualPlanTarget(asset, make_profile(), (other.id,)),),
        references=(other,),
    )
    assert VisualPlanBlockerCode.REFERENCE_TARGET_MISMATCH in {
        item.code for item in mismatched.blockers
    }

    same_asset_wrong_item = make_reference(
        "ref-wrong-item",
        ReferenceTarget(asset.id, component_id=ComponentId("body")),
    )
    wrong_item = VisualJobPlanner().plan(
        "lantern-plan",
        "Lantern Plan",
        (VisualPlanTarget(asset, make_profile(), (same_asset_wrong_item.id,)),),
        references=(same_asset_wrong_item,),
    )
    assert VisualPlanBlockerCode.REFERENCE_TARGET_MISMATCH in {
        item.code for item in wrong_item.blockers
    }


def test_dependency_graph_blocks_stale_and_missing_prerequisites() -> None:
    source = make_asset("source-prop")
    target = make_asset("target-prop")
    source_key = DependencyKey(DependencyNodeKind.ASSET, source.id.value)
    target_key = DependencyKey(DependencyNodeKind.ASSET, target.id.value)
    graph = DependencyGraph.empty()
    graph = graph.add_node(DependencyNode(source_key, RevisionVersion(1)))
    graph = graph.add_node(DependencyNode(target_key, RevisionVersion(1)))
    graph = graph.connect(
        source_key, target_key, DependencyRelation.REQUIRES, InvalidationMode.STALE
    )

    ordered = VisualJobPlanner().plan(
        "dependency-plan",
        "Dependency Plan",
        (
            VisualPlanTarget(source, make_profile()),
            VisualPlanTarget(target, make_profile(profile_id="target-capture")),
        ),
        dependency_graph=graph,
    )
    source_job = next(job for job in ordered.jobs if job.target.asset_id == source.id)
    target_job = next(job for job in ordered.jobs if job.target.asset_id == target.id)
    assert ordered.ordered_job_ids.index(source_job.id) < ordered.ordered_job_ids.index(
        target_job.id
    )

    stale = graph.invalidate(source_key, APPROVAL_REVOKED).graph
    blocked = plan_for(target, make_profile(), dependency_graph=stale)
    assert blocked.state is VisualPlanState.BLOCKED
    assert VisualPlanBlockerCode.STALE_DEPENDENCY in {item.code for item in blocked.blockers}
    assert VisualPlanBlockerCode.MISSING_DEPENDENCY_JOB in {item.code for item in blocked.blockers}


def test_visual_bible_budget_blocks_excess_work() -> None:
    body = AssetComponent(ComponentId("body"), DisplayName("Body"))
    requirement = CaptureRequirement(
        body.id,
        DisplayName("Body"),
        CaptureRequirementKind.COMPONENT,
    )
    plan = plan_for(
        make_asset(components=(body,)),
        make_profile(
            requirements=(requirement,),
            subject_modes=frozenset({CaptureSubjectMode.ASSET, CaptureSubjectMode.COMPONENTS}),
        ),
        visual_bible=make_bible(max_jobs=1, max_outputs=1),
    )
    codes = {item.code for item in plan.blockers}
    assert plan.state is VisualPlanState.BLOCKED
    assert VisualPlanBlockerCode.BUDGET_JOBS_EXCEEDED in codes
    assert VisualPlanBlockerCode.BUDGET_OUTPUTS_EXCEEDED in codes


def test_plan_contract_and_fixture_round_trip() -> None:
    plan = plan_for(make_asset(), make_profile())
    contract = VisualJobPlanContract.from_domain(plan)
    assert contract.to_domain() == plan
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert VisualJobPlanContract.model_validate(fixture).to_domain().id.value == "fixture-plan"


def test_public_plan_is_side_effect_free() -> None:
    plan = plan_for(make_asset(), make_profile())
    assert plan.blockers == ()
    assert plan.state is VisualPlanState.READY
