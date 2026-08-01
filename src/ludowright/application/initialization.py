"""Create a new local-first LudoWright project as one bounded use case."""

from __future__ import annotations

import hashlib
import os
import stat
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
    PROJECT_MARKER,
    STATE_SCHEMA_VERSION,
    DependencyGraphRepository,
    EventLog,
    IndexedEntity,
    ProjectFilesystem,
    ProjectLockTimeoutError,
    RepositoryPath,
    StateStore,
)
from ludowright.infrastructure.structured import JsonDocumentRepository

_INITIALIZATION_LOCK = "project-initialize"
_SQLITE_SIDECARS = ("-journal", "-shm", "-wal")


class ProjectInitializationError(RuntimeError):
    """Base failure for project initialization."""


class ProjectInitializationInputError(ProjectInitializationError):
    """Raised when initialization input is invalid or unsafe."""


class ProjectInitializationConflictError(ProjectInitializationError):
    """Raised when initialization would collide with existing state."""


class ProjectInitializationFailureError(ProjectInitializationError):
    """Raised when initialization fails after mutation has started."""


@dataclass(frozen=True, slots=True)
class ProjectInitializationResult:
    """Stable result shared by human and JSON CLI renderers."""

    project_directory: str
    project_id: str
    template_id: str
    template_version: int
    files: tuple[str, ...]
    directories: tuple[str, ...]
    schema_version: int
    state_store_schema_version: int
    dry_run: bool
    warnings: tuple[str, ...]
    state: str

    def as_data(self) -> dict[str, object]:
        """Return the published CLI data shape in stable key/value types."""
        return {
            "directories": list(self.directories),
            "dry_run": self.dry_run,
            "files": list(self.files),
            "project_directory": self.project_directory,
            "project_id": self.project_id,
            "schema_version": self.schema_version,
            "state": self.state,
            "state_store_schema_version": self.state_store_schema_version,
            "template": {"id": self.template_id, "version": self.template_version},
            "warnings": list(self.warnings),
        }


