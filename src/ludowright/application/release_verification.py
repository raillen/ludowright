"""Verify local package releases and prepare a checksum manifest."""

from __future__ import annotations

import hashlib
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from pydantic import ValidationError

from ludowright.application.package_builder import PACKAGE_BUILD_LOCK
from ludowright.application.project_audit import (
    ProjectAuditConflictError,
    ProjectAuditCorruptError,
    ProjectAuditError,
    ProjectAuditResult,
    ProjectAuditService,
)
from ludowright.contracts import (
    PackageIndexContract,
    PackageManifestContract,
    ProjectAuditReportContract,
    ReleaseArtifactContract,
    ReleaseGateContract,
    ReleaseGateState,
    ReleaseManifestContract,
    ReleaseManifestState,
    ReleaseSummaryContract,
    ReleaseVerificationReportContract,
    ReleaseVerificationState,
    ReleaseWarningPolicy,
)
from ludowright.contracts.common import ContractModel
from ludowright.domain import validate_slug
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
    StructuredDocumentError,
    StructuredDocumentSnapshot,
)

RELEASE_VERIFY_LOCK_TIMEOUT = 5.0
RELEASE_MANIFEST_MAX_BYTES = 16 * 1024 * 1024
RELEASE_INDEX_MAX_BYTES = 16 * 1024 * 1024


class ReleaseVerificationError(RuntimeError):
    """Base failure for local release verification."""


class ReleaseVerificationInputError(ReleaseVerificationError):
    """Raised when the release target cannot be selected safely."""


class ReleaseVerificationConflictError(ReleaseVerificationError):
    """Raised when a release manifest changes during verification."""


class ReleaseVerificationCorruptError(ReleaseVerificationError):
    """Raised when project state cannot be inspected safely."""


@dataclass(frozen=True, slots=True)
class ReleaseVerificationResult:
    """Stable result shared by human and JSON CLI surfaces."""

    report: ReleaseVerificationReportContract

    def as_data(self) -> dict[str, object]:
        """Return the published report plus convenient count projections."""
        data = self.report.model_dump(mode="json")
        data.update(
            {
                "error_count": self.report.summary.audit_error_count,
                "warning_count": self.report.summary.audit_warning_count,
            }
        )
        return data


@dataclass(frozen=True, slots=True)
class _PackageFacts:
    manifest: PackageManifestContract
    manifest_payload: bytes
    manifest_digest: str
    manifest_size: int
    index: PackageIndexContract
    index_payload: bytes
    index_digest: str
    index_size: int
    archive_payload: bytes
    archive_digest: str
    archive_size: int
    archive_entries: tuple[PackageArchiveEntry, ...]


