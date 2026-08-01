"""Deterministic, read-only readiness audit for one LudoWright project."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import ValidationError

from ludowright.application.asset_audit import AssetAuditError, AssetAuditService
from ludowright.application.asset_registry import DEFAULT_ASSET_REGISTRY_PATH
from ludowright.contracts import (
    PROJECT_AUDIT_CATEGORY_ORDER,
    ApprovalContract,
    AssetRegistryContract,
    DocumentRefreshStateContract,
    GenerationReceiptContract,
    ImageGenOperationContract,
    PackageIndexContract,
    PackageManifestContract,
    ProjectAuditActionContract,
    ProjectAuditCategory,
    ProjectAuditCategoryContract,
    ProjectAuditFindingContract,
    ProjectAuditReportContract,
    ProjectAuditSeverity,
    ProjectAuditSourceContract,
    ProjectAuditSourceState,
    ProjectAuditState,
    ProjectContract,
    TechnicalSheetReportContract,
    VisualReferenceContract,
)
from ludowright.contracts.common import ContractModel
from ludowright.domain import DependencyNodeKind, FreshnessState
from ludowright.infrastructure import (
    APPROVAL_DIRECTORY,
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_DOCUMENT_DIRECTORY,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    GENERATED_REFERENCE_DIRECTORY,
    GENERATION_RECEIPT_DIRECTORY,
    PACKAGE_ARCHIVE_MAX_BYTES,
    DependencyGraphRepository,
    EventLog,
    EventLogSnapshot,
    JsonDocumentRepository,
    PackageArchiveBuilder,
    PackageFileScanner,
    PackageManifestScanError,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    StateStore,
    StructuredDocumentError,
    UnsafeProjectPathError,
    YamlDocumentRepository,
)
from ludowright.infrastructure.filesystem import PROJECT_MARKER

_JSON_MAX_BYTES = 2 * 1024 * 1024
_PACKAGE_MANIFEST_MAX_BYTES = 16 * 1024 * 1024
_SOURCE_MAX_BYTES = 64 * 1024 * 1024
_AUDIT_LOCK_DIRECTORY_PREFIX = ".ludowright/locks/"
_ContractT = TypeVar("_ContractT", bound="ContractModel")


class ProjectAuditError(RuntimeError):
    """Base failure for global project audits."""


class ProjectAuditCorruptError(ProjectAuditError):
    """Raised when a canonical project input is invalid or unsafe."""


class ProjectAuditConflictError(ProjectAuditError):
    """Raised when a project changes while the audit is reading it."""


@dataclass(frozen=True, slots=True)
class ProjectAuditResult:
    """Stable result shared by the human and JSON CLI renderers."""

    report: ProjectAuditReportContract

    def as_data(self) -> dict[str, object]:
        """Return the report plus convenient count projections."""
        data = self.report.model_dump(mode="json")
        data.update(
            {
                "error_count": self.report.error_count,
                "warning_count": self.report.warning_count,
            }
        )
        return data


@dataclass
class _AuditContext:
    filesystem: ProjectFilesystem
    scanner: PackageFileScanner
    initial_inventory: tuple[str, ...]
    sources: dict[str, ProjectAuditSourceContract] = field(default_factory=dict)
    findings: list[ProjectAuditFindingContract] = field(default_factory=list)
    item_counts: dict[str, int] = field(default_factory=dict)
    directories: set[str] = field(default_factory=set)

    def set_item_count(self, category: str, count: int) -> None:
        self.item_counts[category] = max(0, count)

    def add_source(
        self,
        path: str,
        *,
        state: ProjectAuditSourceState,
        digest: str | None,
        item_count: int = 0,
        size_bytes: int | None = None,
        detail: str,
    ) -> None:
        source = ProjectAuditSourceContract(
            path=path,
            state=state,
            digest=digest,
            item_count=item_count,
            size_bytes=size_bytes,
            detail=detail,
        )
        previous = self.sources.get(path)
        if previous is not None:
            previous_identity = (previous.state, previous.digest, previous.size_bytes)
            current_identity = (source.state, source.digest, source.size_bytes)
            if previous_identity != current_identity:
                raise ProjectAuditConflictError(
                    f"project audit observed different revisions for {path}"
                )
            return
        self.sources[path] = source

    def observe_path(self, path: str, *, detail: str, item_count: int = 1) -> str | None:
        """Observe one regular file without weakening scanner safety."""
        try:
            snapshot, _payload = self.scanner.read_file(path)
        except FileNotFoundError:
            self.add_source(
                path,
                state="missing",
                digest=None,
                item_count=0,
                detail="file is absent",
            )
            return None
        except (PackageManifestScanError, ProjectFilesystemError) as error:
            self.add_source(
                path,
                state="invalid",
                digest=None,
                item_count=0,
                detail=str(error),
            )
            return None
        self.add_source(
            path,
            state="current",
            digest=snapshot.sha256,
            item_count=item_count,
            size_bytes=snapshot.size_bytes,
            detail=detail,
        )
        return snapshot.sha256

    def observe_directory(self, path: str, *, item_count: int, detail: str) -> None:
        repository_path = RepositoryPath(path)
        self.directories.add(path)
        try:
            exists = self.filesystem.directory_exists(repository_path)
        except (ProjectFilesystemError, UnsafeProjectPathError) as error:
            self.add_source(
                path,
                state="invalid",
                digest=None,
                item_count=0,
                detail=str(error),
            )
            return
        self.add_source(
            path,
            state="current" if exists else "missing",
            digest=None,
            item_count=item_count if exists else 0,
            detail=detail if exists else "directory is absent",
        )

    def load_json(
        self,
        path: str,
        model: type[_ContractT],
        *,
        detail: str,
        max_bytes: int = _JSON_MAX_BYTES,
    ) -> _ContractT | None:
        try:
            repository = JsonDocumentRepository(
                self.filesystem,
                RepositoryPath(path),
                model,
                max_bytes=max_bytes,
            )
            snapshot = repository.load()
        except FileNotFoundError:
            self.add_source(
                path,
                state="missing",
                digest=None,
                detail="file is absent",
            )
            return None
        except (
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
            ValueError,
        ) as error:
            self.observe_path(path, detail=f"invalid structured document: {error}")
            return None
        self.add_source(
            path,
            state="current",
            digest=snapshot.digest,
            size_bytes=snapshot.size_bytes,
            detail=detail,
        )
        return snapshot.value

    def load_yaml(
        self,
        path: str,
        model: type[_ContractT],
        *,
        detail: str,
    ) -> _ContractT | None:
        try:
            repository = YamlDocumentRepository(
                self.filesystem,
                RepositoryPath(path),
                model,
            )
            snapshot = repository.load()
        except FileNotFoundError:
            self.add_source(
                path,
                state="missing",
                digest=None,
                detail="file is absent",
            )
            return None
        except (
            ProjectFilesystemError,
            StructuredDocumentError,
            ValidationError,
            ValueError,
        ) as error:
            self.observe_path(path, detail=f"invalid structured document: {error}")
            return None
        self.add_source(
            path,
            state="current",
            digest=snapshot.digest,
            size_bytes=snapshot.size_bytes,
            detail=detail,
        )
        return snapshot.value

    def add_finding(
        self,
        *,
        category: ProjectAuditCategory,
        code: str,
        severity: ProjectAuditSeverity,
        subject: str,
        paths: tuple[str, ...] = (),
        related_ids: tuple[str, ...] = (),
        message: str,
        remediation: str,
    ) -> None:
        self.findings.append(
            ProjectAuditFindingContract(
                category=category,
                code=code,
                severity=severity,
                subject=subject,
                paths=tuple(sorted(set(paths))),
                related_ids=tuple(sorted(set(related_ids))),
                message=message,
                remediation=remediation,
            )
        )

    def verify_file(
        self,
        path: str,
        *,
        category: ProjectAuditCategory,
        code: str,
        subject: str,
        expected_digest: str | None = None,
        expected_size: int | None = None,
        remediation: str,
    ) -> bool:
        actual_digest = self.observe_path(path, detail="referenced artifact")
        source = self.sources[path]
        if actual_digest is None:
            self.add_finding(
                category=category,
                code=code,
                severity="error",
                subject=subject,
                paths=(path,),
                message="referenced artifact is missing or unsafe",
                remediation=remediation,
            )
            return False
        if expected_digest is not None and actual_digest != expected_digest:
            self.add_finding(
                category=category,
                code=code,
                severity="error",
                subject=subject,
                paths=(path,),
                message="referenced artifact checksum does not match its declaration",
                remediation=remediation,
            )
            return False
        if expected_size is not None:
            try:
                size_matches = source.size_bytes == expected_size
            except TypeError:
                size_matches = False
            if not size_matches:
                self.add_finding(
                    category=category,
                    code=code,
                    severity="error",
                    subject=subject,
                    paths=(path,),
                    message="referenced artifact size does not match its declaration",
                    remediation=remediation,
                )
                return False
        return True

    def finish(self) -> str:
        """Detect concurrent changes and return the deterministic source digest."""
        try:
            final_inventory = _inventory(self.scanner)
        except (PackageManifestScanError, ProjectFilesystemError) as error:
            raise ProjectAuditConflictError(
                "project changed while the audit was running"
            ) from error
        if final_inventory != self.initial_inventory:
            raise ProjectAuditConflictError("project files changed while the audit was running")

        for path in self.directories:
            try:
                exists = self.filesystem.directory_exists(RepositoryPath(path))
            except (ProjectFilesystemError, UnsafeProjectPathError) as error:
                raise ProjectAuditConflictError(
                    f"project audit directory became unsafe: {path}"
                ) from error
            expected = self.sources[path].state == "current"
            if exists != expected:
                raise ProjectAuditConflictError(
                    f"project audit directory changed during the audit: {path}"
                )

        for path, source in self.sources.items():
            if source.state == "missing":
                if path in final_inventory:
                    raise ProjectAuditConflictError(
                        f"project audit source appeared during the audit: {path}"
                    )
                continue
            if source.digest is None:
                continue
            try:
                snapshot, _payload = self.scanner.read_file(path)
            except (
                FileNotFoundError,
                PackageManifestScanError,
                ProjectFilesystemError,
            ) as error:
                raise ProjectAuditConflictError(
                    f"project audit source became unreadable: {path}"
                ) from error
            actual = snapshot.sha256
            if actual != source.digest:
                raise ProjectAuditConflictError(
                    f"project audit source changed during the audit: {path}"
                )

        ordered_sources = tuple(self.sources[path] for path in sorted(self.sources))
        digest_payload = json.dumps(
            [source.model_dump(mode="json") for source in ordered_sources],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(digest_payload).hexdigest()


class ProjectAuditService:
    """Audit project readiness without creating or modifying project state."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("project audit requires ProjectFilesystem")
        self._filesystem = filesystem

    def audit(self, *, dry_run: bool = False) -> ProjectAuditResult:
        """Return one deterministic report for the current project snapshot."""
        scanner = PackageFileScanner(
            self._filesystem,
            max_file_bytes=_SOURCE_MAX_BYTES,
        )
        try:
            initial_inventory = _inventory(scanner)
        except (PackageManifestScanError, ProjectFilesystemError) as error:
            raise ProjectAuditCorruptError(
                "project inventory cannot be inspected safely"
            ) from error
        context = _AuditContext(self._filesystem, scanner, initial_inventory)
        project = context.load_json(
            PROJECT_MARKER.value,
            ProjectContract,
            detail="validated project manifest",
        )
        if project is None:
            raise ProjectAuditCorruptError("project manifest is missing or invalid")

        event_snapshot, graph_snapshot, state_store = _audit_product(context, project.id)
        asset_registry = _audit_assets(context)
        document_count = _audit_documents(context)
        references = _audit_references(context, asset_registry)
        approvals = _audit_approvals(context, references)
        _audit_jobs(context, references, graph_snapshot)
        _audit_sheets(context, references)
        _audit_packages(context, project.id)
        _audit_graph_freshness(context, graph_snapshot)

        # Keep these values explicit so an empty but structurally valid project
        # receives review findings instead of being mistaken for a release.
        context.set_item_count("product", 1)
        context.set_item_count("documents", document_count)
        context.set_item_count("assets", len(asset_registry.assets) if asset_registry else 0)
        context.set_item_count("references", len(references))
        context.set_item_count("approvals", len(approvals))
        if event_snapshot is not None and state_store is not None:
            # The variables are intentionally retained in the flow above: the
            # read-only state check is part of the product readiness category.
            del event_snapshot, state_store

        source_digest = context.finish()
        report = _build_report(
            context,
            project_id=project.id,
            project_name=project.name,
            dry_run=dry_run,
            source_digest=source_digest,
        )
        return ProjectAuditResult(report=report)


