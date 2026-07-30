"""End-to-end tests for the resumable interview CLI slice."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application.interviews import InterviewService
from ludowright.cli.app import app
from ludowright.cli.runtime import CliExitCode
from ludowright.contracts.interviews import QuestionnaireContract
from ludowright.domain import (
    AnswerSource,
    CorrelationId,
    EventDraft,
    EventType,
    InterviewSessionId,
    InvalidInterviewError,
    QuestionId,
)
from ludowright.infrastructure import (
    EventLog,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
)

runner = CliRunner()


def questionnaire_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "interview-questionnaire",
        "id": "game-concept",
        "title": "Game concept interview",
        "questions": [
            {
                "id": "mode",
                "prompt": "What mode is planned?",
                "type": "single-choice",
                "required": True,
                "options": [
                    {"id": "solo", "label": "Solo"},
                    {"id": "coop", "label": "Co-op"},
                ],
            },
            {
                "id": "party-size",
                "prompt": "How many players?",
                "type": "integer",
                "required": True,
                "dependencies": [{"question_id": "mode", "operator": "equals", "expected": "coop"}],
                "validation": {"min_value": 2, "max_value": 8},
            },
            {
                "id": "notes",
                "prompt": "Any optional notes?",
                "type": "text",
                "required": False,
            },
        ],
    }


def project_with_questionnaire(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".ludowright").mkdir(parents=True)
    (root / ".ludowright" / "project.json").write_text("{}\n", encoding="utf-8")
    filesystem = ProjectFilesystem(root)
    repository = JsonDocumentRepository(
        filesystem,
        RepositoryPath("questionnaire.json"),
        QuestionnaireContract,
    )
    repository.create(QuestionnaireContract.model_validate(questionnaire_payload()))
    return root


def invoke_json(root: Path, *arguments: str) -> tuple[dict[str, object], int]:
    result = runner.invoke(
        app,
        [
            "--json",
            "interview",
            *arguments,
            str(root),
            "--questionnaire",
            "questionnaire.json",
            "--session",
            "session-one",
        ],
    )
    assert result.stdout
    return json.loads(result.stdout), result.exit_code


def test_next_answer_and_resume_are_persisted_and_audited(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)

    initial, exit_code = invoke_json(root, "next")
    assert exit_code == int(CliExitCode.SUCCESS)
    assert initial["command"] == "interview next"
    assert initial["data"]["question"]["id"] == "mode"
    assert not (root / ".ludowright" / "interviews" / "session-one.json").exists()

    answered, exit_code = invoke_json(root, "answer", "mode", "--value", "coop")
    assert exit_code == int(CliExitCode.SUCCESS)
    assert answered["data"]["operation"] == "answer"
    assert answered["data"]["changed"] is True
    assert answered["data"]["question"]["id"] == "party-size"
    assert answered["data"]["progress"]["answered"] == ["mode"]

    resumed, exit_code = invoke_json(root, "next")
    assert exit_code == int(CliExitCode.SUCCESS)
    assert resumed["data"]["question"]["id"] == "party-size"

    event_log = EventLog(ProjectFilesystem(root)).replay()
    assert [event.event_type.value for event in event_log.events] == ["interview.answer-recorded"]
    session_path = root / ".ludowright" / "interviews" / "session-one.json"
    assert session_path.is_file()
    assert json.loads(session_path.read_text(encoding="utf-8"))["answers"][0]["value"] == "coop"


def test_typed_answer_values_and_human_output_use_rich(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    first, exit_code = invoke_json(root, "answer", "mode", "--value", '"solo"')
    assert exit_code == int(CliExitCode.SUCCESS)
    assert first["data"]["progress"]["complete"] is True

    result = runner.invoke(
        app,
        [
            "interview",
            "answer",
            "notes",
            "--value",
            "A short note",
            str(root),
            "--questionnaire",
            "questionnaire.json",
            "--session",
            "session-one",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Interview session: session-one" in result.stdout
    assert "Progress:" in result.stdout
    assert "\x1b[" not in result.stdout


def test_skip_and_defer_policies_are_explicit(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    deferred, exit_code = invoke_json(root, "defer", "mode")
    assert exit_code == int(CliExitCode.SUCCESS)
    assert deferred["data"]["progress"]["deferred"] == ["mode"]
    assert deferred["data"]["progress"]["complete"] is False

    skipped, exit_code = invoke_json(root, "skip", "notes")
    assert exit_code == int(CliExitCode.SUCCESS)
    assert skipped["data"]["progress"]["skipped"] == ["notes"]

    rejected, exit_code = invoke_json(root, "skip", "party-size")
    assert exit_code == int(CliExitCode.VALIDATION)
    assert rejected["kind"] == "cli-response"
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "invalid-input"


def test_invalid_answer_has_json_error_envelope_and_no_partial_session(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    payload, exit_code = invoke_json(root, "answer", "party-size", "--value", "1")

    assert exit_code == int(CliExitCode.VALIDATION)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid-input"
    assert not (root / ".ludowright" / "interviews" / "session-one.json").exists()
    assert not EventLog(ProjectFilesystem(root)).replay().events


def test_answering_a_blocked_question_is_rejected(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    payload, exit_code = invoke_json(root, "answer", "party-size", "--value", "4")

    assert exit_code == int(CliExitCode.VALIDATION)
    assert payload["error"]["code"] == "invalid-input"
    assert "not currently actionable" in payload["error"]["message"]


def test_questionnaire_change_conflicts_with_existing_session(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    _payload, exit_code = invoke_json(root, "answer", "mode", "--value", "solo")
    assert exit_code == int(CliExitCode.SUCCESS)

    filesystem = ProjectFilesystem(root)
    repository = JsonDocumentRepository(
        filesystem,
        RepositoryPath("questionnaire.json"),
        QuestionnaireContract,
    )
    changed = questionnaire_payload()
    changed["title"] = "Changed interview"
    repository.save(QuestionnaireContract.model_validate(changed))

    payload, exit_code = invoke_json(root, "next")
    assert exit_code == int(CliExitCode.CONFLICT)
    assert payload["error"]["code"] == "conflict"


def test_application_rolls_back_session_when_event_append_fails(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    filesystem = ProjectFilesystem(root)

    class FailingEventLog(EventLog):
        def __init__(self) -> None:
            super().__init__(filesystem)

        def append(self, _draft: EventDraft, *, occurred_at: datetime) -> None:
            raise RuntimeError("event append failed")

    service = InterviewService(
        filesystem,
        RepositoryPath("questionnaire.json"),
        InterviewSessionId("session-one"),
        event_log=FailingEventLog(),
        clock=lambda: datetime(2026, 7, 29, 12, 30, 45, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="event append failed"):
        service.answer(QuestionId("mode"), "solo", source=AnswerSource.HUMAN)

    assert not (root / ".ludowright" / "interviews" / "session-one.json").exists()


def test_event_log_rollback_does_not_hide_original_failure(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    filesystem = ProjectFilesystem(root)
    event_log = EventLog(filesystem)
    event_log.append(
        EventDraft(
            event_type=EventType("project.created"),
            correlation_id=CorrelationId("seed"),
            payload={"seed": True},
        )
    )
    service = InterviewService(
        filesystem,
        RepositoryPath("questionnaire.json"),
        InterviewSessionId("session-one"),
        event_log=event_log,
    )

    with pytest.raises(InvalidInterviewError):
        service.answer(QuestionId("party-size"), 1)


def test_concurrent_mutations_are_serialized_per_session(tmp_path: Path) -> None:
    root = project_with_questionnaire(tmp_path)
    filesystem = ProjectFilesystem(root)

    def answer(value: str):
        return InterviewService(
            filesystem,
            RepositoryPath("questionnaire.json"),
            InterviewSessionId("session-one"),
        ).answer(QuestionId("mode"), value)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(answer, ("solo", "coop")))

    assert all(result.changed for result in results)
    events = EventLog(filesystem).replay().events
    assert len(events) == 2
    assert [event.sequence for event in events] == [1, 2]
