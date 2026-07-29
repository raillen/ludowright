"""Explicit SQLite migration planning, dry runs, backups, receipts, and rollback."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ludowright import __version__
from ludowright.contracts.migrations import (
    MigrationReceiptContract,
    MigrationRunStatus,
)
from ludowright.domain import validate_slug
from ludowright.infrastructure.filesystem import (
    ProjectFilesystem,
    RepositoryPath,
    UnsafeProjectPathError,
)
from ludowright.infrastructure.state_store import (
    DEFAULT_STATE_STORE_PATH,
    STATE_SCHEMA_VERSION,
)
from ludowright.infrastructure.structured import JsonDocumentRepository

TARGET_STATE_SCHEMA_VERSION = STATE_SCHEMA_VERSION
_DEFAULT_BUSY_TIMEOUT_MS = 5_000
_MIGRATION_LOCK = "sqlite-state-migration"
_BACKUP_ROOT = RepositoryPath(".ludowright/backups/migrations")
_TEMP_ROOT = RepositoryPath(".ludowright/tmp/migrations")

MigrationFunction = Callable[[sqlite3.Connection], None]


class MigrationError(RuntimeError):
    """Base class for migration discovery and execution failures."""


class MigrationPlanError(MigrationError):
    """Raised when no safe contiguous migration path exists."""


class MigrationExecutionError(MigrationError):
    """Raised when a migration cannot complete and is rolled back."""


class MigrationRollbackError(MigrationError):
    """Raised when persisted rollback metadata cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class MigrationStep:
    """One deterministic single-version SQLite schema transition."""

    migration_id: str
    source_version: int
    target_version: int
    description: str
    apply: MigrationFunction

    def __post_init__(self) -> None:
        try:
            validate_slug(self.migration_id)
        except (TypeError, ValueError) as error:
            raise MigrationPlanError("migration ID must be a canonical slug") from error
        if (
            isinstance(self.source_version, bool)
            or not isinstance(self.source_version, int)
            or self.source_version < 1
        ):
            raise MigrationPlanError("migration source version must be positive")
        if self.target_version != self.source_version + 1:
            raise MigrationPlanError("migration steps must advance exactly one version")
        if not isinstance(self.description, str) or not self.description.strip():
            raise MigrationPlanError("migration description cannot be empty")
        if not callable(self.apply):
            raise MigrationPlanError("migration apply operation must be callable")


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Contiguous ordered steps from one database revision to another."""

    source_version: int
    target_version: int
    steps: tuple[MigrationStep, ...]

    @property
    def requires_migration(self) -> bool:
        return bool(self.steps)

    @property
    def migration_ids(self) -> tuple[str, ...]:
        return tuple(step.migration_id for step in self.steps)


@dataclass(frozen=True, slots=True)
class MigrationDryRunResult:
    """Validation result produced by migrating a disposable database copy."""

    plan: MigrationPlan
    simulated_digest: str
    validated_at: datetime


@dataclass(frozen=True, slots=True)
class MigrationApplyResult:
    """Result of either a no-op or one completed persisted migration run."""

    plan: MigrationPlan
    receipt: MigrationReceiptContract | None

    @property
    def applied(self) -> bool:
        return self.receipt is not None


class MigrationCatalog:
    """Validated discovery registry for deterministic migration steps."""

    def __init__(self, steps: tuple[MigrationStep, ...]) -> None:
        ordered = tuple(sorted(steps, key=lambda step: step.source_version))
        ids = tuple(step.migration_id for step in ordered)
        sources = tuple(step.source_version for step in ordered)
        if len(ids) != len(set(ids)):
            raise MigrationPlanError("migration IDs must be unique")
        if len(sources) != len(set(sources)):
            raise MigrationPlanError("migration source versions must be unique")
        self._steps = ordered
        self._by_source = {step.source_version: step for step in ordered}

    @property
    def steps(self) -> tuple[MigrationStep, ...]:
        return self._steps

    def plan(self, source_version: int, target_version: int) -> MigrationPlan:
        """Discover one exact contiguous upgrade path."""
        _validate_version(source_version, "source version")
        _validate_version(target_version, "target version")
        if source_version > target_version:
            raise MigrationPlanError("downgrade plans are not supported")
        current = source_version
        planned: list[MigrationStep] = []
        while current < target_version:
            step = self._by_source.get(current)
            if step is None:
                raise MigrationPlanError(f"no migration is registered from schema v{current}")
            planned.append(step)
            current = step.target_version
        return MigrationPlan(
            source_version=source_version,
            target_version=target_version,
            steps=tuple(planned),
        )


class StateMigrationManager:
    """Apply registered SQLite state migrations with durable rollback metadata."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath = DEFAULT_STATE_STORE_PATH,
        *,
        catalog: MigrationCatalog | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("migration manager requires ProjectFilesystem")
        if not isinstance(path, RepositoryPath):
            raise TypeError("migration manager requires RepositoryPath")
        if not path.name.endswith(".sqlite3"):
            raise MigrationError("migration database path must use .sqlite3")
        _validate_positive_integer(busy_timeout_ms, "migration busy timeout")

        self._filesystem = filesystem
        self._path = path
        self._catalog = catalog or STATE_MIGRATIONS
        self._busy_timeout_ms = busy_timeout_ms
        parent = path.parent
        if parent is not None:
            filesystem.ensure_directory(parent)
        filesystem.ensure_directory(_BACKUP_ROOT)
        filesystem.ensure_directory(_TEMP_ROOT)
        self._database_path = filesystem.resolve(path)
        self._sidecars = tuple(
            filesystem.resolve(RepositoryPath(f"{path.value}{suffix}"))
            for suffix in ("-journal", "-shm", "-wal")
        )

    @property
    def path(self) -> RepositoryPath:
        return self._path

    def inspect_version(self) -> int:
        """Read the current SQLite user version without changing the database."""
        self._assert_safe_database_files(require_database=True)
        try:
            with self._connect(self._database_path, readonly=True) as connection:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        except sqlite3.DatabaseError as error:
            raise MigrationError("cannot inspect SQLite state schema") from error
        if version < 1:
            raise MigrationError("existing state database has no supported schema version")
        return version

    def plan(
        self,
        *,
        target_version: int = TARGET_STATE_SCHEMA_VERSION,
    ) -> MigrationPlan:
        """Discover the required migration path for the current database."""
        return self._catalog.plan(self.inspect_version(), target_version)

    def dry_run(
        self,
        *,
        target_version: int = TARGET_STATE_SCHEMA_VERSION,
        timeout: float = 0.0,
    ) -> MigrationDryRunResult:
        """Apply and validate the plan only on a disposable consistent copy."""
        with self._filesystem.lock(_MIGRATION_LOCK, timeout=timeout):
            plan = self.plan(target_version=target_version)
            temporary = self._temporary_path("dry-run")
            try:
                self._create_consistent_copy(self._database_path, temporary)
                self._apply_plan(temporary, plan, run_id="dry-run")
                simulated_digest = _sha256_file(temporary)
            finally:
                _remove_sqlite_files(temporary)
            return MigrationDryRunResult(
                plan=plan,
                simulated_digest=simulated_digest,
                validated_at=datetime.now(UTC),
            )

    def apply(
        self,
        *,
        target_version: int = TARGET_STATE_SCHEMA_VERSION,
        timeout: float = 0.0,
    ) -> MigrationApplyResult:
        """Back up, apply, validate, and persist rollback metadata."""
        with self._filesystem.lock(_MIGRATION_LOCK, timeout=timeout):
            plan = self.plan(target_version=target_version)
            if not plan.requires_migration:
                return MigrationApplyResult(plan=plan, receipt=None)

            run_id = _new_run_id()
            run_directory = _BACKUP_ROOT.child(run_id)
            self._filesystem.ensure_directory(run_directory)
            backup_path = run_directory.child("state-before.sqlite3")
            receipt_path = run_directory.child("rollback.json")
            backup_absolute = self._filesystem.resolve(backup_path)

            self._create_consistent_copy(self._database_path, backup_absolute)
            before_digest = _sha256_file(backup_absolute)
            receipt_repository = JsonDocumentRepository(
                self._filesystem,
                receipt_path,
                MigrationReceiptContract,
                max_bytes=128_000,
            )
            prepared = MigrationReceiptContract(
                run_id=run_id,
                status=MigrationRunStatus.PREPARED,
                database_path=self._path.value,
                backup_path=backup_path.value,
                source_version=plan.source_version,
                target_version=plan.target_version,
                migration_ids=plan.migration_ids,
                started_at=_format_timestamp(datetime.now(UTC)),
                before_digest=before_digest,
                backup_digest=before_digest,
            )
            receipt_snapshot = receipt_repository.create(prepared)

            try:
                self._apply_plan(self._database_path, plan, run_id=run_id)
                after_digest = self._logical_digest(self._database_path)
            except BaseException as error:
                failed = prepared.model_copy(
                    update={
                        "status": MigrationRunStatus.FAILED,
                        "completed_at": _format_timestamp(datetime.now(UTC)),
                        "failure": _safe_failure_text(error),
                    }
                )
                receipt_repository.replace(receipt_snapshot, failed)
                if isinstance(error, MigrationError):
                    raise
                raise MigrationExecutionError(
                    f"state migration {run_id} failed; backup retained"
                ) from error

            completed = prepared.model_copy(
                update={
                    "status": MigrationRunStatus.COMPLETED,
                    "completed_at": _format_timestamp(datetime.now(UTC)),
                    "after_digest": after_digest,
                }
            )
            receipt_repository.replace(receipt_snapshot, completed)
            return MigrationApplyResult(plan=plan, receipt=completed)

    def rollback(self, run_id: str, *, timeout: float = 0.0) -> MigrationReceiptContract:
        """Restore one completed migration backup when the database is unchanged."""
        try:
            validate_slug(run_id)
        except (TypeError, ValueError) as error:
            raise MigrationRollbackError("migration run ID must be canonical") from error

        run_directory = _BACKUP_ROOT.child(run_id)
        receipt_path = run_directory.child("rollback.json")
        receipt_repository = JsonDocumentRepository(
            self._filesystem,
            receipt_path,
            MigrationReceiptContract,
            max_bytes=128_000,
        )

        with self._filesystem.lock(_MIGRATION_LOCK, timeout=timeout):
            snapshot = receipt_repository.load()
            receipt = snapshot.value
            if receipt.status is not MigrationRunStatus.COMPLETED:
                raise MigrationRollbackError(f"migration {run_id} is not in completed state")
            if receipt.after_digest is None:
                raise MigrationRollbackError("completed receipt lacks post-migration digest")
            current_digest = self._logical_digest(self._database_path)
            if current_digest != receipt.after_digest:
                raise MigrationRollbackError(
                    "state database changed after migration; rollback would destroy newer work"
                )

            backup_path = RepositoryPath(receipt.backup_path)
            backup_absolute = self._filesystem.resolve(backup_path)
            if _sha256_file(backup_absolute) != receipt.backup_digest:
                raise MigrationRollbackError("migration backup digest is invalid")

            pre_rollback = run_directory.child("state-before-rollback.sqlite3")
            pre_rollback_absolute = self._filesystem.resolve(pre_rollback)
            self._create_consistent_copy(self._database_path, pre_rollback_absolute)
            pre_rollback_digest = _sha256_file(pre_rollback_absolute)

            try:
                self._replace_database_from_backup(backup_absolute)
                restored_version = self.inspect_version()
                if restored_version != receipt.source_version:
                    raise MigrationRollbackError(
                        "restored database version does not match migration source"
                    )
                restored_digest = self._logical_digest(self._database_path)
                if restored_digest != receipt.before_digest:
                    raise MigrationRollbackError(
                        "restored database content does not match migration backup"
                    )
            except BaseException as error:
                self._replace_database_from_backup(pre_rollback_absolute)
                if isinstance(error, MigrationRollbackError):
                    raise
                raise MigrationRollbackError(
                    f"rollback of migration {run_id} failed; current database restored"
                ) from error

            rolled_back = receipt.model_copy(
                update={
                    "status": MigrationRunStatus.ROLLED_BACK,
                    "rolled_back_at": _format_timestamp(datetime.now(UTC)),
                    "pre_rollback_digest": pre_rollback_digest,
                }
            )
            receipt_repository.replace(snapshot, rolled_back)
            return rolled_back

    def _apply_plan(self, database: Path, plan: MigrationPlan, *, run_id: str) -> None:
        if not plan.requires_migration:
            self._validate_target(database, plan.target_version)
            return
        try:
            with self._connect(database, readonly=False) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
                    if current != plan.source_version:
                        raise MigrationExecutionError(
                            f"migration source changed from v{plan.source_version} to v{current}"
                        )
                    for step in plan.steps:
                        observed = int(connection.execute("PRAGMA user_version").fetchone()[0])
                        if observed != step.source_version:
                            raise MigrationExecutionError(
                                f"migration {step.migration_id} expected v{step.source_version}, "
                                f"found v{observed}"
                            )
                        step.apply(connection)
                        connection.execute(f"PRAGMA user_version = {step.target_version}")
                        if _table_exists(connection, "migration_history"):
                            connection.execute(
                                """
                                INSERT INTO migration_history (
                                    migration_id, run_id, source_version,
                                    target_version, applied_at, tool_version
                                ) VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    step.migration_id,
                                    run_id,
                                    step.source_version,
                                    step.target_version,
                                    _format_timestamp(datetime.now(UTC)),
                                    __version__,
                                ),
                            )
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except sqlite3.DatabaseError as error:
            raise MigrationExecutionError("SQLite migration transaction failed") from error
        self._validate_target(database, plan.target_version)

    def _validate_target(self, database: Path, expected_version: int) -> None:
        try:
            with self._connect(database, readonly=True) as connection:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version != expected_version:
                    raise MigrationExecutionError(
                        f"migrated database is v{version}; expected v{expected_version}"
                    )
                quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
                if quick_check != "ok":
                    raise MigrationExecutionError(
                        f"SQLite quick_check failed after migration: {quick_check}"
                    )
                if expected_version >= 2 and not _table_exists(
                    connection,
                    "migration_history",
                ):
                    raise MigrationExecutionError("migrated database lacks migration_history table")
        except sqlite3.DatabaseError as error:
            raise MigrationExecutionError("cannot validate migrated SQLite database") from error

    def _logical_digest(self, database: Path) -> str:
        temporary = self._temporary_path("digest")
        try:
            self._create_consistent_copy(database, temporary)
            return _sha256_file(temporary)
        finally:
            _remove_sqlite_files(temporary)

    def _create_consistent_copy(self, source: Path, target: Path) -> None:
        self._assert_safe_database_files(require_database=True)
        _prepare_new_database_path(target)
        try:
            with self._connect(source, readonly=True) as source_connection:
                target_connection = sqlite3.connect(target, isolation_level=None)
                try:
                    source_connection.backup(target_connection)
                finally:
                    target_connection.close()
            _fsync_file(target)
            _fsync_directory(target.parent)
        except sqlite3.DatabaseError as error:
            _remove_sqlite_files(target)
            raise MigrationExecutionError("cannot create consistent SQLite backup") from error

    def _replace_database_from_backup(self, backup: Path) -> None:
        temporary = self._temporary_path("restore")
        self._create_consistent_copy(backup, temporary)
        self._assert_safe_database_files(require_database=True)
        for sidecar in self._sidecars:
            if os.path.lexists(sidecar):
                os.unlink(sidecar)
        os.replace(temporary, self._database_path)
        _fsync_file(self._database_path)
        _fsync_directory(self._database_path.parent)
        _remove_sqlite_files(temporary)

    def _temporary_path(self, purpose: str) -> Path:
        token = uuid.uuid4().hex
        relative = _TEMP_ROOT.child(f"{purpose}-{token}.sqlite3")
        return self._filesystem.resolve(relative)

    @contextmanager
    def _connect(
        self,
        database: Path,
        *,
        readonly: bool,
    ) -> Iterator[sqlite3.Connection]:
        if readonly:
            uri = f"{database.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=self._busy_timeout_ms / 1000,
                isolation_level=None,
            )
        else:
            connection = sqlite3.connect(
                database,
                timeout=self._busy_timeout_ms / 1000,
                isolation_level=None,
            )
        try:
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            if not readonly:
                connection.execute("PRAGMA synchronous = FULL")
            yield connection
        finally:
            connection.close()

    def _assert_safe_database_files(self, *, require_database: bool) -> None:
        candidates = (self._database_path, *self._sidecars)
        for index, candidate in enumerate(candidates):
            if not os.path.lexists(candidate):
                if index == 0 and require_database:
                    raise MigrationError(f"state database does not exist: {self._path}")
                continue
            candidate_stat = os.lstat(candidate)
            if stat.S_ISLNK(candidate_stat.st_mode):
                raise UnsafeProjectPathError(
                    f"migration database path cannot be a symlink: {candidate}"
                )
            if not stat.S_ISREG(candidate_stat.st_mode):
                raise MigrationError(f"migration database path must be a regular file: {candidate}")


def _migrate_state_v1_to_v2(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE migration_history (
            migration_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            source_version INTEGER NOT NULL CHECK(source_version >= 1),
            target_version INTEGER NOT NULL CHECK(target_version = source_version + 1),
            applied_at TEXT NOT NULL,
            tool_version TEXT NOT NULL
        ) STRICT, WITHOUT ROWID
        """
    )


