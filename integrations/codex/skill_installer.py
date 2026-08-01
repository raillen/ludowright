"""Install and verify the versioned project-local Codex skill."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from ludowright import __version__
from ludowright.contracts import (
    CodexSkillFileContract,
    CodexSkillManifestContract,
    CodexSkillReportContract,
)
from ludowright.infrastructure import ProjectFilesystem, ProjectFilesystemError, RepositoryPath

CODEX_SKILL_INSTALL_PATH = RepositoryPath(".agents/skills/ludowright")
CODEX_SKILL_LOCK_NAME = "codex-skill"
CODEX_SKILL_MANIFEST_FILENAME = "manifest.json"
CODEX_SKILL_MAX_FILE_BYTES = 200_000

SkillState = Literal[
    "planned",
    "installed",
    "already-installed",
    "updated",
    "already-up-to-date",
    "verified",
    "removed",
    "not-installed",
    "outdated",
    "modified",
    "invalid",
    "unsupported",
    "incompatible",
    "conflict",
]


class CodexSkillError(RuntimeError):
    """Base error for the Codex skill lifecycle."""


class CodexSkillDefinitionError(CodexSkillError):
    """Raised when packaged skill data is malformed or incomplete."""


class CodexSkillCompatibilityError(CodexSkillError):
    """Raised when the installed LudoWright version is too old."""


class CodexSkillConflictError(CodexSkillError):
    """Raised when an operation would overwrite or remove unknown content."""


class CodexSkillNotInstalledError(CodexSkillError):
    """Raised when update requires a skill that is not installed."""


class CodexSkillOperationError(CodexSkillError):
    """Raised after a failed write, preserving the original operation cause."""


@dataclass(frozen=True, slots=True)
class CodexSkillSourceFile:
    """One immutable payload loaded from the packaged skill data."""

    path: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class CodexSkillDefinition:
    """Validated skill manifest and its declared payloads."""

    manifest: CodexSkillManifestContract
    files: tuple[CodexSkillSourceFile, ...]

    def __post_init__(self) -> None:
        paths = tuple(item.path for item in self.files)
        declared = tuple(item.path for item in self.manifest.files)
        if paths != declared:
            raise CodexSkillDefinitionError("Codex skill payloads do not match its manifest")
        if len(paths) != len(set(paths)):
            raise CodexSkillDefinitionError("Codex skill payloads must be unique")
        for item in self.files:
            expected = next(file.sha256 for file in self.manifest.files if file.path == item.path)
            if _sha256(item.payload) != expected:
                raise CodexSkillDefinitionError(
                    f"Codex skill payload checksum does not match: {item.path}"
                )

    @property
    def manifest_payload(self) -> bytes:
        """Return the canonical installed manifest bytes."""
        return _canonical_json_bytes(self.manifest.model_dump(mode="json"))

    def payload_map(self) -> dict[str, bytes]:
        """Return a fresh filename-to-payload mapping for one transaction."""
        return {
            CODEX_SKILL_MANIFEST_FILENAME: self.manifest_payload,
            **{item.path: item.payload for item in self.files},
        }


@dataclass(frozen=True, slots=True)
class CodexSkillResult:
    """Stable application result shared by human and JSON presenters."""

    report: CodexSkillReportContract

    def as_data(self) -> dict[str, object]:
        """Return the published command payload."""
        return cast(dict[str, object], self.report.model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class _Inspection:
    state: SkillState
    target_exists: bool
    manifest: CodexSkillManifestContract | None
    manifest_payload: bytes | None
    payloads: tuple[CodexSkillSourceFile, ...]
    warnings: tuple[str, ...]

    @property
    def installed_version(self) -> int | None:
        return None if self.manifest is None else self.manifest.version

    def existing_payload_map(self) -> dict[str, bytes]:
        """Return the exact files that can be restored after a failed write."""
        if self.manifest_payload is None:
            return {}
        return {
            CODEX_SKILL_MANIFEST_FILENAME: self.manifest_payload,
            **{item.path: item.payload for item in self.payloads},
        }


class CodexSkillService:
    """Manage one project-local, versioned `$ludowright` skill."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        definition: CodexSkillDefinition | None = None,
        framework_version: str = __version__,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("Codex skill installation requires ProjectFilesystem")
        self._filesystem = filesystem
        self._definition = definition or load_codex_skill_definition()
        self._framework_version = framework_version
        _assert_framework_compatibility(
            framework_version,
            self._definition.manifest.minimum_ludowright_version,
        )

    @property
    def definition(self) -> CodexSkillDefinition:
        """Return the validated packaged skill definition."""
        return self._definition

    def install(self, *, dry_run: bool = False) -> CodexSkillResult:
        """Install only into an empty target or an identical existing target."""
        if dry_run:
            inspection = self._inspect()
            return self._install_from_inspection(inspection, dry_run=True)
        with self._filesystem.lock(CODEX_SKILL_LOCK_NAME, timeout=5.0):
            return self._install_from_inspection(self._inspect(), dry_run=False)

    def update(self, *, dry_run: bool = False) -> CodexSkillResult:
        """Update an intact older skill without replacing user-modified files."""
        if dry_run:
            inspection = self._inspect()
            return self._update_from_inspection(inspection, dry_run=True)
        with self._filesystem.lock(CODEX_SKILL_LOCK_NAME, timeout=5.0):
            return self._update_from_inspection(self._inspect(), dry_run=False)

    def verify(self) -> CodexSkillResult:
        """Verify installed files, checksums, identity, and source version."""
        inspection = self._inspect()
        return self._result(
            operation="verify",
            state=inspection.state,
            dry_run=False,
            installed_version=inspection.installed_version,
            warnings=inspection.warnings,
            valid=inspection.state == "verified",
        )

    def remove(self, *, dry_run: bool = False) -> CodexSkillResult:
        """Remove only an intact LudoWright skill and leave unrelated files alone."""
        if dry_run:
            inspection = self._inspect()
            return self._remove_from_inspection(inspection, dry_run=True)
        with self._filesystem.lock(CODEX_SKILL_LOCK_NAME, timeout=5.0):
            return self._remove_from_inspection(self._inspect(), dry_run=False)

    def _install_from_inspection(
        self,
        inspection: _Inspection,
        *,
        dry_run: bool,
    ) -> CodexSkillResult:
        if inspection.state == "verified":
            return self._result(
                operation="install",
                state="already-installed",
                dry_run=dry_run,
                installed_version=inspection.installed_version,
                warnings=inspection.warnings,
                valid=True,
            )
        if inspection.state != "not-installed":
            raise CodexSkillConflictError(
                "the Codex skill target is not empty or contains a modified installation; "
                "use update only for an intact older version"
            )
        if dry_run:
            return self._result(
                operation="install",
                state="planned",
                dry_run=True,
                installed_version=None,
                warnings=inspection.warnings,
                valid=True,
            )
        self._write_transaction(
            old_payloads=inspection.existing_payload_map(),
            target_existed=inspection.target_exists,
        )
        return self._result(
            operation="install",
            state="installed",
            dry_run=False,
            installed_version=self._definition.manifest.version,
            warnings=(),
            valid=True,
        )

    def _update_from_inspection(
        self,
        inspection: _Inspection,
        *,
        dry_run: bool,
    ) -> CodexSkillResult:
        if inspection.state == "not-installed":
            raise CodexSkillNotInstalledError("the LudoWright Codex skill is not installed")
        if inspection.state == "verified":
            return self._result(
                operation="update",
                state="already-up-to-date",
                dry_run=dry_run,
                installed_version=inspection.installed_version,
                warnings=inspection.warnings,
                valid=True,
            )
        if inspection.state != "outdated":
            raise CodexSkillConflictError(
                "the installed Codex skill is modified, incompatible, or newer than this package"
            )
        if dry_run:
            return self._result(
                operation="update",
                state="planned",
                dry_run=True,
                installed_version=inspection.installed_version,
                warnings=inspection.warnings,
                valid=True,
            )
        self._write_transaction(
            old_payloads=inspection.existing_payload_map(),
            target_existed=True,
        )
        return self._result(
            operation="update",
            state="updated",
            dry_run=False,
            installed_version=self._definition.manifest.version,
            warnings=(),
            valid=True,
        )

    def _remove_from_inspection(
        self,
        inspection: _Inspection,
        *,
        dry_run: bool,
    ) -> CodexSkillResult:
        if inspection.state == "not-installed":
            if not dry_run and inspection.target_exists:
                self._filesystem.remove_empty_directory(CODEX_SKILL_INSTALL_PATH)
            return self._result(
                operation="remove",
                state="not-installed",
                dry_run=dry_run,
                installed_version=inspection.installed_version,
                warnings=inspection.warnings,
                valid=True,
            )
        if inspection.state not in {"verified", "outdated", "unsupported"}:
            raise CodexSkillConflictError(
                "the installed Codex skill is modified or does not belong to LudoWright"
            )
        if dry_run:
            return self._result(
                operation="remove",
                state="planned",
                dry_run=True,
                installed_version=inspection.installed_version,
                warnings=inspection.warnings,
                valid=True,
            )
        self._remove_transaction(inspection.existing_payload_map())
        return self._result(
            operation="remove",
            state="removed",
            dry_run=False,
            installed_version=inspection.installed_version,
            warnings=(),
            valid=True,
        )

    def _inspect(self) -> _Inspection:
        target_exists = self._filesystem.directory_exists(CODEX_SKILL_INSTALL_PATH)
        if not target_exists:
            return _Inspection("not-installed", False, None, None, (), ())

        filenames = self._filesystem.list_child_files(CODEX_SKILL_INSTALL_PATH)
        if not filenames:
            return _Inspection("not-installed", True, None, None, (), ())
        if CODEX_SKILL_MANIFEST_FILENAME not in filenames:
            return _Inspection(
                "invalid",
                True,
                None,
                None,
                (),
                ("installed skill manifest is missing",),
            )

        manifest_payload = self._read_installed_file(CODEX_SKILL_MANIFEST_FILENAME)
        try:
            manifest = CodexSkillManifestContract.model_validate(
                json.loads(manifest_payload.decode("utf-8"), object_pairs_hook=_unique_object)
            )
        except (UnicodeDecodeError, TypeError, ValueError, ValidationError):
            return _Inspection(
                "invalid",
                True,
                None,
                manifest_payload,
                (),
                ("installed skill manifest is invalid",),
            )

        warnings: list[str] = []
        expected_filenames = {
            CODEX_SKILL_MANIFEST_FILENAME,
            *(item.path for item in manifest.files),
        }
        if set(filenames) != expected_filenames:
            warnings.append("installed skill files do not match its manifest")

        payloads: list[CodexSkillSourceFile] = []
        files_intact = set(filenames) == expected_filenames
        for item in manifest.files:
            try:
                payload = self._read_installed_file(item.path)
            except (FileNotFoundError, ProjectFilesystemError):
                files_intact = False
                continue
            payloads.append(CodexSkillSourceFile(path=item.path, payload=payload))
            if _sha256(payload) != item.sha256:
                files_intact = False
        if not files_intact:
            warnings.append("installed skill file checksums do not match its manifest")

        canonical_manifest = _canonical_json_bytes(manifest.model_dump(mode="json"))
        if manifest_payload != canonical_manifest:
            warnings.append("installed skill manifest is not canonical")
            files_intact = False
        if manifest.id != self._definition.manifest.id:
            warnings.append("installed skill ID does not match the LudoWright skill")
            files_intact = False
        if manifest.install_path != self._definition.manifest.install_path:
            warnings.append("installed skill path does not match the canonical path")
            files_intact = False

        ordered_warnings = tuple(sorted(set(warnings)))
        if not files_intact:
            state: SkillState = "modified"
        elif manifest.version < self._definition.manifest.version:
            state = "outdated"
        elif manifest.version > self._definition.manifest.version:
            state = "unsupported"
        elif manifest != self._definition.manifest:
            state = "incompatible"
        else:
            state = "verified"
        return _Inspection(
            state,
            True,
            manifest,
            manifest_payload,
            tuple(sorted(payloads, key=lambda item: item.path)),
            ordered_warnings,
        )

    def _read_installed_file(self, filename: str) -> bytes:
        return self._filesystem.read_child_bytes(
            CODEX_SKILL_INSTALL_PATH,
            filename,
            max_bytes=CODEX_SKILL_MAX_FILE_BYTES,
        )

    def _write_transaction(
        self,
        *,
        old_payloads: dict[str, bytes],
        target_existed: bool,
    ) -> None:
        new_payloads = self._definition.payload_map()
        try:
            for filename in sorted(
                name for name in new_payloads if name != CODEX_SKILL_MANIFEST_FILENAME
            ):
                self._filesystem.write_child_bytes(
                    CODEX_SKILL_INSTALL_PATH,
                    filename,
                    new_payloads[filename],
                )
            for filename in sorted(set(old_payloads) - set(new_payloads)):
                self._filesystem.remove_child_file(CODEX_SKILL_INSTALL_PATH, filename)
            self._filesystem.write_child_bytes(
                CODEX_SKILL_INSTALL_PATH,
                CODEX_SKILL_MANIFEST_FILENAME,
                new_payloads[CODEX_SKILL_MANIFEST_FILENAME],
            )
        except BaseException as error:
            try:
                self._restore_transaction(
                    old_payloads=old_payloads,
                    new_filenames=set(new_payloads),
                    target_existed=target_existed,
                )
            except BaseException as rollback_error:
                raise CodexSkillOperationError(
                    f"Codex skill write failed and rollback also failed: {rollback_error}"
                ) from error
            raise CodexSkillOperationError(
                "Codex skill write failed; previous files were restored"
            ) from error

    def _restore_transaction(
        self,
        *,
        old_payloads: dict[str, bytes],
        new_filenames: set[str],
        target_existed: bool,
    ) -> None:
        for filename in sorted(new_filenames - set(old_payloads)):
            self._filesystem.remove_child_file(CODEX_SKILL_INSTALL_PATH, filename)
        for filename in sorted(old_payloads):
            self._filesystem.write_child_bytes(
                CODEX_SKILL_INSTALL_PATH,
                filename,
                old_payloads[filename],
            )
        if not target_existed:
            self._filesystem.remove_empty_directory(CODEX_SKILL_INSTALL_PATH)

    def _remove_transaction(self, old_payloads: dict[str, bytes]) -> None:
        try:
            for filename in sorted(
                (name for name in old_payloads if name != CODEX_SKILL_MANIFEST_FILENAME),
                reverse=True,
            ):
                self._filesystem.remove_child_file(CODEX_SKILL_INSTALL_PATH, filename)
            self._filesystem.remove_child_file(
                CODEX_SKILL_INSTALL_PATH,
                CODEX_SKILL_MANIFEST_FILENAME,
            )
            self._filesystem.remove_empty_directory(CODEX_SKILL_INSTALL_PATH)
        except BaseException as error:
            try:
                for filename in sorted(old_payloads):
                    self._filesystem.write_child_bytes(
                        CODEX_SKILL_INSTALL_PATH,
                        filename,
                        old_payloads[filename],
                    )
            except BaseException as rollback_error:
                raise CodexSkillOperationError(
                    f"Codex skill removal failed and rollback also failed: {rollback_error}"
                ) from error
            raise CodexSkillOperationError(
                "Codex skill removal failed; previous files were restored"
            ) from error

    def _result(
        self,
        *,
        operation: Literal["install", "update", "verify", "remove"],
        state: SkillState,
        dry_run: bool,
        installed_version: int | None,
        warnings: tuple[str, ...],
        valid: bool,
    ) -> CodexSkillResult:
        source_files = (
            CodexSkillFileContract(
                path=CODEX_SKILL_MANIFEST_FILENAME,
                sha256=_sha256(self._definition.manifest_payload),
            ),
            *(
                CodexSkillFileContract(path=item.path, sha256=_sha256(item.payload))
                for item in self._definition.files
            ),
        )
        report = CodexSkillReportContract(
            operation=operation,
            state=state,
            dry_run=dry_run,
            skill_id=self._definition.manifest.id,
            skill_version=self._definition.manifest.version,
            installed_version=installed_version,
            install_path=self._definition.manifest.install_path,
            framework_version=self._framework_version,
            files=tuple(sorted(source_files, key=lambda item: item.path)),
            warnings=tuple(sorted(set(warnings))),
            valid=valid,
        )
        return CodexSkillResult(report=report)


