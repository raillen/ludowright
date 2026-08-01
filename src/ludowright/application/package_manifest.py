"""Build deterministic, read-only package inventories from project sources."""

from __future__ import annotations

import os
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Literal

from ludowright.application.asset_registry import DEFAULT_ASSET_REGISTRY_PATH
from ludowright.contracts import (
    AssetRegistryContract,
    PackageExcludedPathContract,
    PackageFileContract,
    PackageLicenseContract,
    PackageManifestContract,
    PackageMissingItemContract,
    PackageProvenanceContract,
    PackageSourceVersionContract,
    ProjectContract,
    VisualReferenceContract,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    DEFAULT_STATE_STORE_PATH,
    GENERATED_REFERENCE_DIRECTORY,
    STATE_SCHEMA_VERSION,
    DependencyGraphRepository,
    EventLog,
    JsonDocumentRepository,
    PackageFileScanner,
    PackageFileSnapshot,
    PackageManifestScanError,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    UnsafeProjectPathError,
    YamlDocumentRepository,
)
from ludowright.infrastructure.filesystem import PROJECT_MARKER

PACKAGE_MANIFEST_LOCK = "package-manifest"
PACKAGE_MANIFEST_MAX_BYTES = 16 * 1024 * 1024
PACKAGE_MANIFEST_DEFAULT_ID = "default"
PACKAGE_MANIFEST_LOCK_TIMEOUT = 5.0

_TRANSIENT_EXCLUSIONS = (
    (".git", "transient"),
    (".venv", "transient"),
    ("__pycache__", "transient"),
    (".pytest_cache", "tool-cache"),
    (".mypy_cache", "tool-cache"),
    (".ruff_cache", "tool-cache"),
    ("build", "transient"),
    ("dist", "transient"),
    ("site", "transient"),
    (".ludowright/locks", "transient"),
    (".ludowright/state.sqlite3", "derived-state"),
    (".ludowright/state.sqlite3-journal", "derived-state"),
    (".ludowright/state.sqlite3-shm", "derived-state"),
    (".ludowright/state.sqlite3-wal", "derived-state"),
)
_OPTIONAL_SOURCES = (
    (DEFAULT_EVENT_LOG_PATH, "event-log", "optional event log"),
    (DEFAULT_DEPENDENCY_GRAPH_PATH, "dependency-graph", "optional dependency graph"),
    (DEFAULT_ASSET_REGISTRY_PATH, "asset-registry", "optional asset registry"),
)


class PackageManifestError(RuntimeError):
    """Base failure for package manifest generation."""


class PackageManifestInputError(PackageManifestError):
    """Raised when project inputs cannot be safely inventoried."""


class PackageManifestConflictError(PackageManifestError):
    """Raised when a manifest target exists with different content."""


@dataclass(frozen=True, slots=True)
class _SourceObservation:
    digest: str
    schema_version: int
    revision: int | None


@dataclass(frozen=True, slots=True)
class PackageManifestResult:
    """Application result shared by human and JSON CLI renderers."""

    manifest: PackageManifestContract
    output_path: str
    state: str
    dry_run: bool
    warnings: tuple[str, ...] = ()

    def as_data(self) -> dict[str, object]:
        """Return a stable report without changing the persisted manifest shape."""
        included = self.manifest.included_files
        excluded = self.manifest.excluded
        missing = self.manifest.missing
        return {
            "dry_run": self.dry_run,
            "excluded_path_count": len(excluded),
            "included_file_count": len(included),
            "kind": "package-manifest-report",
            "manifest": self.manifest.model_dump(mode="json"),
            "missing_item_count": len(missing),
            "output_path": self.output_path,
            "package_id": self.manifest.package_id,
            "project_id": self.manifest.project_id,
            "schema_version": 1,
            "state": self.state,
            "state_store_schema_version": STATE_SCHEMA_VERSION,
            "warnings": list(self.warnings),
        }


