"""Focused tests for deterministic, safe package manifest generation."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    PackageManifestConflictError,
    PackageManifestError,
    PackageManifestInputError,
    PackageManifestService,
)
from ludowright.cli.app import app
from ludowright.contracts import PackageManifestContract
from ludowright.domain import DependencyGraph
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    DependencyGraphRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    UnsafeProjectPathError,
)

FIXTURE = Path("tests/fixtures/contracts/v1/project.json")
runner = CliRunner()


def _project(tmp_path: Path) -> tuple[Path, ProjectFilesystem]:
    root = tmp_path / "project"
    root.mkdir()
    marker = root / ".ludowright" / "project.json"
    marker.parent.mkdir()
    marker.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return root, ProjectFilesystem(root)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_minimal_manifest_is_created_with_sorted_checksums(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / "README.md").write_text("LudoWright\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("Guide\n", encoding="utf-8")

    result = PackageManifestService(filesystem).create(RepositoryPath("release/manifest.json"))

    assert result.state == "created"
    assert result.manifest.project_id == "locadora-2000"
    assert [item.path for item in result.manifest.included_files] == [
        ".ludowright/project.json",
        "README.md",
        "docs/guide.md",
    ]
    readme = next(item for item in result.manifest.included_files if item.path == "README.md")
    assert readme.sha256 == _sha256(root / "README.md")
    assert result.manifest.manifest_path == "release/manifest.json"
    assert "release/manifest.json" not in {item.path for item in result.manifest.included_files}
    assert (root / "release/manifest.json").is_file()
    PackageManifestContract.model_validate(json.loads((root / "release/manifest.json").read_text()))


def test_manifest_is_deterministic_and_exact_repeat_is_unchanged(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / "README.md").write_text("same\n", encoding="utf-8")
    service = PackageManifestService(filesystem)

    first = service.create(RepositoryPath("release/manifest.json"), package_id="nightly")
    payload = (root / "release/manifest.json").read_bytes()
    second = service.create(RepositoryPath("release/manifest.json"), package_id="nightly")

    assert first.manifest == second.manifest
    assert second.state == "unchanged"
    assert (root / "release/manifest.json").read_bytes() == payload


def test_manifest_refuses_different_existing_output(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    output = root / "release" / "manifest.json"
    output.parent.mkdir()
    output.write_text("not a manifest\n", encoding="utf-8")

    with pytest.raises(PackageManifestConflictError):
        PackageManifestService(filesystem).create(RepositoryPath("release/manifest.json"))

    assert output.read_text(encoding="utf-8") == "not a manifest\n"


def test_dry_run_does_not_create_output_or_lock(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)

    result = PackageManifestService(filesystem).create(
        RepositoryPath("release/manifest.json"),
        dry_run=True,
    )

    assert result.state == "planned"
    assert not (filesystem.root / "release/manifest.json").exists()
    assert not (filesystem.root / ".ludowright" / "locks" / "package-manifest.lock").exists()


def test_missing_and_excluded_sources_are_explicit(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "cache.json").write_text("{}", encoding="utf-8")
    StateStore(filesystem)
    (root / ".ludowright" / "state.sqlite3-wal").write_bytes(b"derived sidecar")

    result = PackageManifestService(filesystem).create(RepositoryPath("manifest.json"))

    assert "release/manifest.json" not in {item.path for item in result.manifest.included_files}
    assert any(
        item.path == ".ludowright/state.sqlite3" and item.reason == "derived-state"
        for item in result.manifest.excluded
    )
    assert any(
        item.path == ".ludowright/state.sqlite3-wal" and item.reason == "derived-state"
        for item in result.manifest.excluded
    )
    assert any(
        item.path == ".pytest_cache" and item.reason == "tool-cache"
        for item in result.manifest.excluded
    )
    assert ".ludowright/events.jsonl" in {item.path for item in result.manifest.missing}
    assert all(item.path != ".pytest_cache/cache.json" for item in result.manifest.included_files)


def test_event_graph_and_state_versions_are_reported(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"")
    DependencyGraphRepository(filesystem).create(DependencyGraph.empty())
    StateStore(filesystem)

    manifest = PackageManifestService(filesystem).create(RepositoryPath("manifest.json")).manifest
    versions = {item.kind: item for item in manifest.source_versions}

    assert versions["event-log"].revision == 0
    assert versions["dependency-graph"].revision == 1
    assert versions["state-store"].schema_version == 2
    assert versions["state-store"].sha256 is None
    assert DEFAULT_EVENT_LOG_PATH.value in {item.path for item in manifest.included_files}
    assert DEFAULT_DEPENDENCY_GRAPH_PATH.value in {item.path for item in manifest.included_files}
    assert DEFAULT_STATE_STORE_PATH.value not in {item.path for item in manifest.included_files}


def test_visual_reference_provenance_and_license_are_published(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    reference = root / ".ludowright" / "visual-references" / "ref-maya-identity.json"
    reference.parent.mkdir()
    reference.write_text(
        Path("tests/fixtures/contracts/v1/visual-reference.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    manifest = PackageManifestService(filesystem).create(RepositoryPath("manifest.json")).manifest

    assert len(manifest.provenance) == 1
    provenance = manifest.provenance[0]
    assert provenance.reference_id == "ref-maya-identity"
    assert provenance.source_uri == "https://example.com/maya-reference.png"
    assert provenance.license_label == "Licensed Reference"
    assert len(manifest.licenses) == 1
    assert manifest.licenses[0].label == "Licensed Reference"
    assert manifest.licenses[0].reference_ids == ("ref-maya-identity",)


def test_write_failure_leaves_no_apparently_valid_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, filesystem = _project(tmp_path)

    def fail_write(*_args: object, **_kwargs: object) -> Path:
        raise OSError("injected write failure")

    monkeypatch.setattr(filesystem, "write_bytes", fail_write)

    with pytest.raises(PackageManifestError, match="could not be written"):
        PackageManifestService(filesystem).create(RepositoryPath("manifest.json"))
    assert not (filesystem.root / "manifest.json").exists()


def test_write_failure_cleans_output_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, filesystem = _project(tmp_path)

    def fail_write(*_args: object, **_kwargs: object) -> Path:
        filesystem.ensure_directory(RepositoryPath("release/failed"))
        raise OSError("injected write failure")

    monkeypatch.setattr(filesystem, "write_bytes", fail_write)

    with pytest.raises(PackageManifestError, match="could not be written"):
        PackageManifestService(filesystem).create(RepositoryPath("release/failed/manifest.json"))
    assert not (filesystem.root / "release/failed/manifest.json").exists()
    assert not (filesystem.root / "release/failed").exists()
    assert not (filesystem.root / "release").exists()


def test_symlink_is_rejected_without_following_it(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = root / "linked.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(PackageManifestInputError, match="symlink"):
        PackageManifestService(filesystem).create(RepositoryPath("manifest.json"))
    assert not (root / "manifest.json").exists()


def test_manifest_output_path_rejects_traversal_and_canonical_sources(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    service = PackageManifestService(filesystem)

    with pytest.raises(UnsafeProjectPathError):
        service.create(RepositoryPath("../manifest.json"))
    with pytest.raises(PackageManifestInputError):
        service.create(DEFAULT_EVENT_LOG_PATH)


def test_concurrent_creation_is_create_or_unchanged(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)

    def create() -> str:
        return (
            PackageManifestService(filesystem).create(RepositoryPath("release/manifest.json")).state
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = sorted(executor.map(lambda _value: create(), range(2)))

    assert states == ["created", "unchanged"]


def test_cli_has_human_json_and_error_surfaces(tmp_path: Path) -> None:
    root, _filesystem = _project(tmp_path)
    human = runner.invoke(app, ["--no-color", "package", "manifest", str(root), "manifest.json"])
    machine = runner.invoke(
        app,
        [
            "--json",
            "package",
            "manifest",
            str(root),
            "release/manifest.json",
            "--package-id",
            "nightly",
        ],
    )
    error = runner.invoke(
        app,
        ["--json", "package", "manifest", str(root), "../unsafe.json"],
    )

    assert human.exit_code == 0
    assert "Package manifest" in human.stdout
    assert machine.exit_code == 0
    machine_payload = json.loads(machine.stdout)
    assert machine_payload["kind"] == "cli-response"
    assert machine_payload["command"] == "package manifest"
    assert machine_payload["data"]["package_id"] == "nightly"
    assert error.exit_code == 4
    error_payload = json.loads(error.stdout)
    assert error_payload["ok"] is False
    assert error_payload["error"]["code"] == "invalid-input"


def test_package_manifest_path_contract_is_portable() -> None:
    manifest = PackageManifestContract(
        package_id="default",
        project_id="locadora-2000",
        manifest_path="Release/Manifest.json",
        included_files=(),
    )

    assert manifest.manifest_path == "Release/Manifest.json"
    with pytest.raises(ValueError):
        PackageManifestContract(
            package_id="default",
            project_id="locadora-2000",
            manifest_path="../manifest.json",
        )
