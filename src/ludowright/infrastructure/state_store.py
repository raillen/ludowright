"""Rebuildable SQLite indexes for workflow progress and canonical project sources."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from ludowright.domain import (
    EventHash,
    FrozenJsonValue,
    freeze_json_object,
    thaw_json_object,
    validate_slug,
)
from ludowright.infrastructure.event_log import EventLogSnapshot
from ludowright.infrastructure.filesystem import (
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    UnsafeProjectPathError,
)

DEFAULT_STATE_STORE_PATH = RepositoryPath(".ludowright/state.sqlite3")
_STATE_SCHEMA_VERSION = 1
_STATE_STORE_LOCK = "sqlite-state-store-init"
_DEFAULT_BUSY_TIMEOUT_MS = 5_000
_DEFAULT_SOURCE_LIMIT = 16 * 1024 * 1024
_DIGEST_LENGTH = 64


class StateStoreError(RuntimeError):
    """Base class for state-store configuration and persistence failures."""


class UnsupportedStateSchemaError(StateStoreError):
    """Raised when the database schema requires a migration."""


class StateStoreCorruptionError(StateStoreError):
    """Raised when indexed state cannot satisfy its persisted contract."""


class EventIndexState(StrEnum):
    IN_SYNC = "in-sync"
    EMPTY_INDEX = "empty-index"
    BEHIND = "behind"
    DIVERGED = "diverged"


class SourceIndexState(StrEnum):
    IN_SYNC = "in-sync"
    MISSING = "missing"
    CHANGED = "changed"
    INVALID_PATH = "invalid-path"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class WorkflowProgress:
    """Indexed progress for one resumable application workflow."""

    workflow_id: str
    workflow_type: str
    status: str
    current_step: str | None
    context: Mapping[str, FrozenJsonValue]
    source_event_sequence: int | None
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_slug_value(self.workflow_id, "workflow ID")
        _validate_slug_value(self.workflow_type, "workflow type")
        _validate_slug_value(self.status, "workflow status")
        if self.current_step is not None:
            _validate_slug_value(self.current_step, "workflow step")
        _validate_optional_sequence(self.source_event_sequence)
        object.__setattr__(self, "context", freeze_json_object(self.context))
        object.__setattr__(self, "updated_at", _normalize_timestamp(self.updated_at))


@dataclass(frozen=True, slots=True)
class IndexedEntity:
    """Digest-bound index entry for one canonical source document."""

    entity_type: str
    entity_id: str
    source_path: RepositoryPath
    source_digest: str
    revision: int
    status: str
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_slug_value(self.entity_type, "entity type")
        _validate_slug_value(self.entity_id, "entity ID")
        if not isinstance(self.source_path, RepositoryPath):
            raise StateStoreError("indexed entity source must use RepositoryPath")
        _validate_digest(self.source_digest, "source digest")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise StateStoreError("indexed entity revision must be a positive integer")
        _validate_slug_value(self.status, "entity status")
        object.__setattr__(self, "updated_at", _normalize_timestamp(self.updated_at))


@dataclass(frozen=True, slots=True)
class EventCheckpoint:
    """Last event-log revision incorporated into the derived index."""

    last_sequence: int
    last_event_hash: EventHash | None
    log_digest: str
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            isinstance(self.last_sequence, bool)
            or not isinstance(self.last_sequence, int)
            or self.last_sequence < 0
        ):
            raise StateStoreError("checkpoint sequence must be a non-negative integer")
        if self.last_sequence == 0 and self.last_event_hash is not None:
            raise StateStoreError("empty checkpoint cannot contain an event hash")
        if self.last_sequence > 0 and not isinstance(self.last_event_hash, EventHash):
            raise StateStoreError("non-empty checkpoint requires an event hash")
        _validate_digest(self.log_digest, "event-log digest")
        object.__setattr__(self, "updated_at", _normalize_timestamp(self.updated_at))


@dataclass(frozen=True, slots=True)
class SourceConsistency:
    """Comparison between one index entry and its current canonical file."""

    entity_type: str
    entity_id: str
    source_path: RepositoryPath | None
    state: SourceIndexState
    expected_digest: str
    actual_digest: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class StateConsistencyReport:
    """Event and source consistency status for the rebuildable index."""

    event_state: EventIndexState
    event_detail: str
    sources: tuple[SourceConsistency, ...]

    @property
    def is_consistent(self) -> bool:
        return self.event_state is EventIndexState.IN_SYNC and all(
            source.state is SourceIndexState.IN_SYNC for source in self.sources
        )


class StateStore:
    """Typed SQLite state index with explicit short transactions."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath = DEFAULT_STATE_STORE_PATH,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
        source_read_limit: int = _DEFAULT_SOURCE_LIMIT,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("state store requires ProjectFilesystem")
        if not isinstance(path, RepositoryPath):
            raise TypeError("state store requires RepositoryPath")
        if not path.name.endswith(".sqlite3"):
            raise StateStoreError("state store path must use the .sqlite3 extension")
        _validate_positive_integer(busy_timeout_ms, "SQLite busy timeout")
        _validate_positive_integer(source_read_limit, "source read limit")

        self._filesystem = filesystem
        self._path = path
        self._busy_timeout_ms = busy_timeout_ms
        self._source_read_limit = source_read_limit
        parent = path.parent
        if parent is not None:
            self._filesystem.ensure_directory(parent)
        self._database_path = self._filesystem.resolve(path)
        self._sidecars = tuple(
            self._filesystem.resolve(
                RepositoryPath(f"{path.value}{suffix}"),
            )
            for suffix in ("-journal", "-shm", "-wal")
        )
        with self._filesystem.lock(_STATE_STORE_LOCK, timeout=busy_timeout_ms / 1000):
            self._assert_safe_database_files()
            self._initialize_schema()
            self._assert_safe_database_files()

    @property
    def path(self) -> RepositoryPath:
        return self._path

    @property
    def schema_version(self) -> int:
        return _STATE_SCHEMA_VERSION

    def save_workflow(self, progress: WorkflowProgress) -> None:
        """Insert or replace one workflow progress record."""
        if not isinstance(progress, WorkflowProgress):
            raise TypeError("save_workflow requires WorkflowProgress")
        context_json = _canonical_json(thaw_json_object(progress.context))
        with self._transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO workflow_progress (
                    workflow_id, workflow_type, status, current_step,
                    context_json, source_event_sequence, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    workflow_type = excluded.workflow_type,
                    status = excluded.status,
                    current_step = excluded.current_step,
                    context_json = excluded.context_json,
                    source_event_sequence = excluded.source_event_sequence,
                    updated_at = excluded.updated_at
                """,
                (
                    progress.workflow_id,
                    progress.workflow_type,
                    progress.status,
                    progress.current_step,
                    context_json,
                    progress.source_event_sequence,
                    _format_timestamp(progress.updated_at),
                ),
            )

    def get_workflow(self, workflow_id: str) -> WorkflowProgress | None:
        """Return one workflow progress record by canonical ID."""
        _validate_slug_value(workflow_id, "workflow ID")
        with self._transaction(write=False) as connection:
            row = connection.execute(
                "SELECT * FROM workflow_progress WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return None if row is None else _workflow_from_row(row)

    def list_workflows(self) -> tuple[WorkflowProgress, ...]:
        """Return workflows in stable ID order."""
        with self._transaction(write=False) as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_progress ORDER BY workflow_id"
            ).fetchall()
        return tuple(_workflow_from_row(row) for row in rows)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete one derived workflow record and report whether it existed."""
        _validate_slug_value(workflow_id, "workflow ID")
        with self._transaction(write=True) as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_progress WHERE workflow_id = ?",
                (workflow_id,),
            )
            return cursor.rowcount == 1

    def index_entity(self, entity: IndexedEntity) -> None:
        """Insert or replace one canonical-source index entry."""
        if not isinstance(entity, IndexedEntity):
            raise TypeError("index_entity requires IndexedEntity")
        with self._transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO indexed_entity (
                    entity_type, entity_id, source_path, source_digest,
                    revision, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    source_path = excluded.source_path,
                    source_digest = excluded.source_digest,
                    revision = excluded.revision,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    entity.entity_type,
                    entity.entity_id,
                    entity.source_path.value,
                    entity.source_digest,
                    entity.revision,
                    entity.status,
                    _format_timestamp(entity.updated_at),
                ),
            )

    def get_entity(self, entity_type: str, entity_id: str) -> IndexedEntity | None:
        """Return one indexed entity by typed key."""
        _validate_slug_value(entity_type, "entity type")
        _validate_slug_value(entity_id, "entity ID")
        with self._transaction(write=False) as connection:
            row = connection.execute(
                """
                SELECT * FROM indexed_entity
                WHERE entity_type = ? AND entity_id = ?
                """,
                (entity_type, entity_id),
            ).fetchone()
        return None if row is None else _entity_from_row(row)

    def list_entities(self, *, entity_type: str | None = None) -> tuple[IndexedEntity, ...]:
        """Return indexed entities in stable type and ID order."""
        if entity_type is not None:
            _validate_slug_value(entity_type, "entity type")
        with self._transaction(write=False) as connection:
            if entity_type is None:
                rows = connection.execute(
                    "SELECT * FROM indexed_entity ORDER BY entity_type, entity_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM indexed_entity
                    WHERE entity_type = ? ORDER BY entity_id
                    """,
                    (entity_type,),
                ).fetchall()
        return tuple(_entity_from_row(row) for row in rows)

    def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        """Delete one derived entity index entry."""
        _validate_slug_value(entity_type, "entity type")
        _validate_slug_value(entity_id, "entity ID")
        with self._transaction(write=True) as connection:
            cursor = connection.execute(
                """
                DELETE FROM indexed_entity
                WHERE entity_type = ? AND entity_id = ?
                """,
                (entity_type, entity_id),
            )
            return cursor.rowcount == 1

    def record_event_checkpoint(
        self,
        snapshot: EventLogSnapshot,
        *,
        updated_at: datetime | None = None,
    ) -> EventCheckpoint:
        """Record the exact event-log revision included in the state index."""
        if not isinstance(snapshot, EventLogSnapshot):
            raise TypeError("record_event_checkpoint requires EventLogSnapshot")
        checkpoint = EventCheckpoint(
            last_sequence=snapshot.last_sequence,
            last_event_hash=snapshot.last_hash,
            log_digest=snapshot.digest,
            updated_at=updated_at or datetime.now(UTC),
        )
        with self._transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO event_checkpoint (
                    singleton, last_sequence, last_event_hash, log_digest, updated_at
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    last_sequence = excluded.last_sequence,
                    last_event_hash = excluded.last_event_hash,
                    log_digest = excluded.log_digest,
                    updated_at = excluded.updated_at
                """,
                (
                    checkpoint.last_sequence,
                    (
                        checkpoint.last_event_hash.value
                        if checkpoint.last_event_hash is not None
                        else None
                    ),
                    checkpoint.log_digest,
                    _format_timestamp(checkpoint.updated_at),
                ),
            )
        return checkpoint

    def get_event_checkpoint(self) -> EventCheckpoint | None:
        """Return the indexed event-log checkpoint, when present."""
        with self._transaction(write=False) as connection:
            row = connection.execute(
                "SELECT * FROM event_checkpoint WHERE singleton = 1"
            ).fetchone()
        return None if row is None else _checkpoint_from_row(row)

    def check_consistency(self, event_snapshot: EventLogSnapshot) -> StateConsistencyReport:
        """Compare the derived database with event and canonical-file revisions."""
        if not isinstance(event_snapshot, EventLogSnapshot):
            raise TypeError("check_consistency requires EventLogSnapshot")
        event_state, event_detail = self._check_event_checkpoint(event_snapshot)
        sources = tuple(self._check_source(entity) for entity in self.list_entities())
        return StateConsistencyReport(
            event_state=event_state,
            event_detail=event_detail,
            sources=sources,
        )

    def _check_event_checkpoint(
        self,
        snapshot: EventLogSnapshot,
    ) -> tuple[EventIndexState, str]:
        checkpoint = self.get_event_checkpoint()
        if checkpoint is None:
            if not snapshot.events:
                return EventIndexState.IN_SYNC, "empty event log requires no checkpoint"
            return EventIndexState.EMPTY_INDEX, "state store has no event checkpoint"
        if checkpoint.last_sequence > snapshot.last_sequence:
            return EventIndexState.DIVERGED, "state checkpoint is ahead of the event log"
        if checkpoint.last_sequence == 0:
            if snapshot.last_sequence == 0 and checkpoint.log_digest == snapshot.digest:
                return EventIndexState.IN_SYNC, "empty event checkpoint matches"
            return EventIndexState.BEHIND, "event log contains events after the empty checkpoint"

        indexed_event = snapshot.events[checkpoint.last_sequence - 1]
        if indexed_event.event_hash != checkpoint.last_event_hash:
            return EventIndexState.DIVERGED, "checkpoint event hash does not match replay history"
        if checkpoint.last_sequence < snapshot.last_sequence:
            return EventIndexState.BEHIND, (
                f"state index stops at event {checkpoint.last_sequence}; "
                f"log ends at {snapshot.last_sequence}"
            )
        if checkpoint.log_digest != snapshot.digest:
            return EventIndexState.DIVERGED, "checkpoint log digest does not match exact log bytes"
        return EventIndexState.IN_SYNC, "event checkpoint matches the complete log"

    def _check_source(self, entity: IndexedEntity) -> SourceConsistency:
        try:
            payload = self._filesystem.read_bytes(
                entity.source_path,
                max_bytes=self._source_read_limit,
            )
        except FileNotFoundError:
            return SourceConsistency(
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                source_path=entity.source_path,
                state=SourceIndexState.MISSING,
                expected_digest=entity.source_digest,
                actual_digest=None,
                detail="canonical source file is missing",
            )
        except UnsafeProjectPathError as error:
            return SourceConsistency(
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                source_path=entity.source_path,
                state=SourceIndexState.INVALID_PATH,
                expected_digest=entity.source_digest,
                actual_digest=None,
                detail=str(error),
            )
        except ProjectFilesystemError as error:
            return SourceConsistency(
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                source_path=entity.source_path,
                state=SourceIndexState.UNREADABLE,
                expected_digest=entity.source_digest,
                actual_digest=None,
                detail=str(error),
            )

        actual_digest = hashlib.sha256(payload).hexdigest()
        state = (
            SourceIndexState.IN_SYNC
            if actual_digest == entity.source_digest
            else SourceIndexState.CHANGED
        )
        detail = (
            "canonical source digest matches"
            if state is SourceIndexState.IN_SYNC
            else "canonical source changed after indexing"
        )
        return SourceConsistency(
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            source_path=entity.source_path,
            state=state,
            expected_digest=entity.source_digest,
            actual_digest=actual_digest,
            detail=detail,
        )

    def _initialize_schema(self) -> None:
        try:
            with self._connect() as connection:
                current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if current_version not in {0, _STATE_SCHEMA_VERSION}:
                    raise UnsupportedStateSchemaError(
                        f"state schema v{current_version} is not supported by v{_STATE_SCHEMA_VERSION}"
                    )
                if current_version == _STATE_SCHEMA_VERSION:
                    self._validate_schema(connection)
                    return
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in _SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {_STATE_SCHEMA_VERSION}")
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                self._validate_schema(connection)
        except sqlite3.DatabaseError as error:
            raise StateStoreCorruptionError("SQLite state database is invalid") from error

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        expected = {"event_checkpoint", "indexed_entity", "workflow_progress"}
        if not expected.issubset(tables):
            raise StateStoreCorruptionError(
                f"SQLite state schema is incomplete: missing {sorted(expected - tables)}"
            )
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise StateStoreCorruptionError(f"SQLite quick_check failed: {integrity}")

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        self._assert_safe_database_files()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if not write:
                    connection.execute("PRAGMA query_only = ON")
                try:
                    yield connection
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except sqlite3.DatabaseError as error:
            raise StateStoreCorruptionError("SQLite state operation failed") from error
        finally:
            self._assert_safe_database_files()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._assert_safe_database_files()
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA trusted_schema = OFF")
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise StateStoreError("SQLite state store requires WAL journal mode")
            yield connection
        finally:
            connection.close()

    def _assert_safe_database_files(self) -> None:
        for candidate in (self._database_path, *self._sidecars):
            if not os.path.lexists(candidate):
                continue
            candidate_stat = os.lstat(candidate)
            if stat.S_ISLNK(candidate_stat.st_mode):
                raise UnsafeProjectPathError(
                    f"SQLite state path cannot be a symlink: {candidate}"
                )
            if not stat.S_ISREG(candidate_stat.st_mode):
                raise StateStoreError(
                    f"SQLite state path must be a regular file: {candidate}"
                )


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE workflow_progress (
        workflow_id TEXT PRIMARY KEY,
        workflow_type TEXT NOT NULL,
        status TEXT NOT NULL,
        current_step TEXT,
        context_json TEXT NOT NULL,
        source_event_sequence INTEGER,
        updated_at TEXT NOT NULL,
        CHECK(source_event_sequence IS NULL OR source_event_sequence >= 1)
    ) STRICT
    """,
    "CREATE INDEX workflow_progress_status_idx ON workflow_progress(status, workflow_id)",
    """
    CREATE TABLE indexed_entity (
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        source_path TEXT NOT NULL,
        source_digest TEXT NOT NULL CHECK(length(source_digest) = 64),
        revision INTEGER NOT NULL CHECK(revision >= 1),
        status TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(entity_type, entity_id)
    ) STRICT, WITHOUT ROWID
    """,
    "CREATE INDEX indexed_entity_path_idx ON indexed_entity(source_path)",
    """
    CREATE TABLE event_checkpoint (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        last_sequence INTEGER NOT NULL CHECK(last_sequence >= 0),
        last_event_hash TEXT CHECK(last_event_hash IS NULL OR length(last_event_hash) = 64),
        log_digest TEXT NOT NULL CHECK(length(log_digest) = 64),
        updated_at TEXT NOT NULL,
        CHECK(
            (last_sequence = 0 AND last_event_hash IS NULL)
            OR (last_sequence > 0 AND last_event_hash IS NOT NULL)
        )
    ) STRICT
    """,
)


def _workflow_from_row(row: sqlite3.Row) -> WorkflowProgress:
    try:
        context = json.loads(row["context_json"])
        if not isinstance(context, dict):
            raise StateStoreCorruptionError("workflow context must be a JSON object")
        return WorkflowProgress(
            workflow_id=row["workflow_id"],
            workflow_type=row["workflow_type"],
            status=row["status"],
            current_step=row["current_step"],
            context=context,
            source_event_sequence=row["source_event_sequence"],
            updated_at=_parse_timestamp(row["updated_at"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise StateStoreCorruptionError("workflow progress row is invalid") from error


def _entity_from_row(row: sqlite3.Row) -> IndexedEntity:
    try:
        return IndexedEntity(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            source_path=RepositoryPath(row["source_path"]),
            source_digest=row["source_digest"],
            revision=row["revision"],
            status=row["status"],
            updated_at=_parse_timestamp(row["updated_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise StateStoreCorruptionError("indexed entity row is invalid") from error


def _checkpoint_from_row(row: sqlite3.Row) -> EventCheckpoint:
    try:
        return EventCheckpoint(
            last_sequence=row["last_sequence"],
            last_event_hash=(
                EventHash(row["last_event_hash"])
                if row["last_event_hash"] is not None
                else None
            ),
            log_digest=row["log_digest"],
            updated_at=_parse_timestamp(row["updated_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise StateStoreCorruptionError("event checkpoint row is invalid") from error


def _canonical_json(value: dict[str, object]) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise StateStoreError("state context cannot be serialized as JSON") from error


def _validate_slug_value(value: str, label: str) -> None:
    try:
        validate_slug(value)
    except (TypeError, ValueError) as error:
        raise StateStoreError(f"{label} must be a canonical slug") from error


def _validate_digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != _DIGEST_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateStoreError(f"{label} must be lowercase SHA-256")


def _validate_optional_sequence(value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateStoreError("source event sequence must be a positive integer")


def _validate_positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateStoreError(f"{label} must be a positive integer")


def _normalize_timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StateStoreError("state timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return _normalize_timestamp(value).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise StateStoreCorruptionError("state timestamp must be text")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise StateStoreCorruptionError("state timestamp is not canonical UTC") from error
    if _format_timestamp(parsed) != value:
        raise StateStoreCorruptionError("state timestamp is not canonical UTC")
    return parsed
