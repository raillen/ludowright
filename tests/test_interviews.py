"""Tests for the guided-interview question model and its public contract."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ludowright.contracts.interviews import QuestionnaireContract
from ludowright.domain import (
    AnswerProvenance,
    AnswerSource,
    DependencyOperator,
    InterviewSession,
    InvalidInterviewError,
    OptionId,
    Question,
    QuestionDependency,
    QuestionId,
    Questionnaire,
    QuestionnaireId,
    QuestionOption,
    QuestionType,
    QuestionValidation,
)
from ludowright.domain.names import DisplayName


def option(identifier: str, label: str | None = None) -> QuestionOption:
    return QuestionOption(OptionId(identifier), DisplayName(label or identifier.title()))


def questionnaire(*questions: Question) -> Questionnaire:
    return Questionnaire(QuestionnaireId("game"), DisplayName("Game interview"), questions)


def provenance() -> AnswerProvenance:
    return AnswerProvenance(
        source=AnswerSource.HUMAN,
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        actor="designer",
    )


def test_pending_calculation_respects_dependencies_in_declaration_order() -> None:
    mode = Question(
        QuestionId("mode"),
        "What mode is planned?",
        QuestionType.SINGLE_CHOICE,
        options=(option("solo"), option("coop")),
    )
    party_size = Question(
        QuestionId("party-size"),
        "How many players are in the party?",
        QuestionType.INTEGER,
        dependencies=(QuestionDependency(QuestionId("mode"), DependencyOperator.EQUALS, "coop"),),
    )
    session = InterviewSession(questionnaire(party_size, mode))

    initial = session.pending_questions()
    assert initial.pending == (QuestionId("mode"),)
    assert initial.blocked[0].question_id == QuestionId("party-size")
    assert not initial.is_complete

    answered = session.record_answer(QuestionId("mode"), "solo", provenance()).pending_questions()
    assert answered.not_applicable == (QuestionId("party-size"),)
    assert answered.is_complete


def test_required_and_optional_questions_are_reported_separately() -> None:
    required = Question(QuestionId("required"), "Required answer", QuestionType.TEXT)
    optional = Question(
        QuestionId("optional"), "Optional answer", QuestionType.TEXT, required=False
    )
    progress = InterviewSession(questionnaire(required, optional)).pending_questions()

    assert progress.pending == (QuestionId("required"), QuestionId("optional"))
    assert progress.required_pending == (QuestionId("required"),)
    assert not progress.is_complete
    assert progress.next_question == QuestionId("required")


@pytest.mark.parametrize(
    ("question_type", "value"),
    [
        (QuestionType.TEXT, 10),
        (QuestionType.BOOLEAN, 1),
        (QuestionType.INTEGER, True),
        (QuestionType.NUMBER, "1"),
    ],
)
def test_answer_validation_is_strict(question_type: QuestionType, value: object) -> None:
    question = Question(QuestionId("answer"), "Answer", question_type)

    with pytest.raises(InvalidInterviewError):
        question.validate_answer(value)


def test_multi_choice_answers_are_canonical_tuples_and_reject_duplicates() -> None:
    question = Question(
        QuestionId("features"),
        "Which features?",
        QuestionType.MULTI_CHOICE,
        options=(option("cards"), option("dice")),
    )

    assert question.validate_answer(["cards", "dice"]) == ("cards", "dice")
    with pytest.raises(InvalidInterviewError):
        question.validate_answer(["cards", "cards"])


def test_questionnaire_rejects_unknown_and_cyclic_dependencies() -> None:
    with pytest.raises(InvalidInterviewError, match="unknown question"):
        questionnaire(
            Question(
                QuestionId("child"),
                "Child",
                QuestionType.BOOLEAN,
                dependencies=(
                    QuestionDependency(QuestionId("missing"), DependencyOperator.EQUALS, True),
                ),
            )
        )

    first = Question(
        QuestionId("first"),
        "First",
        QuestionType.BOOLEAN,
        dependencies=(QuestionDependency(QuestionId("second"), DependencyOperator.EQUALS, True),),
    )
    second = Question(
        QuestionId("second"),
        "Second",
        QuestionType.BOOLEAN,
        dependencies=(QuestionDependency(QuestionId("first"), DependencyOperator.EQUALS, True),),
    )
    with pytest.raises(InvalidInterviewError, match="cycles"):
        questionnaire(first, second)


def test_contains_dependency_requires_a_declared_multi_choice_option() -> None:
    features = Question(
        QuestionId("features"),
        "Which features?",
        QuestionType.MULTI_CHOICE,
        options=(option("cards"),),
    )
    dependent = Question(
        QuestionId("detail"),
        "Describe the cards.",
        QuestionType.TEXT,
        dependencies=(
            QuestionDependency(QuestionId("features"), DependencyOperator.CONTAINS, "unknown"),
        ),
    )

    with pytest.raises(InvalidInterviewError, match="declared multi-choice option"):
        questionnaire(features, dependent)


def test_validation_bounds_must_match_question_shape() -> None:
    with pytest.raises(InvalidInterviewError, match="numeric bounds"):
        Question(
            QuestionId("text"),
            "Text",
            QuestionType.TEXT,
            validation=QuestionValidation(min_value=1),
        )


def test_answer_replacement_is_immutable_and_keeps_provenance() -> None:
    session = InterviewSession(
        questionnaire(Question(QuestionId("name"), "Name", QuestionType.TEXT))
    )
    updated = session.record_answer(QuestionId("name"), "Alice", provenance())
    replaced = updated.record_answer(
        QuestionId("name"),
        "Bob",
        AnswerProvenance(
            source=AnswerSource.CODEX,
            recorded_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    assert session.answers == ()
    assert updated.answers[0].value == "Alice"
    assert replaced.answers[0].value == "Bob"
    assert replaced.answers[0].provenance.source is AnswerSource.CODEX


def test_provenance_requires_utc_and_timezone_aware_time() -> None:
    with pytest.raises(InvalidInterviewError):
        AnswerProvenance(AnswerSource.HUMAN, datetime(2026, 1, 1))
    with pytest.raises(InvalidInterviewError):
        AnswerProvenance(
            AnswerSource.HUMAN,
            datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-3))),
        )


def test_questionnaire_contract_validates_and_round_trips_to_domain() -> None:
    contract = QuestionnaireContract.model_validate(
        {
            "schema_version": 1,
            "kind": "interview-questionnaire",
            "id": "game",
            "title": "Game interview",
            "questions": [
                {
                    "id": "mode",
                    "prompt": "What mode is planned?",
                    "type": "single-choice",
                    "options": [
                        {"id": "solo", "label": "Solo"},
                        {"id": "coop", "label": "Co-op"},
                    ],
                },
                {
                    "id": "party-size",
                    "prompt": "How many players?",
                    "type": "integer",
                    "dependencies": [
                        {"question_id": "mode", "operator": "equals", "expected": "coop"}
                    ],
                },
            ],
        }
    )

    domain = contract.to_domain()
    assert domain.questions[0].id == QuestionId("mode")
    assert domain.questions[1].dependencies[0].question_id == QuestionId("mode")


def test_questionnaire_contract_rejects_unknown_fields_and_invalid_dependencies() -> None:
    with pytest.raises(ValidationError):
        QuestionnaireContract.model_validate(
            {
                "schema_version": 1,
                "kind": "interview-questionnaire",
                "id": "game",
                "title": "Game interview",
                "questions": [{"id": "q", "prompt": "Q", "type": "text"}],
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError):
        QuestionnaireContract.model_validate(
            {
                "schema_version": 1,
                "kind": "interview-questionnaire",
                "id": "game",
                "title": "Game interview",
                "questions": [
                    {
                        "id": "q",
                        "prompt": "Q",
                        "type": "single-choice",
                        "options": [{"id": "yes", "label": "Yes"}],
                        "dependencies": [
                            {"question_id": "missing", "operator": "equals", "expected": "yes"}
                        ],
                    }
                ],
            }
        )
