"""Tests for deterministic, safe asset workbook export."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest
from typer.testing import CliRunner

from ludowright.application import AssetRegistryService, AssetWorkbookExportService
from ludowright.cli.app import app
from ludowright.contracts import AssetContract
from ludowright.domain import (
    DependencyEdge,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    InvalidationMode,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DependencyGraphRepository,
    OdsWorkbookConflictError,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    UnsafeProjectPathError,
)

runner = CliRunner()


def _project(tmp_path: Path) -> ProjectFilesystem:
    marker = tmp_path / ".ludowright" / "project.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(tmp_path)


def _asset(
    *,
    asset_id: str = "prop-cabinet",
    name: str = "Arcade Cabinet",
    priority: str = "high",
) -> AssetContract:
    return AssetContract.model_validate(
        {
            "schema_version": 1,
            "kind": "asset",
            "id": asset_id,
            "name": name,
            "family": "prop",
            "subtype": "container",
            "priority": priority,
            "status": "planned",
            "components": [
                {
                    "id": "body",
                    "name": "Body",
                    "status": "planned",
                    "required": True,
                },
                {
                    "id": "trim",
                    "name": "Trim",
                    "status": "planned",
                    "required": False,
                    "parent_id": "body",
                },
            ],
            "variants": [],
            "states": [],
        }
    )


def _create_sources(filesystem: ProjectFilesystem) -> None:
    AssetRegistryService(filesystem).create_many((_asset(),))
    asset_key = DependencyKey(DependencyNodeKind.ASSET, "prop-cabinet")
    reference_key = DependencyKey(DependencyNodeKind.REFERENCE, "cabinet-front")
    graph = DependencyGraph(
        revision=RevisionVersion(2),
        nodes=(
            DependencyNode(asset_key, RevisionVersion(1)),
            DependencyNode(reference_key, RevisionVersion(1)),
        ),
        edges=(
            DependencyEdge(
                source=reference_key,
                target=asset_key,
                relation=DependencyRelation.REFERENCES,
                invalidation_mode=InvalidationMode.REVIEW,
                observed_source_revision=RevisionVersion(1),
            ),
        ),
    )
    DependencyGraphRepository(filesystem).create(graph)


def test_export_creates_valid_workbook_from_canonical_sources(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _create_sources(filesystem)

    result = AssetWorkbookExportService(filesystem).export(RepositoryPath("exports/assets.ods"))

    assert result.report.state == "exported"
    assert result.report.asset_count == 1
    assert result.report.state_store_schema_version == 2
    assert result.report.dependency_graph_revision == 2
    assert result.report.dependency_graph_state == "current"
    assert [item.rows for item in result.report.sheet_row_counts] == [1, 2, 1, 3, 1, 1]
    with ZipFile(tmp_path / "exports/assets.ods") as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == ZIP_STORED
        assert archive.read("mimetype").decode() == "application/vnd.oasis.opendocument.spreadsheet"
        content = archive.read("content.xml").decode()
        assert content.index('table:name="Overview"') < content.index('table:name="Dependencies"')


def test_empty_project_export_is_valid_and_reports_reference_limitation(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)

    result = AssetWorkbookExportService(filesystem).export(RepositoryPath("exports/empty.ods"))

    assert result.report.asset_count == 0
    assert result.report.dependency_graph_state == "absent"
    assert result.report.dependency_graph_revision == 0
    assert result.report.sheet_row_counts[2].rows == 0
    assert (tmp_path / "exports/empty.ods").is_file()


def test_dry_run_is_read_only_and_deterministic(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _create_sources(filesystem)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    first = AssetWorkbookExportService(filesystem).export(
        RepositoryPath("exports/one.ods"), dry_run=True
    )
    second = AssetWorkbookExportService(filesystem).export(
        RepositoryPath("exports/two.ods"), dry_run=True
    )

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after
    assert first.report.state == second.report.state == "planned"
    assert first.report.output_sha256 == second.report.output_sha256
    assert first.report.source_digest == second.report.source_digest
    assert not (tmp_path / "exports").exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    output = RepositoryPath("exports/assets.ods")
    filesystem.write_bytes(output, b"approved")

    with pytest.raises(OdsWorkbookConflictError):
        AssetWorkbookExportService(filesystem).export(output)

    assert filesystem.read_bytes(output) == b"approved"


def test_invalid_and_symlink_outputs_are_rejected(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    service = AssetWorkbookExportService(filesystem)

    with pytest.raises(UnsafeProjectPathError):
        service.export(RepositoryPath("../unsafe.ods"))

    if os.name != "nt":
        target = tmp_path / "approved.ods"
        target.write_bytes(b"approved")
        link = tmp_path / "exports.ods"
        link.symlink_to(target)
        with pytest.raises(ProjectFilesystemError):
            service.export(RepositoryPath("exports.ods"))


def test_write_failure_does_not_leave_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = _project(tmp_path)
    output = RepositoryPath("exports/failure.ods")

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected workbook write failure")

    monkeypatch.setattr(ProjectFilesystem, "write_bytes", fail_write)
    with pytest.raises(OSError, match="injected workbook write failure"):
        AssetWorkbookExportService(filesystem).export(output)

    assert not (tmp_path / output.value).exists()
    assert not (tmp_path / "exports").exists()
    assert not list(tmp_path.glob("exports/.failure.ods.*.tmp"))


def test_concurrent_same_target_has_one_winner_and_one_conflict(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _create_sources(filesystem)
    output = RepositoryPath("exports/concurrent.ods")

    def run() -> str:
        try:
            return AssetWorkbookExportService(filesystem).export(output).report.state
        except OdsWorkbookConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(pool.map(lambda _index: run(), range(2)))

    assert sorted(states) == ["conflict", "exported"]
    assert (tmp_path / output.value).stat().st_size > 0


def test_cli_human_and_json_output_use_published_report(tmp_path: Path) -> None:
    _project(tmp_path)

    human = runner.invoke(app, ["assets", "export-ods", str(tmp_path), "exports/assets.ods"])
    assert human.exit_code == 0
    assert "Asset workbook export" in human.stdout
    assert "Overview" in human.stdout

    json_result = runner.invoke(
        app,
        ["--json", "assets", "export-ods", str(tmp_path), "exports/second.ods", "--dry-run"],
    )
    assert json_result.exit_code == 0
    response = json.loads(json_result.stdout)
    assert response["kind"] == "cli-response"
    assert response["command"] == "assets export-ods"
    assert response["ok"] is True
    assert response["data"]["state"] == "planned"


def test_cli_json_error_uses_conflict_envelope(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    output = tmp_path / "exports" / "assets.ods"
    output.parent.mkdir()
    output.write_bytes(b"approved")

    result = runner.invoke(
        app,
        ["--json", "assets", "export-ods", str(filesystem.root), "exports/assets.ods"],
    )

    assert result.exit_code == 5
    response = json.loads(result.stdout)
    assert response["ok"] is False
    assert response["error"]["code"] == "conflict"


def test_cli_json_error_rejects_traversal(tmp_path: Path) -> None:
    _project(tmp_path)

    result = runner.invoke(
        app,
        ["--json", "assets", "export-ods", str(tmp_path), "../unsafe.ods"],
    )

    assert result.exit_code == 4
    response = json.loads(result.stdout)
    assert response["ok"] is False
    assert response["error"]["code"] == "invalid-input"


def test_graph_source_path_is_the_published_canonical_path() -> None:
    assert DEFAULT_DEPENDENCY_GRAPH_PATH.value == ".ludowright/dependency-graph.json"
