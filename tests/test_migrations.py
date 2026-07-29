"""Tests for explicit SQLite migration planning, backup, receipts, and rollback."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest
from pydantic import ValidationError

from ludowright.contracts import MigrationReceiptContract, MigrationRunStatus
from ludowright.infrastructure import (
    MigrationCatalog,
    MigrationError,
    MigrationExecutionError,
    MigrationPlanError,
    MigrationRollbackError,
    MigrationStep,
    ProjectFilesystem,
    StateMigrationManager,
    StateStore,
    UnsafeProjectPathError,
    UnsupportedStateSchemaError,
    WorkflowProgress,
)

_V1_SCHEMA = (
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


def create_v1_database(tmp_path: Path) -> Path:
    directory = tmp_path / ".ludowright"
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "state.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("BEGIN IMMEDIATE")
        for statement in _V1_SCHEMA:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            """
            INSERT INTO workflow_progress (
                workflow_id, workflow_type, status, current_step,
                context_json, source_event_sequence, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project-intake",
                "guided-intake",
                "in-progress",
                "collect-platforms",
                '{"answered":3}',
                1,
                "2026-07-29T15:00:00.123456Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return database


def database_version(database: Path) -> int:
    connection = sqlite3.connect(database)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def table_names(database: Path) -> set[str]:
    connection = sqlite3.connect(database)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()


def receipt_paths(tmp_path: Path) -> list[Path]:
    root = tmp_path / ".ludowright/backups/migrations"
    return sorted(root.glob("*/rollback.json")) if root.exists() else []


def load_receipt(path: Path) -> MigrationReceiptContract:
    return MigrationReceiptContract.model_validate_json(path.read_text(encoding="utf-8"))


def failing_migration(_connection: sqlite3.Connection) -> None:
    _connection.execute("CREATE TABLE should_rollback (value TEXT) STRICT")
    raise RuntimeError("deliberate migration failure")


def create_v3_marker(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE state_v3_marker (value TEXT) STRICT")


def test_migration_catalog_discovers_contiguous_plan() -> None:
    first = MigrationStep("one-to-two", 1, 2, "first", lambda _connection: None)
    second = MigrationStep("two-to-three", 2, 3, "second", lambda _connection: None)
    catalog = MigrationCatalog((second, first))

    plan = catalog.plan(1, 3)

    assert plan.requires_migration is True
    assert plan.migration_ids == ("one-to-two", "two-to-three")
    assert catalog.plan(3, 3).steps == ()


@pytest.mark.parametrize(
    "steps",
    [
        (
            MigrationStep("duplicate", 1, 2, "first", lambda _connection: None),
            MigrationStep("duplicate", 2, 3, "second", lambda _connection: None),
        ),
        (
            MigrationStep("one-a", 1, 2, "first", lambda _connection: None),
            MigrationStep("one-b", 1, 2, "second", lambda _connection: None),
        ),
    ],
)
def test_migration_catalog_rejects_ambiguous_steps(
    steps: tuple[MigrationStep, MigrationStep],
) -> None:
    with pytest.raises(MigrationPlanError):
        MigrationCatalog(steps)


def test_migration_catalog_rejects_gaps_and_downgrades() -> None:
    catalog = MigrationCatalog(
        (MigrationStep("one-to-two", 1, 2, "first", lambda _connection: None),)
    )

    with pytest.raises(MigrationPlanError, match="no migration"):
        catalog.plan(1, 3)
    with pytest.raises(MigrationPlanError, match="downgrade"):
        catalog.plan(2, 1)


def test_state_store_v1_requires_explicit_migration(tmp_path: Path) -> None:
    create_v1_database(tmp_path)

    with pytest.raises(UnsupportedStateSchemaError):
        StateStore(ProjectFilesystem(tmp_path))

    plan = StateMigrationManager(ProjectFilesystem(tmp_path)).plan()
    assert plan.source_version == 1
    assert plan.target_version == 2
    assert plan.migration_ids == ("state-v1-to-v2-migration-history",)


def test_dry_run_migrates_only_disposable_copy(tmp_path: Path) -> None:
    database = create_v1_database(tmp_path)
    manager = StateMigrationManager(ProjectFilesystem(tmp_path))

    result = manager.dry_run()

    assert result.plan.requires_migration is True
    assert len(result.simulated_digest) == 64
    assert database_version(database) == 1
    assert "migration_history" not in table_names(database)
    assert receipt_paths(tmp_path) == []
    assert list((tmp_path / ".ludowright/tmp/migrations").glob("*.sqlite3")) == []


def test_apply_migrates_v1_to_v2_and_preserves_data(tmp_path: Path) -> None:
    database = create_v1_database(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)
    manager = StateMigrationManager(filesystem)

    result = manager.apply()

    assert result.applied is True
    assert result.receipt is not None
    assert result.receipt.status is MigrationRunStatus.COMPLETED
    assert database_version(database) == 2
    assert "migration_history" in table_names(database)

    connection = sqlite3.connect(database)
    try:
        workflow_row = connection.execute(
            "SELECT workflow_id, status FROM workflow_progress"
        ).fetchone()
        migration_row = connection.execute(
            """
            SELECT migration_id, source_version, target_version
            FROM migration_history
            """
        ).fetchone()
    finally:
        connection.close()
    assert workflow_row == ("project-intake", "in-progress")
    assert migration_row == ("state-v1-to-v2-migration-history", 1, 2)

    receipt_path = receipt_paths(tmp_path)[0]
    receipt = load_receipt(receipt_path)
    assert receipt == result.receipt
    backup = tmp_path / receipt.backup_path
    assert database_version(backup) == 1
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == receipt.backup_digest

    state = StateStore(filesystem)
    assert state.schema_version == 2
    assert state.get_workflow("project-intake") is not None


def test_apply_is_noop_for_current_database(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    StateStore(filesystem)

    result = StateMigrationManager(filesystem).apply()

    assert result.applied is False
    assert result.plan.steps == ()
    assert result.receipt is None
    assert receipt_paths(tmp_path) == []


def test_failed_migration_rolls_back_and_keeps_failed_receipt(tmp_path: Path) -> None:
    database = create_v1_database(tmp_path)
    catalog = MigrationCatalog(
        (
            MigrationStep(
                "state-v1-to-v2-failure",
                1,
                2,
                "fail deliberately",
                failing_migration,
            ),
        )
    )
    manager = StateMigrationManager(ProjectFilesystem(tmp_path), catalog=catalog)

    with pytest.raises(MigrationExecutionError):
        manager.apply()

    assert database_version(database) == 1
    assert "should_rollback" not in table_names(database)
    receipt = load_receipt(receipt_paths(tmp_path)[0])
    assert receipt.status is MigrationRunStatus.FAILED
    assert receipt.failure is not None
    assert "deliberate migration failure" in receipt.failure
    assert database_version(tmp_path / receipt.backup_path) == 1


def test_completed_migration_can_be_rolled_back(tmp_path: Path) -> None:
    database = create_v1_database(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)
    manager = StateMigrationManager(filesystem)
    applied = manager.apply()
    assert applied.receipt is not None

    rolled_back = manager.rollback(applied.receipt.run_id)

    assert rolled_back.status is MigrationRunStatus.ROLLED_BACK
    assert rolled_back.rolled_back_at is not None
    assert rolled_back.pre_rollback_digest is not None
    assert database_version(database) == 1
    assert "migration_history" not in table_names(database)
    assert load_receipt(receipt_paths(tmp_path)[0]) == rolled_back
    with pytest.raises(UnsupportedStateSchemaError):
        StateStore(filesystem)
    with pytest.raises(MigrationRollbackError, match="not in completed"):
        manager.rollback(applied.receipt.run_id)


def test_rollback_refuses_database_changed_after_migration(tmp_path: Path) -> None:
    create_v1_database(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)
    manager = StateMigrationManager(filesystem)
    applied = manager.apply()
    assert applied.receipt is not None
    StateStore(filesystem).save_workflow(
        WorkflowProgress(
            workflow_id="new-workflow",
            workflow_type="migration-test",
            status="active",
            current_step=None,
            context={"changed": True},
            source_event_sequence=None,
            updated_at=datetime_from_text("2026-07-29T16:00:00.123456Z"),
        )
    )

    with pytest.raises(MigrationRollbackError, match="changed after migration"):
        manager.rollback(applied.receipt.run_id)

    assert database_version(tmp_path / ".ludowright/state.sqlite3") == 2


def test_rollback_refuses_tampered_backup(tmp_path: Path) -> None:
    create_v1_database(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)
    manager = StateMigrationManager(filesystem)
    applied = manager.apply()
    assert applied.receipt is not None
    backup = tmp_path / applied.receipt.backup_path
    backup.write_bytes(backup.read_bytes() + b"tampered")

    with pytest.raises(MigrationRollbackError, match="backup digest"):
        manager.rollback(applied.receipt.run_id)


def test_rollback_refuses_backup_symlink(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are unavailable")
    create_v1_database(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)
    manager = StateMigrationManager(filesystem)
    applied = manager.apply()
    assert applied.receipt is not None
    backup = tmp_path / applied.receipt.backup_path
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(backup.read_bytes())
    backup.unlink()
    backup.symlink_to(outside)

    with pytest.raises(UnsafeProjectPathError, match="symlink"):
        manager.rollback(applied.receipt.run_id)


def test_missing_database_cannot_be_planned(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="does not exist"):
        StateMigrationManager(ProjectFilesystem(tmp_path)).plan()


def test_concurrent_apply_produces_one_migration_and_one_noop(tmp_path: Path) -> None:
    create_v1_database(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)

    def apply() -> bool:
        return StateMigrationManager(filesystem).apply(timeout=10.0).applied

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: apply(), range(2)))

    assert sorted(results) == [False, True]
    assert database_version(tmp_path / ".ludowright/state.sqlite3") == 2
    assert len(receipt_paths(tmp_path)) == 1


def test_post_commit_validation_failure_restores_v1_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = create_v1_database(tmp_path)
    manager = StateMigrationManager(ProjectFilesystem(tmp_path))

    def fail_validation(_database: Path, _expected_version: int) -> None:
        raise MigrationExecutionError("post-commit validation failed")

    monkeypatch.setattr(manager, "_validate_target", fail_validation)

    with pytest.raises(MigrationExecutionError, match="post-commit validation failed"):
        manager.apply()

    assert database_version(database) == 1
    assert "migration_history" not in table_names(database)
    receipt = load_receipt(receipt_paths(tmp_path)[0])
    assert receipt.status is MigrationRunStatus.FAILED
    assert receipt.failure is not None
    assert "database restored from backup" in receipt.failure


def test_state_write_waits_until_migration_backup_window_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    state = StateStore(filesystem)
    catalog = MigrationCatalog(
        (
            MigrationStep(
                "state-v2-to-v3-test-marker",
                2,
                3,
                "add a test-only v3 marker",
                create_v3_marker,
            ),
        )
    )
    manager = StateMigrationManager(filesystem, catalog=catalog)
    backup_complete = Event()
    writer_started = Event()
    writer_finished = Event()
    original_copy = manager._create_consistent_copy

    def controlled_copy(source: Path, target: Path) -> None:
        original_copy(source, target)
        if target.name == "state-before.sqlite3":
            backup_complete.set()
            assert writer_started.wait(5.0)
            assert not writer_finished.wait(0.2)

    monkeypatch.setattr(manager, "_create_consistent_copy", controlled_copy)

    pending = WorkflowProgress(
        workflow_id="concurrent-write",
        workflow_type="migration-test",
        status="complete",
        current_step=None,
        context={"preserved": True},
        source_event_sequence=None,
        updated_at=datetime_from_text("2026-07-29T16:30:00.123456Z"),
    )

    def write_state() -> None:
        writer_started.set()
        state.save_workflow(pending)
        writer_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        migration_future = executor.submit(
            manager.apply,
            target_version=3,
            timeout=10.0,
        )
        assert backup_complete.wait(5.0)
        writer_future = executor.submit(write_state)
        migrated = migration_future.result(timeout=10.0)
        writer_future.result(timeout=10.0)

    assert migrated.applied is True
    assert writer_finished.is_set()
    assert state.get_workflow("concurrent-write") == pending
    assert database_version(tmp_path / ".ludowright/state.sqlite3") == 3
    assert migrated.receipt is not None
    with pytest.raises(MigrationRollbackError, match="changed after migration"):
        manager.rollback(migrated.receipt.run_id)


def test_migration_receipt_contract_rejects_invalid_states() -> None:
    base = {
        "run_id": "migration-example",
        "status": "prepared",
        "database_path": ".ludowright/state.sqlite3",
        "backup_path": (".ludowright/backups/migrations/migration-example/state-before.sqlite3"),
        "source_version": 1,
        "target_version": 2,
        "migration_ids": ["state-v1-to-v2-migration-history"],
        "started_at": "2026-07-29T15:00:00.123456Z",
        "before_digest": "1" * 64,
        "backup_digest": "1" * 64,
    }

    with pytest.raises(ValidationError):
        MigrationReceiptContract.model_validate({**base, "status": "completed"})
    with pytest.raises(ValidationError):
        MigrationReceiptContract.model_validate({**base, "target_version": 1})
    with pytest.raises(ValidationError):
        MigrationReceiptContract.model_validate({**base, "migration_ids": ["same", "same"]})


def datetime_from_text(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