def _audit_product(
    context: _AuditContext,
    project_id: str,
) -> tuple[EventLogSnapshot | None, Any | None, StateStore | None]:
    event_snapshot: EventLogSnapshot | None = None
    event_path = DEFAULT_EVENT_LOG_PATH.value
    if context.sources.get(event_path) is None:
        if event_path not in context.initial_inventory:
            context.add_source(
                event_path,
                state="missing",
                digest=None,
                detail="canonical event log is absent",
            )
            context.add_finding(
                category="product",
                code="event-log-missing",
                severity="error",
                subject=event_path,
                paths=(event_path,),
                message="the canonical event log is missing",
                remediation="restore the event log or initialize the project again",
            )
        else:
            try:
                event_snapshot = EventLog(context.filesystem).replay()
                context.observe_path(event_path, detail="validated hash-chained event log")
            except Exception as error:
                context.observe_path(event_path, detail="invalid event log")
                context.add_finding(
                    category="product",
                    code="event-log-invalid",
                    severity="error",
                    subject=event_path,
                    paths=(event_path,),
                    message=f"the event log cannot be replayed safely: {error}",
                    remediation="repair the event log through its explicit recovery workflow",
                )

    graph_snapshot = None
    graph_path = DEFAULT_DEPENDENCY_GRAPH_PATH.value
    try:
        graph_snapshot = DependencyGraphRepository(context.filesystem).load_optional()
    except Exception as error:
        context.observe_path(graph_path, detail="invalid dependency graph")
        context.add_finding(
            category="product",
            code="dependency-graph-invalid",
            severity="error",
            subject=graph_path,
            paths=(graph_path,),
            message=f"the dependency graph cannot be validated safely: {error}",
            remediation="restore a valid dependency graph from canonical project state",
        )
    else:
        if graph_snapshot is None:
            context.add_source(
                graph_path,
                state="missing",
                digest=None,
                detail="canonical dependency graph is absent",
            )
            context.add_finding(
                category="product",
                code="dependency-graph-missing",
                severity="error",
                subject=graph_path,
                paths=(graph_path,),
                message="the canonical dependency graph is missing",
                remediation="restore or rebuild the dependency graph before production work",
            )
        else:
            graph_digest = context.observe_path(
                graph_path,
                detail="validated dependency graph",
                item_count=1,
            )
            if graph_digest != graph_snapshot.digest:
                raise ProjectAuditConflictError(
                    "dependency graph changed while the audit was reading it"
                )
            project_nodes = tuple(
                node
                for node in graph_snapshot.graph.nodes
                if node.key.kind is DependencyNodeKind.PROJECT and node.key.id == project_id
            )
            if not project_nodes:
                context.add_finding(
                    category="product",
                    code="project-node-missing",
                    severity="error",
                    subject=project_id,
                    paths=(graph_path,),
                    related_ids=(project_id,),
                    message="the dependency graph has no node for the project manifest",
                    remediation="rebuild the graph with the project node before continuing",
                )

    state_store: StateStore | None = None
    state_path = DEFAULT_STATE_STORE_PATH.value
    if state_path not in context.initial_inventory:
        context.add_source(
            state_path,
            state="missing",
            digest=None,
            detail="SQLite state store is absent",
        )
        context.add_finding(
            category="product",
            code="state-store-missing",
            severity="error",
            subject=state_path,
            paths=(state_path,),
            message="the rebuildable SQLite state store is missing",
            remediation="initialize or rebuild the current SQLite state store",
        )
    else:
        try:
            state_store = StateStore(context.filesystem, read_only=True)
            context.observe_path(state_path, detail="validated read-only SQLite state store")
            if event_snapshot is not None:
                consistency = state_store.check_consistency(event_snapshot)
                if not consistency.is_consistent:
                    context.add_finding(
                        category="product",
                        code="state-index-inconsistent",
                        severity="error",
                        subject=state_path,
                        paths=(state_path, event_path),
                        message="SQLite does not match the canonical event log or indexed sources",
                        remediation="rebuild the derived SQLite index from canonical project files",
                    )
            if state_store.get_entity("project", project_id) is None:
                context.add_finding(
                    category="product",
                    code="project-index-missing",
                    severity="error",
                    subject=project_id,
                    paths=(state_path, PROJECT_MARKER.value),
                    related_ids=(project_id,),
                    message="the project manifest is not indexed in SQLite",
                    remediation="rebuild the derived state index without changing canonical files",
                )
        except Exception as error:
            context.observe_path(state_path, detail="invalid SQLite state store")
            context.add_finding(
                category="product",
                code="state-store-invalid",
                severity="error",
                subject=state_path,
                paths=(state_path,),
                message=f"the SQLite state store cannot be inspected read-only: {error}",
                remediation="restore a valid state store at the current schema version",
            )
    return event_snapshot, graph_snapshot, state_store


