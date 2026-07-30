"""Immutable, declarative model for guided project interviews."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from ludowright.domain.errors import InvalidInterviewError
from ludowright.domain.identifiers import OptionId, QuestionId, QuestionnaireId
from ludowright.domain.names import DisplayName

type ScalarAnswer = str | bool | int | float
type AnswerValue = ScalarAnswer | tuple[str, ...]


class QuestionType(StrEnum):
    """Supported answer shapes for the first interview engine slice."""

    TEXT = "text"
    SINGLE_CHOICE = "single-choice"
    MULTI_CHOICE = "multi-choice"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"


class DependencyOperator(StrEnum):
    """Safe, non-evaluated predicates used to reveal a question."""

    EQUALS = "equals"
    NOT_EQUALS = "not-equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not-contains"


class AnswerSource(StrEnum):
    """Origin of an answer, retained for auditability and later replay."""

    HUMAN = "human"
    CODEX = "codex"
    IMPORTED = "imported"
    DEFAULT = "default"


def _validate_text(value: str, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidInterviewError(f"{label} must be non-empty and have no surrounding whitespace")
    if len(value) > maximum:
        raise InvalidInterviewError(f"{label} cannot exceed {maximum} characters")
    if unicodedata.normalize("NFC", value) != value:
        raise InvalidInterviewError(f"{label} must use canonical Unicode NFC normalization")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise InvalidInterviewError(f"{label} cannot contain control or format characters")
    return value


def _validate_scalar(value: object) -> ScalarAnswer:
    if isinstance(value, (str, bool, int, float)) and not isinstance(value, complex):
        if isinstance(value, float) and not math.isfinite(value):
            raise InvalidInterviewError("numeric answers must be finite")
        return value
    raise InvalidInterviewError("dependency values must be strings, booleans, or numbers")


@dataclass(frozen=True, slots=True)
class QuestionOption:
    """Stable selectable value and its human-facing label."""

    id: OptionId
    label: DisplayName


@dataclass(frozen=True, slots=True)
class QuestionValidation:
    """Bounded validation rules shared by supported question types."""

    min_length: int | None = None
    max_length: int | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None

    def __post_init__(self) -> None:
        if self.min_length is not None and (
            isinstance(self.min_length, bool) or self.min_length < 0
        ):
            raise InvalidInterviewError("min_length must be a non-negative integer")
        if self.max_length is not None and (
            isinstance(self.max_length, bool) or self.max_length < 0
        ):
            raise InvalidInterviewError("max_length must be a non-negative integer")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise InvalidInterviewError("min_length cannot exceed max_length")
        for label, value in (("min_value", self.min_value), ("max_value", self.max_value)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise InvalidInterviewError(f"{label} must be a number")
            if isinstance(value, float) and not math.isfinite(value):
                raise InvalidInterviewError(f"{label} must be finite")
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise InvalidInterviewError("min_value cannot exceed max_value")


@dataclass(frozen=True, slots=True)
class QuestionDependency:
    """A typed predicate against a previously answered question."""

    question_id: QuestionId
    operator: DependencyOperator
    expected: ScalarAnswer

    def __post_init__(self) -> None:
        _validate_scalar(self.expected)

    def matches(self, answer: AnswerValue) -> bool:
        if self.operator in (DependencyOperator.CONTAINS, DependencyOperator.NOT_CONTAINS):
            if not isinstance(answer, tuple) or not isinstance(self.expected, str):
                return False
            result = self.expected in answer
        else:
            result = type(answer) is type(self.expected) and answer == self.expected
        return (
            result
            if self.operator in (DependencyOperator.EQUALS, DependencyOperator.CONTAINS)
            else not result
        )


@dataclass(frozen=True, slots=True)
class Question:
    """One declarative question and the rules required to answer it."""

    id: QuestionId
    prompt: str
    type: QuestionType
    required: bool = True
    options: tuple[QuestionOption, ...] = ()
    dependencies: tuple[QuestionDependency, ...] = ()
    validation: QuestionValidation = QuestionValidation()

    def __post_init__(self) -> None:
        _validate_text(self.prompt, "question prompt", 4_000)
        if not isinstance(self.required, bool):
            raise InvalidInterviewError("question required must be boolean")
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise InvalidInterviewError(f"question {self.id} contains duplicate option IDs")
        if self.type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTI_CHOICE):
            if not self.options:
                raise InvalidInterviewError(f"choice question {self.id} requires options")
        elif self.options:
            raise InvalidInterviewError(
                f"question {self.id} cannot declare options for type {self.type}"
            )
        if self.type in (QuestionType.TEXT,):
            if self.validation.min_value is not None or self.validation.max_value is not None:
                raise InvalidInterviewError("text questions cannot declare numeric bounds")
        elif self.type in (QuestionType.INTEGER, QuestionType.NUMBER):
            if self.validation.min_length is not None or self.validation.max_length is not None:
                raise InvalidInterviewError("numeric questions cannot declare length bounds")
        elif (
            self.validation.min_length is not None
            or self.validation.max_length is not None
            or self.validation.min_value is not None
            or self.validation.max_value is not None
        ):
            raise InvalidInterviewError(
                f"question type {self.type} cannot declare validation bounds"
            )

    def validate_answer(self, value: object) -> AnswerValue:
        if self.type is QuestionType.TEXT:
            if not isinstance(value, str):
                raise InvalidInterviewError(f"answer for {self.id} must be text")
            normalized = _validate_text(value, f"answer for {self.id}", 4_000)
            if (
                self.validation.min_length is not None
                and len(normalized) < self.validation.min_length
            ):
                raise InvalidInterviewError(
                    f"answer for {self.id} is shorter than the minimum length"
                )
            if (
                self.validation.max_length is not None
                and len(normalized) > self.validation.max_length
            ):
                raise InvalidInterviewError(f"answer for {self.id} exceeds the maximum length")
            return normalized
        if self.type is QuestionType.SINGLE_CHOICE:
            if not isinstance(value, str) or value not in {
                str(option.id) for option in self.options
            }:
                raise InvalidInterviewError(f"answer for {self.id} must select one declared option")
            return value
        if self.type is QuestionType.MULTI_CHOICE:
            if not isinstance(value, (tuple, list)) or not all(
                isinstance(item, str) for item in value
            ):
                raise InvalidInterviewError(f"answer for {self.id} must select declared options")
            normalized_choices = tuple(value)
            if len(set(normalized_choices)) != len(normalized_choices):
                raise InvalidInterviewError(f"answer for {self.id} cannot repeat an option")
            valid_options = {str(option.id) for option in self.options}
            if not set(normalized_choices).issubset(valid_options):
                raise InvalidInterviewError(f"answer for {self.id} contains an undeclared option")
            return normalized_choices
        if self.type is QuestionType.BOOLEAN:
            if not isinstance(value, bool):
                raise InvalidInterviewError(f"answer for {self.id} must be boolean")
            return value
        if self.type is QuestionType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidInterviewError(f"answer for {self.id} must be an integer")
            numeric: int | float = value
        else:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise InvalidInterviewError(f"answer for {self.id} must be a number")
            numeric = value
        if isinstance(numeric, float) and not math.isfinite(numeric):
            raise InvalidInterviewError(f"answer for {self.id} must be finite")
        if self.validation.min_value is not None and numeric < self.validation.min_value:
            raise InvalidInterviewError(f"answer for {self.id} is below the minimum value")
        if self.validation.max_value is not None and numeric > self.validation.max_value:
            raise InvalidInterviewError(f"answer for {self.id} exceeds the maximum value")
        return numeric


@dataclass(frozen=True, slots=True)
class Questionnaire:
    """Ordered, acyclic collection of questions used by an interview."""

    id: QuestionnaireId
    title: DisplayName
    questions: tuple[Question, ...]

    def __post_init__(self) -> None:
        if not self.questions:
            raise InvalidInterviewError("a questionnaire requires at least one question")
        question_ids = [question.id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise InvalidInterviewError("a questionnaire cannot contain duplicate question IDs")
        question_map = {question.id: question for question in self.questions}
        for question in self.questions:
            dependency_ids = [dependency.question_id for dependency in question.dependencies]
            if len(dependency_ids) != len(set(dependency_ids)):
                raise InvalidInterviewError(
                    f"question {question.id} contains duplicate dependencies"
                )
            for dependency in question.dependencies:
                target = question_map.get(dependency.question_id)
                if target is None:
                    raise InvalidInterviewError(
                        f"question {question.id} depends on unknown question "
                        f"{dependency.question_id}"
                    )
                if dependency.operator in (
                    DependencyOperator.CONTAINS,
                    DependencyOperator.NOT_CONTAINS,
                ):
                    if (
                        target.type is not QuestionType.MULTI_CHOICE
                        or not isinstance(dependency.expected, str)
                        or dependency.expected not in {str(option.id) for option in target.options}
                    ):
                        raise InvalidInterviewError(
                            "contains dependencies require a declared multi-choice option"
                        )
                elif target.type is QuestionType.MULTI_CHOICE:
                    raise InvalidInterviewError(
                        "multi-choice dependencies must use contains operators"
                    )
                else:
                    target.validate_answer(dependency.expected)
        self._assert_acyclic(question_map)

    @staticmethod
    def _assert_acyclic(question_map: dict[QuestionId, Question]) -> None:
        visiting: set[QuestionId] = set()
        visited: set[QuestionId] = set()

        def visit(question_id: QuestionId) -> None:
            if question_id in visiting:
                raise InvalidInterviewError("question dependencies cannot contain cycles")
            if question_id in visited:
                return
            visiting.add(question_id)
            for dependency in question_map[question_id].dependencies:
                visit(dependency.question_id)
            visiting.remove(question_id)
            visited.add(question_id)

        for question_id in question_map:
            visit(question_id)

    def question(self, question_id: QuestionId) -> Question:
        for question in self.questions:
            if question.id == question_id:
                return question
        raise InvalidInterviewError(f"unknown question {question_id}")


@dataclass(frozen=True, slots=True)
class AnswerProvenance:
    """Origin metadata retained with every answer."""

    source: AnswerSource
    recorded_at: datetime
    actor: str | None = None
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise InvalidInterviewError("answer provenance requires a timezone-aware timestamp")
        if self.recorded_at.utcoffset() != timedelta(0):
            raise InvalidInterviewError("answer provenance timestamps must be normalized to UTC")
        if self.actor is not None:
            _validate_text(self.actor, "answer provenance actor", 120)
        if self.source_ref is not None:
            _validate_text(self.source_ref, "answer provenance source reference", 2_048)


@dataclass(frozen=True, slots=True)
class AnswerRecord:
    """One validated answer plus its immutable provenance."""

    question_id: QuestionId
    value: AnswerValue
    provenance: AnswerProvenance


@dataclass(frozen=True, slots=True)
class BlockedQuestion:
    """A question whose dependencies are not answered yet."""

    question_id: QuestionId
    unresolved_dependencies: tuple[QuestionId, ...]
    required: bool


@dataclass(frozen=True, slots=True)
class PendingQuestions:
    """Deterministic interview progress projection."""

    pending: tuple[QuestionId, ...]
    required_pending: tuple[QuestionId, ...]
    blocked: tuple[BlockedQuestion, ...]
    not_applicable: tuple[QuestionId, ...]
    answered: tuple[QuestionId, ...]

    @property
    def is_complete(self) -> bool:
        return not self.required_pending and not any(item.required for item in self.blocked)

    @property
    def next_question(self) -> QuestionId | None:
        if self.required_pending:
            return self.required_pending[0]
        return self.pending[0] if self.pending else None


@dataclass(frozen=True, slots=True)
class InterviewSession:
    """Immutable answer set that can be safely replaced by each command."""

    questionnaire: Questionnaire
    answers: tuple[AnswerRecord, ...] = ()

    def __post_init__(self) -> None:
        answer_ids = [answer.question_id for answer in self.answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise InvalidInterviewError("an interview cannot contain duplicate answers")
        for answer in self.answers:
            self.questionnaire.question(answer.question_id).validate_answer(answer.value)

    def record_answer(
        self,
        question_id: QuestionId,
        value: object,
        provenance: AnswerProvenance,
    ) -> InterviewSession:
        question = self.questionnaire.question(question_id)
        normalized = question.validate_answer(value)
        replacement = AnswerRecord(question_id, normalized, provenance)
        answers = tuple(
            replacement if answer.question_id == question_id else answer for answer in self.answers
        )
        if all(answer.question_id != question_id for answer in self.answers):
            answers += (replacement,)
        return InterviewSession(self.questionnaire, answers)

    def pending_questions(self) -> PendingQuestions:
        answer_map = {answer.question_id: answer.value for answer in self.answers}
        pending: list[QuestionId] = []
        required_pending: list[QuestionId] = []
        blocked: list[BlockedQuestion] = []
        not_applicable: list[QuestionId] = []
        answered: list[QuestionId] = []
        for question in self.questionnaire.questions:
            if question.id in answer_map:
                answered.append(question.id)
                continue
            unresolved = tuple(
                dependency.question_id
                for dependency in question.dependencies
                if dependency.question_id not in answer_map
            )
            if unresolved:
                blocked.append(BlockedQuestion(question.id, unresolved, question.required))
                continue
            if any(
                not dependency.matches(answer_map[dependency.question_id])
                for dependency in question.dependencies
            ):
                not_applicable.append(question.id)
                continue
            pending.append(question.id)
            if question.required:
                required_pending.append(question.id)
        return PendingQuestions(
            pending=tuple(pending),
            required_pending=tuple(required_pending),
            blocked=tuple(blocked),
            not_applicable=tuple(not_applicable),
            answered=tuple(answered),
        )
