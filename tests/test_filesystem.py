"""Tests for project-root discovery, safe paths, atomic writes, and locks."""

from __future__ import annotations

import os
import stat
import string
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

import ludowright.infrastructure.filesystem as filesystem_module
from ludowright.infrastructure import (
    LOCK_DIRECTORY,
    PROJECT_MARKER,
    ProjectFilesystem,
    ProjectFilesystemError,
    ProjectLockOwnershipError,
    ProjectLockTimeoutError,
    ProjectRootNotFoundError,
    RepositoryPath,
    UnsafeProjectPathError,
)


def make_filesystem(tmp_path: Path) -> ProjectFilesystem:
    root = tmp_path / "project"
    root.mkdir()
    return ProjectFilesystem(root)


def create_marker(root: Path, content: str = "{}\n") -> Path:
    marker = root.joinpath(*PROJECT_MARKER.parts)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(content, encoding="utf-8")
    return marker


@pytest.mark.parametrize(
    "value",
    [
        ".ludowright/project.json",
        "assets/chr-maya/spec.json",
        "data/cache_file-v1.json",
        "schemas/v1/project.schema.json",
    ],
)
def test_repository_path_accepts_canonical_portable_values(value: str) -> None:
    path = RepositoryPath(value)

    assert str(path) == value
    assert path.parts == tuple(value.split("/"))


@pytest.mark.parametrize(
    "value",
    [
        "",
        " surrounding ",
        "/absolute",
        "../outside",
        "assets/../outside",
        "assets/./item",
        "assets//item",
        "assets\\item",
        "Assets/item",
        "assets/item name",
        "assets/ação",
        "assets/trailing.",
        "con.json",
        "assets/lpt1.txt",
        "a" * 1_025,
        "assets/" + "a" * 256,
    ],
)
def test_repository_path_rejects_unsafe_or_noncanonical_values(value: str) -> None:
    with pytest.raises(UnsafeProjectPathError):
        RepositoryPath(value)


def test_repository_path_parent_and_child_preserve_canonical_form() -> None:
    base = RepositoryPath("assets/chr-maya")

    child = base.child("references", "front.png")

    assert child == RepositoryPath("assets/chr-maya/references/front.png")
    assert child.parent == RepositoryPath("assets/chr-maya/references")
    assert child.name == "front.png"
    assert RepositoryPath("root.json").parent is None


_SAFE_SEGMENT_ALPHABET = string.ascii_lowercase + string.digits + "-_"


@given(
    st.lists(
        st.text(alphabet=_SAFE_SEGMENT_ALPHABET, min_size=1, max_size=20),
        min_size=1,
        max_size=6,
    )
)
def test_repository_path_round_trip_for_safe_segments(segments: list[str]) -> None:
    assume(
        all(segment.split(".", maxsplit=1)[0] not in {"con", "nul", "prn"} for segment in segments)
    )
    value = "/".join(segments)

    path = RepositoryPath(value)

    assert RepositoryPath.parse(path.value) == path
    assert path.parts == tuple(segments)


def test_filesystem_requires_existing_directory_root(tmp_path: Path) -> None:
    with pytest.raises(ProjectFilesystemError, match="does not exist"):
        ProjectFilesystem(tmp_path / "missing")

    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectFilesystemError, match="not a directory"):
        ProjectFilesystem(file_path)


