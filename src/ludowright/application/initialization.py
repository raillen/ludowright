"""Create a new local-first LudoWright project as one bounded use case."""

from __future__ import annotations

import hashlib
import os
import shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ludowright.application.templates import TemplateNotFoundError, load_template
from ludowright.contracts import (
    ProjectContract,
    TemplateDefinitionContract,
    TemplateSelectionContract,
)
from ludowright.domain import (
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    ProjectId,
    RevisionVersion,
)
from ludowright.infrastructure import (
    LOCK_DIRECTORY,
    PROJECT_MARKER,
    DependencyGraphRepository,
    EventLog,
    IndexedEntity,
    ProjectFilesystem,
    ProjectFilesystemError,
    ProjectLockTimeoutError,
    RepositoryPath,
    StateStore,
)
from ludowright.infrastructure.structured import JsonDocumentRepository

_INITIALIZATION_LOCK = "project-initialize"


class ProjectInitializationError(RuntimeError):
    """Base failure for the project initialization use case."""


class ProjectInitializationInputError(ProjectInitializationError):
    """Raised when a name, template, or target path is invalid."""


class ProjectInitializationConflictError(ProjectInitializationError):
    """Raised when initialization would overwrite an existing target."""


class ProjectInitializationFailureError(ProjectInitializationError):
    """Raised after a partial initialization was rolled back."""


@dataclass(frozen=True, slots=True)
class ProjectInitializationResult:
    """Stable result shared by human and machine CLI renderers."""

    project_directory: str
    project_id: str
    template_id: str
    template_version: int
    files: tuple[str, ...]
    directories: tuple[str, ...]
    schema_version: int
    dry_run: bool
    warnings: tuple[str, ...]
    state: str

    def as_data(self) -> dict[str, object]:
        """Return JSON-compatible command data."""
        return {
            "directories": list(self.directories),
            "dry_run": self.dry_run,
            "files": list(self.files),
            "project_directory": self.project_directory,
            "project_id": self.project_id,
            "schema_version": self.schema_version,
            "state": self.state,
            "template": {
                "id": self.template_id,
                "version": self.template_version,
            },
            "warnings": list(self.warnings),
        }