STATE_MIGRATIONS = MigrationCatalog(
    (
        MigrationStep(
            migration_id="state-v1-to-v2-migration-history",
            source_version=1,
            target_version=2,
            description="add strict migration history table",
            apply=_migrate_state_v1_to_v2,
        ),
    )
)


def _new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%S%f")
    return f"migration-{timestamp}-{uuid.uuid4().hex[:12]}"


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MigrationError("migration timestamp must be timezone-aware")
    return (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace(
            "+00:00",
            "Z",
        )
    )


def _sha256_file(path: Path) -> str:
    _require_regular_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_new_database_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path):
        raise MigrationExecutionError(f"temporary database path already exists: {path}")


def _remove_sqlite_files(path: Path) -> None:
    for candidate in (
        path,
        Path(f"{path}-journal"),
        Path(f"{path}-shm"),
        Path(f"{path}-wal"),
    ):
        if os.path.lexists(candidate):
            candidate_stat = os.lstat(candidate)
            if stat.S_ISLNK(candidate_stat.st_mode):
                raise UnsafeProjectPathError(
                    f"temporary migration path became a symlink: {candidate}"
                )
            if not stat.S_ISREG(candidate_stat.st_mode):
                raise MigrationError(f"temporary migration path is not a regular file: {candidate}")
            os.unlink(candidate)


def _require_regular_file(path: Path) -> None:
    if not os.path.lexists(path):
        raise MigrationError(f"required migration file is missing: {path}")
    path_stat = os.lstat(path)
    if stat.S_ISLNK(path_stat.st_mode):
        raise UnsafeProjectPathError(f"migration file cannot be a symlink: {path}")
    if not stat.S_ISREG(path_stat.st_mode):
        raise MigrationError(f"migration file must be regular: {path}")


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _safe_failure_text(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}".strip()
    return text[:4_000] or type(error).__name__


def _validate_version(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MigrationPlanError(f"{label} must be a positive integer")


def _validate_positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MigrationError(f"{label} must be a positive integer")