class PackageManifestService:
    """Create one deterministic package manifest without mutating project sources."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("package manifests require ProjectFilesystem")
        self._filesystem = filesystem
        self._project_repository = JsonDocumentRepository(
            filesystem,
            PROJECT_MARKER,
            ProjectContract,
        )
        self._scanner = PackageFileScanner(filesystem)

    def create(
        self,
        output_path: RepositoryPath,
        *,
        package_id: str = PACKAGE_MANIFEST_DEFAULT_ID,
        dry_run: bool = False,
    ) -> PackageManifestResult:
        """Plan or create a canonical manifest using create-only semantics."""
        if not isinstance(output_path, RepositoryPath):
            raise TypeError("package manifest output requires RepositoryPath")
        if not output_path.name.endswith(".json"):
            raise PackageManifestInputError(
                "package manifest output paths must use the .json extension"
            )
        if output_path in {
            PROJECT_MARKER,
            DEFAULT_EVENT_LOG_PATH,
            DEFAULT_DEPENDENCY_GRAPH_PATH,
            DEFAULT_ASSET_REGISTRY_PATH,
            DEFAULT_STATE_STORE_PATH,
        }:
            raise PackageManifestInputError(
                f"package manifest cannot replace a canonical source: {output_path}"
            )

        operation = (
            nullcontext()
            if dry_run
            else self._filesystem.lock(
                PACKAGE_MANIFEST_LOCK,
                timeout=PACKAGE_MANIFEST_LOCK_TIMEOUT,
            )
        )
        with operation:
            manifest = self._build_manifest(output_path, package_id=package_id)
            payload = JsonDocumentRepository(
                self._filesystem,
                output_path,
                PackageManifestContract,
                max_bytes=PACKAGE_MANIFEST_MAX_BYTES,
            ).canonical_bytes(manifest)
            state = "planned" if dry_run else self._persist(output_path, payload)
        warnings = tuple(f"missing optional source: {item.path}" for item in manifest.missing)
        return PackageManifestResult(
            manifest=manifest,
            output_path=output_path.value,
            state=state,
            dry_run=dry_run,
            warnings=warnings,
        )

    def _build_manifest(
        self,
        output_path: RepositoryPath,
        *,
        package_id: str,
    ) -> PackageManifestContract:
        try:
            scan = self._scanner.scan(
                excluded_paths=(*_TRANSIENT_EXCLUSIONS, (output_path.value, "manifest-output"))
            )
        except PackageManifestScanError as error:
            raise PackageManifestInputError(str(error)) from error

        files = {snapshot.path: snapshot for snapshot in scan.files}
        project_snapshot = self._project_repository.load()
        _require_scanned_digest(files, PROJECT_MARKER.value, project_snapshot.digest)

        source_versions: list[PackageSourceVersionContract] = [
            PackageSourceVersionContract(
                path=PROJECT_MARKER.value,
                kind="project",
                schema_version=project_snapshot.value.schema_version,
                sha256=project_snapshot.digest,
            )
        ]
        missing: list[PackageMissingItemContract] = []
        for path, kind, detail in _OPTIONAL_SOURCES:
            source = self._load_optional_source(path, kind)
            if source is None:
                missing.append(
                    PackageMissingItemContract(
                        path=path.value,
                        reason="optional-source",
                        detail=f"{detail} is absent",
                    )
                )
                continue
            _require_scanned_digest(files, path.value, source.digest)
            source_versions.append(
                PackageSourceVersionContract(
                    path=path.value,
                    kind=kind,
                    schema_version=source.schema_version,
                    revision=source.revision,
                    sha256=source.digest,
                )
            )

        state_path = DEFAULT_STATE_STORE_PATH.value
        excluded_paths = {item.path: item.reason for item in scan.excluded}
        if state_path in excluded_paths:
            source_versions.append(
                PackageSourceVersionContract(
                    path=state_path,
                    kind="state-store",
                    schema_version=STATE_SCHEMA_VERSION,
                )
            )
        else:
            missing.append(
                PackageMissingItemContract(
                    path=state_path,
                    reason="optional-source",
                    detail="rebuildable SQLite state store is absent",
                )
            )

        provenance = self._load_provenance(files)
        licenses = _licenses_from_provenance(provenance)
        excluded = tuple(
            PackageExcludedPathContract(path=item.path, reason=_excluded_reason(item.reason))
            for item in scan.excluded
        )
        included = tuple(
            PackageFileContract(
                path=item.path,
                size_bytes=item.size_bytes,
                sha256=item.sha256,
            )
            for item in scan.files
        )
        return PackageManifestContract(
            package_id=package_id,
            project_id=project_snapshot.value.id,
            manifest_path=output_path.value,
            included_files=included,
            source_versions=tuple(sorted(source_versions, key=lambda item: item.path)),
            provenance=tuple(sorted(provenance, key=lambda item: item.path)),
            licenses=licenses,
            missing=tuple(sorted(missing, key=lambda item: item.path)),
            excluded=excluded,
        )

    def _load_optional_source(
        self,
        path: RepositoryPath,
        kind: str,
    ) -> _SourceObservation | None:
        if kind == "event-log":
            if not os.path.lexists(self._filesystem.resolve(path)):
                return None
            try:
                event_snapshot = EventLog(self._filesystem).replay()
            except FileNotFoundError:
                return None
            return _SourceObservation(
                digest=event_snapshot.digest,
                schema_version=1,
                revision=event_snapshot.last_sequence,
            )
        if kind == "dependency-graph":
            graph_snapshot = DependencyGraphRepository(self._filesystem).load_optional()
            if graph_snapshot is None:
                return None
            return _SourceObservation(
                digest=graph_snapshot.digest,
                schema_version=1,
                revision=graph_snapshot.graph.revision.value,
            )
        if kind == "asset-registry":
            registry_snapshot = YamlDocumentRepository(
                self._filesystem,
                path,
                AssetRegistryContract,
            ).load_optional()
            if registry_snapshot is None:
                return None
            return _SourceObservation(
                digest=registry_snapshot.digest,
                schema_version=registry_snapshot.value.schema_version,
                revision=registry_snapshot.value.version,
            )
        raise AssertionError(f"unsupported package source kind: {kind}")

    def _load_provenance(
        self,
        files: dict[str, PackageFileSnapshot],
    ) -> tuple[PackageProvenanceContract, ...]:
        prefix = f"{GENERATED_REFERENCE_DIRECTORY.value}/"
        values: list[PackageProvenanceContract] = []
        for path in sorted(files):
            if not path.startswith(prefix) or not path.endswith(".json"):
                continue
            try:
                repository_path = RepositoryPath.parse(path)
            except (UnsafeProjectPathError, ValueError):
                continue
            snapshot = JsonDocumentRepository(
                self._filesystem,
                repository_path,
                VisualReferenceContract,
            ).load()
            file_snapshot = files[path]
            if snapshot.digest != file_snapshot.sha256:
                raise PackageManifestInputError(
                    f"visual reference changed during package scan: {path}"
                )
            reference = snapshot.value
            provenance = reference.provenance
            values.append(
                PackageProvenanceContract(
                    path=path,
                    reference_id=reference.id,
                    status=reference.status,
                    approval_id=reference.approval_id,
                    origin=provenance.origin,
                    content_revision=provenance.content_revision,
                    source_uri=provenance.source_uri,
                    source_job_id=provenance.source_job_id,
                    source_receipt_id=provenance.source_receipt_id,
                    parent_reference_ids=provenance.parent_reference_ids,
                    creator=provenance.creator,
                    license_label=provenance.license_label,
                )
            )
        return tuple(values)

    def _persist(self, output_path: RepositoryPath, payload: bytes) -> str:
        target = self._filesystem.resolve(output_path)
        if os.path.lexists(target):
            try:
                current = self._filesystem.read_bytes(
                    output_path,
                    max_bytes=PACKAGE_MANIFEST_MAX_BYTES,
                )
            except (FileNotFoundError, IsADirectoryError, OSError) as error:
                raise PackageManifestConflictError(
                    f"package manifest target is not a regular file: {output_path}"
                ) from error
            if current == payload:
                return "unchanged"
            raise PackageManifestConflictError(
                f"package manifest already exists with different content: {output_path}"
            )
        created_directories = _missing_parent_directories(self._filesystem, output_path)
        try:
            self._filesystem.write_bytes(output_path, payload)
        except Exception as error:
            for directory in created_directories:
                try:
                    self._filesystem.remove_empty_directory(directory)
                except (ProjectFilesystemError, OSError):
                    break
            raise PackageManifestError(
                f"package manifest could not be written: {output_path}"
            ) from error
        return "created"


def _require_scanned_digest(
    files: dict[str, PackageFileSnapshot],
    path: str,
    digest: str,
) -> None:
    snapshot = files.get(path)
    if snapshot is None or snapshot.sha256 != digest:
        raise PackageManifestInputError(f"source changed during package scan: {path}")


def _missing_parent_directories(
    filesystem: ProjectFilesystem,
    output_path: RepositoryPath,
) -> tuple[RepositoryPath, ...]:
    missing: list[RepositoryPath] = []
    parent = output_path.parent
    while parent is not None:
        if os.path.lexists(filesystem.resolve(parent)):
            break
        missing.append(parent)
        parent = parent.parent
    return tuple(missing)


def _licenses_from_provenance(
    provenance: tuple[PackageProvenanceContract, ...],
) -> tuple[PackageLicenseContract, ...]:
    references_by_label: dict[str, list[str]] = {}
    for item in provenance:
        if item.license_label is not None:
            references_by_label.setdefault(item.license_label, []).append(item.reference_id)
    return tuple(
        PackageLicenseContract(
            label=label,
            reference_ids=tuple(sorted(reference_ids)),
        )
        for label, reference_ids in sorted(references_by_label.items())
    )


def _excluded_reason(
    reason: str,
) -> Literal["manifest-output", "derived-state", "transient", "tool-cache"]:
    if reason == "manifest-output":
        return "manifest-output"
    if reason == "derived-state":
        return "derived-state"
    if reason == "transient":
        return "transient"
    if reason == "tool-cache":
        return "tool-cache"
    raise PackageManifestInputError(f"unsupported package exclusion reason: {reason}")


__all__ = [
    "PACKAGE_MANIFEST_DEFAULT_ID",
    "PACKAGE_MANIFEST_LOCK",
    "PACKAGE_MANIFEST_LOCK_TIMEOUT",
    "PackageManifestConflictError",
    "PackageManifestError",
    "PackageManifestInputError",
    "PackageManifestResult",
    "PackageManifestService",
]