class ProjectInitializationService:
    """Orchestrate safe, deterministic creation of one new project."""

    def initialize(
        self,
        target: Path | str,
        *,
        name: str,
        template_id: str = "minimal",
        dry_run: bool = False,
    ) -> ProjectInitializationResult:
        """Plan or create one project without modifying an existing target."""
        template = self._load_template(template_id)
        project = self._build_project(name, template)
        target_path = _validate_target_path(target)
        existing = _inspect_target(target_path)
        if existing == "occupied":
            raise ProjectInitializationConflictError(
                f"project target is not empty and will not be overwritten: {target_path}"
            )
        result = self._planned_result(target_path, project.id, template, dry_run=dry_run)
        if dry_run:
            return result

        created_target = not target_path.exists()
        _ensure_parent_directory(target_path.parent)
        if created_target:
            try:
                target_path.mkdir()
            except FileExistsError:
                raise ProjectInitializationConflictError(
                    f"project target was created concurrently: {target_path}"
                ) from None

        filesystem = ProjectFilesystem(target_path)
        lock_acquired = False
        try:
            filesystem.ensure_directory(LOCK_DIRECTORY, mode=0o700)
            with filesystem.lock(_INITIALIZATION_LOCK, timeout=0.0):
                lock_acquired = True
                try:
                    self._create_project(filesystem, project, template)
                except ProjectInitializationError:
                    raise
                except BaseException as error:
                    raise ProjectInitializationFailureError(
                        "project initialization failed and was rolled back"
                    ) from error
        except ProjectLockTimeoutError as error:
            raise ProjectInitializationConflictError(
                f"project initialization is already running: {target_path}"
            ) from error
        except BaseException:
            if lock_acquired or existing == "empty" or created_target:
                _rollback_project(target_path, template, remove_target=created_target)
            raise

        return result.__class__(
            project_directory=result.project_directory,
            project_id=result.project_id,
            template_id=result.template_id,
            template_version=result.template_version,
            files=result.files,
            directories=result.directories,
            schema_version=result.schema_version,
            dry_run=False,
            warnings=result.warnings,
            state="created",
        )

    @staticmethod
    def _load_template(template_id: str) -> TemplateDefinitionContract:
        try:
            return load_template(template_id)
        except TemplateNotFoundError as error:
            raise ProjectInitializationInputError(str(error)) from error

    @staticmethod
    def _build_project(name: str, template: TemplateDefinitionContract) -> ProjectContract:
        try:
            project_id = ProjectId.from_name(name)
            return ProjectContract(
                id=project_id.value,
                name=name,
                dimensions=template.project_defaults.dimensions,
                targets=template.project_defaults.targets,
                template=TemplateSelectionContract(
                    id=template.id,
                    version=template.version,
                ),
            )
        except (TypeError, ValueError) as error:
            raise ProjectInitializationInputError(f"invalid project name: {name!r}") from error

    @staticmethod
    def _planned_result(
        target: Path,
        project_id: str,
        template: TemplateDefinitionContract,
        *,
        dry_run: bool,
    ) -> ProjectInitializationResult:
        return ProjectInitializationResult(
            project_directory=target.as_posix(),
            project_id=project_id,
            template_id=template.id,
            template_version=template.version,
            files=tuple(sorted(item.path for item in template.files)),
            directories=tuple(sorted(template.directories)),
            schema_version=1,
            dry_run=dry_run,
            warnings=(),
            state="planned",
        )

    @staticmethod
    def _create_project(
        filesystem: ProjectFilesystem,
        project: ProjectContract,
        template: TemplateDefinitionContract,
    ) -> None:
        paths = {item.role: RepositoryPath(item.path) for item in template.files}
        if paths["manifest"] != PROJECT_MARKER:
            raise ProjectFilesystemError(
                "the initialization manifest must use the canonical project marker path"
            )
        for directory in sorted(template.directories):
            filesystem.ensure_directory(RepositoryPath(directory))

        event_log = EventLog(filesystem, paths["event-log"])
        filesystem.write_bytes(paths["event-log"], b"")
        event_snapshot = event_log.replay()

        graph = DependencyGraph.empty().add_node(
            DependencyNode(
                key=DependencyKey(DependencyNodeKind.PROJECT, project.id),
                revision=RevisionVersion(1),
            )
        )
        graph_repository = DependencyGraphRepository(filesystem, paths["dependency-graph"])
        graph_repository.create(graph)

        state_store = StateStore(filesystem, paths["state-store"])
        timestamp = datetime.now(UTC)
        state_store.record_event_checkpoint(event_snapshot, updated_at=timestamp)

        manifest_path = paths["manifest"]
        manifest_repository = JsonDocumentRepository(filesystem, manifest_path, ProjectContract)
        manifest_payload = manifest_repository.canonical_bytes(project)
        state_store.index_entity(
            IndexedEntity(
                entity_type="project",
                entity_id=project.id,
                source_path=manifest_path,
                source_digest=hashlib.sha256(manifest_payload).hexdigest(),
                revision=1,
                status="active",
                updated_at=timestamp,
            )
        )

        # The marker is deliberately the final write. Discovery therefore never
        # treats a project with incomplete infrastructure as valid.
        filesystem.write_bytes(manifest_path, manifest_payload)
        manifest_repository.load()
        graph_repository.load()
        validated_snapshot = event_log.replay()
        if not state_store.check_consistency(validated_snapshot).is_consistent:
            raise ProjectFilesystemError("initialized project state is inconsistent")
        if state_store.get_entity("project", project.id) is None:
            raise ProjectFilesystemError("initialized project manifest was not indexed")


def _validate_target_path(target: Path | str) -> Path:
    try:
        path = Path(target).expanduser()
    except (OSError, TypeError, ValueError) as error:
        raise ProjectInitializationInputError("project path is invalid") from error
    if "\x00" in str(path) or any(part == ".." for part in path.parts):
        raise ProjectInitializationInputError("project path cannot contain traversal")
    if not path.is_absolute():
        path = Path.cwd() / path
    path = Path(os.path.abspath(path))
    _reject_symlink_components(path)
    if path.exists() and not path.is_dir():
        raise ProjectInitializationConflictError(f"project target is not a directory: {path}")
    return path


def _inspect_target(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        next(path.iterdir())
    except StopIteration:
        return "empty"
    except OSError as error:
        raise ProjectInitializationInputError("project target cannot be inspected") from error
    return "occupied"


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts:
        if part == path.anchor:
            continue
        current /= part
        if os.path.lexists(current) and current.is_symlink():
            raise ProjectInitializationInputError(
                f"project path cannot contain symlinks: {current}"
            )


def _ensure_parent_directory(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            raise ProjectInitializationInputError("project path has no usable parent")
        current = parent
    if current.is_symlink() or not current.is_dir():
        raise ProjectInitializationInputError("project path parent is not a safe directory")
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            if directory.is_symlink() or not directory.is_dir():
                raise ProjectInitializationInputError(
                    "project path parent changed during creation"
                ) from None


def _rollback_project(
    target: Path,
    template: TemplateDefinitionContract,
    *,
    remove_target: bool,
) -> None:
    if remove_target:
        if target.exists() and target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        return
    root = target / ".ludowright"
    if root.exists() and root.is_dir() and not root.is_symlink():
        shutil.rmtree(root)
    for directory in sorted(template.directories, key=len, reverse=True):
        candidate = target / Path(directory)
        if candidate.exists() and candidate.is_dir() and not candidate.is_symlink():
            with suppress(OSError):
                candidate.rmdir()
