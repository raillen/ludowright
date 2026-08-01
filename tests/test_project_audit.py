"""Focused tests for the deterministic global project audit."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ludowright.application.project_audit as project_audit
from ludowright.application import (
    PackageBuilderService,
    PackageManifestService,
    ProjectAuditConflictError,
    ProjectAuditCorruptError,
    ProjectAuditService,
)
from ludowright.cli.app import app
from ludowright.contracts import AssetRegistryContract, ProjectContract
from ludowright.domain import (
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    PROJECT_MARKER,
    DependencyGraphRepository,
    EventLog,
    IndexedEntity,
    PackageFileScanner,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
)
from ludowright.infrastructure.structured import JsonDocumentRepository, YamlDocumentRepository

runner = CliRunner()


def _project(tmp_path: Path) -> tuple[Path, ProjectFilesystem]:
    root = tmp_path / "project"
    root.mkdir()
    filesystem = ProjectFilesystem(root)
    filesystem.ensure_directory(RepositoryPath(".ludowright"))
    project = ProjectContract.model_validate(
        {
            "id": "locadora-2000",
            "name": "Locadora 2000",
            "dimensions": "3d",
            "targets": [{"platform": "windows"}],
        }
    )
    manifest = JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract)
    payload = manifest.canonical_bytes(project)
    filesystem.write_bytes(PROJECT_MARKER, payload)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"")
    graph = DependencyGraph.empty().add_node(
        DependencyNode(
            key=DependencyKey(DependencyNodeKind.PROJECT, project.id),
            revision=RevisionVersion(1),
        )
    )
    DependencyGraphRepository(filesystem).create(graph)
    event_snapshot = EventLog(filesystem).replay()
    timestamp = datetime.now(UTC)
    state_store = StateStore(filesystem)
    state_store.record_event_checkpoint(event_snapshot, updated_at=timestamp)
    state_store.index_entity(
        IndexedEntity(
            entity_type="project",
            entity_id=project.id,
            source_path=PROJECT_MARKER,
            source_digest=hashlib.sha256(payload).hexdigest(),
            revision=1,
            status="active",
            updated_at=timestamp,
        )
    )
    return root, filesystem


def _tree_digest(root: Path) -> str:
    entries: list[bytes] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            entries.append(b"link:" + relative + b":" + path.readlink().as_posix().encode())
        elif path.is_file():
            entries.append(b"file:" + relative + b":" + hashlib.sha256(path.read_bytes()).digest())
        else:
            entries.append(b"dir:" + relative)
    return hashlib.sha256(b"\n".join(entries)).hexdigest()


def test_audit_reports_structural_readiness_without_mutating_files(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    before = _tree_digest(root)

    first = ProjectAuditService(filesystem).audit(dry_run=True)
    second = ProjectAuditService(filesystem).audit(dry_run=True)

    assert first.report.state == "needs-review"
    assert first.report.valid is False
    assert first.as_data() == second.as_data()
    assert {finding.code for finding in first.report.findings} == {
        "asset-registry-missing",
        "documents-directory-missing",
        "package-manifest-missing",
    }
    sources = {source.path: source.state for source in first.report.sources}
    assert sources[DEFAULT_EVENT_LOG_PATH.value] == "current"
    assert sources[".ludowright/dependency-graph.json"] == "current"
    assert sources[".ludowright/state.sqlite3"] == "current"
    assert _tree_digest(root) == before


def test_audit_cli_human_output_is_readable(tmp_path: Path) -> None:
    root, _filesystem = _project(tmp_path)

    result = runner.invoke(app, ["--no-color", "audit", str(root), "--dry-run"])

    assert result.exit_code == 0
    assert "LudoWright project audit" in result.stdout
    assert "documents" in result.stdout
    assert "documents-directory-missing" in result.stdout


def test_audit_cli_json_uses_envelope_and_check_exit_code(tmp_path: Path) -> None:
    root, _filesystem = _project(tmp_path)

    result = runner.invoke(app, ["--json", "audit", str(root), "--check"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["kind"] == "cli-response"
    assert payload["command"] == "audit"
    assert payload["ok"] is False
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["state"] == "needs-review"


def test_audit_rejects_invalid_manifest_with_json_error_envelope(tmp_path: Path) -> None:
    root = tmp_path / "project"
    marker = root / ".ludowright" / "project.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["--json", "audit", str(root)])

    assert result.exit_code == 6
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "corrupt-state"


def test_audit_rejects_symlinks_before_reading_project_state(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("not project state", encoding="utf-8")
    try:
        (root / "unsafe-link").symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ProjectAuditCorruptError):
        ProjectAuditService(filesystem).audit()


def test_audit_detects_concurrent_source_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, filesystem = _project(tmp_path)
    original_inventory = project_audit._inventory
    calls = 0

    def changing_inventory(scanner: PackageFileScanner) -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        inventory = original_inventory(scanner)
        if calls == 2:
            marker = root / PROJECT_MARKER.value
            marker.write_text(marker.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return inventory

    monkeypatch.setattr(project_audit, "_inventory", changing_inventory)

    with pytest.raises(ProjectAuditConflictError):
        ProjectAuditService(filesystem).audit()


def test_audit_uses_current_state_store_schema_in_read_only_mode(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    database = root / ".ludowright" / "state.sqlite3"
    before = database.read_bytes()

    result = ProjectAuditService(filesystem).audit()

    assert result.report.sources
    state_source = next(
        source for source in result.report.sources if source.path.endswith("state.sqlite3")
    )
    assert state_source.state == "current"
    assert state_source.size_bytes == len(before)
    assert database.read_bytes() == before
    assert not database.with_name("state.sqlite3-wal").exists()


def test_audit_source_paths_are_relative_and_safe(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)

    report = ProjectAuditService(filesystem).audit().report

    assert all(
        not path.startswith(("/", "\\")) for path in (source.path for source in report.sources)
    )
    assert all(".." not in source.path.split("/") for source in report.sources)
    assert report.sources == tuple(sorted(report.sources, key=lambda source: source.path))


def test_audit_validates_package_manifest_index_and_archive(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    manifest_path = RepositoryPath("release/package-manifest.json")
    PackageManifestService(filesystem).create(manifest_path, package_id="demo")
    PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release"))

    report = ProjectAuditService(filesystem).audit().report

    package_findings = [finding for finding in report.findings if finding.category == "package"]
    assert all(finding.severity == "warning" for finding in package_findings)
    assert {finding.code for finding in package_findings} == {"package-optional-source-missing"}
    package_category = next(item for item in report.categories if item.category == "package")
    assert package_category.item_count == 2
    assert (root / "release" / "demo.zip").is_file()


def test_audit_keeps_semantic_asset_subjects_out_of_slug_related_ids(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    registry = json.loads(
        Path("tests/fixtures/contracts/v1/asset-registry.json").read_text(encoding="utf-8")
    )
    registry["assets"][0]["id"] = "prop-lantern"
    registry["assets"][0]["components"][0]["id"] = "lantern-body"
    YamlDocumentRepository(
        filesystem,
        RepositoryPath("assets/registry.yaml"),
        AssetRegistryContract,
    ).create(AssetRegistryContract.model_validate(registry))

    report = ProjectAuditService(filesystem).audit().report
    metadata_finding = next(
        finding
        for finding in report.findings
        if finding.code == "asset-incomplete-production-metadata"
    )

    assert metadata_finding.related_ids == ("prop-lantern",)
    assert all(
        ":" not in related_id for finding in report.findings for related_id in finding.related_ids
    )


__all__ = []
