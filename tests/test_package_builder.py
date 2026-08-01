"""Focused tests for safe, deterministic package building."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    PackageBuilderConflictError,
    PackageBuilderError,
    PackageBuilderInputError,
    PackageBuilderService,
    PackageManifestService,
)
from ludowright.cli.app import app
from ludowright.contracts import PackageIndexContract
from ludowright.infrastructure import (
    PackageArchiveBuilder,
    PackageArchiveEntry,
    PackageArchiveError,
    ProjectFilesystem,
    RepositoryPath,
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


def _manifest(filesystem: ProjectFilesystem) -> RepositoryPath:
    path = RepositoryPath("manifest.json")
    PackageManifestService(filesystem).create(path, package_id="nightly")
    return path


def test_builder_creates_zip_index_and_fixed_metadata(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / "README.md").write_text("LudoWright\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("Guide\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)

    result = PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release"))

    assert result.state == "created"
    assert result.archive_path.value == "release/nightly.zip"
    assert result.index_path.value == "release/nightly.index.json"
    assert result.archive_size_bytes == (root / result.archive_path.value).stat().st_size
    index = PackageIndexContract.model_validate(
        json.loads((root / result.index_path.value).read_text(encoding="utf-8"))
    )
    assert index.archive_member_count == 5
    assert index.archive_manifest_path == "__ludowright__/package-manifest.json"

    with ZipFile(root / result.archive_path.value) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == sorted(info.filename for info in infos)
        assert all(info.compress_type == ZIP_DEFLATED for info in infos)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert archive.read("README.md") == b"LudoWright\n"
        assert (
            archive.read("__ludowright__/package-manifest.json")
            == (root / manifest_path.value).read_bytes()
        )
        assert (
            archive.read("__ludowright__/package-index.json")
            == (root / result.index_path.value).read_bytes()
        )


def test_builder_is_reproducible_and_exact_repeat_is_unchanged(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / "README.md").write_text("same\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)
    service = PackageBuilderService(filesystem)

    first = service.build(manifest_path, RepositoryPath("release"))
    archive_bytes = (root / first.archive_path.value).read_bytes()
    index_bytes = (root / first.index_path.value).read_bytes()
    second = service.build(manifest_path, RepositoryPath("release"))

    assert second.state == "unchanged"
    assert second.archive_sha256 == hashlib.sha256(archive_bytes).hexdigest()
    assert (root / first.archive_path.value).read_bytes() == archive_bytes
    assert (root / first.index_path.value).read_bytes() == index_bytes


def test_builder_dry_run_does_not_create_directory_or_lock(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    manifest_path = _manifest(filesystem)

    result = PackageBuilderService(filesystem).build(
        manifest_path,
        RepositoryPath("release"),
        dry_run=True,
    )

    assert result.state == "planned"
    assert not (filesystem.root / "release").exists()
    assert not (filesystem.root / ".ludowright" / "locks" / "package-build.lock").exists()


def test_builder_refuses_changed_source_without_writing_outputs(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    source = root / "README.md"
    source.write_text("before\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)
    source.write_text("after\n", encoding="utf-8")

    with pytest.raises(PackageBuilderConflictError, match="changed"):
        PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release"))
    assert not (root / "release").exists()


def test_builder_refuses_missing_source_and_symlink(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    source = root / "README.md"
    source.write_text("content\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)
    source.unlink()

    with pytest.raises(PackageBuilderConflictError, match="missing"):
        PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release"))

    source.write_text("content\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    source.unlink()
    try:
        source.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(PackageBuilderInputError, match="symlink"):
        PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release-2"))


def test_builder_refuses_unsafe_release_directory(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    manifest_path = _manifest(filesystem)

    with pytest.raises(PackageBuilderInputError, match=r"outside \.ludowright"):
        PackageBuilderService(filesystem).build(
            manifest_path,
            RepositoryPath(".ludowright/releases"),
        )


def test_builder_conflict_never_overwrites_existing_target(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / "README.md").write_text("content\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)
    release = root / "release"
    release.mkdir()
    archive = release / "nightly.zip"
    archive.write_bytes(b"user artifact")

    with pytest.raises(PackageBuilderConflictError):
        PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release"))
    assert archive.read_bytes() == b"user artifact"


def test_builder_rolls_back_archive_when_index_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, filesystem = _project(tmp_path)
    manifest_path = _manifest(filesystem)
    original_write = filesystem.write_bytes

    def fail_index(path: RepositoryPath, payload: bytes, **kwargs: object) -> Path:
        if path.name.endswith(".index.json"):
            raise OSError("injected index failure")
        return original_write(path, payload, **kwargs)

    monkeypatch.setattr(filesystem, "write_bytes", fail_index)

    with pytest.raises(PackageBuilderError, match="could not be written") as failure:
        PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release/final"))
    assert isinstance(failure.value.__cause__, OSError)
    assert not (filesystem.root / "release/final").exists()
    assert not (filesystem.root / "release").exists()


def test_builder_rolls_back_when_atomic_writer_fails_after_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, filesystem = _project(tmp_path)
    manifest_path = _manifest(filesystem)
    original_write = filesystem.write_bytes

    def publish_then_fail(path: RepositoryPath, payload: bytes, **kwargs: object) -> Path:
        result = original_write(path, payload, **kwargs)
        if path.name.endswith(".zip"):
            raise OSError("injected post-publish failure")
        return result

    monkeypatch.setattr(filesystem, "write_bytes", publish_then_fail)

    with pytest.raises(PackageBuilderError, match="could not be written"):
        PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release/post-fail"))
    assert not (filesystem.root / "release/post-fail").exists()
    assert not (filesystem.root / "release").exists()


def test_builder_serializes_concurrent_creators(tmp_path: Path) -> None:
    _root, filesystem = _project(tmp_path)
    manifest_path = _manifest(filesystem)

    def build() -> str:
        return (
            PackageBuilderService(filesystem).build(manifest_path, RepositoryPath("release")).state
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = sorted(executor.map(lambda _value: build(), range(2)))

    assert states == ["created", "unchanged"]


def test_archive_builder_rejects_traversal_and_duplicate_entries() -> None:
    builder = PackageArchiveBuilder()

    with pytest.raises(PackageArchiveError):
        builder.build((PackageArchiveEntry(path="../outside.txt", payload=b"x"),))
    with pytest.raises(PackageArchiveError):
        builder.build(
            (
                PackageArchiveEntry(path="same.txt", payload=b"x"),
                PackageArchiveEntry(path="same.txt", payload=b"y"),
            )
        )


def test_package_build_cli_has_human_json_and_error_envelope(tmp_path: Path) -> None:
    root, filesystem = _project(tmp_path)
    (root / "README.md").write_text("content\n", encoding="utf-8")
    manifest_path = _manifest(filesystem)
    human = runner.invoke(
        app,
        ["--no-color", "package", "build", str(root), manifest_path.value, "release"],
    )
    machine = runner.invoke(
        app,
        [
            "--json",
            "package",
            "build",
            str(root),
            manifest_path.value,
            "release-2",
        ],
    )
    error = runner.invoke(
        app,
        ["--json", "package", "build", str(root), "../manifest.json", "release-3"],
    )

    assert human.exit_code == 0
    assert "Package build" in human.stdout
    assert machine.exit_code == 0
    machine_payload = json.loads(machine.stdout)
    assert machine_payload["kind"] == "cli-response"
    assert machine_payload["command"] == "package build"
    assert machine_payload["data"]["archive_path"] == "release-2/nightly.zip"
    assert error.exit_code == 4
    error_payload = json.loads(error.stdout)
    assert error_payload["ok"] is False
    assert error_payload["error"]["code"] == "invalid-input"