class ReleaseVerificationService:
    """Verify one local package release without publishing or signing it."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("release verification requires ProjectFilesystem")
        self._filesystem = filesystem
        self._scanner = PackageFileScanner(filesystem)

    def verify(
        self,
        release_directory: RepositoryPath,
        *,
        package_id: str | None = None,
        allow_warnings: bool = False,
        dry_run: bool = False,
    ) -> ReleaseVerificationResult:
        """Verify a package and create its checksum manifest when allowed."""
        if not isinstance(release_directory, RepositoryPath):
            raise TypeError("release verification requires RepositoryPath")
        if not isinstance(allow_warnings, bool) or not isinstance(dry_run, bool):
            raise TypeError("release verification flags must be booleans")
        _validate_release_directory(release_directory)
        if package_id is not None:
            try:
                validate_slug(package_id)
            except ValueError as error:
                raise ReleaseVerificationInputError(str(error)) from error

        operation = (
            nullcontext()
            if dry_run
            else self._filesystem.lock(
                PACKAGE_BUILD_LOCK,
                timeout=RELEASE_VERIFY_LOCK_TIMEOUT,
            )
        )
        with operation:
            audit = _audit_project(self._filesystem)
            selected_index_path, selected_package_id = self._select_index(
                release_directory,
                package_id=package_id,
            )
            release_manifest_path = release_directory.child(f"{selected_package_id}.release.json")
            gates: list[ReleaseGateContract] = [_project_audit_gate(audit.report)]
            facts = self._verify_package(
                release_directory,
                selected_index_path,
                selected_package_id,
                release_manifest_path,
                audit.report.project_id,
                gates,
            )
            prepared_manifest = (
                _build_release_manifest(
                    facts,
                    project_id=audit.report.project_id,
                    release_directory=release_directory,
                    release_manifest_path=release_manifest_path,
                )
                if facts is not None
                else None
            )
            manifest_state: ReleaseManifestState = "not-created"
            _append_release_manifest_gate(
                self._filesystem,
                release_manifest_path,
                prepared_manifest,
                gates,
            )
            candidate_state: ReleaseManifestState = (
                "planned" if prepared_manifest is not None else "not-created"
            )
            report = _build_report(
                audit,
                package_id=selected_package_id,
                release_directory=release_directory,
                release_manifest_path=release_manifest_path,
                allow_warnings=allow_warnings,
                dry_run=dry_run,
                manifest_state=candidate_state,
                gates=gates,
                release_manifest=prepared_manifest,
            )
            if not report.valid and candidate_state == "planned":
                report = _build_report(
                    audit,
                    package_id=selected_package_id,
                    release_directory=release_directory,
                    release_manifest_path=release_manifest_path,
                    allow_warnings=allow_warnings,
                    dry_run=dry_run,
                    manifest_state=manifest_state,
                    gates=gates,
                    release_manifest=prepared_manifest,
                )
            if report.valid and prepared_manifest is not None:
                manifest_state = (
                    "planned"
                    if dry_run
                    else self._persist_manifest(release_manifest_path, prepared_manifest)
                )
                report = _build_report(
                    audit,
                    package_id=selected_package_id,
                    release_directory=release_directory,
                    release_manifest_path=release_manifest_path,
                    allow_warnings=allow_warnings,
                    dry_run=dry_run,
                    manifest_state=manifest_state,
                    gates=gates,
                    release_manifest=prepared_manifest,
                )
            return ReleaseVerificationResult(report=report)

    def _select_index(
        self,
        release_directory: RepositoryPath,
        *,
        package_id: str | None,
    ) -> tuple[RepositoryPath, str]:
        if package_id is not None:
            return release_directory.child(f"{package_id}.index.json"), package_id
        try:
            paths = self._scanner.list_paths(suffix=".index.json")
        except PackageManifestScanError as error:
            raise ReleaseVerificationInputError(str(error)) from error
        prefix = f"{release_directory.value}/"
        candidates = tuple(
            path for path in paths if path.startswith(prefix) and "/" not in path[len(prefix) :]
        )
        if len(candidates) != 1:
            raise ReleaseVerificationInputError(
                "release verification requires exactly one package index; "
                "use --package-id when the directory contains multiple releases"
            )
        index_path = RepositoryPath.parse(candidates[0])
        candidate_id = PurePosixPath(candidates[0]).name.removesuffix(".index.json")
        try:
            validate_slug(candidate_id)
        except ValueError as error:
            raise ReleaseVerificationInputError(
                "the package index filename must contain a valid package ID"
            ) from error
        return index_path, candidate_id

    def _verify_package(
        self,
        release_directory: RepositoryPath,
        index_path: RepositoryPath,
        package_id: str,
        release_manifest_path: RepositoryPath,
        project_id: str,
        gates: list[ReleaseGateContract],
    ) -> _PackageFacts | None:
        index_snapshot = _load_json(
            self._filesystem,
            index_path,
            PackageIndexContract,
            max_bytes=RELEASE_INDEX_MAX_BYTES,
        )
        if index_snapshot is None:
            gates.append(
                _gate(
                    "package-index",
                    "failed",
                    "the package index is missing or invalid",
                    (index_path.value,),
                )
            )
            gates.extend(
                (
                    _gate(
                        "package-manifest",
                        "failed",
                        "the package manifest cannot be located without a valid index",
                        (index_path.value,),
                    ),
                    _gate(
                        "package-archive",
                        "failed",
                        "the package archive cannot be located without a valid index",
                        (index_path.value,),
                    ),
                    _gate(
                        "package-checksums",
                        "failed",
                        "package checksums cannot be verified without a valid index",
                        (index_path.value,),
                    ),
                )
            )
            return None

        index = index_snapshot.value
        index_gate_ok = index_snapshot.canonical
        expected_index_path = release_directory.child(f"{package_id}.index.json")
        expected_archive_path = release_directory.child(f"{package_id}.zip")
        index_details: list[str] = []
        if not index_snapshot.canonical:
            index_details.append("the package index is not canonical JSON")
        if index.package_id != package_id:
            index_gate_ok = False
            index_details.append("package ID differs from the selected release")
        if index.project_id != project_id:
            index_gate_ok = False
            index_details.append("project ID differs from the audited project")
        if index.index_path != expected_index_path.value:
            index_gate_ok = False
            index_details.append("declared index path differs from the release target")
        if index.archive_path != expected_archive_path.value:
            index_gate_ok = False
            index_details.append("declared archive path differs from the release target")
        try:
            reread_index_payload = self._filesystem.read_bytes(
                index_path,
                max_bytes=RELEASE_INDEX_MAX_BYTES,
            )
        except (FileNotFoundError, ProjectFilesystemError) as error:
            index_gate_ok = False
            index_payload = None
            index_details.append(f"package index cannot be reread safely: {error}")
        else:
            index_payload = reread_index_payload
            if hashlib.sha256(reread_index_payload).hexdigest() != index_snapshot.digest:
                index_gate_ok = False
                index_details.append("package index changed during verification")
        gates.append(
            _gate(
                "package-index",
                "passed" if index_gate_ok else "failed",
                (
                    "; ".join(index_details)
                    if index_details
                    else "package index is canonical and targets this release"
                ),
                (index_path.value,),
            )
        )

        manifest_path = _repository_path(index.manifest_path)
        manifest_snapshot = (
            _load_json(
                self._filesystem,
                manifest_path,
                PackageManifestContract,
                max_bytes=RELEASE_MANIFEST_MAX_BYTES,
            )
            if manifest_path is not None
            else None
        )
        manifest_gate_ok = manifest_snapshot is not None
        manifest_details: list[str] = []
        manifest_payload: bytes | None = None
        if manifest_snapshot is None:
            manifest_details.append("the package manifest is missing or invalid")
        else:
            manifest = manifest_snapshot.value
            if manifest_path is not None:
                try:
                    manifest_payload = self._filesystem.read_bytes(
                        manifest_path,
                        max_bytes=RELEASE_MANIFEST_MAX_BYTES,
                    )
                except (FileNotFoundError, ProjectFilesystemError) as error:
                    manifest_gate_ok = False
                    manifest_details.append(f"package manifest cannot be reread safely: {error}")
                else:
                    if hashlib.sha256(manifest_payload).hexdigest() != manifest_snapshot.digest:
                        manifest_gate_ok = False
                        manifest_details.append("package manifest changed during verification")
            if not manifest_snapshot.canonical:
                manifest_gate_ok = False
                manifest_details.append("the package manifest is not canonical JSON")
            if manifest.project_id != index.project_id:
                manifest_gate_ok = False
                manifest_details.append("package manifest project differs from package index")
            if manifest.package_id != index.package_id:
                manifest_gate_ok = False
                manifest_details.append("package manifest package differs from package index")
            if manifest.manifest_path != index.manifest_path:
                manifest_gate_ok = False
                manifest_details.append("package manifest path differs from package index")
            if manifest_snapshot.digest != index.manifest_sha256:
                manifest_gate_ok = False
                manifest_details.append("package manifest checksum differs from package index")
            if release_manifest_path.value in {item.path for item in manifest.included_files}:
                manifest_gate_ok = False
                manifest_details.append(
                    "release checksum manifest cannot be included in its own package"
                )
        gates.append(
            _gate(
                "package-manifest",
                "passed" if manifest_gate_ok else "failed",
                (
                    "; ".join(manifest_details)
                    if manifest_details
                    else "package manifest is canonical and matches the index"
                ),
                (index.manifest_path,),
            )
        )

        try:
            archive_snapshot, archive_payload = self._scanner.read_file(
                index.archive_path,
                max_bytes=PACKAGE_ARCHIVE_MAX_BYTES,
            )
        except (FileNotFoundError, PackageManifestScanError, ProjectFilesystemError) as error:
            gates.append(_gate("package-archive", "failed", str(error), (index.archive_path,)))
            gates.append(
                _gate(
                    "package-checksums",
                    "failed",
                    "package checksums cannot be verified without a readable archive",
                    (index.archive_path, index_path.value),
                )
            )
            return None
        try:
            inspection = PackageArchiveBuilder().inspect(archive_payload)
        except PackageArchiveError as error:
            gates.append(_gate("package-archive", "failed", str(error), (index.archive_path,)))
            gates.append(
                _gate(
                    "package-checksums",
                    "failed",
                    "package checksums cannot be verified for an invalid archive",
                    (index.archive_path, index_path.value),
                )
            )
            return None
        archive_gate_ok = inspection.result.member_count == index.archive_member_count
        archive_detail = (
            "package archive is canonical and has the indexed member count"
            if archive_gate_ok
            else "package archive member count differs from package index"
        )
        gates.append(
            _gate(
                "package-archive",
                "passed" if archive_gate_ok else "failed",
                archive_detail,
                (index.archive_path,),
            )
        )

        if (
            manifest_snapshot is None
            or manifest_path is None
            or manifest_payload is None
            or index_payload is None
        ):
            gates.append(
                _gate(
                    "package-checksums",
                    "failed",
                    "package checksums cannot be cross-checked without a valid manifest",
                    (index.manifest_path, index_path.value, index.archive_path),
                )
            )
            return None

        checksum_ok, checksum_detail = _check_package_contents(
            index,
            index_payload=index_payload,
            manifest_payload=manifest_payload,
            manifest=manifest_snapshot.value,
            archive_entries=inspection.entries,
        )
        gates.append(
            _gate(
                "package-checksums",
                "passed" if checksum_ok else "failed",
                checksum_detail,
                (index.manifest_path, index_path.value, index.archive_path),
            )
        )
        if not (manifest_gate_ok and index_gate_ok and archive_gate_ok and checksum_ok):
            return None
        return _PackageFacts(
            manifest=manifest_snapshot.value,
            manifest_payload=manifest_payload,
            manifest_digest=manifest_snapshot.digest,
            manifest_size=manifest_snapshot.size_bytes,
            index=index,
            index_payload=index_payload,
            index_digest=index_snapshot.digest,
            index_size=index_snapshot.size_bytes,
            archive_payload=archive_payload,
            archive_digest=archive_snapshot.sha256,
            archive_size=archive_snapshot.size_bytes,
            archive_entries=inspection.entries,
        )

    def _persist_manifest(
        self,
        path: RepositoryPath,
        manifest: ReleaseManifestContract,
    ) -> Literal["created", "unchanged"]:
        repository = JsonDocumentRepository(
            self._filesystem,
            path,
            ReleaseManifestContract,
            max_bytes=RELEASE_MANIFEST_MAX_BYTES,
        )
        payload = repository.canonical_bytes(manifest)
        try:
            existing = self._filesystem.read_bytes(path, max_bytes=RELEASE_MANIFEST_MAX_BYTES)
        except FileNotFoundError:
            existing = None
        except ProjectFilesystemError as error:
            raise ReleaseVerificationConflictError(
                f"release manifest target is not safely readable: {path}"
            ) from error
        if existing is not None:
            if existing == payload:
                return "unchanged"
            raise ReleaseVerificationConflictError(
                f"release manifest already exists with different content: {path}"
            )
        try:
            self._filesystem.write_bytes(path, payload)
        except OSError as error:
            raise ReleaseVerificationError(
                f"release manifest could not be written: {path}"
            ) from error
        return "created"


def _audit_project(filesystem: ProjectFilesystem) -> ProjectAuditResult:
    try:
        return ProjectAuditService(filesystem).audit(dry_run=True)
    except ProjectAuditConflictError:
        raise
    except ProjectAuditCorruptError:
        raise
    except ProjectAuditError:
        raise


def _load_json[TContract: ContractModel](
    filesystem: ProjectFilesystem,
    path: RepositoryPath | None,
    model: type[TContract],
    *,
    max_bytes: int,
) -> StructuredDocumentSnapshot[TContract] | None:
    if path is None:
        return None
    try:
        return JsonDocumentRepository(
            filesystem,
            path,
            model,
            max_bytes=max_bytes,
        ).load()
    except (FileNotFoundError, ProjectFilesystemError, StructuredDocumentError, ValidationError):
        return None


def _repository_path(path: str) -> RepositoryPath | None:
    try:
        return RepositoryPath.parse(path)
    except ProjectFilesystemError:
        return None


def _project_audit_gate(report: ProjectAuditReportContract) -> ReleaseGateContract:
    error_count = report.error_count
    warning_count = report.warning_count
    state: ReleaseGateState = "failed" if error_count else "warning" if warning_count else "passed"
    detail = (
        "project audit contains blocking findings"
        if error_count
        else "project audit contains warnings"
        if warning_count
        else "project audit has no findings"
    )
    return _gate("project-audit", state, detail)


def _build_release_manifest(
    facts: _PackageFacts,
    *,
    project_id: str,
    release_directory: RepositoryPath,
    release_manifest_path: RepositoryPath,
) -> ReleaseManifestContract:
    return ReleaseManifestContract(
        project_id=project_id,
        package_id=facts.index.package_id,
        release_directory=release_directory.value,
        release_manifest_path=release_manifest_path.value,
        archive_member_count=facts.index.archive_member_count,
        artifacts=(
            ReleaseArtifactContract(
                kind="package-manifest",
                path=facts.index.manifest_path,
                size_bytes=facts.manifest_size,
                sha256=facts.manifest_digest,
            ),
            ReleaseArtifactContract(
                kind="package-index",
                path=facts.index.index_path,
                size_bytes=facts.index_size,
                sha256=facts.index_digest,
            ),
            ReleaseArtifactContract(
                kind="package-archive",
                path=facts.index.archive_path,
                size_bytes=facts.archive_size,
                sha256=facts.archive_digest,
            ),
        ),
    )


def _append_release_manifest_gate(
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
    prepared: ReleaseManifestContract | None,
    gates: list[ReleaseGateContract],
) -> None:
    if prepared is None:
        gates.append(
            _gate(
                "release-manifest",
                "failed",
                "a checksum manifest cannot be prepared until package artifacts pass",
                (path.value,),
            )
        )
        return
    package_manifest = next(gate for gate in gates if gate.code == "package-manifest")
    if package_manifest.state != "passed":
        gates.append(
            _gate(
                "release-manifest",
                "failed",
                "the release manifest cannot be prepared from a failed package manifest gate",
                (path.value,),
            )
        )
        return
    try:
        existing = filesystem.read_bytes(path, max_bytes=RELEASE_MANIFEST_MAX_BYTES)
    except FileNotFoundError:
        gates.append(
            _gate(
                "release-manifest",
                "passed",
                "checksum manifest is ready to create",
                (path.value,),
            )
        )
        return
    except ProjectFilesystemError as error:
        gates.append(_gate("release-manifest", "failed", str(error), (path.value,)))
        return
    expected = JsonDocumentRepository(
        filesystem,
        path,
        ReleaseManifestContract,
        max_bytes=RELEASE_MANIFEST_MAX_BYTES,
    ).canonical_bytes(prepared)
    if existing == expected:
        gates.append(
            _gate(
                "release-manifest",
                "passed",
                "checksum manifest matches the verified release",
                (path.value,),
            )
        )
    else:
        gates.append(
            _gate(
                "release-manifest",
                "failed",
                "checksum manifest already exists with different content",
                (path.value,),
            )
        )


def _build_report(
    audit: ProjectAuditResult,
    *,
    package_id: str,
    release_directory: RepositoryPath,
    release_manifest_path: RepositoryPath,
    allow_warnings: bool,
    dry_run: bool,
    manifest_state: ReleaseManifestState,
    gates: list[ReleaseGateContract],
    release_manifest: ReleaseManifestContract | None,
) -> ReleaseVerificationReportContract:
    ordered_gates = tuple(sorted(gates, key=lambda gate: gate.code))
    warning_policy: ReleaseWarningPolicy = "allow" if allow_warnings else "block"
    failed = any(gate.state == "failed" for gate in ordered_gates)
    warnings = any(gate.state == "warning" for gate in ordered_gates)
    state: ReleaseVerificationState = (
        "blocked"
        if failed or (warnings and warning_policy == "block")
        else "ready-with-warnings"
        if warnings
        else "ready"
    )
    summary = ReleaseSummaryContract(
        artifact_count=len(release_manifest.artifacts) if release_manifest else 0,
        archive_member_count=(release_manifest.archive_member_count if release_manifest else 0),
        archive_size_bytes=(
            next(
                item.size_bytes
                for item in release_manifest.artifacts
                if item.kind == "package-archive"
            )
            if release_manifest
            else 0
        ),
        audit_error_count=audit.report.error_count,
        audit_warning_count=audit.report.warning_count,
        gate_count=len(ordered_gates),
    )
    return ReleaseVerificationReportContract(
        dry_run=dry_run,
        project_id=audit.report.project_id,
        project_name=audit.report.project_name,
        package_id=package_id,
        release_directory=release_directory.value,
        release_manifest_path=release_manifest_path.value,
        warning_policy=warning_policy,
        audit_state=audit.report.state,
        audit_source_digest=audit.report.source_digest,
        state=state,
        valid=state != "blocked",
        manifest_state=manifest_state,
        summary=summary,
        gates=ordered_gates,
        audit_findings=audit.report.findings,
        release_manifest=release_manifest,
    )


def _check_package_contents(
    index: PackageIndexContract,
    *,
    index_payload: bytes,
    manifest_payload: bytes,
    manifest: PackageManifestContract,
    archive_entries: tuple[PackageArchiveEntry, ...],
) -> tuple[bool, str]:
    actual_entries = {entry.path: entry.payload for entry in archive_entries}
    expected_paths = {entry.path for entry in index.entries} | {index.archive_index_path}
    if set(actual_entries) != expected_paths:
        return False, "package archive members differ from package index entries"
    internal_manifest = actual_entries.get(index.archive_manifest_path)
    internal_index = actual_entries.get(index.archive_index_path)
    if internal_manifest != manifest_payload:
        return False, "archived package manifest differs from its project source"
    if internal_index != index_payload:
        return False, "archived package index differs from its external index"

    manifest_files = {item.path: (item.size_bytes, item.sha256) for item in manifest.included_files}
    for entry in index.entries:
        payload = actual_entries.get(entry.path)
        if payload is None:
            return False, f"package archive is missing indexed member: {entry.path}"
        if len(payload) != entry.size_bytes or hashlib.sha256(payload).hexdigest() != entry.sha256:
            return False, f"package archive member checksum differs from index: {entry.path}"
        if entry.kind == "project-file":
            if manifest_files.get(entry.source_path) != (entry.size_bytes, entry.sha256):
                return False, f"package index source differs from manifest: {entry.source_path}"
        elif entry.source_path != index.manifest_path:
            return False, "package manifest archive entry has an invalid source path"
    project_paths = {entry.source_path for entry in index.entries if entry.kind == "project-file"}
    if project_paths != set(manifest_files):
        return False, "package index project members differ from package manifest"
    return True, "package manifest, index, archive, and member checksums match"


def _gate(
    code: str,
    state: ReleaseGateState,
    detail: str,
    paths: tuple[str, ...] = (),
) -> ReleaseGateContract:
    return ReleaseGateContract(
        code=code,
        state=state,
        detail=detail,
        paths=tuple(sorted(set(paths))),
    )


def _validate_release_directory(path: RepositoryPath) -> None:
    if path.value == ".ludowright" or path.value.startswith(".ludowright/"):
        raise ReleaseVerificationInputError("release directories must remain outside .ludowright")


__all__ = [
    "RELEASE_INDEX_MAX_BYTES",
    "RELEASE_MANIFEST_MAX_BYTES",
    "RELEASE_VERIFY_LOCK_TIMEOUT",
    "ReleaseVerificationConflictError",
    "ReleaseVerificationCorruptError",
    "ReleaseVerificationError",
    "ReleaseVerificationInputError",
    "ReleaseVerificationResult",
    "ReleaseVerificationService",
]
