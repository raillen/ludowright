"""Tests for deterministic incremental document refresh."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    DocumentRefreshError,
    DocumentRefreshRequest,
    DocumentRefreshService,
)
from ludowright.cli.app import app
from ludowright.contracts import (
    DocumentRefreshRequestContract,
    DocumentRefreshStateContract,
)
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    PROJECT_MARKER,
    DocumentRefreshRepository,
    EventLog,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    UnsafeProjectPathError,
)

runner = CliRunner()


def _context(title: str = "Echoes") -> dict[str, object]:
    return {
        "title": title,
        "body": "A small game.",
        "sections": [{"title": "Summary", "body": "A small game."}],
    }


def _request(
    *,
    document_id: str = "game-brief",
    source: bytes = b"source-v1",
    title: str = "Echoes",
) -> DocumentRefreshRequest:
    return DocumentRefreshRequest(
        document_id=document_id,
        template_id="minimal",
        context=_context(title),
        source_hashes={"interview": hashlib.sha256(source).hexdigest()},
    )


def _filesystem(root: Path) -> ProjectFilesystem:
    filesystem = ProjectFilesystem(root)
    filesystem.write_text(PROJECT_MARKER, "{}\n")
    return filesystem


def test_initial_refresh_creates_output_state_and_audit_event(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path)

    result = DocumentRefreshService(filesystem).refresh([_request()])

    assert result.refreshed_documents == ("game-brief",)
    assert result.plans[0].status == "new"
    output = tmp_path / ".ludowright" / "documents" / "game-brief.md"
    state = tmp_path / ".ludowright" / "documents" / "game-brief.json"
    assert output.is_file()
    assert state.is_file()
    assert "ludowright:generated:start" in output.read_text(encoding="utf-8")
    assert DocumentRefreshRepository(filesystem, "game-brief").load().value.status == "current"
    events = EventLog(filesystem).replay().events
    assert len(events) == 1
    assert events[0].event_type.value == "document.refreshed"


def test_refresh_creates_missing_parent_directories_and_is_idempotent(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    service = DocumentRefreshService(filesystem)

    first = service.refresh([_request()])
    event_bytes = (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes()
    second = service.refresh([_request()])

    assert first.refreshed_documents == ("game-brief",)
    assert second.refreshed_documents == ()
    assert second.plans[0].status == "current"
    assert (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes() == event_bytes


def test_changed_source_is_marked_stale_and_planned_as_affected(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    service = DocumentRefreshService(filesystem)
    service.refresh([_request()])

    plan = service.plan([_request(source=b"source-v2")])[0]

    assert plan.status == "stale"
    assert plan.changed_sources == ("interview",)
    assert "source-changed" in plan.reasons
    assert plan.requires_refresh


def test_manual_sections_are_preserved_across_refresh(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    service = DocumentRefreshService(filesystem)
    service.refresh([_request()])
    output_path = RepositoryPath(".ludowright/documents/game-brief.md")
    original = filesystem.read_text(output_path)
    manual = (
        '\n<!-- ludowright:manual:start id="review-notes" approved="true" -->\n'
        "Keep this approved note.\n"
        "<!-- ludowright:manual:end -->\n"
    )
    filesystem.write_text(output_path, original + manual)

    result = service.refresh([_request(source=b"source-v2")])
    refreshed = filesystem.read_text(output_path)

    assert result.plans[0].status == "stale"
    assert "manual-section-changed" in result.plans[0].reasons
    assert manual.strip() in refreshed
    assert result.plans[0].manual_sections[0].approved is True


def test_malformed_manual_section_fails_without_overwriting_output(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    service = DocumentRefreshService(filesystem)
    service.refresh([_request()])
    output_path = RepositoryPath(".ludowright/documents/game-brief.md")
    malformed = (
        filesystem.read_text(output_path)
        + '<!-- ludowright:manual:start id="notes" approved="true" -->\n'
    )
    filesystem.write_text(output_path, malformed)

    with pytest.raises(DocumentRefreshError):
        service.refresh([_request(source=b"source-v2")])

    assert filesystem.read_text(output_path) == malformed


def test_multiple_requests_are_sorted_and_planned_deterministically(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    requests = (_request(document_id="zeta"), _request(document_id="alpha"))

    first = DocumentRefreshService(filesystem).plan(requests)
    second = DocumentRefreshService(filesystem).plan(reversed(requests))

    assert tuple(plan.document_id for plan in first) == ("alpha", "zeta")
    assert first == second


def test_dry_run_does_not_create_project_files(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    result = DocumentRefreshService(filesystem).refresh([_request()], dry_run=True)

    assert result.dry_run is True
    assert result.affected_documents == ("game-brief",)
    assert not (tmp_path / ".ludowright").exists()


def test_failure_during_state_write_rolls_back_output_and_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    def fail_create(*args: object, **kwargs: object) -> object:
        raise OSError("simulated state failure")

    monkeypatch.setattr(DocumentRefreshRepository, "create", fail_create)

    with pytest.raises(OSError, match="simulated state failure"):
        DocumentRefreshService(filesystem).refresh([_request()])

    assert not (tmp_path / ".ludowright" / "documents" / "game-brief.md").exists()
    assert not (tmp_path / ".ludowright" / "documents" / "game-brief.json").exists()
    assert not (tmp_path / DEFAULT_EVENT_LOG_PATH.value).exists()


def test_failure_in_event_append_rolls_back_all_persisted_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    def fail_append(*args: object, **kwargs: object) -> object:
        raise OSError("simulated event failure")

    monkeypatch.setattr(EventLog, "append", fail_append)

    with pytest.raises(OSError, match="simulated event failure"):
        DocumentRefreshService(filesystem).refresh([_request()])

    assert not (tmp_path / ".ludowright" / "documents" / "game-brief.md").exists()
    assert not (tmp_path / ".ludowright" / "documents" / "game-brief.json").exists()
    assert not (tmp_path / DEFAULT_EVENT_LOG_PATH.value).exists()


def test_existing_output_symlink_is_rejected(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    output_directory = tmp_path / ".ludowright" / "documents"
    output_directory.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    output = output_directory / "game-brief.md"
    try:
        output.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(UnsafeProjectPathError):
        DocumentRefreshService(filesystem).refresh([_request()])

    assert outside.read_text(encoding="utf-8") == "outside"


def test_request_and_state_fixtures_use_published_contracts() -> None:
    request = json.loads(
        Path("tests/fixtures/contracts/v1/document-refresh-request.json").read_text()
    )
    state = json.loads(Path("tests/fixtures/contracts/v1/document-refresh.json").read_text())

    assert DocumentRefreshRequestContract.model_validate(request).document_id == "game-brief"
    assert DocumentRefreshStateContract.model_validate(state).status == "current"


def test_cli_supports_human_and_json_refresh_surfaces(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path)
    request_path = RepositoryPath(".ludowright/request.json")
    request_contract = DocumentRefreshRequestContract(
        document_id="game-brief",
        template_id="minimal",
        context=_context(),
        source_hashes=(),
    )
    JsonDocumentRepository(
        filesystem,
        request_path,
        DocumentRefreshRequestContract,
    ).create(request_contract)

    human = runner.invoke(
        app,
        ["--no-color", "documents", "refresh", request_path.value, str(tmp_path)],
    )
    machine = runner.invoke(
        app,
        ["--json", "documents", "refresh", request_path.value, str(tmp_path), "--dry-run"],
    )

    assert human.exit_code == 0, human.stdout
    assert "Document refresh" in human.stdout
    assert machine.exit_code == 0, machine.stdout
    payload = json.loads(machine.stdout)
    assert payload["command"] == "documents refresh"
    assert payload["ok"] is True
    assert payload["data"]["schema_version"] == 1
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["plans"][0]["status"] == "current"


def test_cli_rejects_traversal_in_request_path(tmp_path: Path) -> None:
    _filesystem(tmp_path)

    result = runner.invoke(
        app,
        ["--json", "documents", "refresh", "../request.json", str(tmp_path)],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid-input"
