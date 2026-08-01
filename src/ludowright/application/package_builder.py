"""Build reproducible ZIP packages from a validated package manifest."""

from __future__ import annotations

import hashlib
import os
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from ludowright.contracts import (
    PACKAGE_INDEX_ARCHIVE_PATH,
    PACKAGE_MANIFEST_ARCHIVE_PATH,
    PackageIndexContract,
    PackageIndexEntryContract,
    PackageManifestContract,
    ProjectContract,
)
from ludowright.infrastructure import (
    PACKAGE_ARCHIVE_MAX_BYTES,
    JsonDocumentRepository,
    PackageArchiveBuilder,
    PackageArchiveEntry,
    PackageArchiveError,
    PackageFileScanner,
    PackageManifestScanError,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
)
from ludowright.infrastructure.filesystem import PROJECT_MARKER

PACKAGE_BUILD_LOCK = "package-build"
PACKAGE_BUILD_LOCK_TIMEOUT = 5.0
PACKAGE_BUILD_MANIFEST_MAX_BYTES = 16 * 1024 * 1024
PACKAGE_BUILD_INDEX_MAX_BYTES = 16 * 1024 * 1024

PackageBuildState = Literal["planned", "created", "unchanged"]


class PackageBuilderError(RuntimeError):
    """Base failure for reproducible package building."""


class PackageBuilderInputError(PackageBuilderError):
    """Raised when a manifest or release target is invalid."""


class PackageBuilderConflictError(PackageBuilderError):
    """Raised when source or output bytes conflict with the requested build."""


class PackageBuilderRollbackError(PackageBuilderError):
    """Raised when a failed build cannot clean up its own new artifacts."""


@dataclass(frozen=True, slots=True)
class _PreparedPackage:
    index: PackageIndexContract
    index_payload: bytes
    archive_payload: bytes
    archive_sha256: str
    archive_path: RepositoryPath
    index_path: RepositoryPath


@dataclass(frozen=True, slots=True)
class PackageBuildResult:
    """Stable result shared by human and JSON CLI presentation."""

    index: PackageIndexContract
    archive_path: RepositoryPath
    index_path: RepositoryPath
    archive_sha256: str
    archive_size_bytes: int
    state: PackageBuildState
    dry_run: bool

    def as_data(self) -> dict[str, object]:
        """Return a JSON-compatible package build report."""
        return {
            "archive_path": self.archive_path.value,
            "archive_sha256": self.archive_sha256,
            "archive_size_bytes": self.archive_size_bytes,
            "dry_run": self.dry_run,
            "index": self.index.model_dump(mode="json"),
            "index_path": self.index_path.value,
            "kind": "package-build-report",
            "package_id": self.index.package_id,
            "project_id": self.index.project_id,
            "schema_version": 1,
            "state": self.state,
            "warnings": [],
        }


