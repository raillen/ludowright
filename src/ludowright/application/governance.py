"""Application workflows for immutable decisions, approvals, and audit events."""

from __future__ import annotations

from pathlib import Path

from ludowright.contracts import ApprovalContract, DecisionContract
from ludowright.contracts.governance import ApprovalSubjectContract, ApprovalSubjectKind
from ludowright.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
    CorrelationId,
    Decision,
    DecisionId,
    DecisionStatus,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DisplayName,
    DomainValidationError,
    EventDraft,
    EventType,
    FrozenJsonValue,
    ReviewNote,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_STATE_STORE_PATH,
    ApprovalRepository,
    ApprovalSnapshot,
    DecisionRepository,
    DecisionSnapshot,
    DependencyGraphRepository,
    EventLog,
    ProjectFilesystem,
    ProjectFilesystemError,
    StateStore,
    StateStoreError,
)
from ludowright.infrastructure.dependency_graph import DependencyGraphSnapshot

_GOVERNANCE_LOCK = "governance-write"
_GOVERNANCE_LOCK_TIMEOUT = 5.0


class GovernanceInputError(DomainValidationError):
    """Raised when application input cannot form a canonical governance record."""


class GovernanceStateError(RuntimeError):
    """Raised when canonical governance state cannot be coordinated safely."""


class GovernanceOperationError(RuntimeError):
    """Raised after a failed mutation was rolled back or could not be rolled back."""