def _audit_documents(context: _AuditContext) -> int:
    directory = DEFAULT_DOCUMENT_DIRECTORY.value
    paths = tuple(path for path in context.initial_inventory if path.startswith(f"{directory}/"))
    markdown_paths = tuple(path for path in paths if path.endswith(".md"))
    json_paths = tuple(path for path in paths if path.endswith(".json"))
    context.observe_directory(
        directory,
        item_count=len(markdown_paths),
        detail="project document outputs and refresh snapshots",
    )
    for path in json_paths:
        state = context.load_json(
            path,
            DocumentRefreshStateContract,
            detail="validated document refresh state",
        )
        if state is None:
            context.add_finding(
                category="documents",
                code="document-state-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="a persisted document refresh state is invalid",
                remediation="restore the state from the canonical document refresh contract",
            )
    directory_exists = context.filesystem.directory_exists(RepositoryPath(directory))
    if not directory_exists:
        context.add_finding(
            category="documents",
            code="documents-directory-missing",
            severity="warning",
            subject=directory,
            paths=(directory,),
            message="the project has no generated document directory",
            remediation="complete the guided documentation phase before release review",
        )
    elif not markdown_paths:
        context.add_finding(
            category="documents",
            code="documents-empty",
            severity="warning",
            subject=directory,
            paths=(directory,),
            message="the document directory has no Markdown outputs",
            remediation="generate at least the required product and architecture documents",
        )
    return len(markdown_paths)