def test_discover_finds_nearest_project_marker(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    nested = inner / "assets" / "characters"
    nested.mkdir(parents=True)
    create_marker(outer)
    create_marker(inner)

    discovered = ProjectFilesystem.discover(nested)

    assert discovered.root == inner.resolve()


def test_discover_accepts_file_start_and_rejects_missing_marker(tmp_path: Path) -> None:
    root = tmp_path / "project"
    source = root / "assets" / "item.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    create_marker(root)

    assert ProjectFilesystem.discover(source).root == root.resolve()

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    with pytest.raises(ProjectRootNotFoundError):
        ProjectFilesystem.discover(unrelated)


def test_discover_rejects_symlink_marker(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    marker = root.joinpath(*PROJECT_MARKER.parts)
    marker.parent.mkdir()
    target = tmp_path / "marker.json"
    target.write_text("{}", encoding="utf-8")
    try:
        marker.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(UnsafeProjectPathError, match="marker"):
        ProjectFilesystem.discover(root)


def test_ensure_directory_creates_safe_tree_idempotently(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    path = RepositoryPath("assets/characters/chr-maya")

    created = filesystem.ensure_directory(path)

    assert created.is_dir()
    assert filesystem.ensure_directory(path) == created


def test_ensure_directory_rejects_file_ancestor(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    (filesystem.root / "assets").write_text("not a directory", encoding="utf-8")

    with pytest.raises(ProjectFilesystemError, match="non-directory"):
        filesystem.ensure_directory(RepositoryPath("assets/characters"))


def test_resolve_and_writes_reject_symlink_ancestor(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    assets = filesystem.root / "assets"
    assets.mkdir()
    link = assets / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    unsafe = RepositoryPath("assets/escape/payload.json")
    with pytest.raises(UnsafeProjectPathError, match="symlink"):
        filesystem.resolve(unsafe)
    with pytest.raises(UnsafeProjectPathError, match="symlink"):
        filesystem.write_text(unsafe, "{}\n")

    assert not (outside / "payload.json").exists()


def test_atomic_write_and_bounded_read_round_trip(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    path = RepositoryPath("data/project.json")

    written = filesystem.write_text(path, '{"version":1}\n')

    assert written == filesystem.root / "data" / "project.json"
    assert filesystem.read_text(path, max_bytes=1_024) == '{"version":1}\n'
    assert not list(written.parent.glob(".project.json.*.tmp"))


def test_atomic_write_preserves_existing_file_mode(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX mode preservation is not portable to Windows")
    filesystem = make_filesystem(tmp_path)
    path = RepositoryPath("data/private.json")
    target = filesystem.write_text(path, "old\n", mode=0o600)

    filesystem.write_text(path, "new\n")

    assert stat.S_IMODE(os.lstat(target).st_mode) == 0o600


def test_atomic_write_failure_preserves_previous_file_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = make_filesystem(tmp_path)
    path = RepositoryPath("data/project.json")
    target = filesystem.write_text(path, "old\n")

    def fail_replace(source: Path | str, destination: Path | str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(filesystem_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        filesystem.write_text(path, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert not list(target.parent.glob(".project.json.*.tmp"))


def test_atomic_write_rejects_symlink_target(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("outside\n", encoding="utf-8")
    target = filesystem.root / "target.json"
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(UnsafeProjectPathError, match="symlink"):
        filesystem.write_text(RepositoryPath("target.json"), "inside\n")

    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_bounded_read_rejects_oversized_file(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    path = RepositoryPath("data/large.bin")
    filesystem.write_bytes(path, b"12345")

    with pytest.raises(ProjectFilesystemError, match="read limit"):
        filesystem.read_bytes(path, max_bytes=4)
    with pytest.raises(ValueError, match="non-negative"):
        filesystem.read_bytes(path, max_bytes=-1)


def test_exclusive_lock_writes_metadata_and_releases(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)

    with filesystem.lock("project-write") as lock:
        assert lock.locked is True
        assert lock.metadata is not None
        assert lock.metadata.name == "project-write"
        assert lock.metadata.pid == os.getpid()
        assert filesystem.read_lock_metadata("project-write") == lock.metadata

    assert lock.locked is False
    assert filesystem.read_lock_metadata("project-write") is None


def test_second_lock_times_out_until_first_releases(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    first = filesystem.lock("project-write").acquire()
    try:
        with pytest.raises(ProjectLockTimeoutError, match="timed out"):
            filesystem.lock("project-write", timeout=0).acquire()
    finally:
        first.release()

    with filesystem.lock("project-write") as acquired:
        assert acquired.locked is True


def test_lock_release_detects_changed_ownership_token(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    lock = filesystem.lock("project-write").acquire()
    lock_path = filesystem.root.joinpath(*LOCK_DIRECTORY.parts, "project-write.lock")
    original = lock.metadata
    assert original is not None
    lock_path.write_text(
        original.to_json().decode().replace(original.token, "different-token"),
        encoding="utf-8",
    )

    with pytest.raises(ProjectLockOwnershipError, match="ownership token"):
        lock.release()

    lock_path.unlink()


def test_malformed_lock_metadata_is_rejected(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path)
    lock_directory = filesystem.ensure_directory(LOCK_DIRECTORY)
    (lock_directory / "broken.lock").write_text("not-json", encoding="utf-8")

    with pytest.raises(ProjectLockOwnershipError, match="malformed"):
        filesystem.read_lock_metadata("broken")


@pytest.mark.parametrize("name", ["", "Project", "project_write", "project.write", "ação"])
def test_invalid_lock_names_are_rejected(tmp_path: Path, name: str) -> None:
    filesystem = make_filesystem(tmp_path)

    with pytest.raises(ProjectFilesystemError, match="lock name"):
        filesystem.lock(name)


@pytest.mark.parametrize(
    ("timeout", "poll_interval"),
    [(-1, 0.05), (float("inf"), 0.05), (0, 0), (0, -1)],
)
def test_invalid_lock_timing_is_rejected(
    tmp_path: Path,
    timeout: float,
    poll_interval: float,
) -> None:
    filesystem = make_filesystem(tmp_path)

    with pytest.raises(ValueError):
        filesystem.lock(
            "project-write",
            timeout=timeout,
            poll_interval=poll_interval,
        )
