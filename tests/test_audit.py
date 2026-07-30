"""Tests for the read-only structural project audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application.audit import StructuralAuditService
from ludowright.cli.app import app
from ludowright.contracts import ProjectContract
from ludowright.domain import DependencyGraph
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    DependencyGraphRepository,
    EventLog,
    IndexedEntity,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    StateStoreError,
)

runner = CliRunner()


def make_project(root: Path) -> ProjectFilesystem:
    filesystem = ProjectFilesystem(root)
    JsonDocumentRepository(
        filesystem,
        RepositoryPath(".ludowright/project.json"),
        ProjectContract,
    ).create(
        ProjectContract.model_validate(
            {
                "id": "audit-game",
                "name": "Audit Game",
                "dimensions": "2d",
                "targets": [{"platform": "linux"}],
            }
        )
    )
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"")
    DependencyGraphRepository(filesystem).create(DependencyGraph.empty())
    state = StateStore(filesystem)
    state.record_event_checkpoint(EventLog(filesystem).replay())
    return filesystem


def test_clean_project_audit_is_read_only_and_deterministic(tmp_path: Path) -> None:
    filesystem = make_project(tmp_path)
    tracked = {
        path: path.read_bytes()
        for path in (
            filesystem.root / ".ludowright/project.json",
            filesystem.root / ".ludowright/events.jsonl",
            filesystem.root / ".ludowright/dependency-graph.json",
            filesystem.root / ".ludowright/state.sqlite3",
        )
    }

    first = StructuralAuditService().inspect(tmp_path)
    second = StructuralAuditService().inspect(tmp_path)

    assert first.response.state == "clean"
    assert first.response.findings == ()
    assert first.as_data() == second.as_data()
    assert all(path.read_bytes() == payload for path, payload in tracked.items())


def test_clean_project_audit_uses_cli_json_envelope(tmp_path: Path) -> None:
    make_project(tmp_path)

    result = runner.invoke(app, ["audit", str(tmp_path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "audit"
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["read_only"] is True
    assert payload["data"]["state"] == "clean"


def test_audit_reports_missing_canonical_paths_in_json(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    JsonDocumentRepository(
        filesystem,
        RepositoryPath(".ludowright/project.json"),
        ProjectContract,
    ).create(
        ProjectContract.model_validate(
            {
                "id": "audit-game",
                "name": "Audit Game",
                "dimensions": "2d",
                "targets": [{"platform": "linux"}],
            }
        )
    )

    result = runner.invoke(app, ["--json", "audit", str(tmp_path)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["state"] == "issues-found"
    assert [finding["code"] for finding in payload["data"]["findings"]] == [
        "dependency-graph-missing",
        "event-log-missing",
        "state-store-missing",
    ]


def test_audit_outside_project_uses_project_not_found_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--json", "audit", str(tmp_path)])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "project-not-found"


def test_audit_reports_corrupt_event_log_and_incomplete_tail(tmp_path: Path) -> None:
    filesystem = make_project(tmp_path)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"{not-json}\n")

    corrupt = StructuralAuditService().inspect(tmp_path)
    assert "event-log-corrupt" in corrupt.finding_codes

    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"{}")
    incomplete = StructuralAuditService().inspect(tmp_path)
    assert "event-log-incomplete-tail" in incomplete.finding_codes


def test_audit_reports_state_schema_version_mismatch(tmp_path: Path) -> None:
    make_project(tmp_path)
    database = tmp_path / ".ludowright/state.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()

    result = StructuralAuditService().inspect(tmp_path)

    assert "state-store-version-mismatch" in result.finding_codes
    version = next(
        item for item in result.response.schema_versions if item.component == "state-store"
    )
    assert version.observed == 1
    assert version.state == "mismatch"


def test_audit_reports_unexpected_approved_file_mutation(tmp_path: Path) -> None:
    filesystem = make_project(tmp_path)
    source = RepositoryPath("assets/approved.json")
    original = b'{"value":1}\n'
    filesystem.write_bytes(source, original)
    state = StateStore(filesystem)
    state.index_entity(
        IndexedEntity(
            entity_type="reference",
            entity_id="front-view",
            source_path=source,
            source_digest=hashlib.sha256(original).hexdigest(),
            revision=1,
            status="approved",
            updated_at=datetime.now(UTC),
        )
    )
    state.record_event_checkpoint(EventLog(filesystem).replay())
    filesystem.write_bytes(source, b'{"value":2}\n')

    result = StructuralAuditService().inspect(tmp_path)

    assert "approved-file-mutated" in result.finding_codes
    assert any(
        item.code == "create-new-approved-revision" for item in result.response.repair_guidance
    )


def test_audit_rejects_symlinked_canonical_path(tmp_path: Path) -> None:
    make_project(tmp_path)
    target = tmp_path / "outside-events.jsonl"
    target.write_bytes(b"")
    path = tmp_path / ".ludowright/events.jsonl"
    path.unlink()
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks unavailable: {error}")

    result = StructuralAuditService().inspect(tmp_path)

    assert "event-log-unsafe-path" in result.finding_codes


def test_read_only_state_store_refuses_mutation(tmp_path: Path) -> None:
    filesystem = make_project(tmp_path)
    state = StateStore(filesystem, read_only=True)

    with pytest.raises(StateStoreError, match="read-only"):
        state.delete_workflow("missing-workflow")


def test_audit_human_output_contains_findings(tmp_path: Path) -> None:
    filesystem = make_project(tmp_path)
    filesystem.write_text(RepositoryPath(".ludowright/dependency-graph.json"), "{}")

    result = runner.invoke(app, ["audit", str(tmp_path)])

    assert result.exit_code == 1
    assert "LudoWright structural audit" in result.output
    assert "dependency-graph-corrupt" in result.output
