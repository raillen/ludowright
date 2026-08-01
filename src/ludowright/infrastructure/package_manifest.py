"""Bounded, symlink-free filesystem scanning for package manifests."""

from __future__ import annotations

import hashlib
import io
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from ludowright.contracts.package_manifest import validate_package_path
from ludowright.infrastructure.filesystem import ProjectFilesystem

PACKAGE_MANIFEST_MAX_FILES = 100_000
PACKAGE_MANIFEST_MAX_FILE_BYTES = 64 * 1024 * 1024
PACKAGE_MANIFEST_MAX_TOTAL_BYTES = 1 * 1024 * 1024 * 1024
PACKAGE_MANIFEST_CHUNK_BYTES = 1024 * 1024
PACKAGE_ARCHIVE_MAX_BYTES = PACKAGE_MANIFEST_MAX_TOTAL_BYTES + 16 * 1024 * 1024
PACKAGE_ARCHIVE_MAX_ENTRIES = PACKAGE_MANIFEST_MAX_FILES + 2
PACKAGE_ARCHIVE_COMPRESSION_LEVEL = 9


class PackageManifestScanError(RuntimeError):
    """Base failure for bounded package inventory scans."""


class PackageManifestScanUnsafePathError(PackageManifestScanError):
    """Raised when the scan encounters a symlink or unsafe relative path."""


class PackageManifestScanLimitError(PackageManifestScanError):
    """Raised when project contents exceed package-manifest safety bounds."""


class PackageArchiveError(RuntimeError):
    """Raised when a deterministic ZIP cannot be safely built or validated."""


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


@dataclass(frozen=True, slots=True)
class PackageArchiveEntry:
    """One already-validated payload written to a ZIP member."""

    path: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class PackageArchiveResult:
    """Canonical ZIP bytes and identity facts."""

    payload: bytes
    sha256: str
    member_count: int


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

    def read_file(self, path: str) -> tuple[PackageFileSnapshot, bytes]:
        """Read one package-path file without applying RepositoryPath casing rules."""
        _validate_scanned_path(path)
        target = _resolve_package_path(self._filesystem, path)
        target_stat = os.lstat(target)
        if stat.S_ISLNK(target_stat.st_mode):
            raise PackageManifestScanUnsafePathError(f"package scan encountered a symlink: {path}")
        if not stat.S_ISREG(target_stat.st_mode):
            raise PackageManifestScanUnsafePathError(
                f"package scan encountered a non-regular path: {path}"
            )
        if target_stat.st_size > self._max_file_bytes:
            raise PackageManifestScanLimitError(
                f"project file exceeds the {self._max_file_bytes}-byte package limit: {path}"
            )
        return _read_regular_file(
            target,
            path,
            expected_size=target_stat.st_size,
            max_bytes=self._max_file_bytes,
        )


