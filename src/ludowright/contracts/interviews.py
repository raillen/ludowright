"""Versioned contracts for declarative guided-interview questionnaires."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ludowright.contracts.common import ContractModel, DisplayText, Sha256Text, Slug
from ludowright.domain import (
    AnswerProvenance,
    AnswerRecord,
    AnswerSource,
    DependencyOperator,
    DisplayName,
    DispositionRecord,
    InterviewSession,
    InterviewSessionId,
    OptionId,
    Question,
    QuestionDependency,
    QuestionDisposition,
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

    @classmethod
    def from_domain(cls, value: QuestionOption) -> Self:
        return cls(id=value.id.value, label=value.label.value)


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

    @classmethod
    def from_domain(cls, value: QuestionValidation) -> Self:
        return cls(
            min_length=value.min_length,
            max_length=value.max_length,
            min_value=value.min_value,
            max_value=value.max_value,
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

    @classmethod
    def from_domain(cls, value: QuestionDependency) -> Self:
        return cls(
            question_id=value.question_id.value,
            operator=value.operator,
            expected=value.expected,
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

    @classmethod
    def from_domain(cls, value: Question) -> Self:
        return cls(
            id=value.id.value,
            prompt=value.prompt,
            type=value.type,
            required=value.required,
            options=tuple(QuestionOptionContract.from_domain(item) for item in value.options),
            dependencies=tuple(
                QuestionDependencyContract.from_domain(item) for item in value.dependencies
            ),
            validation=QuestionValidationContract.from_domain(value.validation),
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

    @classmethod
    def from_domain(cls, value: Questionnaire) -> Self:
        return cls(
            id=value.id.value,
            title=value.title.value,
            questions=tuple(QuestionContract.from_domain(item) for item in value.questions),
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

    @classmethod
    def from_domain(cls, value: AnswerProvenance) -> Self:
        return cls(
            source=value.source,
            recorded_at=value.recorded_at,
            actor=value.actor,
            source_ref=value.source_ref,
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

    @classmethod
    def from_domain(cls, value: AnswerRecord) -> Self:
        return cls(
            question_id=value.question_id.value,
            value=value.value,
            provenance=AnswerProvenanceContract.from_domain(value.provenance),
        )


class DispositionRecordContract(ContractModel):
    question_id: Slug
    disposition: QuestionDisposition
    provenance: AnswerProvenanceContract

    def to_domain(self) -> DispositionRecord:
        return DispositionRecord(
            question_id=QuestionId(self.question_id),
            disposition=self.disposition,
            provenance=self.provenance.to_domain(),
        )

    @classmethod
    def from_domain(cls, value: DispositionRecord) -> Self:
        return cls(
            question_id=value.question_id.value,
            disposition=value.disposition,
            provenance=AnswerProvenanceContract.from_domain(value.provenance),
        )


class InterviewSessionContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["interview-session"] = "interview-session"
    id: Slug
    questionnaire_digest: Sha256Text
    questionnaire: QuestionnaireContract
    answers: Annotated[tuple[AnswerRecordContract, ...], Field(max_length=1_024)] = ()
    dispositions: Annotated[tuple[DispositionRecordContract, ...], Field(max_length=1_024)] = ()

    def to_domain(self) -> InterviewSession:
        questionnaire = self.questionnaire.to_domain()
        return InterviewSession(
            questionnaire=questionnaire,
            answers=tuple(answer.to_domain() for answer in self.answers),
            dispositions=tuple(item.to_domain() for item in self.dispositions),
        )

    @classmethod
    def from_domain(
        cls,
        value: InterviewSession,
        *,
        session_id: InterviewSessionId,
        questionnaire_digest: str,
    ) -> Self:
        if not isinstance(session_id, InterviewSessionId):
            raise TypeError("interview session serialization requires InterviewSessionId")
        return cls(
            id=session_id.value,
            questionnaire_digest=questionnaire_digest,
            questionnaire=QuestionnaireContract.from_domain(value.questionnaire),
            answers=tuple(AnswerRecordContract.from_domain(item) for item in value.answers),
            dispositions=tuple(
                DispositionRecordContract.from_domain(item) for item in value.dispositions
            ),
        )

    @model_validator(mode="after")
    def validate_session(self) -> Self:
        self.to_domain()
        return self


class InterviewQuestionViewContract(ContractModel):
    """Question projection returned by the interactive CLI."""

    id: Slug
    prompt: QuestionPrompt
    type: QuestionType
    required: StrictBool
    options: Annotated[tuple[QuestionOptionContract, ...], Field(max_length=128)] = ()


class InterviewBlockedQuestionContract(ContractModel):
    question_id: Slug
    unresolved_dependencies: Annotated[tuple[Slug, ...], Field(max_length=64)]
    required: StrictBool


class InterviewProgressContract(ContractModel):
    pending: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    required_pending: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    blocked: Annotated[tuple[InterviewBlockedQuestionContract, ...], Field(max_length=1_024)]
    not_applicable: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    answered: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    skipped: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    deferred: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    required_skipped: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    required_deferred: Annotated[tuple[Slug, ...], Field(max_length=1_024)]
    complete: StrictBool
    next_question: Slug | None = None


class InterviewInteractionContract(ContractModel):
    """Command-specific data carried inside the published CLI envelope."""

    schema_version: Literal[1] = 1
    kind: Literal["interview-interaction"] = "interview-interaction"
    session_id: Slug
    questionnaire_id: Slug
    operation: Literal["next", "answer", "skip", "defer"]
    changed: StrictBool
    question: InterviewQuestionViewContract | None = None
    progress: InterviewProgressContract