def _audit_assets(context: _AuditContext) -> AssetRegistryContract | None:
    path = DEFAULT_ASSET_REGISTRY_PATH.value
    registry = context.load_yaml(
        path,
        AssetRegistryContract,
        detail="validated canonical asset registry",
    )
    if registry is None:
        if context.sources[path].state == "missing":
            context.add_finding(
                category="assets",
                code="asset-registry-missing",
                severity="warning",
                subject=path,
                paths=(path,),
                message="the project has no canonical asset registry",
                remediation="create the asset registry before planning production work",
            )
        else:
            context.add_finding(
                category="assets",
                code="asset-registry-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="the canonical asset registry is invalid",
                remediation="restore a valid YAML asset registry without overwriting evidence",
            )
        return None

    if not registry.assets:
        context.add_finding(
            category="assets",
            code="asset-registry-empty",
            severity="warning",
            subject=path,
            paths=(path,),
            message="the asset registry contains no assets",
            remediation="discover or record the assets required by the project",
        )
        return registry

    try:
        result = AssetAuditService(context.filesystem).audit(dry_run=True)
    except AssetAuditError as error:
        raise ProjectAuditConflictError("asset sources changed during the global audit") from error
    except Exception as error:
        context.add_finding(
            category="assets",
            code="asset-audit-invalid",
            severity="error",
            subject=path,
            paths=(path, DEFAULT_DEPENDENCY_GRAPH_PATH.value),
            message=f"the asset completeness audit could not run: {error}",
            remediation="repair the registry and dependency graph before release review",
        )
        return registry

    for finding in result.report.findings:
        context.add_finding(
            category="assets",
            code=f"asset-{finding.code}",
            severity=finding.severity,
            subject=finding.subject,
            paths=(path, DEFAULT_DEPENDENCY_GRAPH_PATH.value),
            related_ids=(finding.asset_id,) if finding.asset_id is not None else (),
            message=finding.message,
            remediation="complete the asset registry and dependency prerequisites",
        )
    return registry


def _audit_references(
    context: _AuditContext,
    registry: AssetRegistryContract | None,
) -> dict[str, VisualReferenceContract]:
    prefix = f"{GENERATED_REFERENCE_DIRECTORY.value}/"
    paths = tuple(
        path
        for path in context.initial_inventory
        if path.startswith(prefix) and path.endswith(".json")
    )
    references: dict[str, VisualReferenceContract] = {}
    asset_ids = {asset.id for asset in registry.assets} if registry else set()
    for path in paths:
        reference = context.load_json(
            path,
            VisualReferenceContract,
            detail="validated visual reference",
        )
        if reference is None:
            context.add_finding(
                category="references",
                code="reference-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="a persisted visual reference is invalid",
                remediation="restore the reference contract and its provenance fields",
            )
            continue
        if reference.id in references:
            context.add_finding(
                category="references",
                code="reference-duplicate-id",
                severity="error",
                subject=reference.id,
                paths=(path,),
                related_ids=(reference.id,),
                message="more than one reference file declares the same ID",
                remediation="retain one canonical reference record per immutable ID",
            )
            continue
        references[reference.id] = reference
        if asset_ids and reference.target.asset_id not in asset_ids:
            context.add_finding(
                category="references",
                code="reference-target-missing",
                severity="error",
                subject=reference.id,
                paths=(path, DEFAULT_ASSET_REGISTRY_PATH.value),
                related_ids=(reference.id, reference.target.asset_id),
                message="the reference targets an asset absent from the registry",
                remediation="restore the target asset or remove the orphan reference safely",
            )
        if reference.status.value != "approved":
            context.add_finding(
                category="references",
                code="reference-not-approved",
                severity="warning",
                subject=reference.id,
                paths=(path,),
                related_ids=(reference.id,),
                message="the reference is not approved for downstream production use",
                remediation="review the exact immutable reference revision before packaging",
            )
        elif reference.approval_id is None:
            context.add_finding(
                category="references",
                code="approved-reference-without-approval",
                severity="error",
                subject=reference.id,
                paths=(path,),
                related_ids=(reference.id,),
                message="an approved reference does not name its approval record",
                remediation="restore the revision-bound approval relationship",
            )
    if registry and registry.assets and not references:
        context.add_finding(
            category="references",
            code="references-missing",
            severity="warning",
            subject=GENERATED_REFERENCE_DIRECTORY.value,
            paths=(GENERATED_REFERENCE_DIRECTORY.value,),
            message="the project has assets but no generated visual references",
            remediation="plan and record the required visual reference jobs",
        )
    context.observe_directory(
        GENERATED_REFERENCE_DIRECTORY.value,
        item_count=len(references),
        detail="generated visual reference records",
    )
    return references


