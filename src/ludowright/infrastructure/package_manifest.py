"""Bounded, symlink-free filesystem scanning for package manifests."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ludowright.contracts.package_manifest import validate_package_path
from ludowright.infrastructure.filesystem import ProjectFilesystem

PACKAGE_MANIFEST_MAX_FILES = 100_000
PACKAGE_MANIFEST_MAX_FILE_BYTES = 64 * 1024 * 1024
PACKAGE_MANIFEST_MAX_TOTAL_BYTES = 1 * 1024 * 1024 * 1024
PACKAGE_MANIFEST_CHUNK_BYTES = 1024 * 1024


class PackageManifestScanError(RuntimeError):
    """Base failure for bounded package inventory scans."""


class PackageManifestScanUnsafePathError(PackageManifestScanError):
    """Raised when the scan encounters a symlink or unsafe relative path."""


class PackageManifestScanLimitError(PackageManifestScanError):
    """Raised when project contents exceed package-manifest safety bounds."""


@dataclass(frozen=True, slots=True)
class PackageFileSnapshot:
    """One regular file observed during a scan."""

    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PackageExcludedPath:
    """One existing or planned path excluded from package contents."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class PackageScanResult:
    """Deterministic scan output consumed by the application service."""

    files: tuple[PackageFileSnapshot, ...]
    excluded: tuple[PackageExcludedPath, ...]


