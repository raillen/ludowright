"""Versioned contracts for declarative guided-interview questionnaires."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ludowright.contracts.common import ContractModel, DisplayText, Slug
from ludowright.domain import (
    AnswerProvenance,
    AnswerRecord,
    AnswerSource,
    DependencyOperator,
    DisplayName,
    InterviewSession,
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

QuestionPrompt = Annotated[str, Field(min_length=1, max_length=4_000)]
DependencyValue = StrictStr | StrictBool | StrictInt | StrictFloat
AnswerValue = DependencyValue | tuple[StrictStr, ...]


class QuestionOptionContract(ContractModel):
    id: Slug
    label: DisplayText

    def to_domain(self) -> QuestionOption:
        return QuestionOption(id=OptionId(self.id), label=DisplayName(self.label))


class QuestionValidationContract(ContractModel):
    min_length: Annotated[int, Field(ge=0, le=4_000)] | None = None
    max_length: Annotated[int, Field(ge=0, le=4_000)] | None = None
    min_value: StrictInt | StrictFloat | None = None
    max_value: StrictInt | StrictFloat | None = None

    def to_domain(self) -> QuestionValidation:
        return QuestionValidation(
            min_length=self.min_length,
            max_length=self.max_length,
            min_value=self.min_value,
            max_value=self.max_value,
        )


class QuestionDependencyContract(ContractModel):
    question_id: Slug
    operator: DependencyOperator
    expected: DependencyValue

    def to_domain(self) -> QuestionDependency:
        return QuestionDependency(
            question_id=QuestionId(self.question_id),
            operator=self.operator,
            expected=self.expected,
        )


class QuestionContract(ContractModel):
    id: Slug
    prompt: QuestionPrompt
    type: QuestionType
    required: StrictBool = True
    options: Annotated[tuple[QuestionOptionContract, ...], Field(max_length=128)] = ()
    dependencies: Annotated[tuple[QuestionDependencyContract, ...], Field(max_length=64)] = ()
    validation: QuestionValidationContract = QuestionValidationContract()

    def to_domain(self) -> Question:
        return Question(
            id=QuestionId(self.id),
            prompt=self.prompt,
            type=self.type,
            required=self.required,
            options=tuple(option.to_domain() for option in self.options),
            dependencies=tuple(dependency.to_domain() for dependency in self.dependencies),
            validation=self.validation.to_domain(),
        )


class QuestionnaireContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["interview-questionnaire"] = "interview-questionnaire"
    id: Slug
    title: DisplayText
    questions: Annotated[tuple[QuestionContract, ...], Field(min_length=1, max_length=1_024)]

    def to_domain(self) -> Questionnaire:
        return Questionnaire(
            id=QuestionnaireId(self.id),
            title=DisplayName(self.title),
            questions=tuple(question.to_domain() for question in self.questions),
        )

    @model_validator(mode="after")
    def validate_questionnaire(self) -> Self:
        self.to_domain()
        return self


class AnswerProvenanceContract(ContractModel):
    source: AnswerSource
    recorded_at: datetime
    actor: DisplayText | None = None
    source_ref: Annotated[str, Field(min_length=1, max_length=2_048)] | None = None

    def to_domain(self) -> AnswerProvenance:
        return AnswerProvenance(
            source=self.source,
            recorded_at=self.recorded_at,
            actor=self.actor,
            source_ref=self.source_ref,
        )


class AnswerRecordContract(ContractModel):
    question_id: Slug
    value: AnswerValue
    provenance: AnswerProvenanceContract

    def to_domain(self) -> AnswerRecord:
        return AnswerRecord(
            question_id=QuestionId(self.question_id),
            value=self.value,
            provenance=self.provenance.to_domain(),
        )


class InterviewSessionContract(ContractModel):
    """Non-published adapter used by future CLI and state-store integrations."""

    questionnaire: QuestionnaireContract
    answers: Annotated[tuple[AnswerRecordContract, ...], Field(max_length=1_024)] = ()

    def to_domain(self) -> InterviewSession:
        questionnaire = self.questionnaire.to_domain()
        return InterviewSession(
            questionnaire=questionnaire,
            answers=tuple(answer.to_domain() for answer in self.answers),
        )

    @model_validator(mode="after")
    def validate_session(self) -> Self:
        self.to_domain()
        return self