def _audit_approvals(
    context: _AuditContext,
    references: dict[str, VisualReferenceContract],
) -> dict[str, ApprovalContract]:
    prefix = f"{APPROVAL_DIRECTORY.value}/"
    paths = tuple(
        path
        for path in context.initial_inventory
        if path.startswith(prefix) and path.endswith(".json")
    )
    approvals: dict[str, ApprovalContract] = {}
    for path in paths:
        approval = context.load_json(path, ApprovalContract, detail="validated approval record")
        if approval is None:
            context.add_finding(
                category="approvals",
                code="approval-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="a persisted approval record is invalid",
                remediation="restore the immutable approval history from its contract",
            )
            continue
        if approval.id in approvals:
            context.add_finding(
                category="approvals",
                code="approval-duplicate-id",
                severity="error",
                subject=approval.id,
                paths=(path,),
                related_ids=(approval.id,),
                message="more than one approval file declares the same ID",
                remediation="retain one canonical approval history per ID",
            )
            continue
        approvals[approval.id] = approval
        if (
            approval.subject.subject_kind.value == "reference"
            and approval.subject.id not in references
        ):
            context.add_finding(
                category="approvals",
                code="approval-subject-missing",
                severity="error",
                subject=approval.id,
                paths=(path, GENERATED_REFERENCE_DIRECTORY.value),
                related_ids=(approval.id, approval.subject.id),
                message="the approval refers to a reference that is not present",
                remediation="restore the referenced immutable record before using the approval",
            )

    for reference in references.values():
        if reference.status.value != "approved":
            continue
        approval = approvals.get(reference.approval_id or "")
        if approval is None:
            context.add_finding(
                category="approvals",
                code="approval-missing-for-reference",
                severity="error",
                subject=reference.id,
                paths=(GENERATED_REFERENCE_DIRECTORY.value, APPROVAL_DIRECTORY.value),
                related_ids=(reference.id,),
                message="the approved reference has no readable approval record",
                remediation="restore the approval that matches the exact reference revision",
            )
            continue
        if (
            approval.subject.subject_kind.value != "reference"
            or approval.subject.id != reference.id
        ):
            context.add_finding(
                category="approvals",
                code="approval-subject-mismatch",
                severity="error",
                subject=reference.id,
                paths=(APPROVAL_DIRECTORY.value,),
                related_ids=(approval.id, reference.id),
                message="the approval does not target the approved reference",
                remediation="create a new revision-bound approval for this reference",
            )
        if approval.history[-1].status.value != "approved":
            context.add_finding(
                category="approvals",
                code="approval-not-approved",
                severity="error",
                subject=approval.id,
                paths=(APPROVAL_DIRECTORY.value,),
                related_ids=(approval.id, reference.id),
                message="the approval history is not currently approved",
                remediation="complete or supersede the approval history explicitly",
            )
    if references and not approvals:
        context.add_finding(
            category="approvals",
            code="approvals-missing",
            severity="warning",
            subject=APPROVAL_DIRECTORY.value,
            paths=(APPROVAL_DIRECTORY.value,),
            message="the project has references but no approval records",
            remediation="review required references with a distinct human reviewer",
        )
    context.observe_directory(
        APPROVAL_DIRECTORY.value,
        item_count=len(approvals),
        detail="revision-bound approval records",
    )
    return approvals


