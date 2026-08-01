"""Derived deterministic workbook export for the canonical asset repository."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from importlib import resources
from typing import Protocol, cast

from ludowright.application.asset_registry import (
    DEFAULT_ASSET_REGISTRY_PATH,
    AssetRegistryService,
)
from ludowright.contracts import (
    AssetContract,
    AssetWorkbookExportReportContract,
    AssetWorkbookSheetRowCountContract,
    AssetWorkbookTemplateContract,
)
from ludowright.domain import (
    AssetStatus,
    DependencyGraph,
    DependencyNodeKind,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    STATE_SCHEMA_VERSION,
    DependencyGraphRepository,
    OdsSheet,
    OdsWorkbook,
    OdsWorkbookWriter,
    ProjectFilesystem,
    RepositoryPath,
)
from ludowright.infrastructure.ods import OdsCell

_TEMPLATE_RESOURCE = "asset-registry.json"
_DECOMPOSITION_LOCK = "asset-decomposition"
_REGISTRY_LOCK = "asset-registry"
_SOURCE_MAX_BYTES = 64 * 1024 * 1024
_REFERENCE_WARNING = (
    "visual reference details are not persisted in the current asset registry; "
    "the References sheet is an availability view"
)
_PRIORITY_RANK = {
    "critical": 1,
    "high": 2,
    "normal": 3,
    "low": 4,
    "backlog": 5,
}
_ITEM_KIND_ORDER = {"component": 0, "variant": 1, "state": 2}


class AssetWorkbookError(RuntimeError):
    """Base failure for derived asset workbook export."""


@dataclass(frozen=True, slots=True)
class AssetWorkbookResult:
    """Stable application result for human and JSON CLI renderers."""

    report: AssetWorkbookExportReportContract

    def as_data(self) -> dict[str, object]:
        """Return the published JSON-compatible export report."""
        return cast(dict[str, object], self.report.model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class _SourceState:
    registry_bytes: bytes | None
    graph_bytes: bytes | None
    registry_version: int
    assets: tuple[AssetContract, ...]
    graph: DependencyGraph
    graph_present: bool


class _ProductionItem(Protocol):
    """Common typed view over component, variant, and state contracts."""

    id: str
    name: str
    status: AssetStatus
    required: bool


class AssetWorkbookExportService:
    """Export canonical asset data to one deterministic, derived ODS workbook."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        writer: OdsWorkbookWriter | None = None,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("asset workbook export requires ProjectFilesystem")
        self._filesystem = filesystem
        self._registry = AssetRegistryService(filesystem)
        self._graph_repository = DependencyGraphRepository(filesystem)
        self._writer = writer or OdsWorkbookWriter()
        self._template = _load_template()

    @property
    def template(self) -> AssetWorkbookTemplateContract:
        """Return the validated data-defined workbook template."""
        return self._template

    def export(
        self,
        output_path: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> AssetWorkbookResult:
        """Plan or create one workbook without replacing an existing target."""
        if not isinstance(output_path, RepositoryPath):
            raise TypeError("asset workbook output requires RepositoryPath")
        if not output_path.name.endswith(".ods"):
            raise AssetWorkbookError("asset workbook output paths must use the .ods extension")

        with ExitStack() as stack:
            if not dry_run:
                stack.enter_context(self._filesystem.lock(_DECOMPOSITION_LOCK, timeout=5.0))
                stack.enter_context(self._filesystem.lock(_REGISTRY_LOCK, timeout=5.0))
            before = self._read_sources()
            payload = self._writer.render(self._build_workbook(before))
            after = self._read_sources()
            if _source_digest(before) != _source_digest(after):
                raise AssetWorkbookError(
                    "asset registry or dependency graph changed during workbook export"
                )
            validation = self._writer.validate(
                payload,
                expected_sheet_names=tuple(sheet.name for sheet in self._template.sheets),
            )
            if not dry_run:
                self._writer.create(self._filesystem, output_path, payload)

        report = AssetWorkbookExportReportContract(
            state="planned" if dry_run else "exported",
            dry_run=dry_run,
            output_path=output_path.value,
            template_id=self._template.template_id,
            template_version=self._template.template_version,
            sheet_names=tuple(sheet.name for sheet in self._template.sheets),
            sheet_row_counts=tuple(
                AssetWorkbookSheetRowCountContract(
                    sheet=sheet.name,
                    rows=len(self._rows_for_sheet(before, sheet.name)),
                )
                for sheet in self._template.sheets
            ),
            registry_path=DEFAULT_ASSET_REGISTRY_PATH.value,
            registry_version=before.registry_version,
            state_store_schema_version=STATE_SCHEMA_VERSION,
            dependency_graph_path=DEFAULT_DEPENDENCY_GRAPH_PATH.value,
            dependency_graph_revision=(before.graph.revision.value if before.graph_present else 0),
            dependency_graph_state="current" if before.graph_present else "absent",
            asset_count=len(before.assets),
            source_digest=_source_digest(before),
            output_sha256=validation.package_sha256,
            warnings=(_REFERENCE_WARNING,),
            valid=True,
        )
        return AssetWorkbookResult(report=report)

    def _read_sources(self) -> _SourceState:
        registry_bytes = _read_optional(self._filesystem, DEFAULT_ASSET_REGISTRY_PATH)
        graph_bytes = _read_optional(self._filesystem, DEFAULT_DEPENDENCY_GRAPH_PATH)
        registry_result = self._registry.list_assets()
        graph_snapshot = self._graph_repository.load_optional()
        return _SourceState(
            registry_bytes=registry_bytes,
            graph_bytes=graph_bytes,
            registry_version=registry_result.registry_version,
            assets=registry_result.assets,
            graph=(graph_snapshot.graph if graph_snapshot is not None else DependencyGraph.empty()),
            graph_present=graph_snapshot is not None,
        )

    def _build_workbook(self, source: _SourceState) -> OdsWorkbook:
        sheets: list[OdsSheet] = []
        for template_sheet in self._template.sheets:
            rows = self._rows_for_sheet(source, template_sheet.name)
            columns = tuple(column.label for column in template_sheet.columns)
            preamble = _overview_preamble(source) if template_sheet.name == "Overview" else ()
            sheets.append(
                OdsSheet(
                    name=template_sheet.name,
                    columns=columns,
                    rows=tuple(
                        tuple(row.get(column.id) for column in template_sheet.columns)
                        for row in rows
                    ),
                    preamble=preamble,
                )
            )
        return OdsWorkbook(sheets=tuple(sheets))

    def _rows_for_sheet(
        self,
        source: _SourceState,
        sheet_name: str,
    ) -> tuple[Mapping[str, OdsCell], ...]:
        if sheet_name == "Overview":
            return _overview_rows(source)
        if sheet_name == "Components":
            return _component_rows(source.assets)
        if sheet_name == "References":
            return _reference_rows(source)
        if sheet_name == "Status":
            return _status_rows(source.assets)
        if sheet_name == "Priority":
            return _priority_rows(source.assets)
        if sheet_name == "Dependencies":
            return _dependency_rows(source)
        raise AssetWorkbookError(f"unsupported asset workbook sheet: {sheet_name}")


def _load_template() -> AssetWorkbookTemplateContract:
    try:
        template_resource = resources.files("ludowright.workbook_data").joinpath(_TEMPLATE_RESOURCE)
        payload = template_resource.read_text(encoding="utf-8")
        return AssetWorkbookTemplateContract.model_validate(json.loads(payload))
    except (OSError, TypeError, ValueError) as error:
        raise AssetWorkbookError("the packaged asset workbook template is invalid") from error


def _read_optional(filesystem: ProjectFilesystem, path: RepositoryPath) -> bytes | None:
    try:
        return filesystem.read_bytes(path, max_bytes=_SOURCE_MAX_BYTES)
    except FileNotFoundError:
        return None


def _source_digest(source: _SourceState) -> str:
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


def _overview_preamble(source: _SourceState) -> tuple[tuple[OdsCell, ...], ...]:
    return (
        ("LudoWright Asset Workbook",),
        ("Template", "asset-registry", "Version", 1),
        ("Registry", DEFAULT_ASSET_REGISTRY_PATH.value, "Version", source.registry_version),
        (
            "Dependency Graph",
            DEFAULT_DEPENDENCY_GRAPH_PATH.value,
            "Revision",
            source.graph.revision.value if source.graph_present else "absent",
        ),
        ("Source Digest", _source_digest(source)),
        ("",),
    )


def _overview_rows(source: _SourceState) -> tuple[Mapping[str, OdsCell], ...]:
    dependency_counts = _dependency_counts(source.graph)
    rows: list[Mapping[str, OdsCell]] = []
    for asset in source.assets:
        rows.append(
            {
                "asset_id": asset.id,
                "name": asset.name,
                "family": asset.family.value,
                "subtype": asset.subtype or "",
                "status": asset.status.value,
                "priority": asset.priority.value,
                "component_count": len(asset.components),
                "variant_count": len(asset.variants),
                "state_count": len(asset.states),
                "required_item_count": sum(
                    item.required for _kind, items in _items(asset) for item in items
                ),
                "dependency_count": dependency_counts.get(asset.id, 0),
                "freshness": _node_freshness(source.graph, DependencyNodeKind.ASSET, asset.id),
            }
        )
    return tuple(rows)


def _component_rows(assets: tuple[AssetContract, ...]) -> tuple[Mapping[str, OdsCell], ...]:
    rows: list[Mapping[str, OdsCell]] = []
    for asset in assets:
        for item_kind, items in _items(asset):
            for item in items:
                rows.append(
                    {
                        "asset_id": asset.id,
                        "item_kind": item_kind,
                        "item_id": item.id,
                        "name": item.name,
                        "status": item.status.value,
                        "required": item.required,
                        "parent_id": getattr(item, "parent_id", None) or "",
                    }
                )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                str(row["asset_id"]),
                _ITEM_KIND_ORDER[str(row["item_kind"])],
                str(row["item_id"]),
            ),
        )
    )


