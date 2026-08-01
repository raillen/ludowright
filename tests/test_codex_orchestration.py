"""Tests for the declarative Codex orchestration policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from integrations.codex import (
    CodexOrchestrationError,
    load_codex_orchestration_policy,
)
from pydantic import ValidationError

from ludowright.contracts import CodexOrchestrationContextContract


def ready_context(**overrides: object) -> CodexOrchestrationContextContract:
    values: dict[str, object] = {
        "status_inspected": True,
        "status_state": "ready",
    }
    values.update(overrides)
    return CodexOrchestrationContextContract.model_validate(values)


def test_packaged_policy_is_canonical_and_versioned() -> None:
    policy = load_codex_orchestration_policy()

    assert policy.id == "default"
    assert policy.version == 1
    assert policy.contract.skill_id == "ludowright"
    assert len(policy.contract.phases) == 6
    policy_path = (
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "codex"
        / "skills"
        / "ludowright"
        / "orchestration.json"
    )
    canonical = (
        json.dumps(
            policy.contract.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    assert policy.source_hash == hashlib.sha256(canonical).hexdigest()
    assert policy_path.read_bytes()


def test_policy_inspects_status_before_any_other_action() -> None:
    plan = load_codex_orchestration_policy().plan({})

    assert plan.state == "continue"
    assert plan.action.action == "inspect-status"
    assert plan.action.subject_id is None


def test_blocked_status_is_reported_without_asking_new_questions() -> None:
    plan = load_codex_orchestration_policy().plan(
        ready_context(
            status_state="blocked",
            status_blockers=("event-log-missing", "state-store-missing"),
            unresolved_questions=("question-camera",),
        )
    )

    assert plan.state == "blocked"
    assert plan.action.action == "report-blockers"
    assert plan.status_blockers == ("event-log-missing", "state-store-missing")


def test_only_the_first_unresolved_question_is_selected() -> None:
    plan = load_codex_orchestration_policy().plan(
        ready_context(unresolved_questions=("question-camera", "question-engine"))
    )

    assert plan.state == "awaiting-input"
    assert plan.action.action == "ask-question"
    assert plan.action.requires_human is True
    assert plan.action.subject_id == "question-camera"


def test_decision_is_recorded_after_questions_are_resolved() -> None:
    plan = load_codex_orchestration_policy().plan(
        ready_context(decisions_to_record=("decision-camera",))
    )

    assert plan.action.action == "record-decision"
    assert plan.action.subject_id == "decision-camera"


def test_failed_validation_blocks_and_pending_validation_runs() -> None:
    policy = load_codex_orchestration_policy()
    failed = policy.plan(ready_context(failed_validations=("quality",)))
    pending = policy.plan(ready_context(pending_validations=("atlas", "quality")))

    assert failed.state == "blocked"
    assert failed.action.action == "resolve-validation"
    assert failed.action.subject_id == "quality"
    assert pending.action.action == "run-validations"
    assert pending.action.subject_id == "atlas"


def test_approval_checkpoint_requires_a_human() -> None:
    plan = load_codex_orchestration_policy().plan(
        ready_context(pending_approvals=("approval-reference",))
    )

    assert plan.state == "approval-required"
    assert plan.action.action == "await-approval"
    assert plan.action.requires_human is True
    assert plan.action.subject_id == "approval-reference"


def test_resume_requires_a_durable_workflow_and_phase() -> None:
    plan = load_codex_orchestration_policy().plan(
        ready_context(
            resume_workflow_id="workflow-documents",
            resume_phase_id="validate",
        )
    )

    assert plan.action.action == "resume-workflow"
    assert plan.action.subject_id == "workflow-documents"
    assert plan.action.phase_id == "validate"


def test_next_phase_and_completion_are_deterministic() -> None:
    policy = load_codex_orchestration_policy()
    context = ready_context(completed_phases=("inspect",))
    first = policy.plan(context)
    second = policy.plan(context)
    complete = policy.plan(
        ready_context(
            completed_phases=("approve", "clarify", "decide", "inspect", "resume", "validate")
        )
    )

    assert first.action.action == "execute-phase"
    assert first.action.phase_id == "clarify"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert complete.state == "complete"
    assert complete.action.action == "complete"


def test_context_and_policy_reject_unknown_or_unsorted_references() -> None:
    with pytest.raises(ValidationError, match="must be sorted"):
        CodexOrchestrationContextContract(
            unresolved_questions=("question-z", "question-a"),
        )

    with pytest.raises(CodexOrchestrationError, match="unknown validation"):
        load_codex_orchestration_policy().plan(
            ready_context(pending_validations=("not-published",))
        )