def _audit_jobs(
    context: _AuditContext,
    references: dict[str, VisualReferenceContract],
    graph_snapshot: Any | None,
) -> None:
    operation_paths = tuple(
        path for path in context.initial_inventory if path.endswith("/operation.json")
    )
    receipt_prefix = f"{GENERATION_RECEIPT_DIRECTORY.value}/"
    receipt_paths = tuple(
        path
        for path in context.initial_inventory
        if path.startswith(receipt_prefix) and path.endswith(".json")
    )
    job_ids: set[str] = set()
    for path in operation_paths:
        operation = context.load_json(
            path,
            ImageGenOperationContract,
            detail="validated ImageGen operation",
        )
        if operation is None:
            context.add_finding(
                category="jobs",
                code="job-operation-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="a persisted ImageGen operation is invalid",
                remediation="restore the immutable operation manifest before execution",
            )
            continue
        job_ids.add(operation.job_id)
        for output in operation.outputs:
            context.verify_file(
                output.path,
                category="jobs",
                code="job-output-missing",
                subject=operation.id,
                remediation="restore the exact output or rerun the immutable job safely",
            )

    receipts_by_job: dict[str, list[GenerationReceiptContract]] = {}
    for path in receipt_paths:
        receipt = context.load_json(
            path,
            GenerationReceiptContract,
            detail="validated generation receipt",
        )
        if receipt is None:
            context.add_finding(
                category="jobs",
                code="generation-receipt-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="a generation receipt is invalid",
                remediation="restore the immutable terminal receipt or preserve it as failed state",
            )
            continue
        job_ids.add(receipt.job_id)
        receipts_by_job.setdefault(receipt.job_id, []).append(receipt)
        if receipt.status.value == "failed":
            context.add_finding(
                category="jobs",
                code="generation-failed",
                severity="warning",
                subject=receipt.id,
                paths=(path,),
                related_ids=(receipt.job_id,),
                message="the latest generation attempt failed",
                remediation="inspect the failure note and retry only with the same job revision",
            )
        for receipt_output in receipt.outputs:
            if receipt_output.reference_id not in references:
                context.add_finding(
                    category="jobs",
                    code="generation-reference-missing",
                    severity="error",
                    subject=receipt.id,
                    paths=(path, GENERATED_REFERENCE_DIRECTORY.value),
                    related_ids=(receipt.id, receipt_output.reference_id),
                    message="the receipt output has no corresponding visual reference record",
                    remediation="restore the candidate reference with its receipt lineage",
                )
            context.verify_file(
                receipt_output.path,
                category="jobs",
                code="generation-output-invalid",
                subject=receipt.id,
                expected_digest=receipt_output.sha256,
                expected_size=receipt_output.size_bytes,
                remediation="restore the exact PNG bytes or create a new receipt-bound attempt",
            )

    if graph_snapshot is not None:
        job_ids.update(
            node.key.id
            for node in graph_snapshot.graph.nodes
            if node.key.kind is DependencyNodeKind.VISUAL_JOB
        )
    for job_id, receipts in receipts_by_job.items():
        attempts = tuple(sorted(receipt.attempt for receipt in receipts))
        if attempts != tuple(range(1, len(attempts) + 1)):
            context.add_finding(
                category="jobs",
                code="generation-attempts-not-contiguous",
                severity="error",
                subject=job_id,
                paths=(GENERATION_RECEIPT_DIRECTORY.value,),
                related_ids=(job_id,),
                message="generation receipts do not form a contiguous attempt history",
                remediation=(
                    "preserve the append-only history and create the missing attempt record"
                ),
            )
    context.set_item_count("jobs", len(job_ids))
    if not job_ids and context.item_counts.get("assets", 0):
        context.add_finding(
            category="jobs",
            code="jobs-missing",
            severity="warning",
            subject="visual-jobs",
            paths=("visual-jobs",),
            message="the project has assets but no planned or executed visual jobs",
            remediation="derive a deterministic visual-job plan for the required assets",
        )


def _audit_sheets(
    context: _AuditContext,
    references: dict[str, VisualReferenceContract],
) -> None:
    sheet_paths = tuple(
        path for path in context.initial_inventory if path.endswith("technical-sheet.json")
    )
    sheet_count = 0
    for path in sheet_paths:
        report = context.load_json(
            path,
            TechnicalSheetReportContract,
            detail="validated technical-sheet report",
        )
        if report is None:
            context.add_finding(
                category="sheets",
                code="technical-sheet-invalid",
                severity="error",
                subject=path,
                paths=(path,),
                message="a technical-sheet report is invalid",
                remediation="restore the report and its deterministic output pair",
            )
            continue
        sheet_count += 1
        context.verify_file(
            report.output.path,
            category="sheets",
            code="technical-sheet-output-invalid",
            subject=report.id,
            expected_digest=report.output.sha256,
            expected_size=report.output.size_bytes,
            remediation="restore the exact sheet PNG or reassemble it create-only",
        )
        request_digest = context.observe_path(
            report.request_path,
            detail="technical-sheet request referenced by report",
        )
        if request_digest != report.request_sha256:
            context.add_finding(
                category="sheets",
                code="technical-sheet-request-changed",
                severity="error",
                subject=report.id,
                paths=(path, report.request_path),
                related_ids=(report.id,),
                message="the sheet report no longer matches its request snapshot",
                remediation="reassemble from the exact request revision without overwriting output",
            )
        for item in report.inputs:
            if item.reference_id not in references:
                context.add_finding(
                    category="sheets",
                    code="technical-sheet-reference-missing",
                    severity="error",
                    subject=report.id,
                    paths=(path, GENERATED_REFERENCE_DIRECTORY.value),
                    related_ids=(report.id, item.reference_id),
                    message="the sheet references a missing visual reference",
                    remediation="restore the approved reference before rebuilding the sheet",
                )
            context.verify_file(
                item.image_path,
                category="sheets",
                code="technical-sheet-input-invalid",
                subject=report.id,
                expected_digest=item.sha256,
                remediation="restore the normalized PNG used by the sheet report",
            )
    context.set_item_count("sheets", sheet_count)
    if references and not sheet_count:
        context.add_finding(
            category="sheets",
            code="technical-sheets-missing",
            severity="warning",
            subject="technical-sheets",
            paths=("technical-sheets",),
            message="the project has visual references but no technical-sheet reports",
            remediation="assemble the required deterministic sheets before packaging",
        )


