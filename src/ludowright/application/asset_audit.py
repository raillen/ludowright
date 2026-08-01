"""Deterministic, read-only completeness auditing for canonical asset state."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from ludowright.application.asset_registry import (
    DEFAULT_ASSET_REGISTRY_PATH,
    AssetRegistryService,
)
from ludowright.contracts import (
    AssetAuditFindingContract,
    AssetAuditReportContract,
    AssetContract,
)
from ludowright.contracts.asset_audit import AssetAuditState
from ludowright.domain import (
    AssetStatus,
    DependencyGraph,
    DependencyNodeKind,
    DependencyRelation,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    STATE_SCHEMA_VERSION,
    DependencyGraphRepository,
    ProjectFilesystem,
    RepositoryPath,
)

_SOURCE_MAX_BYTES = 64 * 1024 * 1024
_INACTIVE_STATUSES = frozenset({AssetStatus.ARCHIVED, AssetStatus.CANCELLED})


class AssetAuditError(RuntimeError):
    """Raised when canonical asset audit inputs cannot be read consistently."""


@dataclass(frozen=True, slots=True)
class AssetAuditResult:
    """Stable result shared by application callers and CLI renderers."""

    report: AssetAuditReportContract

    def as_data(self) -> dict[str, object]:
        """Return the published JSON-compatible audit report."""
        return self.report.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class _AuditSource:
    """One consistent read of the registry and dependency graph."""

    registry_bytes: bytes | None
    graph_bytes: bytes | None
    registry_version: int
    assets: tuple[AssetContract, ...]
    graph: DependencyGraph
    graph_present: bool


class AssetAuditService:
    """Inspect asset completeness without creating or changing project state."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("asset audit requires ProjectFilesystem")
        self._filesystem = filesystem
        self._registry = AssetRegistryService(filesystem)
        self._graph_repository = DependencyGraphRepository(filesystem)

    def audit(self, *, dry_run: bool = False) -> AssetAuditResult:
        """Return a deterministic report from one consistent source snapshot."""
        before = self._read_source()
        after = self._read_source()
        if _source_digest(before) != _source_digest(after):
            raise AssetAuditError("asset registry or dependency graph changed during audit")

        findings = tuple(
            sorted(
                _findings(before.assets, before.graph),
                key=_finding_sort_key,
            )
        )
        state: AssetAuditState = (
            "empty"
            if not before.assets and not findings
            else "valid"
            if not findings
            else "findings"
        )
        report = AssetAuditReportContract(
            state=state,
            dry_run=dry_run,
            registry_path=DEFAULT_ASSET_REGISTRY_PATH.value,
            registry_version=before.registry_version,
            state_store_schema_version=STATE_SCHEMA_VERSION,
            dependency_graph_path=DEFAULT_DEPENDENCY_GRAPH_PATH.value,
            dependency_graph_revision=(before.graph.revision.value if before.graph_present else 0),
            dependency_graph_state="current" if before.graph_present else "absent",
            asset_count=len(before.assets),
            source_digest=_source_digest(before),
            findings=findings,
            valid=not any(finding.severity == "error" for finding in findings),
        )
        return AssetAuditResult(report=report)

    def _read_source(self) -> _AuditSource:
        registry_bytes = _read_optional(self._filesystem, DEFAULT_ASSET_REGISTRY_PATH)
        graph_bytes = _read_optional(self._filesystem, DEFAULT_DEPENDENCY_GRAPH_PATH)
        registry = self._registry.list_assets()
        graph_snapshot = self._graph_repository.load_optional()
        return _AuditSource(
            registry_bytes=registry_bytes,
            graph_bytes=graph_bytes,
            registry_version=registry.registry_version,
            assets=registry.assets,
            graph=(graph_snapshot.graph if graph_snapshot is not None else DependencyGraph.empty()),
            graph_present=graph_snapshot is not None,
        )


