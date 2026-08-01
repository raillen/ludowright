"""Tests for deterministic asset discovery and explicit confirmation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    AssetDiscoveryConfirmationError,
    AssetDiscoveryService,
)
from ludowright.cli.app import app
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    EventLog,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    UnsafeProjectPathError,
)

runner = CliRunner()


def _project(tmp_path: Path) -> ProjectFilesystem:
    marker = tmp_path / ".ludowright" / "project.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(tmp_path)


def _write_document(filesystem: ProjectFilesystem, content: str, name: str = "brief.md") -> None:
    filesystem.write_text(
        RepositoryPath(f".ludowright/documents/{name}"),
        content,
    )


def _marker(
    *,
    asset_id: str | None = None,
    family: str = "character",
    subtype: str = "humanoid",
    priority: str = "high",
    name: str = "Maya",
) -> str:
    identifier = f' id="{asset_id}"' if asset_id is not None else ""
    return (
        "<!-- ludowright:asset-candidate"
        f'{identifier} family="{family}" subtype="{subtype}" priority="{priority}" --> '
        f"{name}"
    )


def test_discovery_is_deterministic_and_skips_code_fences(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(
        filesystem,
        "\n".join(
            (
                "# Brief",
                _marker(),
                "```markdown",
                _marker(asset_id="chr-hidden", name="Hidden"),
                "```",
            )
        )
        + "\n",
    )

    first = AssetDiscoveryService(filesystem).discover().as_data()
    second = AssetDiscoveryService(filesystem).discover().as_data()

    assert first == second
    assert first["state"] == "pending"
    candidates = first["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 1
    assert candidates[0]["asset_id"] == "chr-maya"
    assert candidates[0]["source_line"] == 2
    assert not (tmp_path / "assets/registry.yaml").exists()
    assert not (tmp_path / DEFAULT_EVENT_LOG_PATH.value).exists()


def test_duplicate_candidates_are_ambiguous_and_cannot_be_confirmed(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n", "first.md")
    _write_document(filesystem, _marker() + "\n", "second.md")

    service = AssetDiscoveryService(filesystem)
    report = service.discover()
    assert report.report.state == "ambiguous"
    assert any(issue.code == "duplicate-asset-id" for issue in report.report.issues)
    candidate_id = report.report.candidates[0].candidate_id

    with pytest.raises(AssetDiscoveryConfirmationError) as caught:
        service.discover(confirm_ids=(candidate_id,))

    assert any(issue.code == "confirmation-blocked" for issue in caught.value.report.issues)
    assert not (tmp_path / "assets/registry.yaml").exists()


def test_confirmation_creates_registry_and_audits_source(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n")
    service = AssetDiscoveryService(filesystem)
    candidate_id = service.discover().report.candidates[0].candidate_id

    result = service.discover(confirm_ids=(candidate_id,))

    assert result.report.state == "confirmed"
    assert result.report.confirmed_asset_ids == ("chr-maya",)
    assert result.report.candidates[0].state == "confirmed"
    events = EventLog(filesystem).replay()
    assert [event.event_type.value for event in events.events] == ["asset.discovered"]
    source = events.events[0].payload["discovery_candidates"]
    assert source[0]["source_path"] == ".ludowright/documents/brief.md"
    assert source[0]["source_line"] == 1
    assert StateStore(filesystem).get_entity("asset-registry", "registry") is not None


def test_dry_run_confirmation_does_not_write_any_project_state(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n")
    service = AssetDiscoveryService(filesystem)
    candidate_id = service.discover().report.candidates[0].candidate_id

    result = service.discover(confirm_ids=(candidate_id,), dry_run=True)

    assert result.report.state == "planned"
    assert result.report.dry_run is True
    assert not (tmp_path / "assets/registry.yaml").exists()
    assert not (tmp_path / DEFAULT_EVENT_LOG_PATH.value).exists()
    assert not (tmp_path / ".ludowright/state.sqlite3").exists()


def test_confirmation_rolls_back_registry_and_event_after_state_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n")
    service = AssetDiscoveryService(filesystem)
    candidate_id = service.discover().report.candidates[0].candidate_id

    def fail_index(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected state index failure")

    monkeypatch.setattr(StateStore, "index_entity", fail_index)

    with pytest.raises(RuntimeError, match="injected state index failure"):
        service.discover(confirm_ids=(candidate_id,))

    assert not (tmp_path / "assets/registry.yaml").exists()
    assert not (tmp_path / DEFAULT_EVENT_LOG_PATH.value).exists()


def test_existing_registry_id_is_rejected_without_overwrite(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n")
    service = AssetDiscoveryService(filesystem)
    candidate_id = service.discover().report.candidates[0].candidate_id
    service.discover(confirm_ids=(candidate_id,))
    before = (tmp_path / "assets/registry.yaml").read_bytes()

    report = service.discover()

    assert report.report.candidates[0].state == "rejected"
    assert any(issue.code == "existing-asset-id" for issue in report.report.issues)
    assert (tmp_path / "assets/registry.yaml").read_bytes() == before


def test_invalid_declaration_is_reported_without_partial_creation(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(
        filesystem,
        '<!-- ludowright:asset-candidate family="unknown" --> Broken\n',
    )

    report = AssetDiscoveryService(filesystem).discover()

    assert report.report.state == "invalid"
    assert report.report.issues[0].code == "invalid-declaration"
    assert report.report.valid is False
    assert not (tmp_path / "assets/registry.yaml").exists()


def test_explicit_sources_and_unsafe_paths_are_bounded(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n", "brief.md")
    service = AssetDiscoveryService(filesystem)

    result = service.discover(source_paths=(RepositoryPath(".ludowright/documents/brief.md"),))

    assert len(result.report.candidates) == 1
    with pytest.raises(UnsafeProjectPathError):
        RepositoryPath(".ludowright/documents/../project.json")


@pytest.mark.skipif(
    os.name == "nt", reason="symlink creation may require elevated Windows privileges"
)
def test_symlinked_document_tree_is_rejected(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    documents = tmp_path / ".ludowright" / "documents"
    documents.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(_marker() + "\n", encoding="utf-8")
    linked = documents / "linked.md"
    linked.symlink_to(outside)

    with pytest.raises(UnsafeProjectPathError):
        AssetDiscoveryService(filesystem).discover()


def test_cli_supports_human_json_and_confirmation_error_envelope(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _write_document(filesystem, _marker() + "\n")

    human = runner.invoke(app, ["assets", "discover", str(tmp_path)])
    assert human.exit_code == 0
    assert "Asset discovery" in human.stdout
    assert "chr-maya" in human.stdout

    discovery = runner.invoke(app, ["--json", "assets", "discover", str(tmp_path)])
    assert discovery.exit_code == 0
    payload = json.loads(discovery.stdout)
    candidate_id = payload["data"]["candidates"][0]["candidate_id"]

    invalid = runner.invoke(
        app,
        ["--json", "assets", "discover", str(tmp_path), "--confirm", "missing-candidate"],
    )
    assert invalid.exit_code == 4
    invalid_payload = json.loads(invalid.stdout)
    assert invalid_payload["error"]["code"] == "invalid-input"
    assert invalid_payload["data"]["kind"] == "asset-discovery-report"

    unsafe = runner.invoke(
        app,
        ["--json", "assets", "discover", str(tmp_path), "--source", "../outside.md"],
    )
    assert unsafe.exit_code == 4
    assert json.loads(unsafe.stdout)["error"]["code"] == "invalid-input"

    confirmed = runner.invoke(
        app,
        ["--json", "assets", "discover", str(tmp_path), "--confirm", candidate_id],
    )
    assert confirmed.exit_code == 0
    assert json.loads(confirmed.stdout)["data"]["state"] == "confirmed"
