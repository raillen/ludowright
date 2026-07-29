"""Tests for project identity, targets, engine, stage, and lifecycle."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ludowright.domain import (
    DisplayName,
    EngineSpec,
    InvalidProjectError,
    InvalidProjectTransitionError,
    PlatformFamily,
    Project,
    ProjectDimension,
    ProjectId,
    ProjectIdentity,
    ProjectLifecycle,
    ProjectStage,
    ProjectTarget,
)


def make_project(
    *,
    stage: ProjectStage = ProjectStage.CONCEPT,
    lifecycle: ProjectLifecycle = ProjectLifecycle.ACTIVE,
) -> Project:
    return Project(
        identity=ProjectIdentity(
            id=ProjectId("locadora-2000"),
            name=DisplayName("Locadora 2000"),
            codename=DisplayName("Last Coin"),
        ),
        dimensions=ProjectDimension.THREE_D,
        targets=frozenset(
            {
                ProjectTarget(PlatformFamily.WINDOWS),
                ProjectTarget(PlatformFamily.LINUX),
            }
        ),
        stage=stage,
        lifecycle=lifecycle,
        engine=EngineSpec(name=DisplayName("Godot"), version="4.6.1"),
    )


def test_project_preserves_identity_targets_and_engine() -> None:
    project = make_project()

    assert project.identity.id == ProjectId("locadora-2000")
    assert project.identity.name == DisplayName("Locadora 2000")
    assert project.identity.codename == DisplayName("Last Coin")
    assert project.dimensions is ProjectDimension.THREE_D
    assert project.engine == EngineSpec(name=DisplayName("Godot"), version="4.6.1")
    assert {target.platform for target in project.targets} == {
        PlatformFamily.WINDOWS,
        PlatformFamily.LINUX,
    }


def test_project_aggregate_is_immutable() -> None:
    project = make_project()

    with pytest.raises(FrozenInstanceError):
        project.stage = ProjectStage.PRODUCTION  # type: ignore[misc]


def test_project_requires_at_least_one_target() -> None:
    with pytest.raises(InvalidProjectError, match="at least one target"):
        Project(
            identity=ProjectIdentity(
                id=ProjectId("empty-targets"),
                name=DisplayName("Empty Targets"),
            ),
            dimensions=ProjectDimension.TWO_D,
            targets=frozenset(),
        )


def test_custom_platform_requires_a_label() -> None:
    with pytest.raises(InvalidProjectError, match="requires a label"):
        ProjectTarget(PlatformFamily.OTHER)

    target = ProjectTarget(
        PlatformFamily.OTHER,
        label=DisplayName("Experimental Arcade Cabinet"),
    )
    assert target.label == DisplayName("Experimental Arcade Cabinet")


@pytest.mark.parametrize(
    "version",
    ["", " 4.6", "4.6 ", "4.6\nnightly", "v" * 65],
)
def test_invalid_engine_versions_are_rejected(version: str) -> None:
    with pytest.raises(InvalidProjectError):
        EngineSpec(name=DisplayName("Custom Engine"), version=version)


def test_engine_version_is_optional() -> None:
    assert EngineSpec(name=DisplayName("Custom Engine")).version is None


def test_stage_transition_returns_a_new_project() -> None:
    concept = make_project()
    pre_production = concept.transition_stage(ProjectStage.PRE_PRODUCTION)

    assert concept.stage is ProjectStage.CONCEPT
    assert pre_production.stage is ProjectStage.PRE_PRODUCTION
    assert pre_production.identity is concept.identity
    assert pre_production.targets is concept.targets


def test_stage_transition_can_move_one_adjacent_step_back() -> None:
    project = make_project(stage=ProjectStage.PRODUCTION)

    previous = project.transition_stage(ProjectStage.PRE_PRODUCTION)

    assert previous.stage is ProjectStage.PRE_PRODUCTION


def test_stage_transition_rejects_skipped_stages() -> None:
    project = make_project()

    with pytest.raises(InvalidProjectTransitionError, match="cannot transition project stage"):
        project.transition_stage(ProjectStage.PRODUCTION)


def test_stage_transition_requires_active_lifecycle() -> None:
    project = make_project(lifecycle=ProjectLifecycle.ON_HOLD)

    assert project.can_transition_stage(ProjectStage.PRE_PRODUCTION) is False
    with pytest.raises(InvalidProjectTransitionError):
        project.transition_stage(ProjectStage.PRE_PRODUCTION)


def test_same_stage_and_lifecycle_are_idempotent() -> None:
    project = make_project()

    assert project.transition_stage(ProjectStage.CONCEPT) is project
    assert project.transition_lifecycle(ProjectLifecycle.ACTIVE) is project


def test_project_cannot_complete_before_release() -> None:
    project = make_project(stage=ProjectStage.VALIDATION)

    assert project.can_transition_lifecycle(ProjectLifecycle.COMPLETED) is False
    with pytest.raises(InvalidProjectTransitionError):
        project.transition_lifecycle(ProjectLifecycle.COMPLETED)

    with pytest.raises(InvalidProjectError, match="completed project"):
        make_project(
            stage=ProjectStage.CONCEPT,
            lifecycle=ProjectLifecycle.COMPLETED,
        )


def test_released_project_can_complete_and_reactivate() -> None:
    released = make_project(stage=ProjectStage.RELEASED)

    completed = released.transition_lifecycle(ProjectLifecycle.COMPLETED)
    active_again = completed.transition_lifecycle(ProjectLifecycle.ACTIVE)

    assert completed.lifecycle is ProjectLifecycle.COMPLETED
    assert active_again.lifecycle is ProjectLifecycle.ACTIVE


def test_cancelled_project_can_reactivate() -> None:
    cancelled = make_project().transition_lifecycle(ProjectLifecycle.CANCELLED)

    assert (
        cancelled.transition_lifecycle(ProjectLifecycle.ACTIVE).lifecycle
        is ProjectLifecycle.ACTIVE
    )


def test_archived_project_is_terminal() -> None:
    archived = make_project().transition_lifecycle(ProjectLifecycle.ARCHIVED)

    assert archived.can_transition_lifecycle(ProjectLifecycle.ACTIVE) is False
    assert archived.can_transition_stage(ProjectStage.PRE_PRODUCTION) is False
    with pytest.raises(InvalidProjectTransitionError):
        archived.transition_lifecycle(ProjectLifecycle.ACTIVE)


_EXPECTED_STAGE_TRANSITIONS = {
    ProjectStage.CONCEPT: {ProjectStage.PRE_PRODUCTION},
    ProjectStage.PRE_PRODUCTION: {ProjectStage.CONCEPT, ProjectStage.PRODUCTION},
    ProjectStage.PRODUCTION: {ProjectStage.PRE_PRODUCTION, ProjectStage.VALIDATION},
    ProjectStage.VALIDATION: {ProjectStage.PRODUCTION, ProjectStage.RELEASED},
    ProjectStage.RELEASED: {ProjectStage.VALIDATION, ProjectStage.POST_RELEASE},
    ProjectStage.POST_RELEASE: {ProjectStage.RELEASED},
}


@given(st.sampled_from(list(ProjectStage)), st.sampled_from(list(ProjectStage)))
def test_stage_transition_matrix_is_explicit(
    current: ProjectStage,
    target: ProjectStage,
) -> None:
    project = make_project(stage=current)
    expected = target is current or target in _EXPECTED_STAGE_TRANSITIONS[current]

    assert project.can_transition_stage(target) is expected
