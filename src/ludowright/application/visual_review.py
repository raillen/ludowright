"""Application service for reviewing immutable generated visual outputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from pydantic import ValidationError

from ludowright.contracts import (
    ApprovalContract,
    GenerationReceiptContract,
    VisualReferenceContract,
    VisualReviewContract,
)
from ludowright.domain import (
    MANUAL_INVALIDATION,
    SOURCE_REJECTED,
    Approval,
    ApprovalId,
    ApprovalStatus,
    ApprovalSubject,
    CorrelationId,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    EventDraft,
    EventId,
    EventType,
    FreshnessState,
    FrozenJsonValue,
    InvalidationCause,
    InvalidationMode,
    ReferenceStatus,
    RevisionVersion,
    SubjectRevision,
    VisualReference,
    VisualReview,
    VisualReviewOutcome,
    freeze_json_object,
)
from ludowright.infrastructure import (
    APPROVAL_DIRECTORY,
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    VISUAL_REVIEW_DIRECTORY,
    VISUAL_REVIEW_LOCK,
    DependencyGraphRepository,
    GenerationReceiptRepository,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    StructuredDocumentSnapshot,
    VisualReviewRepository,
)
from ludowright.infrastructure.dependency_graph import DependencyGraphSnapshot
from ludowright.infrastructure.event_log import EventLog

ReferenceSnapshot = StructuredDocumentSnapshot[VisualReferenceContract]
ReferenceUpdate = tuple[ReferenceSnapshot, VisualReferenceContract]
ImpactData = dict[str, object]


class VisualReviewError(RuntimeError):
    """Base error for review-workflow application failures."""


class VisualReviewValidationError(VisualReviewError):
    """Raised when a review cannot be applied to the named receipt or references."""


class VisualReviewConflictError(VisualReviewError):
    """Raised when applying a review would overwrite or fork canonical state."""


class VisualReviewRollbackError(VisualReviewError):
    """Raised when restoring canonical state after a failed review is unsafe."""


@dataclass(frozen=True, slots=True)
class VisualReviewResult:
    """Stable result of one review application or dry-run."""

    state: str
    dry_run: bool
    review_id: str
    outcome: str
    receipt_id: str
    reference_ids: tuple[str, ...]
    approval_id: str | None
    paths: tuple[str, ...]
    graph_revision: int
    impacts: tuple[dict[str, object], ...]
    event_sequence: int | None

    def as_data(self) -> dict[str, object]:
        return {
            "state": self.state,
            "dry_run": self.dry_run,
            "schema_version": 1,
            "review_id": self.review_id,
            "outcome": self.outcome,
            "receipt_id": self.receipt_id,
            "reference_ids": list(self.reference_ids),
            "approval_id": self.approval_id,
            "paths": list(self.paths),
            "graph_revision": self.graph_revision,
            "impacts": list(self.impacts),
            "event_sequence": self.event_sequence,
            "warnings": [],
        }


class VisualReviewService:
    """Coordinate review, approval projection, dependency invalidation, and events."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("visual review services require ProjectFilesystem")
        self._filesystem = filesystem
        self._repository = VisualReviewRepository(filesystem)
        self._receipts = GenerationReceiptRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    def apply(
        self,
        input_path: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> VisualReviewResult:
        """Validate and apply one review contract without overwriting its record."""
        contract = self._load_input(input_path)
        review = contract.to_domain()
        self._validate_actor_policy(contract)

        existing = self._repository.load_review_optional(review.id.value)
        if existing is not None:
            if existing.value != contract:
                raise VisualReviewConflictError(
                    f"visual review already exists with different content: {review.id.value}"
                )
            return self._result(
                review_contract=contract,
                graph_revision=self._current_graph_revision(),
                impacts=(),
                state="unchanged",
                dry_run=dry_run,
                event_sequence=None,
            )

        receipt = self._load_receipt(review.receipt_id.value)
        references = self._load_references(review, receipt.output_reference_ids)
        self._validate_review_targets(review, receipt, references)

        prior_review = None
        prior_reference = None
        prior_approval = None
        if review.supersedes is not None:
            prior_review, prior_reference, prior_approval = self._load_superseded(
                review,
                references,
            )

        approval_contract, updated_references, old_reference_update, old_approval_update = (
            self._plan_projection(review, references, prior_reference, prior_approval)
        )
        graph_snapshot = DependencyGraphRepository(self._filesystem).load_optional()
        planned_graph, impacts = self._plan_graph(
            review,
            receipt_id=review.receipt_id.value,
            references=references,
            graph_snapshot=graph_snapshot,
            prior_review=prior_review,
            old_reference_update=old_reference_update,
            approval_contract=approval_contract,
        )
        paths = self._planned_paths(
            review,
            references,
            approval_contract,
            old_reference_update,
            old_approval_update,
        )
        if dry_run:
            return self._result(
                review_contract=contract,
                graph_revision=planned_graph.revision.value,
                impacts=impacts,
                state="planned",
                dry_run=True,
                event_sequence=None,
                paths=paths,
            )

        return self._persist(
            review_contract=contract,
            review=review,
            references=references,
            updated_references=updated_references,
            old_reference_update=old_reference_update,
            approval_contract=approval_contract,
            old_approval_update=old_approval_update,
            graph_snapshot=graph_snapshot,
            planned_graph=planned_graph,
            impacts=impacts,
            paths=paths,
        )

    def _load_input(self, path: RepositoryPath) -> VisualReviewContract:
        if not isinstance(path, RepositoryPath) or not path.name.endswith(".json"):
            raise VisualReviewValidationError("review input must be a project-relative JSON path")
        try:
            return (
                JsonDocumentRepository(
                    self._filesystem,
                    path,
                    VisualReviewContract,
                )
                .load()
                .value
            )
        except FileNotFoundError as error:
            raise VisualReviewValidationError(f"review input does not exist: {path}") from error
        except ValidationError as error:
            raise VisualReviewValidationError(
                f"review input is not a valid visual-review contract: {path}"
            ) from error

    def _validate_actor_policy(self, contract: VisualReviewContract) -> None:
        if contract.reviewer is None or contract.producer is None:
            raise VisualReviewValidationError(
                "new visual reviews require reviewer and producer identities"
            )
        if contract.reviewer.id == contract.producer.id:
            raise VisualReviewValidationError("a reviewer cannot review their own generation")
        if (
            contract.outcome is VisualReviewOutcome.ACCEPTED
            and contract.reviewer.kind.value != "human"
        ):
            raise VisualReviewValidationError("only a human reviewer may approve generated output")

    def _load_receipt(self, receipt_id: str) -> GenerationReceiptContract:
        try:
            receipt = self._receipts.load(self._filesystem, receipt_id)
        except FileNotFoundError as error:
            raise VisualReviewValidationError(str(error)) from error
        if receipt.status.value != "succeeded":
            raise VisualReviewValidationError("only successful generation receipts may be reviewed")
        return receipt

    def _load_references(
        self,
        review: VisualReview,
        output_reference_ids: tuple[str, ...],
    ) -> tuple[ReferenceSnapshot, ...]:
        loaded: list[ReferenceSnapshot] = []
        for reference_id in review.reviewed_reference_ids:
            if reference_id.value not in output_reference_ids:
                raise VisualReviewValidationError(
                    f"review reference is not an output of the named receipt: {reference_id.value}"
                )
            try:
                loaded.append(self._repository.load_reference(reference_id.value))
            except FileNotFoundError as error:
                raise VisualReviewValidationError(
                    f"review reference does not exist: {reference_id.value}"
                ) from error
        return tuple(loaded)

    def _validate_review_targets(
        self,
        review: VisualReview,
        receipt: GenerationReceiptContract,
        references: tuple[ReferenceSnapshot, ...],
    ) -> None:
        snapshots = references
        if review.outcome is VisualReviewOutcome.ACCEPTED and len(snapshots) != 1:
            raise VisualReviewValidationError(
                "an accepted visual review must name exactly one output reference"
            )
        for snapshot in snapshots:
            reference = snapshot.value.to_domain()
            if reference.provenance.source_receipt_id is None or (
                reference.provenance.source_receipt_id.value != receipt.id
            ):
                raise VisualReviewValidationError(
                    f"reference is not provenance-bound to receipt: {reference.id.value}"
                )
            if reference.status not in {ReferenceStatus.CANDIDATE, ReferenceStatus.APPROVED}:
                raise VisualReviewValidationError(
                    "reference cannot be reviewed from status "
                    f"{reference.status.value}: {reference.id.value}"
                )

    def _load_superseded(
        self,
        review: VisualReview,
        references: tuple[ReferenceSnapshot, ...],
    ) -> tuple[VisualReview, tuple[ReferenceSnapshot, VisualReference], Approval]:
        if review.supersedes is None:
            raise VisualReviewValidationError("a superseding review requires a prior review ID")
        prior_snapshot = self._repository.load_review_optional(review.supersedes.value)
        if prior_snapshot is None:
            raise VisualReviewValidationError(
                f"superseded review does not exist: {review.supersedes.value}"
            )
        prior = prior_snapshot.value.to_domain()
        if prior.outcome is not VisualReviewOutcome.ACCEPTED:
            raise VisualReviewValidationError("only an accepted review may be superseded")
        if review.outcome is not VisualReviewOutcome.ACCEPTED:
            raise VisualReviewValidationError("a superseding review must be accepted")
        if len(prior.reviewed_reference_ids) != 1:
            raise VisualReviewValidationError("superseded accepted reviews must have one reference")
        prior_reference_snapshot = self._repository.load_reference(
            prior.reviewed_reference_ids[0].value
        )
        prior_reference = prior_reference_snapshot.value.to_domain()
        current_reference = references[0].value.to_domain()
        if prior_reference.target != current_reference.target:
            raise VisualReviewValidationError("a replacement review must target the same item")
        if prior_reference.status is not ReferenceStatus.APPROVED:
            raise VisualReviewValidationError(
                "a superseded review must project an approved reference"
            )
        if prior.approval_id is None:
            raise VisualReviewValidationError("a superseded review must name its approval")
        prior_approval_snapshot = self._repository.load_approval(prior.approval_id.value)
        return (
            prior,
            (prior_reference_snapshot, prior_reference),
            prior_approval_snapshot.value.to_domain(),
        )

    def _plan_projection(
        self,
        review: VisualReview,
        references: tuple[ReferenceSnapshot, ...],
        prior_reference: tuple[ReferenceSnapshot, VisualReference] | None,
        prior_approval: Approval | None,
    ) -> tuple[
        ApprovalContract | None,
        tuple[ReferenceUpdate, ...],
        ReferenceUpdate | None,
        ApprovalContract | None,
    ]:
        snapshots = references
        approval_contract: ApprovalContract | None = None
        updated: list[ReferenceUpdate] = []
        old_reference_update: ReferenceUpdate | None = None
        old_approval_update: ApprovalContract | None = None
        if review.outcome is VisualReviewOutcome.ACCEPTED:
            reference_snapshot = snapshots[0]
            reference = reference_snapshot.value.to_domain()
            approval_id = cast(ApprovalId, review.approval_id)
            subject = ApprovalSubject(
                id=reference.id,
                revision=SubjectRevision(reference.provenance.content_revision.value),
                label=reference.name,
            )
            approval = Approval.request(approval_id, subject).approve(review.note)
            existing_approval = self._repository.load_approval_optional(approval_id.value)
            if existing_approval is not None:
                current = existing_approval.value.to_domain()
                if current.subject != subject:
                    raise VisualReviewConflictError(
                        "approval ID is bound to another subject revision"
                    )
                if current.status is ApprovalStatus.PENDING:
                    approval = current.approve(review.note)
                elif current.status is ApprovalStatus.APPROVED:
                    approval = current
                else:
                    raise VisualReviewConflictError(
                        f"approval cannot be reused from status {current.status.value}"
                    )
            approval_contract = ApprovalContract.from_domain(approval)
            updated.append(
                (
                    reference_snapshot,
                    VisualReferenceContract.from_domain(reference.approve(approval_id)),
                )
            )
            if prior_reference is not None:
                old_snapshot, old_value = prior_reference
                old_reference_update = (
                    old_snapshot,
                    VisualReferenceContract.from_domain(old_value.supersede(reference.id)),
                )
                if prior_approval is None:
                    raise VisualReviewValidationError("superseded review approval is missing")
                if prior_approval.status is not ApprovalStatus.APPROVED:
                    raise VisualReviewValidationError("superseded approval is not approved")
                old_approval_update = ApprovalContract.from_domain(
                    prior_approval.supersede(approval_id, review.note)
                )
        elif review.outcome is VisualReviewOutcome.REJECTED:
            updated = [
                (snapshot, VisualReferenceContract.from_domain(snapshot.value.to_domain().reject()))
                for snapshot in snapshots
            ]
        else:
            updated = [(snapshot, snapshot.value) for snapshot in snapshots]
        return approval_contract, tuple(updated), old_reference_update, old_approval_update

    def _plan_graph(
        self,
        review: VisualReview,
        *,
        receipt_id: str,
        references: tuple[ReferenceSnapshot, ...],
        graph_snapshot: DependencyGraphSnapshot | None,
        prior_review: VisualReview | None,
        old_reference_update: ReferenceUpdate | None,
        approval_contract: ApprovalContract | None,
    ) -> tuple[DependencyGraph, tuple[ImpactData, ...]]:
        graph = graph_snapshot.graph if graph_snapshot is not None else DependencyGraph.empty()
        receipt_key = DependencyKey(DependencyNodeKind.GENERATION_RECEIPT, receipt_id)
        review_key = DependencyKey(DependencyNodeKind.VISUAL_REVIEW, review.id.value)
        graph = _ensure_node(graph, receipt_key)
        graph = _ensure_node(graph, review_key)
        impacts: tuple[ImpactData, ...] = ()
        for snapshot in references:
            reference = snapshot.value.to_domain()
            reference_key = DependencyKey(DependencyNodeKind.REFERENCE, reference.id.value)
            graph = _ensure_node(graph, reference_key)
            graph = _ensure_edge(
                graph,
                receipt_key,
                reference_key,
                DependencyRelation.GENERATED_FROM,
                InvalidationMode.NONE,
            )
            graph = _ensure_edge(
                graph,
                reference_key,
                review_key,
                DependencyRelation.REFERENCES,
                InvalidationMode.REVIEW,
            )
        if approval_contract is not None:
            approval_key = DependencyKey(DependencyNodeKind.APPROVAL, approval_contract.id)
            graph = _ensure_node(graph, approval_key)
            reference_key = DependencyKey(
                DependencyNodeKind.REFERENCE,
                references[0].value.id,
            )
            graph = _ensure_edge(
                graph,
                approval_key,
                reference_key,
                DependencyRelation.APPROVED_BY,
                InvalidationMode.STALE,
            )
        if prior_review is not None:
            prior_key = DependencyKey(DependencyNodeKind.VISUAL_REVIEW, prior_review.id.value)
            graph = _ensure_node(graph, prior_key)
            graph = _ensure_edge(
                graph,
                prior_key,
                review_key,
                DependencyRelation.SUPERSEDES,
                InvalidationMode.NONE,
            )
        if review.outcome is VisualReviewOutcome.REJECTED:
            impact_list: list[ImpactData] = []
            for snapshot in references:
                key = DependencyKey(DependencyNodeKind.REFERENCE, snapshot.value.id)
                result = graph.invalidate(key, SOURCE_REJECTED, state=FreshnessState.STALE)
                graph = result.graph
                impact_list.extend(_impact_data(result.impacts))
            impacts = tuple(impact_list)
        elif review.outcome is VisualReviewOutcome.CHANGES_REQUESTED:
            impact_list = []
            for snapshot in references:
                key = DependencyKey(DependencyNodeKind.REFERENCE, snapshot.value.id)
                result = graph.invalidate(
                    key,
                    MANUAL_INVALIDATION,
                    state=FreshnessState.REVIEW_REQUIRED,
                )
                graph = result.graph
                impact_list.extend(_impact_data(result.impacts))
            impacts = tuple(impact_list)
        elif old_reference_update is not None:
            old_key = DependencyKey(DependencyNodeKind.REFERENCE, old_reference_update[0].value.id)
            result = graph.invalidate(old_key, MANUAL_INVALIDATION, state=FreshnessState.STALE)
            graph, impacts = result.graph, _impact_data(result.impacts)
        else:
            key = DependencyKey(DependencyNodeKind.REFERENCE, references[0].value.id)
            node = graph.get_node(key)
            if node.freshness is not FreshnessState.FRESH:
                result = graph.refresh(key, RevisionVersion(node.revision.value + 1))
                graph = result.graph
                impacts = _impact_data(result.impacts)
        return graph, impacts

    def _persist(
        self,
        *,
        review_contract: VisualReviewContract,
        review: VisualReview,
        references: tuple[ReferenceSnapshot, ...],
        updated_references: tuple[ReferenceUpdate, ...],
        old_reference_update: ReferenceUpdate | None,
        approval_contract: ApprovalContract | None,
        old_approval_update: ApprovalContract | None,
        graph_snapshot: DependencyGraphSnapshot | None,
        planned_graph: DependencyGraph,
        impacts: tuple[ImpactData, ...],
        paths: tuple[str, ...],
    ) -> VisualReviewResult:
        after_event = None
        graph_repository = DependencyGraphRepository(self._filesystem)
        changed: dict[str, bytes | None] = {}
        prior_directories: dict[RepositoryPath, bool] = {}
        try:
            with self._filesystem.lock(VISUAL_REVIEW_LOCK, timeout=5.0):
                before = {
                    path: _read_optional_bytes(self._filesystem, RepositoryPath(path))
                    for path in paths
                }
                prior_directories = {
                    directory: self._filesystem.directory_exists(directory)
                    for directory in (VISUAL_REVIEW_DIRECTORY, APPROVAL_DIRECTORY)
                }
                changed = {}
                for snapshot, value in updated_references:
                    self._repository.replace_reference(snapshot, value)
                    changed[self._repository.reference_path(value.id).value] = before[
                        self._repository.reference_path(value.id).value
                    ]
                if old_reference_update is not None:
                    self._repository.replace_reference(*old_reference_update)
                    old_path = self._repository.reference_path(old_reference_update[1].id).value
                    changed[old_path] = before[old_path]
                if approval_contract is not None:
                    approval_snapshot = self._repository.load_approval_optional(
                        approval_contract.id
                    )
                    if approval_snapshot is None:
                        self._repository.create_approval(approval_contract)
                    else:
                        self._repository.replace_approval(approval_snapshot, approval_contract)
                    approval_path = self._repository.approval_path(approval_contract.id).value
                    changed[approval_path] = before[approval_path]
                if old_approval_update is not None:
                    old_approval_snapshot = self._repository.load_approval(old_approval_update.id)
                    self._repository.replace_approval(old_approval_snapshot, old_approval_update)
                    old_approval_path = self._repository.approval_path(old_approval_update.id).value
                    changed[old_approval_path] = before[old_approval_path]
                self._repository.create_review(review_contract)
                changed[self._repository.review_path(review.id.value).value] = before[
                    self._repository.review_path(review.id.value).value
                ]
                if graph_snapshot is None:
                    graph_repository.create(planned_graph, timeout=5.0)
                else:
                    graph_repository.replace(graph_snapshot, planned_graph, timeout=5.0)
                changed[DEFAULT_DEPENDENCY_GRAPH_PATH.value] = before[
                    DEFAULT_DEPENDENCY_GRAPH_PATH.value
                ]
                event = EventLog(self._filesystem).append(
                    EventDraft(
                        event_type=EventType(f"visual-review.{review.outcome.value}"),
                        correlation_id=CorrelationId(f"review-{review.id.value}"),
                        payload=_event_payload(review, impacts),
                    ),
                    event_id=EventId(f"event-visual-review-{review.id.value}"),
                    occurred_at=self._clock(),
                    timeout=5.0,
                )
                changed[DEFAULT_EVENT_LOG_PATH.value] = before[DEFAULT_EVENT_LOG_PATH.value]
                _record_state_checkpoint_if_initialized(self._filesystem, event.occurred_at)
                after_event = event.sequence
        except BaseException as error:
            try:
                _restore_files(self._filesystem, changed)
                _restore_directories(self._filesystem, prior_directories)
            except BaseException as rollback_error:
                raise VisualReviewRollbackError(
                    f"visual review rollback failed: {rollback_error}"
                ) from error
            raise
        return self._result(
            review_contract=review_contract,
            graph_revision=planned_graph.revision.value,
            impacts=impacts,
            state="applied",
            dry_run=False,
            event_sequence=after_event,
            paths=paths,
        )

    def _planned_paths(
        self,
        review: VisualReview,
        references: tuple[ReferenceSnapshot, ...],
        approval_contract: ApprovalContract | None,
        old_reference_update: ReferenceUpdate | None,
        old_approval_update: ApprovalContract | None,
    ) -> tuple[str, ...]:
        paths = [
            self._repository.review_path(review.id.value).value,
            DEFAULT_DEPENDENCY_GRAPH_PATH.value,
            DEFAULT_EVENT_LOG_PATH.value,
        ]
        paths.extend(self._repository.reference_path(item.value.id).value for item in references)
        if approval_contract is not None:
            paths.append(self._repository.approval_path(approval_contract.id).value)
        if old_reference_update is not None:
            paths.append(self._repository.reference_path(old_reference_update[0].value.id).value)
        if old_approval_update is not None:
            paths.append(self._repository.approval_path(old_approval_update.id).value)
        return tuple(dict.fromkeys(paths))

    def _current_graph_revision(self) -> int:
        snapshot = DependencyGraphRepository(self._filesystem).load_optional()
        return snapshot.graph.revision.value if snapshot is not None else 0

    def _result(
        self,
        *,
        review_contract: VisualReviewContract,
        graph_revision: int,
        impacts: tuple[ImpactData, ...],
        state: str,
        dry_run: bool,
        event_sequence: int | None,
        paths: tuple[str, ...] | None = None,
    ) -> VisualReviewResult:
        return VisualReviewResult(
            state=state,
            dry_run=dry_run,
            review_id=review_contract.id,
            outcome=review_contract.outcome.value,
            receipt_id=review_contract.receipt_id,
            reference_ids=tuple(review_contract.reviewed_reference_ids),
            approval_id=review_contract.approval_id,
            paths=paths
            or (
                VISUAL_REVIEW_DIRECTORY.child(f"{review_contract.id}.json").value,
                DEFAULT_DEPENDENCY_GRAPH_PATH.value,
                DEFAULT_EVENT_LOG_PATH.value,
            ),
            graph_revision=graph_revision,
            impacts=tuple(impacts),
            event_sequence=event_sequence,
        )


def _ensure_node(graph: DependencyGraph, key: DependencyKey) -> DependencyGraph:
    try:
        graph.get_node(key)
    except KeyError:
        return graph.add_node(DependencyNode(key=key, revision=RevisionVersion(1)))
    return graph


def _ensure_edge(
    graph: DependencyGraph,
    source: DependencyKey,
    target: DependencyKey,
    relation: DependencyRelation,
    mode: InvalidationMode,
) -> DependencyGraph:
    existing = [edge for edge in graph.edges if edge.source == source and edge.target == target]
    if existing:
        if existing[0].relation is not relation or existing[0].invalidation_mode is not mode:
            raise VisualReviewConflictError(
                f"dependency edge already exists with another policy: {source} -> {target}"
            )
        return graph
    return graph.connect(source, target, relation, mode)


def _impact_data(impacts: tuple[InvalidationCause, ...]) -> tuple[ImpactData, ...]:
    return tuple(
        {
            "root": cause.root.token,
            "affected": cause.affected.token,
            "reason": cause.reason.value,
            "state": cause.state.value,
            "path": [item.token for item in cause.path],
        }
        for cause in impacts
    )


def _event_payload(
    review: VisualReview,
    impacts: tuple[ImpactData, ...],
) -> Mapping[str, FrozenJsonValue]:
    payload: dict[str, object] = {
        "review_id": review.id.value,
        "receipt_id": review.receipt_id.value,
        "outcome": review.outcome.value,
        "reference_ids": [item.value for item in review.reviewed_reference_ids],
        "approval_id": review.approval_id.value if review.approval_id is not None else None,
        "supersedes": review.supersedes.value if review.supersedes is not None else None,
        "reviewer_id": review.reviewer.id.value if review.reviewer is not None else None,
        "reviewer_kind": review.reviewer.kind.value if review.reviewer is not None else None,
        "producer_id": review.producer.id.value if review.producer is not None else None,
        "producer_kind": review.producer.kind.value if review.producer is not None else None,
        "impacts": list(impacts),
    }
    return freeze_json_object(payload)


def _read_optional_bytes(filesystem: ProjectFilesystem, path: RepositoryPath) -> bytes | None:
    try:
        return filesystem.read_bytes(path, max_bytes=64 * 1024 * 1024)
    except FileNotFoundError:
        return None


def _record_state_checkpoint_if_initialized(
    filesystem: ProjectFilesystem,
    occurred_at: datetime,
) -> None:
    """Keep the derived event checkpoint current without bootstrapping ad hoc projects."""
    try:
        filesystem.resolve(DEFAULT_STATE_STORE_PATH, must_exist=True)
    except FileNotFoundError:
        return
    StateStore(filesystem).record_event_checkpoint(
        EventLog(filesystem).replay(),
        updated_at=occurred_at,
    )


def _restore_files(filesystem: ProjectFilesystem, before: dict[str, bytes | None]) -> None:
    for raw_path, payload in reversed(tuple(before.items())):
        path = RepositoryPath(raw_path)
        if payload is None:
            filesystem.remove_file(path)
        else:
            filesystem.write_bytes(path, payload)


def _restore_directories(
    filesystem: ProjectFilesystem,
    before: dict[RepositoryPath, bool],
) -> None:
    for directory, existed in reversed(tuple(before.items())):
        if not existed and filesystem.directory_exists(directory):
            filesystem.remove_empty_directory(directory)


__all__ = [
    "VisualReviewConflictError",
    "VisualReviewError",
    "VisualReviewResult",
    "VisualReviewRollbackError",
    "VisualReviewService",
    "VisualReviewValidationError",
]