class PackageArchiveBuilder:
    """Render and validate a reproducible ZIP archive from immutable payloads."""

    def build(self, entries: tuple[PackageArchiveEntry, ...]) -> PackageArchiveResult:
        """Return canonical ZIP bytes with fixed metadata and sorted members."""
        ordered = _validate_archive_entries(entries)
        output = io.BytesIO()
        try:
            with ZipFile(
                output,
                mode="w",
                compression=ZIP_DEFLATED,
                compresslevel=PACKAGE_ARCHIVE_COMPRESSION_LEVEL,
                allowZip64=True,
            ) as archive:
                for entry in ordered:
                    info = ZipInfo(entry.path, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.create_version = 20
                    info.extract_version = 20
                    info.external_attr = 0o100644 << 16
                    info.compress_type = ZIP_DEFLATED
                    archive.writestr(info, entry.payload)
        except (OSError, ValueError, RuntimeError) as error:
            raise PackageArchiveError("could not render package ZIP") from error

        payload = output.getvalue()
        _validate_archive_payload(payload, ordered)
        return PackageArchiveResult(
            payload=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
            member_count=len(ordered),
        )

    def validate(self, payload: bytes) -> PackageArchiveResult:
        """Validate an existing canonical ZIP payload and return its identity."""
        if not isinstance(payload, bytes) or not payload:
            raise PackageArchiveError("package ZIP must contain bytes")
        if len(payload) > PACKAGE_ARCHIVE_MAX_BYTES:
            raise PackageArchiveError("package ZIP exceeds the archive size limit")
        try:
            with ZipFile(io.BytesIO(payload)) as archive:
                infos = tuple(archive.infolist())
                if not infos:
                    raise PackageArchiveError("package ZIP cannot be empty")
                if len(infos) > PACKAGE_ARCHIVE_MAX_ENTRIES:
                    raise PackageArchiveError("package ZIP contains too many entries")
                names = tuple(info.filename for info in infos)
                if names != tuple(sorted(names)) or len(names) != len(set(names)):
                    raise PackageArchiveError("package ZIP entries must be unique and sorted")
                entries = tuple(
                    PackageArchiveEntry(path=info.filename, payload=archive.read(info))
                    for info in infos
                )
        except (BadZipFile, KeyError, OSError, RuntimeError) as error:
            if isinstance(error, PackageArchiveError):
                raise
            raise PackageArchiveError("package ZIP is malformed") from error
        _validate_archive_payload(payload, entries)
        return PackageArchiveResult(
            payload=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
            member_count=len(entries),
        )


def _hash_regular_file(
    path: Path,
    relative: str,
    *,
    expected_size: int,
    max_bytes: int,
) -> PackageFileSnapshot:
    snapshot, _payload = _read_regular_file(
        path,
        relative,
        expected_size=expected_size,
        max_bytes=max_bytes,
    )
    return snapshot


def _read_regular_file(
    path: Path,
    relative: str,
    *,
    expected_size: int,
    max_bytes: int,
) -> tuple[PackageFileSnapshot, bytes]:
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
        chunks: list[bytes] = []
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
                chunks.append(chunk)
        if size != expected_size:
            raise PackageManifestScanError(f"project file changed during package scan: {relative}")
        return (
            PackageFileSnapshot(path=relative, size_bytes=size, sha256=digest.hexdigest()),
            b"".join(chunks),
        )
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


def _resolve_package_path(filesystem: ProjectFilesystem, path: str) -> Path:
    """Resolve a case-sensitive package path while rejecting symlink prefixes."""
    current = filesystem.root
    parts = PurePosixPath(path).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            current_stat = os.lstat(current)
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(current_stat.st_mode):
            raise PackageManifestScanUnsafePathError(f"package path contains a symlink: {path}")
        if index < len(parts) - 1 and not stat.S_ISDIR(current_stat.st_mode):
            raise PackageManifestScanUnsafePathError(
                f"package path contains a non-directory ancestor: {path}"
            )
    return current


def _validate_archive_entries(
    entries: tuple[PackageArchiveEntry, ...],
) -> tuple[PackageArchiveEntry, ...]:
    if not entries:
        raise PackageArchiveError("package ZIP requires at least one entry")
    if len(entries) > PACKAGE_ARCHIVE_MAX_ENTRIES:
        raise PackageArchiveError("package ZIP contains too many entries")
    paths = tuple(entry.path for entry in entries)
    for entry in entries:
        try:
            validate_package_path(entry.path)
        except ValueError as error:
            raise PackageArchiveError(str(error)) from error
        if not isinstance(entry.payload, bytes):
            raise PackageArchiveError("package ZIP entry payloads must be bytes")
        if len(entry.payload) > PACKAGE_MANIFEST_MAX_FILE_BYTES:
            raise PackageArchiveError(f"package ZIP entry exceeds the file limit: {entry.path}")
    if len(paths) != len(set(paths)):
        raise PackageArchiveError("package ZIP entries must be unique")
    total_bytes = sum(len(entry.payload) for entry in entries)
    if total_bytes > PACKAGE_ARCHIVE_MAX_BYTES:
        raise PackageArchiveError("package ZIP uncompressed content exceeds the size limit")
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _validate_archive_payload(
    payload: bytes,
    entries: tuple[PackageArchiveEntry, ...],
) -> None:
    if len(payload) > PACKAGE_ARCHIVE_MAX_BYTES:
        raise PackageArchiveError("package ZIP exceeds the archive size limit")
    expected = {entry.path: entry.payload for entry in entries}
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            infos = tuple(archive.infolist())
            if len(infos) != len(expected):
                raise PackageArchiveError("package ZIP member count is inconsistent")
            if tuple(info.filename for info in infos) != tuple(sorted(expected)):
                raise PackageArchiveError("package ZIP member order is not deterministic")
            if archive.comment:
                raise PackageArchiveError("package ZIP comments are not allowed")
            total_uncompressed = 0
            for info in infos:
                try:
                    validate_package_path(info.filename)
                except ValueError as error:
                    raise PackageArchiveError(str(error)) from error
                if info.is_dir() or info.compress_type != ZIP_DEFLATED:
                    raise PackageArchiveError("package ZIP contains an invalid member")
                if info.date_time != (1980, 1, 1, 0, 0, 0):
                    raise PackageArchiveError("package ZIP timestamps are not fixed")
                if info.create_system != 3 or info.external_attr != 0o100644 << 16:
                    raise PackageArchiveError("package ZIP member metadata is not canonical")
                if (
                    info.create_version != 20
                    or info.extract_version != 20
                    or info.flag_bits != 0
                    or info.internal_attr != 0
                    or info.extra
                    or info.comment
                ):
                    raise PackageArchiveError("package ZIP member flags are not canonical")
                content = archive.read(info)
                if content != expected[info.filename]:
                    raise PackageArchiveError("package ZIP member content is inconsistent")
                total_uncompressed += len(content)
            if total_uncompressed > PACKAGE_ARCHIVE_MAX_BYTES:
                raise PackageArchiveError("package ZIP uncompressed content exceeds the size limit")
    except (BadZipFile, KeyError, OSError, RuntimeError) as error:
        if isinstance(error, PackageArchiveError):
            raise
        raise PackageArchiveError("package ZIP is malformed") from error


def _validate_positive_limit(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")


__all__ = [
    "PACKAGE_ARCHIVE_COMPRESSION_LEVEL",
    "PACKAGE_ARCHIVE_MAX_BYTES",
    "PACKAGE_ARCHIVE_MAX_ENTRIES",
    "PACKAGE_MANIFEST_MAX_FILES",
    "PACKAGE_MANIFEST_MAX_FILE_BYTES",
    "PACKAGE_MANIFEST_MAX_TOTAL_BYTES",
    "PackageArchiveBuilder",
    "PackageArchiveEntry",
    "PackageArchiveError",
    "PackageArchiveResult",
    "PackageExcludedPath",
    "PackageFileScanner",
    "PackageFileSnapshot",
    "PackageManifestScanError",
    "PackageManifestScanLimitError",
    "PackageManifestScanUnsafePathError",
    "PackageScanResult",
]