def _reference_rows(source: _SourceState) -> tuple[Mapping[str, OdsCell], ...]:
    references = [
        node for node in source.graph.nodes if node.key.kind is DependencyNodeKind.REFERENCE
    ]
    rows: list[Mapping[str, OdsCell]] = []
    for node in references:
        asset_ids = sorted(
            edge.target.id
            if edge.source == node.key and edge.target.kind is DependencyNodeKind.ASSET
            else edge.source.id
            for edge in source.graph.edges
            if (edge.source == node.key and edge.target.kind is DependencyNodeKind.ASSET)
            or (edge.target == node.key and edge.source.kind is DependencyNodeKind.ASSET)
        )
        linked_ids = asset_ids or [""]
        for asset_id in linked_ids:
            rows.append(
                {
                    "asset_id": asset_id,
                    "reference_id": node.key.id,
                    "status": "not-available",
                    "freshness": node.freshness.value,
                    "source": "dependency-graph",
                }
            )
    if not rows:
        rows = [
            {
                "asset_id": asset.id,
                "reference_id": "",
                "status": "not-available",
                "freshness": "not-available",
                "source": "not-available",
            }
            for asset in source.assets
        ]
    return tuple(sorted(rows, key=lambda row: (str(row["asset_id"]), str(row["reference_id"]))))


