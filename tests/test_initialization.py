"""Tests for safe, deterministic project initialization."""

from __future__ import annotations

import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    ProjectInitializationConflictError,
    ProjectInitializationFailureError,
    ProjectInitializationInputError,
    ProjectInitializationService,
)
from ludowright.application import initialization as initialization_module
from ludowright.application.templates import load_template
from ludowright.cli.app import app
from ludowright.cli.runtime import CliExitCode
from ludowright.contracts import ProjectContract
from ludowright.infrastructure import (
    DependencyGraphRepository,
    EventLog,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
)
from ludowright.infrastructure.structured import JsonDocumentRepository

runner = CliRunner()


def create_project(target: Path, name: str = "Starfall Courier") -> dict[str, object]:
    return ProjectInitializationService().initialize(target, name=name).as_data()


def test_initializes_minimal_project_with_current_stores(tmp_path: Path) -> None:
    target = tmp_path / "projects" / "starfall"

    data = create_project(target)

    assert data["state"] == "created"
    assert data["project_id"] == "starfall-courier"
    assert data["schema_version"] == 1
    assert data["state_store_schema_version"] == 2
    assert (target / ".ludowright/project.json").is_file()
    assert (target / ".ludowright/events.jsonl").read_bytes() == b""
    if os.name != "nt":
        assert stat.S_IMODE((target / ".ludowright/locks").stat().st_mode) == 0o700
    assert set(data["files"]) == {
        ".ludowright/dependency-graph.json",
        ".ludowright/events.jsonl",
        ".ludowright/project.json",
        ".ludowright/state.sqlite3",
    }

    filesystem = ProjectFilesystem(target)
    manifest = JsonDocumentRepository(
        filesystem,
        RepositoryPath(".ludowright/project.json"),
        ProjectContract,
    ).load()
    assert manifest.value.template is not None
    assert manifest.value.template.id == "minimal"
    assert EventLog(filesystem).replay().last_sequence == 0
    graph = DependencyGraphRepository(filesystem).load().graph
    assert [node.key.token for node in graph.nodes] == ["project:starfall-courier"]
    state = StateStore(filesystem, read_only=True)
    assert state.schema_version == 2
    assert state.get_entity("project", "starfall-courier") is not None
    assert state.check_consistency(EventLog(filesystem).replay()).is_consistent


def test_initializes_in_missing_and_empty_directories(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "game"
    empty = tmp_path / "empty"
    empty.mkdir()

    create_project(missing, "Missing Game")
    create_project(empty, "Empty Game")

    assert (missing / ".ludowright/project.json").is_file()
    assert (empty / ".ludowright/project.json").is_file()


def test_refuses_non_empty_and_existing_projects_without_mutation(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    existing = occupied / "keep.txt"
    existing.write_text("preserve", encoding="utf-8")

    with pytest.raises(ProjectInitializationConflictError):
        create_project(occupied, "Occupied Game")
    assert existing.read_text(encoding="utf-8") == "preserve"

    project = tmp_path / "project"
    create_project(project)
    before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
    with pytest.raises(ProjectInitializationConflictError):
        create_project(project, "Changed Name")
    after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
    assert after == before


@pytest.mark.parametrize("name", ["", "  Game", "Game  ", "\u200bGame"])
def test_rejects_invalid_project_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ProjectInitializationInputError):
        create_project(tmp_path / "game", name)


@pytest.mark.parametrize("path", ["../outside", "game/../outside"])
def test_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ProjectInitializationInputError):
        ProjectInitializationService().initialize(path, name="Safe Name")


@pytest.mark.skipif(os.name == "nt", reason="backslash is the Windows separator")
def test_rejects_backslash_paths(tmp_path: Path) -> None:
    with pytest.raises(ProjectInitializationInputError):
        ProjectInitializationService().initialize("game\\outside", name="Safe Name")


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics are not available")
def test_rejects_symlink_target(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ProjectInitializationInputError):
        create_project(link, "Symlink Game")
    assert not (real / ".ludowright/project.json").exists()


def test_dry_run_is_deterministic_and_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "planned"
    service = ProjectInitializationService()

    first = service.initialize(target, name="Planned Game", dry_run=True).as_data()
    second = service.initialize(target, name="Planned Game", dry_run=True).as_data()

    assert first == second
    assert first["state"] == "planned"
    assert first["dry_run"] is True
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_cli_human_output_and_non_interactive_mode(tmp_path: Path) -> None:
    target = tmp_path / "human"

    result = runner.invoke(
        app,
        ["--no-color", "init", str(target), "--name", "Human Game", "--non-interactive"],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "LudoWright project created." in result.stdout
    assert "ProjectId: human-game" in result.stdout
    assert "Template: minimal v1" in result.stdout


def test_cli_json_success_and_error_envelopes(tmp_path: Path) -> None:
    target = tmp_path / "json"
    success = runner.invoke(
        app,
        ["--json", "init", str(target), "--name", "JSON Game", "--dry-run"],
    )
    success_payload = json.loads(success.stdout)
    assert success.exit_code == int(CliExitCode.SUCCESS)
    assert success_payload["kind"] == "cli-response"
    assert success_payload["command"] == "init"
    assert success_payload["ok"] is True
    assert success_payload["data"]["dry_run"] is True
    assert not target.exists()

    create_project(target, "JSON Game")
    conflict = runner.invoke(
        app,
        ["--json", "init", str(target), "--name", "JSON Game"],
    )
    conflict_payload = json.loads(conflict.stdout)
    assert conflict.exit_code == int(CliExitCode.CONFLICT)
    assert conflict_payload["ok"] is False
    assert conflict_payload["error"]["code"] == "conflict"


def test_rollback_removes_only_generated_project_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingStateStore:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated state-store failure")

    monkeypatch.setattr(initialization_module, "StateStore", FailingStateStore)
    target = tmp_path / "rollback" / "project"

    with pytest.raises(ProjectInitializationFailureError) as failure:
        create_project(target, "Rollback Game")

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert not target.exists()
    assert not (tmp_path / "rollback").exists()


def test_concurrent_initialization_has_one_winner(tmp_path: Path) -> None:
    target = tmp_path / "concurrent"

    def run() -> str:
        try:
            create_project(target, "Concurrent Game")
        except ProjectInitializationConflictError:
            return "conflict"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _item: run(), range(2)))

    assert outcomes == ["conflict", "created"]
    assert (target / ".ludowright/project.json").is_file()


def test_template_is_data_defined_and_plan_lists_are_stable(tmp_path: Path) -> None:
    template = load_template("minimal")
    service = ProjectInitializationService()
    target = tmp_path / "game"
    first = service.initialize(target, name="Game", dry_run=True).as_data()
    second = service.initialize(target, name="Game", dry_run=True).as_data()

    assert first == second
    assert first["template"] == {"id": "minimal", "version": 1}
    assert template.id == "minimal"
