"""Focused tests for local release verification and checksum manifests."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from ludowright.application import (
    PackageBuilderService,
    PackageManifestService,
    ReleaseVerificationService,
)
from ludowright.cli.app import app
from ludowright.contracts import (
    AssetRegistryContract,
    ProjectContract,
    ReleaseManifestContract,
)
from ludowright.domain import (
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_DOCUMENT_DIRECTORY,
    DEFAULT_EVENT_LOG_PATH,
    DependencyGraphRepository,
    EventLog,
    IndexedEntity,
    JsonDocumentRepository,
    PackageFileScanner,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    YamlDocumentRepository,
)
from ludowright.infrastructure.filesystem import PROJECT_MARKER

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
    project_repository = JsonDocumentRepository(filesystem, PROJECT_MARKER, ProjectContract)
    project_payload = project_repository.canonical_bytes(project)
    filesystem.write_bytes(PROJECT_MARKER, project_payload)
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
            source_digest=hashlib.sha256(project_payload).hexdigest(),
            revision=1,
            status="active",
            updated_at=timestamp,
        )
    )

    filesystem.ensure_directory(DEFAULT_DOCUMENT_DIRECTORY)
    filesystem.write_text(
        DEFAULT_DOCUMENT_DIRECTORY.child("overview.md"),
        "# Project overview\n",
    )
    YamlDocumentRepository(
        filesystem,
        RepositoryPath("assets/registry.yaml"),
        AssetRegistryContract,
    ).create(AssetRegistryContract())
    manifest_path = RepositoryPath("release/package-manifest.json")
    PackageManifestService(filesystem).create(manifest_path, package_id="nightly")
    PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release"))
    return root, filesystem


def test_release_verification_allows_warnings_and_creates_checksum_manifest(
    tmp_path: Path,
) -> None:
    root, filesystem = _project(tmp_path)

    result = ReleaseVerificationService(filesystem).verify(
        RepositoryPath("release"),
        package_id="nightly",
        allow_warnings=True,
    )

    assert result.report.state == "ready-with-warnings"
    assert result.report.valid is True
    assert result.report.manifest_state == "created"
    manifest_path = root / "release/nightly.release.json"
    assert manifest_path.is_file()
    manifest = ReleaseManifestContract.model_validate(json.loads(manifest_path.read_text()))
    assert manifest.integrity == "sha256"
    assert [artifact.kind for artifact in manifest.artifacts] == [
        "package-manifest",
        "package-index",
        "package-archive",
    ]
    assert all(
        artifact.sha256 == hashlib.sha256((root / artifact.path).read_bytes()).hexdigest()
        for artifact in manifest.artifacts
    )


def test_release_verification_blocks_warnings_by_default_without_writing(
    tmp_path: Path,
) -> None:
    _root, filesystem = _project(tmp_path)

    result = ReleaseVerificationService(filesystem).verify(RepositoryPath("release"))

    assert result.report.state == "blocked"
    assert result.report.valid is False
    assert result.report.manifest_state == "not-created"
    assert not (filesystem.root / "release/nightly.release.json").exists()
    assert result.report.warning_policy == "block"


def test_release_verification_dry_run_is_read_only_and_deterministic(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    before = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }

    first = ReleaseVerificationService(filesystem).verify(
        RepositoryPath("release"),
        allow_warnings=True,
        dry_run=True,
    )
    second = ReleaseVerificationService(filesystem).verify(
        RepositoryPath("release"),
        allow_warnings=True,
        dry_run=True,
    )

    assert first.report == second.report
    assert first.report.manifest_state == "planned"
    assert not (root / "release/nightly.release.json").exists()
    after = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_release_verification_repeat_is_unchanged(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    service = ReleaseVerificationService(filesystem)

    first = service.verify(RepositoryPath("release"), allow_warnings=True)
    payload = (filesystem.root / "release/nightly.release.json").read_bytes()
    second = service.verify(RepositoryPath("release"), allow_warnings=True)

    assert first.report.manifest_state == "created"
    assert second.report.manifest_state == "unchanged"
    assert second.report.release_manifest == first.report.release_manifest
    assert (filesystem.root / "release/nightly.release.json").read_bytes() == payload


def test_release_verification_cli_json_check_returns_error_envelope(tmp_path: Path) -> None:
    root, _filesystem = _project(tmp_path)

    result = runner.invoke(
        app,
        ["--json", "release", "verify", str(root), "release", "--check"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["kind"] == "cli-response"
    assert payload["command"] == "release verify"
    assert payload["ok"] is False
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["warning_policy"] == "block"


def test_release_verification_cli_human_output(tmp_path: Path) -> None:
    root, _filesystem = _project(tmp_path)

    result = runner.invoke(
        app,
        [
            "--no-color",
            "release",
            "verify",
            str(root),
            "release",
            "--allow-warnings",
        ],
    )

    assert result.exit_code == 0
    assert "LudoWright release verification" in result.stdout
    assert "package-checksums" in result.stdout
    assert "ready-with-warnings" in result.stdout


def test_release_verification_rejects_tampered_archive(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    archive = root / "release/nightly.zip"
    archive.write_bytes(b"not-a-zip")

    result = ReleaseVerificationService(filesystem).verify(
        RepositoryPath("release"),
        allow_warnings=True,
    )

    assert result.report.state == "blocked"
    assert any(
        gate.code == "package-archive" and gate.state == "failed" for gate in result.report.gates
    )
    assert not (root / "release/nightly.release.json").exists()


def test_release_verification_rejects_release_manifest_self_inclusion(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    package_manifest_path = root / "release/package-manifest.json"
    package_manifest = json.loads(package_manifest_path.read_text())
    package_manifest["included_files"].append(
        {
            "path": "release/nightly.release.json",
            "size_bytes": 1,
            "sha256": "0" * 64,
        }
    )
    package_manifest["included_files"].sort(key=lambda item: item["path"])
    package_manifest_path.write_text(json.dumps(package_manifest, indent=2) + "\n")

    result = ReleaseVerificationService(filesystem).verify(
        RepositoryPath("release"),
        allow_warnings=True,
    )

    assert result.report.state == "blocked"
    assert any(
        gate.code == "package-manifest" and gate.state == "failed" for gate in result.report.gates
    )


def test_release_verification_rejects_ambiguous_release_without_package_id(
    tmp_path: Path,
) -> None:
    root, filesystem = _project(tmp_path)
    second_manifest = RepositoryPath("release/second-manifest.json")
    PackageManifestService(filesystem).create(second_manifest, package_id="second")
    PackageBuilderService(filesystem).build(second_manifest, RepositoryPath("release"))

    result = runner.invoke(
        app,
        ["--json", "release", "verify", str(root), "release"],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid-input"


def test_release_verification_serializes_concurrent_creators(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)

    def verify() -> str:
        return (
            ReleaseVerificationService(filesystem)
            .verify(
                RepositoryPath("release"),
                allow_warnings=True,
            )
            .report.manifest_state
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = sorted(executor.map(lambda _value: verify(), range(2)))

    assert states == ["created", "unchanged"]


def test_release_verification_rejects_unsafe_release_path(tmp_path: Path) -> None:
    root, _filesystem = _project(tmp_path)

    result = runner.invoke(
        app,
        ["--json", "release", "verify", str(root), "../release"],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid-input"


def test_release_verification_uses_bounded_safe_scanner(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    scanner = PackageFileScanner(filesystem)

    assert "release/nightly.zip" in scanner.list_paths(suffix=".zip")


__all__ = []