def _findings(
    assets: tuple[AssetContract, ...],
    graph: DependencyGraph,
) -> Iterable[AssetAuditFindingContract]:
    """Yield all asset-domain findings in stable semantic groups."""
    # The registry result is typed at the application boundary; keeping this
    # helper independent from the service makes its deterministic rules easy
    # to exercise without introducing another persistence abstraction.
    asset_by_id = {asset.id: asset for asset in assets}

    for node in graph.nodes:
        if node.key.kind is DependencyNodeKind.ASSET and node.key.id not in asset_by_id:
            yield AssetAuditFindingContract(
                code="orphan-asset-node",
                severity="error",
                subject=node.key.token,
                asset_id=node.key.id,
                message=(
                    f"Dependency graph node {node.key.token} has no matching asset in the registry."
                ),
            )

    for asset in assets:
        if asset.status not in _INACTIVE_STATUSES:
            if not asset.components and not asset.variants and not asset.states:
                yield AssetAuditFindingContract(
                    code="missing-specification",
                    severity="warning",
                    subject=asset.id,
                    asset_id=asset.id,
                    message=(
                        "Asset has no components, variants, or states in its production "
                        "specification."
                    ),
                )

            yield AssetAuditFindingContract(
                code="missing-capture-profile",
                severity="warning",
                subject=asset.id,
                asset_id=asset.id,
                related_subjects=("capture-profile-catalog",),
                message=(
                    "No executable capture-profile catalog is persisted in the current "
                    "project format; decomposition recommendations are advisory only."
                ),
            )

            missing_metadata = _missing_production_metadata(asset)
            if missing_metadata:
                yield AssetAuditFindingContract(
                    code="incomplete-production-metadata",
                    severity="warning",
                    subject=asset.id,
                    asset_id=asset.id,
                    related_subjects=missing_metadata,
                    message=(
                        "Production ownership is incomplete for: "
                        + ", ".join(missing_metadata)
                        + "."
                    ),
                )

    known_assets = set(asset_by_id)
    for edge in graph.edges:
        asset_endpoints = tuple(
            endpoint
            for endpoint in (edge.source, edge.target)
            if endpoint.kind is DependencyNodeKind.ASSET
        )
        unknown = tuple(endpoint for endpoint in asset_endpoints if endpoint.id not in known_assets)
        if unknown or (
            edge.source.kind is DependencyNodeKind.ASSET
            and edge.target.kind is DependencyNodeKind.ASSET
            and edge.relation is not DependencyRelation.REQUIRES
        ):
            related = tuple(sorted({edge.source.token, edge.target.token}))
            missing = ", ".join(endpoint.token for endpoint in unknown)
            reason = (
                f"asset endpoints are missing from the registry: {missing}"
                if unknown
                else "asset-to-asset dependencies must use the 'requires' relation"
            )
            yield AssetAuditFindingContract(
                code="invalid-dependency",
                severity="error",
                subject=f"{edge.source.token}->{edge.target.token}",
                asset_id=(
                    edge.target.id
                    if edge.target.kind is DependencyNodeKind.ASSET
                    else edge.source.id
                    if edge.source.kind is DependencyNodeKind.ASSET
                    else None
                ),
                related_subjects=related,
                message=f"Invalid asset dependency: {reason}.",
            )


def _missing_production_metadata(asset: AssetContract) -> tuple[str, ...]:
    """Return missing ownership fields for one active asset aggregate."""
    missing: list[str] = []
    if asset.owner is None:
        missing.append("asset-owner")
    for kind, items in (
        ("component", asset.components),
        ("variant", asset.variants),
        ("state", asset.states),
    ):
        for item in items:
            if item.required and item.owner is None:
                missing.append(f"{kind}:{item.id}")
    return tuple(sorted(missing))


def _finding_sort_key(
    finding: AssetAuditFindingContract,
) -> tuple[str, str, str, tuple[str, ...], str, str]:
    """Return the canonical finding order shared with the report contract."""
    return (
        finding.code,
        finding.subject,
        finding.asset_id or "",
        finding.related_subjects,
        finding.severity,
        finding.message,
    )


def _read_optional(filesystem: ProjectFilesystem, path: RepositoryPath) -> bytes | None:
    try:
        return filesystem.read_bytes(path, max_bytes=_SOURCE_MAX_BYTES)
    except FileNotFoundError:
        return None


def _source_digest(source: _AuditSource) -> str:
    digest = hashlib.sha256()
    for label, payload in (
        (b"registry", source.registry_bytes),
        (b"dependency-graph", source.graph_bytes),
    ):
        digest.update(label)
        digest.update(b"\0")
        digest.update(payload if payload is not None else b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()
