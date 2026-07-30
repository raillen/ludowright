"""Tests for the bounded ``ludowright init`` use case."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ludowright.application.initialization as initialization
from ludowright.application import (
    ProjectInitializationConflictError,
    ProjectInitializationFailureError,
    ProjectInitializationInputError,
    ProjectInitializationService,
)
from ludowright.cli.app import app
from ludowright.contracts import ProjectContract
from ludowright.domain import DependencyNodeKind
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    PROJECT_MARKER,
    DependencyGraphRepository,
    EventLog,
    ProjectFilesystem,
    StateStore,
)
from ludowright.infrastructure.structured import JsonDocumentRepository

runner = CliRunner()


def test_init_creates_valid_minimal_project_and_current_state_store(tmp_path: Path) -> None:
    target = tmp_path / "game"

    result = ProjectInitializationService().initialize(target, name="Meu Jogo")

    assert result.state == "created"
    assert result.project_id == "meu-jogo"
    assert target.joinpath(*PROJECT_MARKER.parts).is_file()
    assert (target / ".ludowright" / "events.jsonl").read_bytes() == b""

    filesystem = ProjectFilesystem(target)
    manifest = JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract).load().value
    assert manifest.id == "meu-jogo"
    assert manifest.template is not None
    assert manifest.template.id == "minimal"

    event_log = EventLog(filesystem)
    snapshot = event_log.replay()
    assert snapshot.last_sequence == 0

    graph = DependencyGraphRepository(filesystem).load().graph
    project_key = next(
        node.key for node in graph.nodes if node.key.kind is DependencyNodeKind.PROJECT
    )
    assert graph.get_node(project_key).key.id == "meu-jogo"

    state_store = StateStore(filesystem)
    assert state_store.schema_version == 2
    assert state_store.get_event_checkpoint() is not None
    assert state_store.get_entity("project", "meu-jogo") is not None
    assert state_store.check_consistency(snapshot).is_consistent
    assert ProjectFilesystem.discover(target).root == target.resolve()


def test_init_accepts_missing_and_empty_targets(tmp_path: Path) -> None:
    service = ProjectInitializationService()

    service.initialize(tmp_path / "missing" / "game", name="Missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    service.initialize(empty, name="Empty")

    assert (tmp_path / "missing" / "game" / ".ludowright" / "project.json").is_file()
    assert (empty / ".ludowright" / "project.json").is_file()


def test_init_accepts_relative_target_with_portable_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = ProjectInitializationService().initialize("relative-game", name="Relative")

    assert result.project_directory == (tmp_path / "relative-game").as_posix()
    assert (tmp_path / "relative-game" / ".ludowright" / "project.json").is_file()


def test_init_refuses_existing_non_empty_target_and_project(tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "notes.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(ProjectInitializationConflictError):
        ProjectInitializationService().initialize(target, name="Occupied")

    assert (target / "notes.txt").read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("name", ["", "  Game", "Game  ", "\u200bGame"])
def test_init_rejects_invalid_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(ProjectInitializationInputError):
        ProjectInitializationService().initialize(tmp_path / "game", name=name)


@pytest.mark.parametrize("path", ["../outside", "game/../outside"])
def test_init_rejects_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProjectInitializationInputError):
        ProjectInitializationService().initialize(path, name="Game")


def test_init_rejects_symlink_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "game"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ProjectInitializationInputError):
        ProjectInitializationService().initialize(link, name="Game")


def test_init_dry_run_is_deterministic_and_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "game"
    service = ProjectInitializationService()

    first = service.initialize(target, name="Meu Jogo", dry_run=True)
    second = service.initialize(target, name="Meu Jogo", dry_run=True)

    assert first == second
    assert first.dry_run is True
    assert first.state == "planned"
    assert not target.exists()


def test_init_human_output_and_non_interactive_mode(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["init", str(tmp_path / "game"), "--name", "CLI Game", "--non-interactive"],
    )

    assert result.exit_code == 0
    assert "LudoWright project created." in result.stdout
    assert "ProjectId: cli-game" in result.stdout


def test_init_json_output_uses_published_envelope_and_dry_run(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "init",
            str(tmp_path / "game"),
            "--name",
            "CLI Game",
            "--template",
            "minimal",
            "--non-interactive",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "init"
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["template"] == {"id": "minimal", "version": 1}
    assert not (tmp_path / "game").exists()


def test_init_json_conflict_has_semantic_error_envelope(tmp_path: Path) -> None:
    target = tmp_path / "game"
    target.mkdir()
    (target / "existing.txt").write_text("keep", encoding="utf-8")

    result = runner.invoke(
        app,
        ["--json", "init", str(target), "--name", "Game", "--non-interactive"],
    )

    assert result.exit_code == 5
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "conflict"


def test_init_rolls_back_after_intermediate_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "game"

    def fail_state_store(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated state-store failure")

    monkeypatch.setattr(initialization, "StateStore", fail_state_store)

    with pytest.raises(ProjectInitializationFailureError) as error:
        ProjectInitializationService().initialize(target, name="Game")

    assert isinstance(error.value.__cause__, RuntimeError)
    assert not target.joinpath(*PROJECT_MARKER.parts).exists()
    assert not target.joinpath(*DEFAULT_EVENT_LOG_PATH.parts).exists()
    assert not target.exists()


def test_init_concurrent_calls_publish_at_most_one_project(tmp_path: Path) -> None:
    target = tmp_path / "game"

    def initialize() -> str:
        try:
            return ProjectInitializationService().initialize(target, name="Game").state
        except ProjectInitializationConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _item: initialize(), range(2)))

    assert outcomes.count("created") == 1
    assert outcomes.count("conflict") == 1


def test_init_template_is_versioned_data_and_paths_are_declared(tmp_path: Path) -> None:
    result = ProjectInitializationService().initialize(
        tmp_path / "game",
        name="Game",
        template_id="minimal",
        dry_run=True,
    )

    assert result.template_id == "minimal"
    assert result.template_version == 1
    assert result.files == tuple(sorted(result.files))
    assert result.directories == tuple(sorted(result.directories))
    assert str(DEFAULT_DEPENDENCY_GRAPH_PATH) in result.files
    assert str(DEFAULT_STATE_STORE_PATH) in result.files
