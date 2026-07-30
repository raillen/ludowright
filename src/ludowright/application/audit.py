"""Read-only structural inspection of a LudoWright project."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import ValidationError

from ludowright.contracts import (
    AuditComponentContract,
    AuditFindingContract,
    AuditProjectContract,
    AuditVersionContract,
    ProjectContract,
    RepairGuidanceContract,
    StructuralAuditContract,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    CorruptEventLogError,
    DependencyGraphRepository,
    EventLog,
    EventLogError,
    EventLogSnapshot,
    IncompleteEventLogTailError,
    ProjectFilesystem,
    ProjectFilesystemError,
    ProjectRootNotFoundError,
    RepositoryPath,
    SourceIndexState,
    StateStore,
    StateStoreCorruptionError,
    StateStoreError,
    StructuredDocumentError,
    UnsafeProjectPathError,
    UnsupportedStateSchemaError,
)
from ludowright.infrastructure.filesystem import PROJECT_MARKER
from ludowright.infrastructure.structured import JsonDocumentRepository


class StructuralAuditError(RuntimeError):
    """Raised when the audit cannot establish a trusted project boundary."""


@dataclass(frozen=True, slots=True)
class _Finding:
    code: str
    component: str
    detail: str
    repair_code: str
    path: str | None = None
    severity: Literal["error", "warning"] = "error"

    def contract(self) -> AuditFindingContract:
        return AuditFindingContract(
            code=self.code,
            severity=self.severity,
            component=self.component,
            path=self.path,
            detail=self.detail,
            repair_code=self.repair_code,
        )


@dataclass(frozen=True, slots=True)
class StructuralAuditResult:
    """Validated, deterministic data shared by both CLI output surfaces."""

    response: StructuralAuditContract

    @property
    def has_findings(self) -> bool:
        return bool(self.response.findings)

    @property
    def finding_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.response.findings)

    def as_data(self) -> dict[str, object]:
        return self.response.model_dump(mode="json")


class StructuralAuditService:
    """Inspect canonical project state without creating or changing files."""

    _EXPECTED_VERSIONS: ClassVar[dict[str, int]] = {
        "manifest": 1,
        "event-log": 1,
        "dependency-graph": 1,
        "state-store": 2,
    }

    def inspect(self, start: Path | str | None = None) -> StructuralAuditResult:
        """Audit the nearest project rooted at ``start``."""
        filesystem = self._discover(start)
        findings: list[_Finding] = []
        components: list[AuditComponentContract] = []
        versions: list[AuditVersionContract] = []
        manifest: ProjectContract | None = None
        event_snapshot: EventLogSnapshot | None = None
        state_store: StateStore | None = None

        manifest, manifest_component, manifest_version = self._inspect_manifest(
            filesystem,
            findings,
        )
        components.append(manifest_component)
        versions.append(manifest_version)

        event_snapshot, event_component, event_version = self._inspect_event_log(
            filesystem,
            findings,
        )
        components.append(event_component)
        versions.append(event_version)

        graph_component, graph_version = self._inspect_graph(filesystem, findings)
        components.append(graph_component)
        versions.append(graph_version)

        state_store, state_component, state_version = self._inspect_state_store(
            filesystem,
            findings,
        )
        components.append(state_component)
        versions.append(state_version)

        if state_store is not None and event_snapshot is not None:
            try:
                self._inspect_consistency(
                    state_store,
                    event_snapshot,
                    findings,
                )
            except (ProjectFilesystemError, StateStoreError):
                self._add_finding(
                    findings,
                    "state-store-corrupt",
                    "state-store",
                    "the SQLite state store contains data that cannot be trusted",
                    "rebuild-state-store",
                    DEFAULT_STATE_STORE_PATH,
                )

        findings.sort(key=lambda finding: (finding.component, finding.path or "", finding.code))
        repair_guidance = self._repair_guidance(findings)
        project = (
            AuditProjectContract(id=manifest.id, name=manifest.name)
            if manifest is not None
            else None
        )
        response = StructuralAuditContract(
            project_directory=filesystem.root.as_posix(),
            project=project,
            state="issues-found" if findings else "clean",
            schema_versions=tuple(versions),
            components=tuple(components),
            findings=tuple(finding.contract() for finding in findings),
            repair_guidance=repair_guidance,
        )
        return StructuralAuditResult(response=response)

    @staticmethod
    def _discover(start: Path | str | None) -> ProjectFilesystem:
        try:
            return ProjectFilesystem.discover(start or Path.cwd())
        except ProjectRootNotFoundError:
            raise
        except ProjectFilesystemError as error:
            raise StructuralAuditError("project root is unsafe or invalid") from error

    def _inspect_manifest(
        self,
        filesystem: ProjectFilesystem,
        findings: list[_Finding],
    ) -> tuple[ProjectContract | None, AuditComponentContract, AuditVersionContract]:
        path = PROJECT_MARKER
        presence = self._presence(filesystem, path)
        expected = self._EXPECTED_VERSIONS["manifest"]
        if presence == "missing":
            self._add_finding(
                findings,
                "manifest-missing",
                "manifest",
                "the canonical project manifest is missing",
                "run-init",
                path,
            )
            return (
                None,
                self._component("manifest", path, "missing", "file is absent"),
                self._version("manifest", expected, None, "missing"),
            )
        if presence == "unsafe":
            self._add_finding(
                findings,
                "manifest-unsafe-path",
                "manifest",
                "the project manifest path is unsafe or is a symlink",
                "remove-unsafe-path",
                path,
            )
            return (
                None,
                self._component("manifest", path, "unsafe", "path is not trusted"),
                self._version("manifest", expected, None, "unavailable"),
            )
        try:
            manifest = JsonDocumentRepository(filesystem, path, ProjectContract).load().value
        except (
            FileNotFoundError,
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
        ) as error:
            code = (
                "manifest-version-mismatch"
                if "schema_version" in str(error)
                else "manifest-corrupt"
            )
            repair = "restore-project-manifest"
            detail = "the project manifest does not satisfy the published project contract"
            self._add_finding(findings, code, "manifest", detail, repair, path)
            version_state: Literal["mismatch", "unavailable"] = (
                "mismatch" if code.endswith("version-mismatch") else "unavailable"
            )
            return (
                None,
                self._component("manifest", path, "corrupt", detail),
                self._version("manifest", expected, None, version_state),
            )
        return (
            manifest,
            self._component("manifest", path, "valid", "manifest matches the published contract"),
            self._version("manifest", expected, manifest.schema_version, "match"),
        )

    def _inspect_event_log(
        self,
        filesystem: ProjectFilesystem,
        findings: list[_Finding],
    ) -> tuple[EventLogSnapshot | None, AuditComponentContract, AuditVersionContract]:
        path = DEFAULT_EVENT_LOG_PATH
        expected = self._EXPECTED_VERSIONS["event-log"]
        presence = self._presence(filesystem, path)
        if presence == "missing":
            self._add_finding(
                findings,
                "event-log-missing",
                "event-log",
                "the canonical event log is missing",
                "rebuild-event-log",
                path,
            )
            return (
                None,
                self._component("event-log", path, "missing", "file is absent"),
                self._version("event-log", expected, None, "missing"),
            )
        if presence == "unsafe":
            self._add_finding(
                findings,
                "event-log-unsafe-path",
                "event-log",
                "the event-log path is unsafe or is a symlink",
                "remove-unsafe-path",
                path,
            )
            return (
                None,
                self._component("event-log", path, "unsafe", "path is not trusted"),
                self._version("event-log", expected, None, "unavailable"),
            )
        try:
            snapshot = EventLog(filesystem).replay()
        except (CorruptEventLogError, EventLogError, ProjectFilesystemError) as error:
            code = (
                "event-log-incomplete-tail"
                if isinstance(error, IncompleteEventLogTailError)
                else "event-log-corrupt"
            )
            repair = (
                "recover-event-log-tail"
                if code == "event-log-incomplete-tail"
                else "restore-event-log"
            )
            detail = "the event log cannot be replayed safely"
            self._add_finding(findings, code, "event-log", detail, repair, path)
            return (
                None,
                self._component("event-log", path, "corrupt", detail),
                self._version("event-log", expected, None, "unavailable"),
            )
        return (
            snapshot,
            self._component(
                "event-log",
                path,
                "valid",
                f"{snapshot.last_sequence} event(s) replayed successfully",
            ),
            self._version("event-log", expected, 1, "match"),
        )

    def _inspect_graph(
        self,
        filesystem: ProjectFilesystem,
        findings: list[_Finding],
    ) -> tuple[AuditComponentContract, AuditVersionContract]:
        path = DEFAULT_DEPENDENCY_GRAPH_PATH
        expected = self._EXPECTED_VERSIONS["dependency-graph"]
        presence = self._presence(filesystem, path)
        if presence == "missing":
            self._add_finding(
                findings,
                "dependency-graph-missing",
                "dependency-graph",
                "the canonical dependency graph is missing",
                "rebuild-dependency-graph",
                path,
            )
            return self._component(
                "dependency-graph", path, "missing", "file is absent"
            ), self._version("dependency-graph", expected, None, "missing")
        if presence == "unsafe":
            self._add_finding(
                findings,
                "dependency-graph-unsafe-path",
                "dependency-graph",
                "the dependency graph path is unsafe or is a symlink",
                "remove-unsafe-path",
                path,
            )
            return self._component(
                "dependency-graph", path, "unsafe", "path is not trusted"
            ), self._version("dependency-graph", expected, None, "unavailable")
        try:
            snapshot = DependencyGraphRepository(filesystem).load()
        except (
            FileNotFoundError,
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
            ValueError,
        ) as error:
            detail = "the dependency graph does not satisfy its published contract"
            code = (
                "dependency-graph-version-mismatch"
                if "schema_version" in str(error)
                else "dependency-graph-corrupt"
            )
            self._add_finding(
                findings,
                code,
                "dependency-graph",
                detail,
                "restore-dependency-graph",
                path,
            )
            state: Literal["mismatch", "unavailable"] = (
                "mismatch" if code.endswith("version-mismatch") else "unavailable"
            )
            return self._component("dependency-graph", path, "corrupt", detail), self._version(
                "dependency-graph", expected, None, state
            )
        return self._component(
            "dependency-graph",
            path,
            "valid",
            f"{len(snapshot.graph.nodes)} node(s), {len(snapshot.graph.edges)} edge(s)",
        ), self._version("dependency-graph", expected, 1, "match")

    def _inspect_state_store(
        self,
        filesystem: ProjectFilesystem,
        findings: list[_Finding],
    ) -> tuple[StateStore | None, AuditComponentContract, AuditVersionContract]:
        path = DEFAULT_STATE_STORE_PATH
        expected = self._EXPECTED_VERSIONS["state-store"]
        presence = self._presence(filesystem, path)
        if presence == "missing":
            self._add_finding(
                findings,
                "state-store-missing",
                "state-store",
                "the SQLite state store is missing",
                "rebuild-state-store",
                path,
            )
            return (
                None,
                self._component("state-store", path, "missing", "file is absent"),
                self._version("state-store", expected, None, "missing"),
            )
        if presence == "unsafe":
            self._add_finding(
                findings,
                "state-store-unsafe-path",
                "state-store",
                "the SQLite state-store path is unsafe or is a symlink",
                "remove-unsafe-path",
                path,
            )
            return (
                None,
                self._component("state-store", path, "unsafe", "path is not trusted"),
                self._version("state-store", expected, None, "unavailable"),
            )
        try:
            store = StateStore(filesystem, read_only=True)
        except UnsupportedStateSchemaError as error:
            observed = _unsupported_version(str(error))
            detail = "the SQLite state store requires an explicit schema migration"
            self._add_finding(
                findings,
                "state-store-version-mismatch",
                "state-store",
                detail,
                "run-state-migration",
                path,
            )
            return (
                None,
                self._component("state-store", path, "corrupt", detail),
                self._version("state-store", expected, observed, "mismatch"),
            )
        except (
            FileNotFoundError,
            ProjectFilesystemError,
            StateStoreCorruptionError,
            StateStoreError,
        ) as error:
            detail = "the SQLite state store cannot be inspected safely in read-only mode"
            repair = "stop-active-writers" if "active WAL" in str(error) else "rebuild-state-store"
            self._add_finding(findings, "state-store-corrupt", "state-store", detail, repair, path)
            return (
                None,
                self._component("state-store", path, "corrupt", detail),
                self._version("state-store", expected, None, "unavailable"),
            )
        return (
            store,
            self._component(
                "state-store",
                path,
                "valid",
                "schema validated through a read-only SQLite connection",
            ),
            self._version("state-store", expected, store.schema_version, "match"),
        )

    @staticmethod
    def _inspect_consistency(
        state_store: StateStore,
        event_snapshot: EventLogSnapshot,
        findings: list[_Finding],
    ) -> None:
        report = state_store.check_consistency(event_snapshot)
        if report.event_state.value != "in-sync":
            _add_consistency_finding(
                findings,
                f"state-index-{report.event_state.value}",
                "state-store",
                report.event_detail,
                "refresh-state-index",
                DEFAULT_STATE_STORE_PATH,
            )
        entities = {
            (entity.entity_type, entity.entity_id): entity for entity in state_store.list_entities()
        }
        for source in report.sources:
            key = (source.entity_type, source.entity_id)
            entity = entities[key]
            path = source.source_path
            if source.state is SourceIndexState.IN_SYNC:
                continue
            approved = entity.status == "approved"
            if approved and source.state is SourceIndexState.CHANGED:
                code = "approved-file-mutated"
                repair = "create-new-approved-revision"
            elif approved and source.state is SourceIndexState.MISSING:
                code = "approved-file-missing"
                repair = "restore-approved-file"
            elif approved and source.state is SourceIndexState.INVALID_PATH:
                code = "approved-file-unsafe-path"
                repair = "remove-unsafe-path"
            else:
                code = f"canonical-source-{source.state.value}"
                repair = "refresh-state-index"
            _add_consistency_finding(findings, code, "approved-files", source.detail, repair, path)

    @staticmethod
    def _presence(filesystem: ProjectFilesystem, path: RepositoryPath) -> str:
        try:
            filesystem.resolve(path, must_exist=True)
        except FileNotFoundError:
            return "missing"
        except (ProjectFilesystemError, UnsafeProjectPathError):
            return "unsafe"
        return "present"

    @staticmethod
    def _component(
        name: str,
        path: RepositoryPath,
        state: Literal["valid", "missing", "corrupt", "unsafe", "unavailable"],
        detail: str,
    ) -> AuditComponentContract:
        return AuditComponentContract(name=name, path=path.value, state=state, detail=detail)

    @staticmethod
    def _version(
        component: str,
        expected: int,
        observed: int | None,
        state: Literal["match", "missing", "mismatch", "unavailable"],
    ) -> AuditVersionContract:
        return AuditVersionContract(
            component=component,
            expected=expected,
            observed=observed,
            state=state,
        )

    @staticmethod
    def _add_finding(
        findings: list[_Finding],
        code: str,
        component: str,
        detail: str,
        repair_code: str,
        path: RepositoryPath,
    ) -> None:
        findings.append(
            _Finding(
                code=code,
                component=component,
                detail=detail,
                repair_code=repair_code,
                path=path.value,
            )
        )

    @staticmethod
    def _repair_guidance(findings: list[_Finding]) -> tuple[RepairGuidanceContract, ...]:
        actions = {
            "create-new-approved-revision": RepairGuidanceContract(
                code="create-new-approved-revision",
                description=(
                    "preserve the changed file as a new revision and request approval again"
                ),
                command="ludowright approval request PATH --revision <new-fingerprint>",
            ),
            "rebuild-dependency-graph": RepairGuidanceContract(
                code="rebuild-dependency-graph",
                description="rebuild the graph from canonical project records after review",
                command="ludowright graph rebuild PATH",
            ),
            "rebuild-event-log": RepairGuidanceContract(
                code="rebuild-event-log",
                description="restore the event log from a trusted project backup",
                command="restore .ludowright/events.jsonl from a trusted backup",
            ),
            "rebuild-state-store": RepairGuidanceContract(
                code="rebuild-state-store",
                description="preserve diagnostic evidence, then rebuild the derived SQLite index",
                command="ludowright state rebuild PATH",
            ),
            "recover-event-log-tail": RepairGuidanceContract(
                code="recover-event-log-tail",
                description="explicitly remove only the incomplete trailing event-log fragment",
                command="ludowright event-log recover-tail PATH",
            ),
            "refresh-state-index": RepairGuidanceContract(
                code="refresh-state-index",
                description="replay canonical events and refresh the derived source index",
                command="ludowright state refresh PATH",
            ),
            "remove-unsafe-path": RepairGuidanceContract(
                code="remove-unsafe-path",
                description=(
                    "remove the symlink or non-regular entry and restore a regular project file"
                ),
                command="remove the unsafe path, then rerun the audit",
            ),
            "restore-approved-file": RepairGuidanceContract(
                code="restore-approved-file",
                description=(
                    "restore the approved file from its trusted revision or supersede it explicitly"
                ),
                command="restore the approved source, then rerun the audit",
            ),
            "restore-dependency-graph": RepairGuidanceContract(
                code="restore-dependency-graph",
                description=(
                    "restore or regenerate the graph only after preserving the corrupt file"
                ),
                command="restore .ludowright/dependency-graph.json from a trusted source",
            ),
            "restore-event-log": RepairGuidanceContract(
                code="restore-event-log",
                description="preserve the corrupt log and restore it from a trusted backup",
                command="restore .ludowright/events.jsonl from a trusted source",
            ),
            "restore-project-manifest": RepairGuidanceContract(
                code="restore-project-manifest",
                description=(
                    "restore a manifest that validates against the published project contract"
                ),
                command="restore .ludowright/project.json from a trusted source",
            ),
            "run-init": RepairGuidanceContract(
                code="run-init",
                description="initialize the project through the project initialization workflow",
                command='ludowright init PATH --name "Game name"',
            ),
            "run-state-migration": RepairGuidanceContract(
                code="run-state-migration",
                description=(
                    "plan, dry-run, back up, and explicitly apply the required state migration"
                ),
                command="ludowright migrate state PATH --dry-run",
            ),
            "stop-active-writers": RepairGuidanceContract(
                code="stop-active-writers",
                description=(
                    "stop local writers and rerun the audit against a quiescent SQLite store"
                ),
                command="stop active LudoWright writers, then rerun the audit",
            ),
        }
        selected = {finding.repair_code for finding in findings}
        return tuple(actions[code] for code in sorted(selected))


def _add_consistency_finding(
    findings: list[_Finding],
    code: str,
    component: str,
    detail: str,
    repair_code: str,
    path: RepositoryPath | None,
) -> None:
    findings.append(
        _Finding(
            code=code,
            component=component,
            detail=detail,
            repair_code=repair_code,
            path=path.value if path is not None else None,
        )
    )


def _unsupported_version(message: str) -> int | None:
    match = re.search(r"state schema v(\d+)", message)
    return int(match.group(1)) if match else None