class GovernanceService:
    """Coordinate canonical governance documents, graph nodes, and event history."""

    def record_decision(
        self,
        project: Path | str,
        *,
        decision_id: str,
        title: str,
        note: str | None = None,
    ) -> dict[str, object]:
        identifier = _decision_id(decision_id)
        decision = Decision.propose(identifier, DisplayName(title), _review_note(note))
        filesystem = _discover(project)
        with filesystem.lock(_GOVERNANCE_LOCK, timeout=_GOVERNANCE_LOCK_TIMEOUT):
            repository = DecisionRepository(filesystem)
            snapshot = repository.create(decision)
            event = self._commit_decision(
                filesystem,
                repository,
                before=None,
                after=snapshot,
                operation="recorded",
            )
        return _decision_result(filesystem, snapshot, event[0], event[1])

    def list_decisions(self, project: Path | str) -> dict[str, object]:
        filesystem = _discover(project)
        decisions = DecisionRepository(filesystem).list()
        return {
            "project_directory": filesystem.root.as_posix(),
            "decisions": [_decision_summary(item) for item in decisions],
        }

    def inspect_decision(
        self,
        project: Path | str,
        *,
        decision_id: str,
    ) -> dict[str, object]:
        filesystem = _discover(project)
        snapshot = DecisionRepository(filesystem).load(_decision_id(decision_id))
        return {
            "project_directory": filesystem.root.as_posix(),
            "path": snapshot.path.value,
            "decision": DecisionContract.from_domain(snapshot.decision).model_dump(mode="json"),
        }

    def transition_decision(
        self,
        project: Path | str,
        *,
        decision_id: str,
        status: DecisionStatus,
        note: str | None = None,
    ) -> dict[str, object]:
        if status not in {
            DecisionStatus.ACCEPTED,
            DecisionStatus.REJECTED,
            DecisionStatus.WITHDRAWN,
        }:
            raise GovernanceInputError(
                "decision transitions support accepted, rejected, or withdrawn"
            )
        filesystem = _discover(project)
        with filesystem.lock(_GOVERNANCE_LOCK, timeout=_GOVERNANCE_LOCK_TIMEOUT):
            repository = DecisionRepository(filesystem)
            before = repository.load(_decision_id(decision_id))
            after_decision = _transition_decision(before.decision, status, _review_note(note))
            if after_decision is before.decision:
                return _decision_result(filesystem, before, None, ())
            after = repository.replace(before, after_decision)
            event = self._commit_decision(
                filesystem,
                repository,
                before=before,
                after=after,
                operation="transitioned",
                previous_status=before.decision.status.value,
            )
        return _decision_result(filesystem, after, event[0], event[1])

    def supersede_decision(
        self,
        project: Path | str,
        *,
        decision_id: str,
        replacement_id: str,
        note: str | None = None,
    ) -> dict[str, object]:
        identifier = _decision_id(decision_id)
        replacement = _decision_id(replacement_id)
        filesystem = _discover(project)
        with filesystem.lock(_GOVERNANCE_LOCK, timeout=_GOVERNANCE_LOCK_TIMEOUT):
            repository = DecisionRepository(filesystem)
            before = repository.load(identifier)
            replacement_snapshot = repository.load(replacement)
            after_decision = before.decision.supersede(replacement, _review_note(note))
            after = repository.replace(before, after_decision)
            event = self._commit_decision(
                filesystem,
                repository,
                before=before,
                after=after,
                operation="superseded",
                previous_status=before.decision.status.value,
                replacement_id=replacement_snapshot.decision.id.value,
            )
        return _decision_result(filesystem, after, event[0], event[1])

    def request_approval(
        self,
        project: Path | str,
        *,
        approval_id: str,
        subject_kind: str,
        subject_id: str,
        revision: str,
        label: str | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        identifier = _approval_id(approval_id)
        try:
            subject = ApprovalSubjectContract(
                subject_kind=ApprovalSubjectKind(subject_kind),
                id=subject_id,
                revision=revision,
                label=label,
            ).to_domain()
        except (TypeError, ValueError) as error:
            raise GovernanceInputError(f"invalid approval subject: {error}") from error
        approval = Approval.request(identifier, subject, _review_note(note))
        filesystem = _discover(project)
        with filesystem.lock(_GOVERNANCE_LOCK, timeout=_GOVERNANCE_LOCK_TIMEOUT):
            repository = ApprovalRepository(filesystem)
            snapshot = repository.create(approval)
            event = self._commit_approval(
                filesystem,
                repository,
                before=None,
                after=snapshot,
                operation="requested",
            )
        return _approval_result(filesystem, snapshot, event[0], event[1])

    def list_approvals(self, project: Path | str) -> dict[str, object]:
        filesystem = _discover(project)
        approvals = ApprovalRepository(filesystem).list()
        return {
            "project_directory": filesystem.root.as_posix(),
            "approvals": [_approval_summary(item) for item in approvals],
        }

    def inspect_approval(
        self,
        project: Path | str,
        *,
        approval_id: str,
    ) -> dict[str, object]:
        filesystem = _discover(project)
        snapshot = ApprovalRepository(filesystem).load(_approval_id(approval_id))
        return {
            "project_directory": filesystem.root.as_posix(),
            "path": snapshot.path.value,
            "approval": ApprovalContract.from_domain(snapshot.approval).model_dump(mode="json"),
        }

    def transition_approval(
        self,
        project: Path | str,
        *,
        approval_id: str,
        status: ApprovalStatus,
        note: str | None = None,
    ) -> dict[str, object]:
        if status in {ApprovalStatus.PENDING, ApprovalStatus.SUPERSEDED}:
            raise GovernanceInputError(
                "approval transitions do not accept pending or superseded as a target"
            )
        filesystem = _discover(project)
        with filesystem.lock(_GOVERNANCE_LOCK, timeout=_GOVERNANCE_LOCK_TIMEOUT):
            repository = ApprovalRepository(filesystem)
            before = repository.load(_approval_id(approval_id))
            after_approval = _transition_approval(before.approval, status, _review_note(note))
            if after_approval is before.approval:
                return _approval_result(filesystem, before, None, ())
            after = repository.replace(before, after_approval)
            event = self._commit_approval(
                filesystem,
                repository,
                before=before,
                after=after,
                operation="transitioned",
                previous_status=before.approval.status.value,
            )
        return _approval_result(filesystem, after, event[0], event[1])

    def supersede_approval(
        self,
        project: Path | str,
        *,
        approval_id: str,
        replacement_id: str,
        note: str | None = None,
    ) -> dict[str, object]:
        identifier = _approval_id(approval_id)
        replacement = _approval_id(replacement_id)
        filesystem = _discover(project)
        with filesystem.lock(_GOVERNANCE_LOCK, timeout=_GOVERNANCE_LOCK_TIMEOUT):
            repository = ApprovalRepository(filesystem)
            before = repository.load(identifier)
            replacement_snapshot = repository.load(replacement)
            after_approval = before.approval.supersede(replacement, _review_note(note))
            after = repository.replace(before, after_approval)
            event = self._commit_approval(
                filesystem,
                repository,
                before=before,
                after=after,
                operation="superseded",
                previous_status=before.approval.status.value,
                replacement_id=replacement_snapshot.approval.id.value,
            )
        return _approval_result(filesystem, after, event[0], event[1])

    def _commit_decision(
        self,
        filesystem: ProjectFilesystem,
        repository: DecisionRepository,
        *,
        before: DecisionSnapshot | None,
        after: DecisionSnapshot,
        operation: str,
        previous_status: str | None = None,
        replacement_id: str | None = None,
    ) -> tuple[int, tuple[str, ...]]:
        graph_repository = DependencyGraphRepository(filesystem)
        graph_before: DependencyGraphSnapshot | None = None
        graph_written = False
        try:
            graph_before = graph_repository.load()
            graph_after = _advance_graph(
                graph_before,
                DependencyNodeKind.DECISION,
                after.decision.id.value,
                len(after.decision.history),
            )
            if graph_after != graph_before.graph:
                graph_repository.replace(graph_before, graph_after)
                graph_written = True
            event = _append_event(
                filesystem,
                entity_kind="decision",
                entity_id=after.decision.id.value,
                operation=operation,
                status=after.decision.status.value,
                history_sequence=len(after.decision.history),
                previous_status=previous_status,
                replacement_id=replacement_id,
                note=after.decision.current.note,
            )
            warnings = _update_state_checkpoint(filesystem)
        except BaseException as error:
            try:
                if before is None:
                    repository.remove(after)
                else:
                    repository.replace(after, before.decision)
                if graph_written and graph_before is not None:
                    graph_repository.save(graph_before.graph)
            except BaseException as rollback_error:
                raise GovernanceOperationError(
                    "decision operation failed and rollback also failed"
                ) from rollback_error
            raise GovernanceOperationError("decision operation was rolled back") from error
        return event, warnings

    def _commit_approval(
        self,
        filesystem: ProjectFilesystem,
        repository: ApprovalRepository,
        *,
        before: ApprovalSnapshot | None,
        after: ApprovalSnapshot,
        operation: str,
        previous_status: str | None = None,
        replacement_id: str | None = None,
    ) -> tuple[int, tuple[str, ...]]:
        graph_repository = DependencyGraphRepository(filesystem)
        graph_before: DependencyGraphSnapshot | None = None
        graph_written = False
        try:
            graph_before = graph_repository.load()
            graph_after = _advance_graph(
                graph_before,
                DependencyNodeKind.APPROVAL,
                after.approval.id.value,
                len(after.approval.history),
            )
            if graph_after != graph_before.graph:
                graph_repository.replace(graph_before, graph_after)
                graph_written = True
            event = _append_event(
                filesystem,
                entity_kind="approval",
                entity_id=after.approval.id.value,
                operation=operation,
                status=after.approval.status.value,
                history_sequence=len(after.approval.history),
                previous_status=previous_status,
                replacement_id=replacement_id,
                note=after.approval.current.note,
                subject_revision=after.approval.subject.revision.value,
            )
            warnings = _update_state_checkpoint(filesystem)
        except BaseException as error:
            try:
                if before is None:
                    repository.remove(after)
                else:
                    repository.replace(after, before.approval)
                if graph_written and graph_before is not None:
                    graph_repository.save(graph_before.graph)
            except BaseException as rollback_error:
                raise GovernanceOperationError(
                    "approval operation failed and rollback also failed"
                ) from rollback_error
            raise GovernanceOperationError("approval operation was rolled back") from error
        return event, warnings


def _discover(project: Path | str) -> ProjectFilesystem:
    try:
        return ProjectFilesystem.discover(project)
    except (TypeError, OSError) as error:
        raise GovernanceInputError("project path is invalid") from error


def _decision_id(value: str) -> DecisionId:
    try:
        return DecisionId(value)
    except (TypeError, ValueError) as error:
        raise GovernanceInputError(f"invalid decision ID: {value!r}") from error


def _approval_id(value: str) -> ApprovalId:
    try:
        return ApprovalId(value)
    except (TypeError, ValueError) as error:
        raise GovernanceInputError(f"invalid approval ID: {value!r}") from error


def _review_note(value: str | None) -> ReviewNote | None:
    if value is None:
        return None
    try:
        return ReviewNote(value)
    except ValueError as error:
        raise GovernanceInputError(str(error)) from error


def _transition_decision(
    decision: Decision,
    status: DecisionStatus,
    note: ReviewNote | None,
) -> Decision:
    if status is DecisionStatus.ACCEPTED:
        return decision.accept(note)
    if status is DecisionStatus.REJECTED:
        return decision.reject(note)
    return decision.withdraw(note)


def _transition_approval(
    approval: Approval,
    status: ApprovalStatus,
    note: ReviewNote | None,
) -> Approval:
    transitions = {
        ApprovalStatus.APPROVED: approval.approve,
        ApprovalStatus.CHANGES_REQUESTED: approval.request_changes,
        ApprovalStatus.REJECTED: approval.reject,
        ApprovalStatus.WITHDRAWN: approval.withdraw,
        ApprovalStatus.REVOKED: approval.revoke,
    }
    return transitions[status](note)


def _advance_graph(
    snapshot: DependencyGraphSnapshot,
    kind: DependencyNodeKind,
    identifier: str,
    revision: int,
) -> DependencyGraph:
    key = DependencyKey(kind, identifier)
    graph = snapshot.graph
    try:
        current = graph.get_node(key)
    except KeyError:
        return graph.add_node(DependencyNode(key=key, revision=RevisionVersion(revision)))
    if current.revision.value == revision:
        return graph
    if current.revision.value > revision:
        raise GovernanceStateError(
            f"dependency graph revision is ahead of {key.token}: {current.revision.value}"
        )
    try:
        return graph.publish_revision(key, RevisionVersion(revision)).graph
    except (KeyError, ValueError) as error:
        raise GovernanceStateError(f"cannot advance dependency graph node: {key.token}") from error


def _append_event(
    filesystem: ProjectFilesystem,
    *,
    entity_kind: str,
    entity_id: str,
    operation: str,
    status: str,
    history_sequence: int,
    previous_status: str | None,
    replacement_id: str | None,
    note: ReviewNote | None,
    subject_revision: str | None = None,
) -> int:
    payload: dict[str, FrozenJsonValue] = {
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "history_sequence": history_sequence,
        "operation": operation,
        "path": f"{entity_kind}s/{entity_id}.json",
        "status": status,
    }
    if previous_status is not None:
        payload["previous_status"] = previous_status
    if replacement_id is not None:
        payload["replacement_id"] = replacement_id
    if note is not None:
        payload["note"] = str(note)
    if subject_revision is not None:
        payload["subject_revision"] = subject_revision
    record = EventLog(filesystem).append(
        EventDraft(
            event_type=EventType(f"{entity_kind}.{operation}"),
            correlation_id=CorrelationId(f"{entity_kind}-{entity_id}"),
            payload=payload,
        )
    )
    return record.sequence


def _decision_summary(snapshot: DecisionSnapshot) -> dict[str, object]:
    decision = snapshot.decision
    return {
        "id": decision.id.value,
        "path": snapshot.path.value,
        "status": decision.status.value,
        "title": decision.title.value,
        "history_length": len(decision.history),
    }


def _approval_summary(snapshot: ApprovalSnapshot) -> dict[str, object]:
    approval = snapshot.approval
    return {
        "id": approval.id.value,
        "path": snapshot.path.value,
        "status": approval.status.value,
        "subject": {
            "id": approval.subject.id.value,
            "kind": approval.subject.id.kind,
            "revision": approval.subject.revision.value,
        },
        "history_length": len(approval.history),
    }


def _decision_result(
    filesystem: ProjectFilesystem,
    snapshot: DecisionSnapshot,
    event_sequence: int | None,
    warnings: tuple[str, ...],
) -> dict[str, object]:
    return {
        "project_directory": filesystem.root.as_posix(),
        "path": snapshot.path.value,
        "id": snapshot.decision.id.value,
        "status": snapshot.decision.status.value,
        "history_length": len(snapshot.decision.history),
        "event_sequence": event_sequence,
        "warnings": list(warnings),
    }


def _approval_result(
    filesystem: ProjectFilesystem,
    snapshot: ApprovalSnapshot,
    event_sequence: int | None,
    warnings: tuple[str, ...],
) -> dict[str, object]:
    return {
        "project_directory": filesystem.root.as_posix(),
        "path": snapshot.path.value,
        "id": snapshot.approval.id.value,
        "status": snapshot.approval.status.value,
        "history_length": len(snapshot.approval.history),
        "event_sequence": event_sequence,
        "warnings": list(warnings),
    }


def _update_state_checkpoint(filesystem: ProjectFilesystem) -> tuple[str, ...]:
    """Refresh the derived event checkpoint without making SQLite authoritative."""
    try:
        filesystem.resolve(DEFAULT_STATE_STORE_PATH, must_exist=True)
    except FileNotFoundError:
        return ()
    try:
        state_store = StateStore(filesystem)
        state_store.record_event_checkpoint(EventLog(filesystem).replay())
    except (ProjectFilesystemError, StateStoreError):
        return ("state-store-checkpoint-not-updated",)
    return ()