class PackageFileScanner:
    """Enumerate regular project files without following links or special files."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        max_files: int = PACKAGE_MANIFEST_MAX_FILES,
        max_file_bytes: int = PACKAGE_MANIFEST_MAX_FILE_BYTES,
        max_total_bytes: int = PACKAGE_MANIFEST_MAX_TOTAL_BYTES,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("package scanning requires ProjectFilesystem")
        _validate_positive_limit(max_files, "file limit")
        _validate_positive_limit(max_file_bytes, "per-file byte limit")
        _validate_positive_limit(max_total_bytes, "total byte limit")
        if max_file_bytes > max_total_bytes:
            raise ValueError("per-file byte limit cannot exceed total byte limit")
        self._filesystem = filesystem
        self._max_files = max_files
        self._max_file_bytes = max_file_bytes
        self._max_total_bytes = max_total_bytes

    def scan(
        self,
        *,
        excluded_paths: tuple[tuple[str, str], ...] = (),
    ) -> PackageScanResult:
        """Return sorted file snapshots and explicit exclusions."""
        exclusions = _normalize_exclusions(excluded_paths)
        files: list[PackageFileSnapshot] = []
        excluded: dict[str, str] = {}
        total_bytes = 0

        def visit(directory: Path, relative_parts: tuple[str, ...]) -> None:
            nonlocal total_bytes
            try:
                children = sorted(directory.iterdir(), key=lambda item: item.name)
            except OSError as error:
                relative = "/".join(relative_parts) or "."
                raise PackageManifestScanError(
                    f"cannot inspect project directory: {relative}"
                ) from error

            for child in children:
                child_parts = (*relative_parts, child.name)
                relative = "/".join(child_parts)
                _validate_scanned_path(relative)
                try:
                    child_stat = os.lstat(child)
                except OSError as error:
                    raise PackageManifestScanError(
                        f"cannot inspect project path: {relative}"
                    ) from error
                if stat.S_ISLNK(child_stat.st_mode):
                    raise PackageManifestScanUnsafePathError(
                        f"package scan encountered a symlink: {relative}"
                    )

                exclusion_reason = _matching_exclusion(relative, exclusions)
                if exclusion_reason is not None:
                    excluded[relative] = exclusion_reason
                    continue

                if stat.S_ISDIR(child_stat.st_mode):
                    visit(child, child_parts)
                    continue
                if not stat.S_ISREG(child_stat.st_mode):
                    raise PackageManifestScanUnsafePathError(
                        f"package scan encountered a non-regular path: {relative}"
                    )

                if len(files) >= self._max_files:
                    raise PackageManifestScanLimitError(
                        f"project exceeds the {self._max_files}-file package limit"
                    )
                if child_stat.st_size > self._max_file_bytes:
                    raise PackageManifestScanLimitError(
                        f"project file exceeds the {self._max_file_bytes}-byte package limit: "
                        f"{relative}"
                    )
                snapshot = _hash_regular_file(
                    child,
                    relative,
                    expected_size=child_stat.st_size,
                    max_bytes=self._max_file_bytes,
                )
                total_bytes += snapshot.size_bytes
                if total_bytes > self._max_total_bytes:
                    raise PackageManifestScanLimitError(
                        f"project exceeds the {self._max_total_bytes}-byte package limit"
                    )
                files.append(snapshot)

        visit(self._filesystem.root, ())
        for path, reason in exclusions:
            if path not in excluded and path == _manifest_output_path(exclusions):
                excluded[path] = reason

        return PackageScanResult(
            files=tuple(sorted(files, key=lambda item: item.path)),
            excluded=tuple(
                PackageExcludedPath(path=path, reason=excluded[path]) for path in sorted(excluded)
            ),
        )


def _hash_regular_file(
    path: Path,
    relative: str,
    *,
    expected_size: int,
    max_bytes: int,
) -> PackageFileSnapshot:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PackageManifestScanError(f"cannot read project file: {relative}") from error

    try:
        opened_stat = os.fstat(descriptor)
        if stat.S_ISLNK(opened_stat.st_mode) or not stat.S_ISREG(opened_stat.st_mode):
            raise PackageManifestScanUnsafePathError(
                f"package scan target changed to a non-regular path: {relative}"
            )
        if opened_stat.st_size != expected_size:
            raise PackageManifestScanError(f"project file changed during package scan: {relative}")

        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            while True:
                chunk = stream.read(PACKAGE_MANIFEST_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise PackageManifestScanLimitError(
                        f"project file changed beyond the {max_bytes}-byte package limit: "
                        f"{relative}"
                    )
                digest.update(chunk)
        if size != expected_size:
            raise PackageManifestScanError(f"project file changed during package scan: {relative}")
        return PackageFileSnapshot(path=relative, size_bytes=size, sha256=digest.hexdigest())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _normalize_exclusions(
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    normalized: dict[str, str] = {}
    for path, reason in values:
        try:
            validate_package_path(path)
        except ValueError as error:
            raise PackageManifestScanUnsafePathError(str(error)) from error
        if not isinstance(reason, str) or not reason:
            raise ValueError("package exclusion reasons must be non-empty strings")
        normalized[path] = reason
    return tuple(sorted(normalized.items()))


def _matching_exclusion(
    path: str,
    exclusions: tuple[tuple[str, str], ...],
) -> str | None:
    matches = [
        (excluded_path, reason)
        for excluded_path, reason in exclusions
        if path == excluded_path or path.startswith(f"{excluded_path}/")
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]


def _manifest_output_path(exclusions: tuple[tuple[str, str], ...]) -> str:
    for path, reason in exclusions:
        if reason == "manifest-output":
            return path
    return ""


def _validate_scanned_path(path: str) -> None:
    try:
        validate_package_path(path)
    except ValueError as error:
        raise PackageManifestScanUnsafePathError(str(error)) from error


def _validate_positive_limit(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


__all__ = [
    "PACKAGE_MANIFEST_MAX_FILES",
    "PACKAGE_MANIFEST_MAX_FILE_BYTES",
    "PACKAGE_MANIFEST_MAX_TOTAL_BYTES",
    "PackageExcludedPath",
    "PackageFileScanner",
    "PackageFileSnapshot",
    "PackageManifestScanError",
    "PackageManifestScanLimitError",
    "PackageManifestScanUnsafePathError",
    "PackageScanResult",
]
