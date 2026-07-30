"""Application orchestration for resumable interview CLI commands."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ludowright.contracts.interviews import (
    InterviewSessionContract,
    QuestionnaireContract,
)
from ludowright.domain import (
    AnswerProvenance,
    AnswerSource,
    CorrelationId,
    EventDraft,
    EventType,
    FrozenJsonValue,
    InterviewSession,
    InterviewSessionId,
    PendingQuestions,
    Question,
    QuestionId,
    Questionnaire,
)
from ludowright.infrastructure import (
    EventLog,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StructuredDocumentConflictError,
    StructuredDocumentParseError,
    StructuredDocumentSnapshot,
)

DEFAULT_SESSION_DIRECTORY = RepositoryPath(".ludowright/interviews")
_SESSION_MAX_BYTES = 8 * 1024 * 1024
type InterviewOperation = Literal["next", "answer", "skip", "defer"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InterviewApplicationError(RuntimeError):
    """Raised when a session cannot be safely persisted or reconciled."""


@dataclass(frozen=True, slots=True)
class InterviewView:
    """Pure application result consumed by human and JSON CLI renderers."""

    session_id: InterviewSessionId
    questionnaire_id: str
    operation: InterviewOperation
    changed: bool
    question: Question | None
    progress: PendingQuestions


class InterviewService:
    """Coordinate questionnaire loading, session snapshots, and event facts."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        questionnaire_path: RepositoryPath,
        session_id: InterviewSessionId,
        *,
        event_log: EventLog | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("interview service requires ProjectFilesystem")
        if not isinstance(questionnaire_path, RepositoryPath):
            raise TypeError("interview service requires RepositoryPath")
        if not isinstance(session_id, InterviewSessionId):
            raise TypeError("interview service requires InterviewSessionId")
        self._filesystem = filesystem
        self._questionnaire_path = questionnaire_path
        self._session_id = session_id
        self._event_log = event_log or EventLog(filesystem)
        self._clock = clock

    @property
    def session_path(self) -> RepositoryPath:
        """Return the canonical repository-relative session path."""
        return DEFAULT_SESSION_DIRECTORY.child(f"{self._session_id.value}.json")

    def next_question(self) -> InterviewView:
        """Read current progress without creating or mutating a session."""
        questionnaire, session, _snapshot, _questionnaire_digest = self._load_state()
        progress = session.pending_questions()
        question = (
            questionnaire.question(progress.next_question) if progress.next_question else None
        )
        return InterviewView(
            session_id=self._session_id,
            questionnaire_id=questionnaire.id.value,
            operation="next",
            changed=False,
            question=question,
            progress=progress,
        )

    def answer(
        self,
        question_id: QuestionId,
        value: object,
        *,
        source: AnswerSource = AnswerSource.HUMAN,
        actor: str | None = None,
    ) -> InterviewView:
        """Validate, persist, and audit one answer."""
        recorded_at = self._clock()
        provenance = AnswerProvenance(source, recorded_at, actor=actor)
        return self._mutate(
            operation="answer",
            question_id=question_id,
            provenance=provenance,
            mutate=lambda session: session.record_answer(question_id, value, provenance),
            event_type="interview.answer-recorded",
            event_payload={
                "question_id": question_id.value,
                "value": _event_value(value),
                "source": source.value,
            },
        )

    def skip(
        self,
        question_id: QuestionId,
        *,
        source: AnswerSource = AnswerSource.HUMAN,
        actor: str | None = None,
    ) -> InterviewView:
        """Persist the conservative optional-only skip policy."""
        recorded_at = self._clock()
        provenance = AnswerProvenance(source, recorded_at, actor=actor)
        return self._mutate(
            operation="skip",
            question_id=question_id,
            provenance=provenance,
            mutate=lambda session: session.skip_question(question_id, provenance),
            event_type="interview.question-skipped",
            event_payload={"question_id": question_id.value, "source": source.value},
        )

    def defer(
        self,
        question_id: QuestionId,
        *,
        source: AnswerSource = AnswerSource.HUMAN,
        actor: str | None = None,
    ) -> InterviewView:
        """Persist a defer decision while keeping required work incomplete."""
        recorded_at = self._clock()
        provenance = AnswerProvenance(source, recorded_at, actor=actor)
        return self._mutate(
            operation="defer",
            question_id=question_id,
            provenance=provenance,
            mutate=lambda session: session.defer_question(question_id, provenance),
            event_type="interview.question-deferred",
            event_payload={"question_id": question_id.value, "source": source.value},
        )

    def _mutate(
        self,
        *,
        operation: InterviewOperation,
        question_id: QuestionId,
        provenance: AnswerProvenance,
        mutate: Callable[[InterviewSession], InterviewSession],
        event_type: str,
        event_payload: Mapping[str, FrozenJsonValue],
    ) -> InterviewView:
        with self._filesystem.lock(self._session_id.value, timeout=5.0):
            questionnaire, session, prior_snapshot, questionnaire_digest = self._load_state()
            updated = mutate(session)
            changed = updated != session
            if changed:
                self._persist_with_event(
                    session=updated,
                    questionnaire_digest=questionnaire_digest,
                    prior_snapshot=prior_snapshot,
                    event_type=event_type,
                    occurred_at=provenance.recorded_at,
                    event_payload={
                        **event_payload,
                        "session_id": self._session_id.value,
                        "recorded_at": _format_timestamp(provenance.recorded_at),
                    },
                )
            progress = updated.pending_questions()
            question = (
                questionnaire.question(progress.next_question) if progress.next_question else None
            )
            return InterviewView(
                session_id=self._session_id,
                questionnaire_id=questionnaire.id.value,
                operation=operation,
                changed=changed,
                question=question,
                progress=progress,
            )

    def _load_state(
        self,
    ) -> tuple[
        Questionnaire,
        InterviewSession,
        StructuredDocumentSnapshot[InterviewSessionContract] | None,
        str,
    ]:
        questionnaire_snapshot = self._load_questionnaire()
        questionnaire = questionnaire_snapshot.value.to_domain()
        session_repository = self._session_repository()
        try:
            session_snapshot = session_repository.load_optional()
        except ValueError as error:
            raise StructuredDocumentParseError(
                f"interview session could not be parsed: {self.session_path}"
            ) from error
        if session_snapshot is None:
            return (
                questionnaire,
                InterviewSession(questionnaire),
                None,
                questionnaire_snapshot.digest,
            )
        if session_snapshot.value.questionnaire_digest != questionnaire_snapshot.digest:
            raise StructuredDocumentConflictError(
                "questionnaire changed after this interview session was created"
            )
        return (
            questionnaire,
            session_snapshot.value.to_domain(),
            session_snapshot,
            questionnaire_snapshot.digest,
        )

    def _load_questionnaire(self) -> StructuredDocumentSnapshot[QuestionnaireContract]:
        try:
            return JsonDocumentRepository(
                self._filesystem,
                self._questionnaire_path,
                QuestionnaireContract,
                max_bytes=_SESSION_MAX_BYTES,
            ).load()
        except FileNotFoundError as error:
            raise StructuredDocumentParseError(
                f"questionnaire file does not exist: {self._questionnaire_path}"
            ) from error
        except ValueError as error:
            raise StructuredDocumentParseError(
                f"questionnaire document is invalid: {self._questionnaire_path}"
            ) from error

    def _session_repository(self) -> JsonDocumentRepository[InterviewSessionContract]:
        return JsonDocumentRepository(
            self._filesystem,
            self.session_path,
            InterviewSessionContract,
            max_bytes=_SESSION_MAX_BYTES,
        )

    def _persist_with_event(
        self,
        *,
        session: InterviewSession,
        questionnaire_digest: str,
        prior_snapshot: StructuredDocumentSnapshot[InterviewSessionContract] | None,
        event_type: str,
        occurred_at: datetime,
        event_payload: Mapping[str, FrozenJsonValue],
    ) -> None:
        repository = self._session_repository()
        previous_bytes: bytes | None = None
        if prior_snapshot is not None:
            previous_bytes = self._filesystem.read_bytes(self.session_path)
        contract = InterviewSessionContract.from_domain(
            session,
            session_id=self._session_id,
            questionnaire_digest=questionnaire_digest,
        )
        try:
            if prior_snapshot is None:
                repository.create(contract)
            else:
                repository.save(contract, expected_digest=prior_snapshot.digest)
            self._event_log.append(
                EventDraft(
                    event_type=EventType(event_type),
                    correlation_id=CorrelationId(self._session_id.value),
                    payload=event_payload,
                ),
                occurred_at=occurred_at,
            )
        except BaseException as error:
            try:
                if previous_bytes is None:
                    self._filesystem.remove_file(self.session_path)
                else:
                    self._filesystem.write_bytes(self.session_path, previous_bytes)
            except BaseException as rollback_error:
                raise InterviewApplicationError(
                    f"interview session rollback failed after persistence error: {rollback_error}"
                ) from error
            raise


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _event_value(value: object) -> FrozenJsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return tuple(_event_value(item) for item in value)
    raise TypeError(f"unsupported interview event value: {type(value).__name__}")
