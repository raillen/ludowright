"""Tests for the read-only project status use case and CLI surface."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import ProjectStatusService
from ludowright.cli.app import app
from ludowright.contracts import ProjectContract
from ludowright.contracts.project import ProjectTargetContract
from ludowright.domain import (
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    InvalidationMode,
    PlatformFamily,
    ProjectDimension,
    ProjectId,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    PROJECT_MARKER,
    DependencyGraphRepository,
    EventLog,
    IndexedEntity,
    ProjectFilesystem,
    StateStore,
    StateStoreError,
)
from ludowright.infrastructure.structured import JsonDocumentRepository

runner = CliRunner()
_FIXED_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def create_project(root: Path) -> None:
    root.mkdir()
    filesystem = ProjectFilesystem(root)
    manifest_repository = JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract)
    manifest = ProjectContract(
        id="status-game",
        name="Status Game",
        dimensions=ProjectDimension.TWO_D,
        targets=(
            ProjectTargetContract(
                platform=PlatformFamily.OTHER,
                label="Local test target",
            ),
        ),
    )
    manifest_snapshot = manifest_repository.create(manifest)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"")

    project_key = DependencyKey(DependencyNodeKind.PROJECT, ProjectId("status-game").value)
    graph = DependencyGraph.empty().add_node(
        DependencyNode(key=project_key, revision=RevisionVersion(1))
    )
    DependencyGraphRepository(filesystem).create(graph)

    event_log = EventLog(filesystem)
    event_snapshot = event_log.replay()
    store = StateStore(filesystem)
    store.index_entity(
        _indexed_manifest(
            digest=manifest_snapshot.digest,
        )
    )
    store.record_event_checkpoint(event_snapshot, updated_at=_FIXED_TIMESTAMP)


def _indexed_manifest(*, digest: str) -> IndexedEntity:
    return IndexedEntity(
        entity_type="project",
        entity_id="status-game",
        source_path=PROJECT_MARKER,
        source_digest=digest,
        revision=1,
        status="active",
        updated_at=_FIXED_TIMESTAMP,
    )


def test_status_reports_healthy_project_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    before = snapshot_tree(root)

    result = ProjectStatusService().inspect(root)

    assert result.readiness_state == "ready"
    assert result.project_id == "status-game"
    assert result.blockers == ()
    assert result.stale_outputs == ()
    assert result.consistency["state"] == "consistent"
    assert snapshot_tree(root) == before


def test_status_discovers_nearest_project_from_nested_path(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    nested = root / "docs"
    nested.mkdir()

    result = ProjectStatusService().inspect(nested)

    assert result.project_directory == root.resolve().as_posix()


def test_status_reports_missing_components_without_creating_them(tmp_path: Path) -> None:
    root = tmp_path / "partial"
    root.mkdir()
    filesystem = ProjectFilesystem(root)
    manifest = ProjectContract(
        id="partial-game",
        name="Partial Game",
        dimensions=ProjectDimension.TWO_D,
        targets=(ProjectTargetContract(platform=PlatformFamily.OTHER, label="Test"),),
    )
    JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract).create(manifest)

    result = ProjectStatusService().inspect(root)

    assert result.readiness_state == "blocked"
    assert [issue.code for issue in result.blockers] == [
        "dependency-graph-missing",
        "event-log-missing",
        "state-store-missing",
    ]
    assert not root.joinpath(*DEFAULT_STATE_STORE_PATH.parts).exists()


def test_status_reports_stale_outputs_and_refresh_action(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    filesystem = ProjectFilesystem(root)
    repository = DependencyGraphRepository(filesystem)
    snapshot = repository.load()
    project_key = DependencyKey(DependencyNodeKind.PROJECT, "status-game")
    document_key = DependencyKey(DependencyNodeKind.DOCUMENT, "design")
    graph = snapshot.graph.add_node(
        DependencyNode(key=document_key, revision=RevisionVersion(1))
    ).connect(
        project_key,
        document_key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.STALE,
    )
    graph = graph.publish_revision(project_key, RevisionVersion(2)).graph
    repository.replace(snapshot, graph)

    result = ProjectStatusService().inspect(root)

    assert result.readiness_state == "blocked"
    assert result.blockers == ()
    assert result.stale_outputs[0]["id"] == "design"
    assert result.stale_outputs[0]["state"] == "stale"
    assert result.recommended_actions[0]["code"] == "refresh-stale-outputs"


def test_status_reports_review_required_outputs(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    filesystem = ProjectFilesystem(root)
    repository = DependencyGraphRepository(filesystem)
    snapshot = repository.load()
    project_key = DependencyKey(DependencyNodeKind.PROJECT, "status-game")
    document_key = DependencyKey(DependencyNodeKind.DOCUMENT, "design")
    graph = snapshot.graph.add_node(
        DependencyNode(key=document_key, revision=RevisionVersion(1))
    ).connect(
        project_key,
        document_key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.REVIEW,
    )
    graph = graph.publish_revision(project_key, RevisionVersion(2)).graph
    repository.replace(snapshot, graph)

    result = ProjectStatusService().inspect(root)

    assert result.readiness_state == "needs-review"
    assert result.recommended_actions[0]["code"] == "review-affected-outputs"


def test_status_reports_changed_canonical_source_as_blocker(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    filesystem = ProjectFilesystem(root)
    repository = JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract)
    original = repository.load().value
    repository.save(original.model_copy(update={"name": "Changed Name"}))

    result = ProjectStatusService().inspect(root)

    assert result.readiness_state == "blocked"
    assert any(issue.code == "canonical-source-changed" for issue in result.blockers)


def test_status_read_only_store_rejects_writes(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    filesystem = ProjectFilesystem(root)
    store = StateStore(filesystem, read_only=True)

    assert store.read_only is True
    with pytest.raises(StateStoreError, match="read-only"):
        store.delete_workflow("missing")


def test_status_json_is_deterministic_and_uses_cli_envelope(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)

    first = runner.invoke(app, ["--json", "status", str(root)])
    second = runner.invoke(app, ["--json", "status", str(root)])

    assert first.exit_code == 0
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["command"] == "status"
    assert payload["ok"] is True
    assert payload["data"]["readiness"] == {"stage": "concept", "state": "ready"}


def test_status_human_output_uses_rich_components_table(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)

    result = runner.invoke(app, ["status", str(root)])

    assert result.exit_code == 0
    assert "Project status: ready" in result.stdout
    assert "Components" in result.stdout
    assert "state-store" in result.stdout


def test_status_missing_project_uses_project_not_found_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--json", "status", str(tmp_path)])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "project-not-found"


def test_status_corrupt_event_log_uses_corrupt_state_error(tmp_path: Path) -> None:
    root = tmp_path / "game"
    create_project(root)
    (root / DEFAULT_EVENT_LOG_PATH.value).write_text("invalid\n", encoding="utf-8")

    result = runner.invoke(app, ["--json", "status", str(root)])

    assert result.exit_code == 6
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "corrupt-state"


def snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