class ProjectInitializationService:
    """Create one valid project with create-only and rollback-safe semantics."""

    def initialize(
        self,
        target: Path | str,
        *,
        name: str,
        template_id: str = "minimal",
        dry_run: bool = False,
    ) -> ProjectInitializationResult:
        """Plan or create a project without overwriting an existing target."""
        template = self._load_template(template_id)
        project = self._build_project(name, template)
        target_path = self._validate_target_path(target)
        target_state = self._inspect_target(target_path)
        if target_state == "occupied":
            raise ProjectInitializationConflictError(
                f"project directory is not empty: {target_path}"
            )

        result = self._planned_result(target_path, template, project.id)
        if dry_run:
            return result

        created_target = False
        created_parents: tuple[Path, ...] = ()
        try:
            created_parents = self._ensure_parent_directory(target_path.parent)
            if target_path.exists():
                if not target_path.is_dir() or self._inspect_target(target_path) != "empty":
                    raise ProjectInitializationConflictError(
                        f"project directory appeared during initialization: {target_path}"
                    )
            else:
                try:
                    target_path.mkdir()
                    created_target = True
                except FileExistsError:
                    raise ProjectInitializationConflictError(
                        f"project directory appeared during initialization: {target_path}"
                    ) from None

            filesystem = ProjectFilesystem(target_path)
            with filesystem.lock(_INITIALIZATION_LOCK, timeout=0.0):
                self._create_project(filesystem, template, project)
        except ProjectLockTimeoutError as error:
            raise ProjectInitializationConflictError(
                f"project initialization is already in progress: {target_path}"
            ) from error
        except ProjectInitializationConflictError:
            raise
        except BaseException as error:
            self._rollback_project(target_path, template, remove_target=created_target)
            self._remove_empty_parent_directories(created_parents)
            if isinstance(error, ProjectInitializationFailureError):
                raise
            raise ProjectInitializationFailureError(
                f"project initialization failed and was rolled back: {target_path}"
            ) from error

        return ProjectInitializationResult(
            project_directory=result.project_directory,
            project_id=result.project_id,
            template_id=result.template_id,
            template_version=result.template_version,
            files=result.files,
            directories=result.directories,
            schema_version=result.schema_version,
            state_store_schema_version=result.state_store_schema_version,
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
        except RuntimeError as error:
            raise ProjectInitializationFailureError(str(error)) from error

    @staticmethod
    def _build_project(name: str, template: TemplateDefinitionContract) -> ProjectContract:
        if not isinstance(name, str):
            raise ProjectInitializationInputError("project name must be text")
        try:
            project_id = ProjectId.from_name(name)
            project = ProjectContract(
                id=project_id.value,
                name=name,
                dimensions=template.project_defaults.dimensions,
                targets=template.project_defaults.targets,
                template=TemplateSelectionContract(
                    id=template.id,
                    version=template.version,
                ),
            )
            project.to_domain()
            return project
        except (TypeError, ValueError) as error:
            raise ProjectInitializationInputError(f"project name is invalid: {name!r}") from error

    @staticmethod
    def _validate_target_path(target: Path | str) -> Path:
        if not isinstance(target, (Path, str)):
            raise ProjectInitializationInputError("project path must be text or a Path")
        raw_target = str(target)
        if not raw_target or "\x00" in raw_target:
            raise ProjectInitializationInputError("project path is invalid")
        if os.name != "nt" and "\\" in raw_target:
            raise ProjectInitializationInputError(
                "project path must use the host platform separator"
            )
        candidate = Path(target).expanduser()
        if any(part == ".." for part in candidate.parts):
            raise ProjectInitializationInputError("project path cannot contain dot traversal")
        absolute = Path(os.path.abspath(candidate))
        ProjectInitializationService._reject_symlink_components(absolute)
        if os.path.lexists(absolute) and not stat.S_ISDIR(absolute.lstat().st_mode):
            raise ProjectInitializationConflictError(
                f"project target is not a directory: {absolute}"
            )
        return absolute

    @staticmethod
    def _reject_symlink_components(path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:] if path.anchor else path.parts:
            current /= part
            if os.path.lexists(current) and current.is_symlink():
                raise ProjectInitializationInputError(f"project path contains a symlink: {current}")

    @staticmethod
    def _inspect_target(target: Path) -> str:
        if not os.path.lexists(target):
            return "missing"
        if target.is_symlink():
            raise ProjectInitializationInputError(f"project target cannot be a symlink: {target}")
        if not target.is_dir():
            raise ProjectInitializationConflictError(f"project target is not a directory: {target}")
        try:
            next(target.iterdir())
        except StopIteration:
            return "empty"
        except OSError as error:
            raise ProjectInitializationInputError(
                f"cannot inspect project target: {target}"
            ) from error
        return "occupied"

    @staticmethod
    def _ensure_parent_directory(parent: Path) -> tuple[Path, ...]:
        ProjectInitializationService._reject_symlink_components(parent)
        missing: list[Path] = []
        current = parent
        while not os.path.lexists(current):
            missing.append(current)
            if current.parent == current:
                break
            current = current.parent
        for existing in (current, *reversed(missing)):
            if os.path.lexists(existing):
                if existing.is_symlink() or not existing.is_dir():
                    raise ProjectInitializationInputError(
                        f"project parent is not a safe directory: {existing}"
                    )
            else:
                try:
                    existing.mkdir()
                except FileExistsError:
                    if existing.is_symlink() or not existing.is_dir():
                        raise ProjectInitializationInputError(
                            f"project parent changed during creation: {existing}"
                        ) from None
        return tuple(reversed(missing))

    def _create_project(
        self,
        filesystem: ProjectFilesystem,
        template: TemplateDefinitionContract,
        project: ProjectContract,
    ) -> None:
        paths = {item.role: RepositoryPath(item.path) for item in template.files}
        if paths["manifest"] != PROJECT_MARKER:
            raise ProjectInitializationFailureError(
                "template manifest path must be .ludowright/project.json"
            )

        for directory in sorted(template.directories):
            mode = 0o700 if directory == ".ludowright/locks" else 0o755
            filesystem.ensure_directory(RepositoryPath(directory), mode=mode)

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

        manifest_repository = JsonDocumentRepository(filesystem, paths["manifest"], ProjectContract)
        manifest_payload = manifest_repository.canonical_bytes(project)
        state_store.index_entity(
            IndexedEntity(
                entity_type="project",
                entity_id=project.id,
                source_path=paths["manifest"],
                source_digest=hashlib.sha256(manifest_payload).hexdigest(),
                revision=1,
                status="active",
                updated_at=timestamp,
            )
        )

        # The marker is the final canonical write. Its presence means all required
        # derived stores have already been initialized and indexed.
        filesystem.write_bytes(paths["manifest"], manifest_payload)
        manifest_repository.load()
        graph_repository.load()
        validated_event_snapshot = event_log.replay()
        if not state_store.check_consistency(validated_event_snapshot).is_consistent:
            raise ProjectInitializationFailureError(
                "initialized state store is inconsistent with the event log"
            )
        if state_store.get_entity("project", project.id) is None:
            raise ProjectInitializationFailureError("initialized project index is missing")

    @staticmethod
    def _planned_result(
        target: Path,
        template: TemplateDefinitionContract,
        project_id: str,
    ) -> ProjectInitializationResult:
        return ProjectInitializationResult(
            project_directory=target.as_posix(),
            project_id=project_id,
            template_id=template.id,
            template_version=template.version,
            files=tuple(sorted(file.path for file in template.files)),
            directories=tuple(sorted(template.directories)),
            schema_version=template.schema_version,
            state_store_schema_version=STATE_SCHEMA_VERSION,
            dry_run=True,
            warnings=(),
            state="planned",
        )

    @staticmethod
    def _rollback_project(
        target: Path,
        template: TemplateDefinitionContract,
        *,
        remove_target: bool,
    ) -> None:
        if not os.path.lexists(target) or target.is_symlink() or not target.is_dir():
            return
        for file in sorted(
            template.files,
            key=lambda item: len(Path(item.path).parts),
            reverse=True,
        ):
            candidate = target.joinpath(*Path(file.path).parts)
            ProjectInitializationService._remove_regular_file(candidate)
            if file.role == "state-store":
                for suffix in _SQLITE_SIDECARS:
                    ProjectInitializationService._remove_regular_file(
                        target.joinpath(*Path(f"{file.path}{suffix}").parts)
                    )
        for directory in sorted(
            template.directories,
            key=lambda item: len(Path(item).parts),
            reverse=True,
        ):
            candidate = target.joinpath(*Path(directory).parts)
            ProjectInitializationService._remove_empty_directory(candidate)
        if remove_target:
            ProjectInitializationService._remove_empty_directory(target)

    @staticmethod
    def _remove_regular_file(path: Path) -> None:
        try:
            if path.is_symlink() or not path.is_file():
                return
            path.unlink()
        except OSError:
            return

    @staticmethod
    def _remove_empty_directory(path: Path) -> None:
        try:
            if path.is_symlink() or not path.is_dir():
                return
            path.rmdir()
        except OSError:
            return

    @staticmethod
    def _remove_empty_parent_directories(parents: tuple[Path, ...]) -> None:
        for parent in sorted(parents, key=lambda item: len(item.parts), reverse=True):
            ProjectInitializationService._remove_empty_directory(parent)
