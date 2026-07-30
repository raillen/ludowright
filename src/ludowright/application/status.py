"""Read-only project readiness and consistency inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ludowright.contracts import ProjectContract
from ludowright.domain import DependencyNode, DependencyNodeKind, FreshnessState
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    PROJECT_MARKER,
    DependencyGraphRepository,
    DependencyGraphSnapshot,
    EventIndexState,
    EventLog,
    EventLogError,
    EventLogSnapshot,
    ProjectFilesystem,
    ProjectFilesystemError,
    ProjectRootNotFoundError,
    RepositoryPath,
    SourceIndexState,
    StateStore,
    StateStoreError,
    StructuredDocumentError,
)
from ludowright.infrastructure.structured import JsonDocumentRepository


class ProjectStatusError(RuntimeError):
    """Base failure for the project status use case."""


class ProjectStatusCorruptError(ProjectStatusError):
    """Raised when persisted project state cannot be inspected safely."""


@dataclass(frozen=True, slots=True)
class StatusIssue:
    """One deterministic blocker found while inspecting a project."""

    code: str
    detail: str
    path: str | None = None

    def as_data(self) -> dict[str, object]:
        return {
            "code": self.code,
            "detail": self.detail,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class StatusComponent:
    """Inspection state for one mandatory project component."""

    name: str
    path: str
    state: str
    detail: str

    def as_data(self) -> dict[str, object]:
        return {
            "detail": self.detail,
            "name": self.name,
            "path": self.path,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class ProjectStatusResult:
    """Stable result shared by the human and JSON CLI renderers."""

    project_directory: str
    project_id: str
    project_name: str
    project_stage: str
    project_lifecycle: str
    readiness_state: str
    components: tuple[StatusComponent, ...]
    blockers: tuple[StatusIssue, ...]
    stale_outputs: tuple[dict[str, object], ...]
    recommended_actions: tuple[dict[str, object], ...]
    consistency: dict[str, object]

    def as_data(self) -> dict[str, object]:
        """Return deterministic JSON-compatible command data."""
        return {
            "blockers": [issue.as_data() for issue in self.blockers],
            "components": [component.as_data() for component in self.components],
            "consistency": self.consistency,
            "project": {
                "id": self.project_id,
                "lifecycle": self.project_lifecycle,
                "name": self.project_name,
                "stage": self.project_stage,
            },
            "project_directory": self.project_directory,
            "readiness": {
                "stage": self.project_stage,
                "state": self.readiness_state,
            },
            "recommended_actions": list(self.recommended_actions),
            "stale_outputs": list(self.stale_outputs),
        }


class ProjectStatusService:
    """Inspect one project without creating, repairing, or rewriting files."""

    def inspect(self, start: Path | str | None = None) -> ProjectStatusResult:
        """Return the current project status from a path or the working directory."""
        filesystem = self._discover(start)
        manifest = self._load_manifest(filesystem)
        blockers: list[StatusIssue] = []

        components: list[StatusComponent] = [
            StatusComponent(
                name="manifest",
                path=PROJECT_MARKER.value,
                state="valid",
                detail="manifest matches the published project contract",
            )
        ]

        event_snapshot, event_component = self._inspect_event_log(filesystem, blockers)
        components.append(event_component)

        graph_snapshot, graph_component = self._inspect_graph(filesystem, blockers)
        components.append(graph_component)

        state_store, state_component = self._inspect_state_store(filesystem, blockers)
        components.append(state_component)

        stale_outputs: tuple[dict[str, object], ...] = ()
        if graph_snapshot is not None:
            stale_outputs = tuple(
                _stale_output(node)
                for node in graph_snapshot.graph.nodes
                if node.key.kind is not DependencyNodeKind.PROJECT
                and node.freshness is not FreshnessState.FRESH
            )
            project_nodes = tuple(
                node
                for node in graph_snapshot.graph.nodes
                if node.key.kind is DependencyNodeKind.PROJECT and node.key.id == manifest.id
            )
            if not project_nodes:
                blockers.append(
                    StatusIssue(
                        code="project-node-missing",
                        detail="dependency graph has no node for the project manifest",
                        path=DEFAULT_DEPENDENCY_GRAPH_PATH.value,
                    )
                )
            elif project_nodes[0].freshness is not FreshnessState.FRESH:
                blockers.append(
                    StatusIssue(
                        code="project-node-not-fresh",
                        detail="the project dependency node is not fresh",
                        path=DEFAULT_DEPENDENCY_GRAPH_PATH.value,
                    )
                )

        consistency = self._check_consistency(
            filesystem,
            state_store=state_store,
            event_snapshot=event_snapshot,
            blockers=blockers,
        )
        blockers = sorted(blockers, key=_issue_sort_key)
        readiness_state = _readiness_state(blockers, stale_outputs)
        recommended_actions = _recommended_actions(
            blockers=tuple(blockers),
            stale_outputs=stale_outputs,
            readiness_state=readiness_state,
        )
        return ProjectStatusResult(
            project_directory=filesystem.root.as_posix(),
            project_id=manifest.id,
            project_name=manifest.name,
            project_stage=manifest.stage.value,
            project_lifecycle=manifest.lifecycle.value,
            readiness_state=readiness_state,
            components=tuple(components),
            blockers=tuple(blockers),
            stale_outputs=stale_outputs,
            recommended_actions=recommended_actions,
            consistency=consistency,
        )

    @staticmethod
    def _discover(start: Path | str | None) -> ProjectFilesystem:
        try:
            return ProjectFilesystem.discover(start or Path.cwd())
        except ProjectRootNotFoundError:
            raise
        except ProjectFilesystemError as error:
            raise ProjectStatusCorruptError("project root is unsafe or invalid") from error

    @staticmethod
    def _load_manifest(filesystem: ProjectFilesystem) -> ProjectContract:
        repository = JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract)
        try:
            return repository.load().value
        except (
            FileNotFoundError,
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
        ) as error:
            raise ProjectStatusCorruptError("project manifest is missing or invalid") from error

    @staticmethod
    def _inspect_event_log(
        filesystem: ProjectFilesystem,
        blockers: list[StatusIssue],
    ) -> tuple[EventLogSnapshot | None, StatusComponent]:
        path = DEFAULT_EVENT_LOG_PATH
        if not _exists(filesystem, path):
            blockers.append(
                StatusIssue(
                    code="event-log-missing",
                    detail="the canonical event log is missing",
                    path=path.value,
                )
            )
            return None, StatusComponent("event-log", path.value, "missing", "file is absent")
        try:
            snapshot = EventLog(filesystem).replay()
        except (EventLogError, ProjectFilesystemError) as error:
            raise ProjectStatusCorruptError("event log cannot be replayed safely") from error
        return snapshot, StatusComponent(
            "event-log",
            path.value,
            "valid",
            f"{snapshot.last_sequence} event(s), digest {snapshot.digest}",
        )

    @staticmethod
    def _inspect_graph(
        filesystem: ProjectFilesystem,
        blockers: list[StatusIssue],
    ) -> tuple[DependencyGraphSnapshot | None, StatusComponent]:
        path = DEFAULT_DEPENDENCY_GRAPH_PATH
        try:
            snapshot = DependencyGraphRepository(filesystem).load_optional()
        except (
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
            ValueError,
        ) as error:
            raise ProjectStatusCorruptError(
                "dependency graph cannot be validated safely"
            ) from error
        if snapshot is None:
            blockers.append(
                StatusIssue(
                    code="dependency-graph-missing",
                    detail="the canonical dependency graph is missing",
                    path=path.value,
                )
            )
            return None, StatusComponent(
                "dependency-graph",
                path.value,
                "missing",
                "file is absent",
            )
        return snapshot, StatusComponent(
            "dependency-graph",
            path.value,
            "valid",
            f"{len(snapshot.graph.nodes)} node(s), {len(snapshot.graph.edges)} edge(s)",
        )

    @staticmethod
    def _inspect_state_store(
        filesystem: ProjectFilesystem,
        blockers: list[StatusIssue],
    ) -> tuple[StateStore | None, StatusComponent]:
        path = DEFAULT_STATE_STORE_PATH
        if not _exists(filesystem, path):
            blockers.append(
                StatusIssue(
                    code="state-store-missing",
                    detail="the SQLite state store is missing",
                    path=path.value,
                )
            )
            return None, StatusComponent("state-store", path.value, "missing", "file is absent")
        try:
            store = StateStore(filesystem, read_only=True)
        except (FileNotFoundError, ProjectFilesystemError, StateStoreError) as error:
            raise ProjectStatusCorruptError(
                "SQLite state store cannot be inspected safely"
            ) from error
        return store, StatusComponent(
            "state-store",
            path.value,
            "valid",
            f"schema version {store.schema_version}, read-only inspection",
        )

    @staticmethod
    def _check_consistency(
        filesystem: ProjectFilesystem,
        *,
        state_store: StateStore | None,
        event_snapshot: EventLogSnapshot | None,
        blockers: list[StatusIssue],
    ) -> dict[str, object]:
        if state_store is None or event_snapshot is None:
            return {"state": "unavailable"}
        try:
            report = state_store.check_consistency(event_snapshot)
        except (StateStoreError, ProjectFilesystemError) as error:
            raise ProjectStatusCorruptError("state consistency cannot be checked safely") from error
        if report.event_state is not EventIndexState.IN_SYNC:
            blockers.append(
                StatusIssue(
                    code=f"state-index-{report.event_state.value}",
                    detail=report.event_detail,
                    path=DEFAULT_STATE_STORE_PATH.value,
                )
            )
        source_data: list[dict[str, object]] = []
        for source in report.sources:
            source_data.append(
                {
                    "entity_id": source.entity_id,
                    "entity_type": source.entity_type,
                    "path": source.source_path.value if source.source_path else None,
                    "state": source.state.value,
                }
            )
            if source.state is not SourceIndexState.IN_SYNC:
                blockers.append(
                    StatusIssue(
                        code=f"canonical-source-{source.state.value}",
                        detail=source.detail,
                        path=source.source_path.value if source.source_path else None,
                    )
                )
        state = "consistent" if report.is_consistent else "inconsistent"
        return {
            "event": {
                "detail": report.event_detail,
                "state": report.event_state.value,
            },
            "sources": source_data,
            "state": state,
        }


def _exists(filesystem: ProjectFilesystem, path: RepositoryPath) -> bool:
    try:
        return filesystem.resolve(path).is_file()
    except ProjectFilesystemError as error:
        raise ProjectStatusCorruptError(f"project path is unsafe: {path}") from error


def _stale_output(node: DependencyNode) -> dict[str, object]:
    return {
        "causes": [
            {
                "affected": cause.affected.token,
                "path": [item.token for item in cause.path],
                "reason": cause.reason.value,
                "root": cause.root.token,
                "state": cause.state.value,
            }
            for cause in node.invalidations
        ],
        "id": node.key.id,
        "kind": node.key.kind.value,
        "revision": node.revision.value,
        "state": node.freshness.value,
    }


def _issue_sort_key(issue: StatusIssue) -> tuple[str, str, str]:
    return (issue.code, issue.path or "", issue.detail)


def _readiness_state(
    blockers: list[StatusIssue],
    stale_outputs: tuple[dict[str, object], ...],
) -> str:
    if blockers:
        return "blocked"
    if any(output["state"] == FreshnessState.REVIEW_REQUIRED.value for output in stale_outputs):
        return "needs-review"
    if stale_outputs:
        return "blocked"
    return "ready"


def _recommended_actions(
    *,
    blockers: tuple[StatusIssue, ...],
    stale_outputs: tuple[dict[str, object], ...],
    readiness_state: str,
) -> tuple[dict[str, object], ...]:
    if blockers:
        return (
            {
                "code": "resolve-blockers",
                "detail": "resolve the reported project consistency blockers before continuing",
            },
        )
    if stale_outputs and readiness_state == "blocked":
        return (
            {
                "code": "refresh-stale-outputs",
                "detail": "refresh or explicitly supersede outputs with stale dependencies",
            },
        )
    if stale_outputs:
        return (
            {
                "code": "review-affected-outputs",
                "detail": "review outputs affected by non-blocking dependency changes",
            },
        )
    return (
        {
            "code": "continue-project-intake",
            "detail": "continue defining canonical project decisions and documents",
        },
    )