def _audit_packages(context: _AuditContext, project_id: str) -> None:
    json_paths = tuple(path for path in context.initial_inventory if path.endswith(".json"))
    manifests: list[tuple[str, PackageManifestContract]] = []
    indexes: list[tuple[str, PackageIndexContract]] = []
    for path in json_paths:
        if path.startswith(_AUDIT_LOCK_DIRECTORY_PREFIX):
            continue
        kind = _json_kind(context, path)
        if kind == "package-manifest":
            manifest = context.load_json(
                path,
                PackageManifestContract,
                detail="validated package manifest",
                max_bytes=_PACKAGE_MANIFEST_MAX_BYTES,
            )
            if manifest is not None:
                manifests.append((path, manifest))
            else:
                context.add_finding(
                    category="package",
                    code="package-manifest-invalid",
                    severity="error",
                    subject=path,
                    paths=(path,),
                    message="a package manifest is invalid",
                    remediation="regenerate the manifest from canonical project sources",
                )
        elif kind == "package-index":
            index = context.load_json(
                path,
                PackageIndexContract,
                detail="validated package index",
                max_bytes=_PACKAGE_MANIFEST_MAX_BYTES,
            )
            if index is not None:
                indexes.append((path, index))
            else:
                context.add_finding(
                    category="package",
                    code="package-index-invalid",
                    severity="error",
                    subject=path,
                    paths=(path,),
                    message="a package index is invalid",
                    remediation="rebuild the package index from the same manifest snapshot",
                )

    context.set_item_count("package", len(manifests) + len(indexes))
    if not manifests:
        context.add_finding(
            category="package",
            code="package-manifest-missing",
            severity="warning",
            subject="package-manifest",
            paths=("package-manifest",),
            message="the project has no package manifest",
            remediation="create a deterministic package manifest before release verification",
        )

    matched_indexes: set[str] = set()
    for manifest_path, manifest in manifests:
        if manifest.project_id != project_id:
            context.add_finding(
                category="package",
                code="package-project-mismatch",
                severity="error",
                subject=manifest.package_id,
                paths=(manifest_path, PROJECT_MARKER.value),
                related_ids=(manifest.package_id, manifest.project_id, project_id),
                message="the package manifest belongs to another project",
                remediation="regenerate the manifest from the selected project",
            )
        if manifest.manifest_path != manifest_path:
            context.add_finding(
                category="package",
                code="package-manifest-path-mismatch",
                severity="error",
                subject=manifest.package_id,
                paths=(manifest_path,),
                related_ids=(manifest.package_id, manifest.project_id),
                message="the manifest path inside the contract differs from its file path",
                remediation="regenerate the manifest at the declared canonical path",
            )
        for missing in manifest.missing:
            context.add_finding(
                category="package",
                code=(
                    "package-required-source-missing"
                    if missing.reason == "required-source"
                    else "package-optional-source-missing"
                ),
                severity="error" if missing.reason == "required-source" else "warning",
                subject=missing.path,
                paths=(manifest_path, missing.path),
                related_ids=(manifest.package_id,),
                message=missing.detail,
                remediation="restore the source or explicitly revise the package inventory",
            )
        for included in manifest.included_files:
            context.verify_file(
                included.path,
                category="package",
                code="package-source-changed",
                subject=manifest.package_id,
                expected_digest=included.sha256,
                expected_size=included.size_bytes,
                remediation="regenerate the manifest before rebuilding the package",
            )
        matching = [
            (path, index) for path, index in indexes if index.manifest_path == manifest_path
        ]
        if not matching:
            context.add_finding(
                category="package",
                code="package-index-missing",
                severity="warning",
                subject=manifest.package_id,
                paths=(manifest_path,),
                related_ids=(manifest.package_id,),
                message="the package manifest has no matching reproducible package index",
                remediation="build the release archive and its package index",
            )
            continue
        for index_path, index in matching:
            matched_indexes.add(index_path)
            if index.project_id != project_id or index.project_id != manifest.project_id:
                context.add_finding(
                    category="package",
                    code="package-index-project-mismatch",
                    severity="error",
                    subject=index.package_id,
                    paths=(manifest_path, index_path, PROJECT_MARKER.value),
                    related_ids=(index.package_id, index.project_id, project_id),
                    message="the package index belongs to another project",
                    remediation="rebuild the package index from the selected project",
                )
            if index.package_id != manifest.package_id:
                context.add_finding(
                    category="package",
                    code="package-index-package-mismatch",
                    severity="error",
                    subject=index.package_id,
                    paths=(manifest_path, index_path),
                    related_ids=(index.package_id, manifest.package_id),
                    message="the package index package ID differs from its manifest",
                    remediation="rebuild the index and manifest as one package revision",
                )
            if index.index_path != index_path:
                context.add_finding(
                    category="package",
                    code="package-index-path-mismatch",
                    severity="error",
                    subject=index.package_id,
                    paths=(index_path,),
                    related_ids=(index.package_id, index.project_id),
                    message="the package index path differs from its file path",
                    remediation="rebuild the index at the declared canonical path",
                )
            manifest_digest = context.sources.get(manifest_path)
            if manifest_digest is None or index.manifest_sha256 != manifest_digest.digest:
                context.add_finding(
                    category="package",
                    code="package-index-manifest-changed",
                    severity="error",
                    subject=index.package_id,
                    paths=(manifest_path, index_path),
                    related_ids=(index.package_id, index.project_id),
                    message="the package index does not match the manifest bytes",
                    remediation="rebuild both package artifacts from one manifest snapshot",
                )
            archive_digest = context.observe_path(index.archive_path, detail="package ZIP archive")
            if archive_digest is None:
                context.add_finding(
                    category="package",
                    code="package-archive-missing",
                    severity="error",
                    subject=index.package_id,
                    paths=(index.archive_path, index_path),
                    related_ids=(index.package_id,),
                    message="the package index points to a missing archive",
                    remediation="build the archive and index together in a release directory",
                )
            else:
                try:
                    archive_snapshot, archive_payload = context.scanner.read_file(
                        index.archive_path,
                        max_bytes=PACKAGE_ARCHIVE_MAX_BYTES,
                    )
                    del archive_snapshot
                    archive_result = PackageArchiveBuilder().validate(archive_payload)
                    if archive_result.member_count != index.archive_member_count:
                        raise ProjectAuditCorruptError(
                            "archive member count differs from the package index"
                        )
                except Exception as error:
                    context.add_finding(
                        category="package",
                        code="package-archive-invalid",
                        severity="error",
                        subject=index.package_id,
                        paths=(index.archive_path, index_path),
                        related_ids=(index.package_id,),
                        message=f"the package archive is not valid: {error}",
                        remediation="rebuild the deterministic ZIP from the validated manifest",
                    )
            for entry in index.entries:
                expected_path = (
                    manifest_path if entry.kind == "package-manifest" else entry.source_path
                )
                context.verify_file(
                    expected_path,
                    category="package",
                    code="package-index-source-changed",
                    subject=index.package_id,
                    expected_digest=entry.sha256,
                    expected_size=entry.size_bytes,
                    remediation="rebuild the package index from the same source snapshot",
                )
    for index_path, index in indexes:
        if index_path not in matched_indexes:
            context.add_finding(
                category="package",
                code="package-index-orphaned",
                severity="error",
                subject=index.package_id,
                paths=(index_path,),
                related_ids=(index.package_id, index.project_id),
                message="the package index has no matching manifest in the project",
                remediation=(
                    "retain the index only with its source manifest or remove it explicitly"
                ),
            )


