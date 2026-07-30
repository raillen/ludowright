"""Persistence, rollback, and CLI tests for the asset registry commands."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    AssetRegistryConflictError,
    AssetRegistryService,
)
from ludowright.cli.app import app
from ludowright.contracts import AssetContract, AssetRegistryContract
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
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
    asset_id: str = "prop-arcade-cabinet",
    name: str = "Arcade Cabinet",
    status: str = "planned",
    family: str = "prop",
    subtype: str | None = "container",
    path: str = "imports/asset.json",
) -> RepositoryPath:
    payload = {
        "schema_version": 1,
        "kind": "asset",
        "id": asset_id,
        "name": name,
        "family": family,
        "subtype": subtype,
        "priority": "high",
        "status": status,
        "components": [],
        "variants": [],
        "states": [],
    }
    repository_path = RepositoryPath(path)
    filesystem.write_text(
        repository_path,
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
    )
    return repository_path


def _registry_payload(*assets: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "asset-registry",
        "version": 1,
        "assets": list(assets),
    }


def test_create_persists_yaml_event_and_current_state_store(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    asset_path = _asset(filesystem)

    result = AssetRegistryService(filesystem).create(asset_path)

    assert result.state == "created"
    assert result.registry_version == 1
    assert (tmp_path / "assets/registry.yaml").is_file()
    events = EventLog(filesystem).replay()
    assert [event.event_type.value for event in events.events] == ["asset.created"]
    assert events.events[0].payload["asset_ids"] == ("prop-arcade-cabinet",)
    state = StateStore(filesystem)
    indexed = state.get_entity("asset-registry", "registry")
    assert indexed is not None
    assert indexed.revision == 1
    assert indexed.source_path == RepositoryPath("assets/registry.yaml")
    assert state.schema_version == 2


def test_create_is_deterministic_and_duplicate_is_safe(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    asset_path = _asset(filesystem)
    service = AssetRegistryService(filesystem)

    first = service.create(asset_path).as_data()
    registry_bytes = (tmp_path / "assets/registry.yaml").read_bytes()
    event_bytes = (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes()

    with pytest.raises(AssetRegistryConflictError):
        service.create(asset_path)

    listed = service.list_assets().as_data()
    assert listed["assets"] == first["assets"]
    assert listed["registry_version"] == first["registry_version"]
    assert listed["operation"] == "list"
    assert listed["state"] == "valid"
    assert (tmp_path / "assets/registry.yaml").read_bytes() == registry_bytes
    assert (tmp_path / DEFAULT_EVENT_LOG_PATH.value).read_bytes() == event_bytes


def test_update_and_archive_are_versioned_and_archive_is_idempotent(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    asset_path = _asset(filesystem)
    service = AssetRegistryService(filesystem)
    service.create(asset_path)

    updated_path = _asset(filesystem, name="Updated Cabinet")
    updated = service.update("prop-arcade-cabinet", updated_path)
    assert updated.registry_version == 2
    assert updated.asset is not None
    assert updated.asset.name == "Updated Cabinet"

    cancelled_path = _asset(
        filesystem,
        name="Completed Cabinet",
        status="cancelled",
    )
    service.update("prop-arcade-cabinet", cancelled_path)
    archived = service.archive("prop-arcade-cabinet")
    assert archived.state == "archived"
    assert archived.asset is not None
    assert archived.asset.status == "archived"
    repeat = service.archive("prop-arcade-cabinet")
    assert repeat.state == "unchanged"
    assert repeat.registry_version == archived.registry_version


def test_dry_run_does_not_create_registry_event_or_state(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    asset_path = _asset(filesystem)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    result = AssetRegistryService(filesystem).create(asset_path, dry_run=True)

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert result.state == "planned"
    assert result.dry_run is True
    assert before == after
    assert not (tmp_path / "assets/registry.yaml").exists()
    assert not (tmp_path / ".ludowright/state.sqlite3").exists()


def test_validate_list_inspect_and_empty_registry_are_read_only(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    service = AssetRegistryService(filesystem)

    empty = service.list_assets()
    assert empty.state == "empty"
    assert empty.assets == ()
    assert service.validate().valid is True
    assert not (tmp_path / "assets/registry.yaml").exists()

    path = _asset(filesystem)
    service.create(path)
    assert service.validate("prop-arcade-cabinet").assets[0].id == "prop-arcade-cabinet"
    assert service.inspect("prop-arcade-cabinet").asset is not None


def test_import_and_export_are_batch_contracts_and_non_overwriting(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    incoming = _asset(
        filesystem,
        asset_id="chr-maya",
        name="Maya",
        family="character",
        subtype="humanoid",
        path="imports/batch-asset.json",
    )
    incoming_contract = AssetContract.model_validate(json.loads(filesystem.read_text(incoming)))
    batch_path = RepositoryPath("imports/batch.json")
    filesystem.write_text(
        batch_path,
        json.dumps(_registry_payload(incoming_contract.model_dump(mode="json"))) + "\n",
    )
    service = AssetRegistryService(filesystem)

    imported = service.import_registry(batch_path)
    assert imported.assets[0].id == "chr-maya"
    assert imported.registry_version == 1
    output_path = RepositoryPath("exports/assets.json")
    exported = service.export_registry(output_path)
    assert exported.output_path == output_path.value
    exported_contract = AssetRegistryContract.model_validate(
        json.loads(filesystem.read_text(output_path))
    )
    assert [asset.id for asset in exported_contract.assets] == ["chr-maya"]
    with pytest.raises(AssetRegistryConflictError):
        service.export_registry(output_path)


def test_failed_state_index_rolls_back_registry_and_event_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = _project(tmp_path)
    asset_path = _asset(filesystem)

    def fail_index(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected state-index failure")

    monkeypatch.setattr(StateStore, "index_entity", fail_index)
    with pytest.raises(OSError, match="injected state-index failure"):
        AssetRegistryService(filesystem).create(asset_path)

    assert not (tmp_path / "assets/registry.yaml").exists()
    assert not (tmp_path / DEFAULT_EVENT_LOG_PATH.value).exists()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require elevated Windows rights")
def test_symlinked_input_is_rejected(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    external = tmp_path.parent / "outside-asset.json"
    external.write_text("{}\n", encoding="utf-8")
    imports = tmp_path / "imports"
    imports.mkdir()
    (imports / "link.json").symlink_to(external)

    with pytest.raises(Exception, match="symlink"):
        AssetRegistryService(filesystem).create(RepositoryPath("imports/link.json"))


def test_concurrent_creates_preserve_both_assets(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    first = _asset(filesystem, asset_id="prop-first", path="imports/first.json")
    second = _asset(filesystem, asset_id="prop-second", path="imports/second.json")

    def create(path: RepositoryPath) -> str:
        return AssetRegistryService(ProjectFilesystem(tmp_path)).create(path).state

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = tuple(executor.map(create, (first, second)))

    assert states == ("created", "created")
    assets = AssetRegistryService(filesystem).list_assets().assets
    assert [asset.id for asset in assets] == ["prop-first", "prop-second"]
    assert EventLog(filesystem).replay().last_sequence == 2


def test_cli_human_and_json_surfaces_and_error_envelope(tmp_path: Path) -> None:
    _project(tmp_path)
    _asset(ProjectFilesystem(tmp_path))

    created = runner.invoke(
        app,
        [
            "--json",
            "assets",
            "create",
            str(tmp_path),
            "--input",
            "imports/asset.json",
        ],
    )
    assert created.exit_code == 0
    created_payload = json.loads(created.stdout)
    assert created_payload["command"] == "assets create"
    assert created_payload["ok"] is True
    assert created_payload["data"]["state"] == "created"
    assert created_payload["data"]["state_store_schema_version"] == 2

    human = runner.invoke(app, ["assets", "list", str(tmp_path)])
    assert human.exit_code == 0
    assert "Asset registry" in human.stdout
    assert "prop-arcade-cabinet" in human.stdout

    missing = runner.invoke(
        app,
        ["--json", "assets", "inspect", str(tmp_path), "prop-missing"],
    )
    assert missing.exit_code == 3
    missing_payload = json.loads(missing.stdout)
    assert missing_payload["ok"] is False
    assert missing_payload["error"]["code"] == "resource-not-found"


def test_cli_rejects_traversal_before_reading_input(tmp_path: Path) -> None:
    _project(tmp_path)
    result = runner.invoke(
        app,
        [
            "--json",
            "assets",
            "create",
            str(tmp_path),
            "--input",
            "../asset.json",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid-input"