def _status_rows(assets: tuple[AssetContract, ...]) -> tuple[Mapping[str, OdsCell], ...]:
    rows: list[Mapping[str, OdsCell]] = []
    for asset in assets:
        domain_asset = asset.to_domain()
        rows.append(
            {
                "asset_id": asset.id,
                "subject_kind": "asset",
                "subject_id": asset.id,
                "name": asset.name,
                "status": asset.status.value,
                "required": True,
                "readiness": "ready" if domain_asset.is_completion_ready else "blocked",
            }
        )
        for item_kind, items in _items(asset):
            for item in items:
                readiness = (
                    "ready"
                    if item.status is AssetStatus.COMPLETED
                    else "blocked"
                    if item.required
                    else "optional"
                )
                rows.append(
                    {
                        "asset_id": asset.id,
                        "subject_kind": item_kind,
                        "subject_id": item.id,
                        "name": item.name,
                        "status": item.status.value,
                        "required": item.required,
                        "readiness": readiness,
                    }
                )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                str(row["asset_id"]),
                str(row["subject_kind"]),
                str(row["subject_id"]),
            ),
        )
    )


def _items(asset: AssetContract) -> tuple[tuple[str, tuple[_ProductionItem, ...]], ...]:
    return (
        ("component", cast(tuple[_ProductionItem, ...], asset.components)),
        ("variant", cast(tuple[_ProductionItem, ...], asset.variants)),
        ("state", cast(tuple[_ProductionItem, ...], asset.states)),
    )


def _priority_rows(assets: tuple[AssetContract, ...]) -> tuple[Mapping[str, OdsCell], ...]:
    return tuple(
        {
            "priority": asset.priority.value,
            "priority_rank": _PRIORITY_RANK[asset.priority.value],
            "asset_id": asset.id,
            "name": asset.name,
            "status": asset.status.value,
        }
        for asset in sorted(
            assets,
            key=lambda asset: (_PRIORITY_RANK[asset.priority.value], asset.id),
        )
    )


def _dependency_rows(source: _SourceState) -> tuple[Mapping[str, OdsCell], ...]:
    return tuple(
        {
            "source": edge.source.token,
            "target": edge.target.token,
            "relation": edge.relation.value,
            "invalidation_mode": edge.invalidation_mode.value,
            "observed_source_revision": edge.observed_source_revision.value,
            "source_freshness": _node_freshness_by_key(source.graph, edge.source),
            "target_freshness": _node_freshness_by_key(source.graph, edge.target),
        }
        for edge in source.graph.edges
    )


def _dependency_counts(graph: DependencyGraph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in graph.edges:
        if edge.source.kind is DependencyNodeKind.ASSET:
            counts[edge.source.id] = counts.get(edge.source.id, 0) + 1
        if edge.target.kind is DependencyNodeKind.ASSET:
            counts[edge.target.id] = counts.get(edge.target.id, 0) + 1
    return counts


def _node_freshness(graph: DependencyGraph, kind: DependencyNodeKind, asset_id: str) -> str:
    for node in graph.nodes:
        if node.key.kind is kind and node.key.id == asset_id:
            return node.freshness.value
    return "not-available"


def _node_freshness_by_key(graph: DependencyGraph, key: object) -> str:
    for node in graph.nodes:
        if node.key == key:
            return node.freshness.value
    return "not-available"