def _audit_graph_freshness(context: _AuditContext, graph_snapshot: Any | None) -> None:
    if graph_snapshot is None:
        return
    for node in graph_snapshot.graph.nodes:
        if node.freshness is FreshnessState.FRESH:
            continue
        category = _category_for_node(node.key.kind)
        if category is None:
            continue
        if node.freshness is FreshnessState.STALE:
            code = "stale-derived-output"
            severity: ProjectAuditSeverity = "error"
            message = "a canonical dependency output is stale"
        else:
            code = "review-required-output"
            severity = "warning"
            message = "a canonical dependency output requires human review"
        context.add_finding(
            category=category,
            code=code,
            severity=severity,
            subject=node.key.token,
            paths=(DEFAULT_DEPENDENCY_GRAPH_PATH.value,),
            related_ids=(node.key.id,),
            message=message,
            remediation="refresh or review the output after reconciling its dependency causes",
        )


def _category_for_node(kind: DependencyNodeKind) -> ProjectAuditCategory | None:
    if kind in {DependencyNodeKind.ASSET, DependencyNodeKind.COMPONENT, DependencyNodeKind.VARIANT}:
        return "assets"
    if kind is DependencyNodeKind.REFERENCE:
        return "references"
    if kind in {DependencyNodeKind.VISUAL_JOB, DependencyNodeKind.GENERATION_RECEIPT}:
        return "jobs"
    if kind in {DependencyNodeKind.VISUAL_REVIEW, DependencyNodeKind.APPROVAL}:
        return "approvals"
    if kind is DependencyNodeKind.TECHNICAL_SHEET:
        return "sheets"
    if kind in {DependencyNodeKind.PACKAGE, DependencyNodeKind.RELEASE}:
        return "package"
    if kind is DependencyNodeKind.DOCUMENT:
        return "documents"
    return None


def _json_kind(context: _AuditContext, path: str) -> str | None:
    try:
        _snapshot, payload = context.scanner.read_file(path)
    except (FileNotFoundError, PackageManifestScanError, ProjectFilesystemError):
        return None
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    kind = parsed.get("kind")
    return kind if isinstance(kind, str) else None


def _inventory(scanner: PackageFileScanner) -> tuple[str, ...]:
    paths = scanner.list_paths()
    return tuple(path for path in paths if not path.startswith(_AUDIT_LOCK_DIRECTORY_PREFIX))


def _build_report(
    context: _AuditContext,
    *,
    project_id: str,
    project_name: str,
    dry_run: bool,
    source_digest: str,
) -> ProjectAuditReportContract:
    ordered_findings = tuple(
        sorted(
            context.findings,
            key=lambda finding: (
                finding.category,
                finding.code,
                finding.subject,
                finding.severity,
                finding.paths,
                finding.related_ids,
            ),
        )
    )
    categories: list[ProjectAuditCategoryContract] = []
    actions: list[ProjectAuditActionContract] = []
    category_order = PROJECT_AUDIT_CATEGORY_ORDER
    for category in category_order:
        category_findings = tuple(item for item in ordered_findings if item.category == category)
        errors = sum(item.severity == "error" for item in category_findings)
        warnings = sum(item.severity == "warning" for item in category_findings)
        category_state: ProjectAuditState = (
            "blocked" if errors else "needs-review" if warnings else "ready"
        )
        categories.append(
            ProjectAuditCategoryContract(
                category=category,
                state=category_state,
                item_count=context.item_counts.get(category, 0),
                error_count=errors,
                warning_count=warnings,
            )
        )
        if category_findings:
            codes = tuple(sorted({item.code for item in category_findings}))
            actions.append(
                ProjectAuditActionContract(
                    code=f"review-{category}",
                    category=category,
                    finding_codes=codes,
                    detail=f"resolve the {category} findings before claiming project readiness",
                )
            )
    errors = sum(item.severity == "error" for item in ordered_findings)
    warnings = sum(item.severity == "warning" for item in ordered_findings)
    state: ProjectAuditState = "blocked" if errors else "needs-review" if warnings else "ready"
    return ProjectAuditReportContract(
        dry_run=dry_run,
        project_id=project_id,
        project_name=project_name,
        state=state,
        valid=state == "ready",
        source_digest=source_digest,
        sources=tuple(context.sources[path] for path in sorted(context.sources)),
        categories=tuple(categories),
        findings=ordered_findings,
        recommended_actions=tuple(
            sorted(
                actions,
                key=lambda action: (action.category, action.code, action.finding_codes),
            )
        ),
    )


__all__ = [
    "ProjectAuditConflictError",
    "ProjectAuditCorruptError",
    "ProjectAuditError",
    "ProjectAuditResult",
    "ProjectAuditService",
]
