"""Tests for asset decomposition, dependency planning, and guided corrections."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    AssetDecompositionService,
    AssetDecompositionValidationError,
    AssetRegistryConflictError,
    AssetRegistryService,
)
from ludowright.cli.app import app
from ludowright.domain import AssetPriority
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DependencyGraphRepository,
    EventLog,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
)

runner = CliRunner()


def _project(tmp_path: Path) -> ProjectFilesystem:
    marker = tmp_path / ".ludowright" / "project.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(tmp_path)


def _asset(
    filesystem: ProjectFilesystem,
    *,
    asset_id: str,
    name: str,
    family: str,
    subtype: str,
    path: str,
) -> None:
    filesystem.write_text(
        RepositoryPath(path),
        json.dumps(
            {
                "schema_version": 1,
                "kind": "asset",
                "id": asset_id,
                "name": name,
                "family": family,
                "subtype": subtype,
                "priority": "high",
                "status": "planned",
                "components": [],
                "variants": [],
                "states": [],
            },
            sort_keys=True,
        )
        + "\n",
    )
    AssetRegistryService(filesystem).create(RepositoryPath(path))


def _decomposition(
    filesystem: ProjectFilesystem,
    *,
    dependencies: list[dict[str, object]] | None = None,
    path: str = "imports/maya-decomposition.json",
) -> RepositoryPath:
    payload = {
        "schema_version": 1,
        "kind": "asset-decomposition",
        "asset_id": "chr-maya",
        "components": [
            {
                "id": "base-body",
                "name": "Base Body",
                "status": "planned",
                "required": True,
            },
            {
                "id": "winter-coat",
                "name": "Winter Coat",
                "status": "planned",
                "required": False,
                "parent_id": "base-body",
            },
        ],
        "variants": [
            {
                "id": "winter",
                "name": "Winter",
                "status": "planned",
                "required": False,
            }
        ],
        "states": [
            {
                "id": "damaged",
                "name": "Damaged",
                "status": "planned",
                "required": False,
            }
        ],
        "dependencies": dependencies or [],
    }
    filesystem.write_text(RepositoryPath(path), json.dumps(payload, sort_keys=True) + "\n")
    return RepositoryPath(path)


def _prepared_project(tmp_path: Path) -> tuple[ProjectFilesystem, RepositoryPath]:
    filesystem = _project(tmp_path)
    _asset(
        filesystem,
        asset_id="prop-arcade-cabinet",
        name="Arcade Cabinet",
        family="prop",
        subtype="container",
        path="imports/cabinet.json",
    )
    _asset(
        filesystem,
        asset_id="chr-maya",
        name="Maya",
        family="character",
        subtype="humanoid",
        path="imports/maya.json",
    )
    decomposition = _decomposition(
        filesystem,
        dependencies=[{"depends_on": "prop-arcade-cabinet", "invalidation_mode": "stale"}],
    )
    return filesystem, decomposition


def test_inspection_is_read_only_and_has_data_defined_recommendation(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _asset(
        filesystem,
        asset_id="chr-maya",
        name="Maya",
        family="character",
        subtype="humanoid",
        path="imports/maya.json",
    )
    event_before = (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes()
    state_before = (tmp_path / ".ludowright/state.sqlite3").read_bytes()

    result = AssetDecompositionService(filesystem).decompose("chr-maya")

    assert result.report.state == "current"
    assert result.report.capture_profile.profile_id == "humanoid-character"
    assert result.report.capture_profile.subject_modes == ("asset",)
    assert not (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).exists()
    assert (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes() == event_before
    assert (tmp_path / ".ludowright/state.sqlite3").read_bytes() == state_before


def test_decomposition_updates_registry_graph_event_and_state_store(tmp_path: Path) -> None:
    filesystem, input_path = _prepared_project(tmp_path)

    result = AssetDecompositionService(filesystem).decompose(
        "chr-maya",
        input_path=input_path,
    )

    assert result.report.state == "updated"
    assert result.report.registry_version == 3
    assert result.report.capture_profile.profile_id == "humanoid-character"
    assert result.report.capture_profile.subject_modes == (
        "asset",
        "components",
        "variants",
        "states",
    )
    assert [item.id for item in result.report.asset.components] == [
        "base-body",
        "winter-coat",
    ]
    graph = DependencyGraphRepository(filesystem).load().graph
    assert {node.key.id for node in graph.nodes} == {"chr-maya", "prop-arcade-cabinet"}
    assert graph.edges[0].source.id == "prop-arcade-cabinet"
    assert graph.edges[0].target.id == "chr-maya"
    assert [event.event_type.value for event in EventLog(filesystem).replay().events] == [
        "asset.created",
        "asset.created",
        "asset.decomposed",
    ]
    event = EventLog(filesystem).replay().events[-1]
    assert event.payload["dependency_ids"] == ("prop-arcade-cabinet",)
    assert StateStore(filesystem).schema_version == 2


def test_repeating_same_decomposition_is_idempotent(tmp_path: Path) -> None:
    filesystem, input_path = _prepared_project(tmp_path)
    service = AssetDecompositionService(filesystem)
    service.decompose("chr-maya", input_path=input_path)
    registry_before = (tmp_path / "assets/registry.yaml").read_bytes()
    graph_before = (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).read_bytes()
    event_before = (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes()

    repeated = service.decompose("chr-maya", input_path=input_path)

    assert repeated.report.state == "current"
    assert repeated.report.registry_version == 3
    assert (tmp_path / "assets/registry.yaml").read_bytes() == registry_before
    assert (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).read_bytes() == graph_before
    assert (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes() == event_before


def test_dry_run_does_not_write_registry_graph_event_or_state(tmp_path: Path) -> None:
    filesystem, input_path = _prepared_project(tmp_path)
    registry_before = (tmp_path / "assets/registry.yaml").read_bytes()
    event_before = (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes()
    state_before = (tmp_path / ".ludowright/state.sqlite3").read_bytes()

    result = AssetDecompositionService(filesystem).decompose(
        "chr-maya",
        input_path=input_path,
        dry_run=True,
    )

    assert result.report.state == "planned"
    assert result.report.dry_run is True
    assert (tmp_path / "assets/registry.yaml").read_bytes() == registry_before
    assert (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes() == event_before
    assert not (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).exists()
    assert (tmp_path / ".ludowright/state.sqlite3").read_bytes() == state_before


def test_unknown_dependency_returns_guided_error_without_mutation(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    _asset(
        filesystem,
        asset_id="chr-maya",
        name="Maya",
        family="character",
        subtype="humanoid",
        path="imports/maya.json",
    )
    input_path = _decomposition(
        filesystem,
        dependencies=[{"depends_on": "prop-missing", "invalidation_mode": "stale"}],
    )
    before = (tmp_path / "assets/registry.yaml").read_bytes()

    with pytest.raises(AssetDecompositionValidationError) as caught:
        AssetDecompositionService(filesystem).decompose(
            "chr-maya",
            input_path=input_path,
        )

    assert caught.value.report.state == "invalid"
    assert caught.value.report.corrections[0].code == "unknown-dependency"
    assert (tmp_path / "assets/registry.yaml").read_bytes() == before
    assert not (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).exists()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require elevated Windows rights")
def test_symlinked_decomposition_input_is_rejected(tmp_path: Path) -> None:
    filesystem, input_path = _prepared_project(tmp_path)
    external = tmp_path.parent / "outside-decomposition.json"
    external.write_bytes((tmp_path / input_path.value).read_bytes())
    link = tmp_path / "imports" / "decomposition-link.json"
    link.symlink_to(external)

    with pytest.raises(Exception, match="symlink"):
        AssetDecompositionService(filesystem).decompose(
            "chr-maya",
            input_path=RepositoryPath("imports/decomposition-link.json"),
        )


def test_graph_is_restored_when_registry_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem, input_path = _prepared_project(tmp_path)
    event_before = (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes()

    def fail_replace(*_args: object, **_kwargs: object) -> object:
        raise OSError("injected registry failure")

    monkeypatch.setattr(AssetRegistryService, "replace_contract", fail_replace)

    with pytest.raises(OSError, match="injected registry failure"):
        AssetDecompositionService(filesystem).decompose(
            "chr-maya",
            input_path=input_path,
        )

    assert not (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).exists()
    assert (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes() == event_before


def test_concurrent_registry_change_fails_closed_and_restores_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem, input_path = _prepared_project(tmp_path)
    original = AssetRegistryService.replace_contract
    changed = False

    def replace_with_concurrent_change(
        service: AssetRegistryService,
        asset: object,
        **kwargs: object,
    ) -> object:
        nonlocal changed
        if not changed and kwargs.get("operation") == "decompose":
            changed = True
            current = service.inspect("chr-maya").asset
            assert current is not None
            original(
                service,
                current.model_copy(update={"priority": AssetPriority.NORMAL}),
            )
        return original(service, asset, **kwargs)

    monkeypatch.setattr(AssetRegistryService, "replace_contract", replace_with_concurrent_change)

    with pytest.raises(AssetRegistryConflictError):
        AssetDecompositionService(filesystem).decompose(
            "chr-maya",
            input_path=input_path,
        )

    assert not (tmp_path / DEFAULT_DEPENDENCY_GRAPH_PATH.value).exists()
    assert AssetRegistryService(filesystem).inspect("chr-maya").asset is not None
    assert (
        AssetRegistryService(filesystem).inspect("chr-maya").asset.priority is AssetPriority.NORMAL
    )


def test_concurrent_same_decomposition_serializes_safely(tmp_path: Path) -> None:
    filesystem, input_path = _prepared_project(tmp_path)

    def apply(_: int) -> str:
        return (
            AssetDecompositionService(ProjectFilesystem(tmp_path))
            .decompose(
                "chr-maya",
                input_path=input_path,
            )
            .report.state
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = tuple(executor.map(apply, (1, 2)))

    assert sorted(states) == ["current", "updated"]
    assert len(EventLog(filesystem).replay().events) == 3
    assert DependencyGraphRepository(filesystem).load().graph.edges


def test_cli_supports_inspection_human_json_and_error_envelope(tmp_path: Path) -> None:
    _filesystem, input_path = _prepared_project(tmp_path)

    human = runner.invoke(app, ["assets", "decompose", str(tmp_path), "chr-maya"])
    assert human.exit_code == 0
    assert "Asset decomposition" in human.stdout
    assert "humanoid-character" in human.stdout

    planned = runner.invoke(
        app,
        [
            "--json",
            "assets",
            "decompose",
            str(tmp_path),
            "chr-maya",
            "--input",
            input_path.value,
            "--dry-run",
        ],
    )
    assert planned.exit_code == 0
    assert json.loads(planned.stdout)["data"]["state"] == "planned"

    invalid = runner.invoke(
        app,
        [
            "--json",
            "assets",
            "decompose",
            str(tmp_path),
            "chr-maya",
            "--input",
            "../unsafe.json",
        ],
    )
    assert invalid.exit_code == 4
    payload = json.loads(invalid.stdout)
    assert payload["error"]["code"] == "invalid-input"