def load_codex_skill_definition() -> CodexSkillDefinition:
    """Load and validate the packaged Codex skill data."""
    manifest_payload = _read_skill_resource(CODEX_SKILL_MANIFEST_FILENAME)
    try:
        manifest = CodexSkillManifestContract.model_validate(
            json.loads(manifest_payload.decode("utf-8"), object_pairs_hook=_unique_object)
        )
    except (UnicodeDecodeError, TypeError, ValueError, ValidationError) as error:
        raise CodexSkillDefinitionError("packaged Codex skill manifest is invalid") from error

    files: list[CodexSkillSourceFile] = []
    for item in manifest.files:
        try:
            payload = _read_skill_resource(item.path)
        except (FileNotFoundError, OSError) as error:
            raise CodexSkillDefinitionError(
                f"packaged Codex skill file is missing: {item.path}"
            ) from error
        files.append(CodexSkillSourceFile(path=item.path, payload=payload))
    return CodexSkillDefinition(manifest=manifest, files=tuple(files))


def _read_skill_resource(filename: str) -> bytes:
    source_root = Path(__file__).resolve().parent / "skills/ludowright"
    payload = (source_root / filename).read_bytes()
    if len(payload) > CODEX_SKILL_MAX_FILE_BYTES:
        raise CodexSkillDefinitionError(
            f"packaged Codex skill file exceeds the size limit: {filename}"
        )
    return payload


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


_VERSION_PATTERN = re.compile(
    r"^(?P<release>\d+(?:\.\d+){1,3})(?:[.-](?P<phase>dev|a|b|rc)(?P<serial>\d+))?$"
)
_PHASE_ORDER = {"dev": 0, "a": 1, "b": 2, "rc": 3}


def _version_key(value: str) -> tuple[tuple[int, ...], int, int]:
    match = _VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise CodexSkillDefinitionError(f"unsupported LudoWright version format: {value!r}")
    release = tuple(int(part) for part in match.group("release").split("."))
    padded_release = (*release, 0, 0, 0, 0)[:4]
    phase = match.group("phase")
    return (
        padded_release,
        4 if phase is None else _PHASE_ORDER[phase],
        0 if phase is None else int(match.group("serial")),
    )


def _assert_framework_compatibility(current: str, minimum: str) -> None:
    if _version_key(current) < _version_key(minimum):
        raise CodexSkillCompatibilityError(
            f"Codex skill requires LudoWright >= {minimum}; installed version is {current}"
        )