class PackageBuilderService:
    """Create one ZIP package and deterministic index without overwriting targets."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("package builders require ProjectFilesystem")
        self._filesystem = filesystem
        self._scanner = PackageFileScanner(filesystem)
        self._archive_builder = PackageArchiveBuilder()

    def build(
        self,
        manifest_path: RepositoryPath,
        release_directory: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> PackageBuildResult:
        """Validate sources and plan or create a reproducible package."""
        if not isinstance(manifest_path, RepositoryPath):
            raise TypeError("package manifests require RepositoryPath")
        if not isinstance(release_directory, RepositoryPath):
            raise TypeError("package releases require RepositoryPath")
        if not manifest_path.name.endswith(".json"):
            raise PackageBuilderInputError("package manifest paths must use the .json extension")
        _validate_release_directory(release_directory)

        operation = (
            nullcontext()
            if dry_run
            else self._filesystem.lock(
                PACKAGE_BUILD_LOCK,
                timeout=PACKAGE_BUILD_LOCK_TIMEOUT,
            )
        )
        with operation:
            prepared = self._prepare(manifest_path, release_directory)
            state = self._existing_state(prepared)
            if state == "unchanged":
                return _result(prepared, state="unchanged", dry_run=dry_run)
            if dry_run:
                return _result(prepared, state="planned", dry_run=True)
            self._persist(prepared)
            return _result(prepared, state="created", dry_run=False)

    def _prepare(
        self,
        manifest_path: RepositoryPath,
        release_directory: RepositoryPath,
    ) -> _PreparedPackage:
        manifest_repository = JsonDocumentRepository(
            self._filesystem,
            manifest_path,
            PackageManifestContract,
            max_bytes=PACKAGE_BUILD_MANIFEST_MAX_BYTES,
        )
        try:
            manifest_snapshot = manifest_repository.load()
        except (FileNotFoundError, ValidationError, ProjectFilesystemError) as error:
            raise PackageBuilderInputError(
                f"package manifest cannot be loaded: {manifest_path}"
            ) from error
        manifest = manifest_snapshot.value
        if manifest.manifest_path != manifest_path.value:
            raise PackageBuilderInputError(
                "package manifest path does not match its declared manifest_path"
            )

        project_snapshot = JsonDocumentRepository(
            self._filesystem,
            PROJECT_MARKER,
            ProjectContract,
        ).load()
        if project_snapshot.value.id != manifest.project_id:
            raise PackageBuilderConflictError("package manifest belongs to a different project")

        archive_path = release_directory.child(f"{manifest.package_id}.zip")
        index_path = release_directory.child(f"{manifest.package_id}.index.json")
        if manifest_path in {archive_path, index_path}:
            raise PackageBuilderInputError("package outputs cannot replace the source manifest")
        included_paths = {item.path for item in manifest.included_files}
        if archive_path.value in included_paths or index_path.value in included_paths:
            raise PackageBuilderConflictError(
                "package release outputs are already included by the source manifest"
            )

        try:
            manifest_payload = self._filesystem.read_bytes(
                manifest_path,
                max_bytes=PACKAGE_BUILD_MANIFEST_MAX_BYTES,
            )
        except (FileNotFoundError, ProjectFilesystemError) as error:
            raise PackageBuilderInputError(
                f"package manifest cannot be read safely: {manifest_path}"
            ) from error
        if hashlib.sha256(manifest_payload).hexdigest() != manifest_snapshot.digest:
            raise PackageBuilderConflictError("package manifest changed during package build")

        archive_entries: list[PackageArchiveEntry] = []
        index_entries: list[PackageIndexEntryContract] = []
        for item in manifest.included_files:
            try:
                snapshot, payload = self._scanner.read_file(item.path)
            except FileNotFoundError as error:
                raise PackageBuilderConflictError(
                    f"package source file is missing: {item.path}"
                ) from error
            except PackageManifestScanError as error:
                raise PackageBuilderInputError(str(error)) from error
            if snapshot.size_bytes != item.size_bytes or snapshot.sha256 != item.sha256:
                raise PackageBuilderConflictError(
                    f"package source file changed since manifest creation: {item.path}"
                )
            archive_entries.append(PackageArchiveEntry(path=item.path, payload=payload))
            index_entries.append(
                PackageIndexEntryContract(
                    path=item.path,
                    source_path=item.path,
                    kind="project-file",
                    size_bytes=len(payload),
                    sha256=snapshot.sha256,
                )
            )

        manifest_archive_entry = PackageArchiveEntry(
            path=PACKAGE_MANIFEST_ARCHIVE_PATH,
            payload=manifest_payload,
        )
        archive_entries.append(manifest_archive_entry)
        index_entries.append(
            PackageIndexEntryContract(
                path=PACKAGE_MANIFEST_ARCHIVE_PATH,
                source_path=manifest_path.value,
                kind="package-manifest",
                size_bytes=len(manifest_payload),
                sha256=manifest_snapshot.digest,
            )
        )
        index = PackageIndexContract(
            package_id=manifest.package_id,
            project_id=manifest.project_id,
            manifest_path=manifest_path.value,
            manifest_sha256=manifest_snapshot.digest,
            archive_path=archive_path.value,
            index_path=index_path.value,
            entries=tuple(sorted(index_entries, key=lambda item: item.path)),
            archive_member_count=len(index_entries) + 1,
            payload_size_bytes=sum(item.size_bytes for item in index_entries),
        )
        index_payload = JsonDocumentRepository(
            self._filesystem,
            index_path,
            PackageIndexContract,
            max_bytes=PACKAGE_BUILD_INDEX_MAX_BYTES,
        ).canonical_bytes(index)
        if len(index_payload) > PACKAGE_BUILD_INDEX_MAX_BYTES:
            raise PackageBuilderInputError("package index exceeds its size limit")
        archive_entries.append(
            PackageArchiveEntry(path=PACKAGE_INDEX_ARCHIVE_PATH, payload=index_payload)
        )
        try:
            archive = self._archive_builder.build(tuple(archive_entries))
        except PackageArchiveError as error:
            raise PackageBuilderInputError(str(error)) from error
        if len(archive.payload) > PACKAGE_ARCHIVE_MAX_BYTES:
            raise PackageBuilderInputError("package archive exceeds its size limit")
        return _PreparedPackage(
            index=index,
            index_payload=index_payload,
            archive_payload=archive.payload,
            archive_sha256=archive.sha256,
            archive_path=archive_path,
            index_path=index_path,
        )

    def _existing_state(self, prepared: _PreparedPackage) -> Literal["new", "unchanged"]:
        paths = (prepared.archive_path, prepared.index_path)
        existing = [os.path.lexists(self._filesystem.resolve(path)) for path in paths]
        if not any(existing):
            return "new"
        if not all(existing):
            raise PackageBuilderConflictError(
                f"package release is partially present: {prepared.archive_path.parent}"
            )
        try:
            archive_payload = self._filesystem.read_bytes(
                prepared.archive_path,
                max_bytes=PACKAGE_ARCHIVE_MAX_BYTES,
            )
            index_payload = self._filesystem.read_bytes(
                prepared.index_path,
                max_bytes=PACKAGE_BUILD_INDEX_MAX_BYTES,
            )
        except (FileNotFoundError, ProjectFilesystemError) as error:
            raise PackageBuilderConflictError(
                "package release targets are not safe regular files: "
                f"{prepared.archive_path.parent}"
            ) from error
        if archive_payload == prepared.archive_payload and index_payload == prepared.index_payload:
            return "unchanged"
        raise PackageBuilderConflictError(
            f"package release already exists with different content: {prepared.archive_path.parent}"
        )

    def _persist(self, prepared: _PreparedPackage) -> None:
        release_directory = prepared.archive_path.parent
        if release_directory is None:
            raise PackageBuilderInputError("package release requires a directory")
        created_directories = _missing_directories(self._filesystem, release_directory)
        created_files: list[RepositoryPath] = []
        try:
            self._filesystem.ensure_directory(release_directory)
            _assert_absent(self._filesystem, prepared.archive_path)
            _write_new_file(
                self._filesystem,
                prepared.archive_path,
                prepared.archive_payload,
                created_files,
            )
            _assert_absent(self._filesystem, prepared.index_path)
            _write_new_file(
                self._filesystem,
                prepared.index_path,
                prepared.index_payload,
                created_files,
            )
        except BaseException as error:
            rollback_errors: list[BaseException] = []
            for path in reversed(created_files):
                try:
                    self._filesystem.remove_file(path)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
            for path in reversed(created_directories):
                try:
                    self._filesystem.remove_empty_directory(path)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise PackageBuilderRollbackError(
                    f"package build failed and cleanup also failed: {prepared.archive_path.parent}"
                ) from error
            if isinstance(error, PackageBuilderConflictError):
                raise
            raise PackageBuilderError(
                f"package release could not be written: {prepared.archive_path.parent}"
            ) from error


def _validate_release_directory(path: RepositoryPath) -> None:
    if path.value == ".ludowright" or path.value.startswith(".ludowright/"):
        raise PackageBuilderInputError(
            "package release directories must remain outside .ludowright"
        )


def _assert_absent(filesystem: ProjectFilesystem, path: RepositoryPath) -> None:
    if os.path.lexists(filesystem.resolve(path)):
        raise PackageBuilderConflictError(f"package target already exists: {path}")


def _write_new_file(
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
    payload: bytes,
    created_files: list[RepositoryPath],
) -> None:
    """Record a target if an atomic writer failed after publishing its bytes."""
    try:
        filesystem.write_bytes(path, payload)
    except BaseException:
        try:
            if filesystem.read_bytes(path, max_bytes=len(payload)) == payload:
                created_files.append(path)
        except (FileNotFoundError, ProjectFilesystemError):
            pass
        raise
    created_files.append(path)


def _missing_directories(
    filesystem: ProjectFilesystem,
    directory: RepositoryPath,
) -> tuple[RepositoryPath, ...]:
    missing: list[RepositoryPath] = []
    for index in range(1, len(directory.parts) + 1):
        candidate = RepositoryPath("/".join(directory.parts[:index]))
        if not os.path.lexists(filesystem.resolve(candidate)):
            missing.append(candidate)
    return tuple(missing)


def _result(
    prepared: _PreparedPackage,
    *,
    state: PackageBuildState,
    dry_run: bool,
) -> PackageBuildResult:
    return PackageBuildResult(
        index=prepared.index,
        archive_path=prepared.archive_path,
        index_path=prepared.index_path,
        archive_sha256=prepared.archive_sha256,
        archive_size_bytes=len(prepared.archive_payload),
        state=state,
        dry_run=dry_run,
    )


__all__ = [
    "PACKAGE_BUILD_LOCK",
    "PACKAGE_BUILD_LOCK_TIMEOUT",
    "PackageBuildResult",
    "PackageBuilderConflictError",
    "PackageBuilderError",
    "PackageBuilderInputError",
    "PackageBuilderRollbackError",
    "PackageBuilderService",
]
