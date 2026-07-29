"""Tests for the rebuildable SQLite workflow and source index."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ludowright.domain import CorrelationId, EventDraft, EventId, EventType
from ludowright.infrastructure import (
    DEFAULT_STATE_STORE_PATH,
    EventIndexState,
    EventLog,
    IndexedEntity,
    ProjectFilesystem,
    RepositoryPath,
    SourceIndexState,
    StateStore,
    StateStoreCorruptionError,
    StateStoreError,
    UnsafeProjectPathError,
    UnsupportedStateSchemaError,
    WorkflowProgress,
)

_FIXED_TIME = datetime(2026, 7, 29, 15, 0, 0, 123456, tzinfo=UTC)


def workflow(
    workflow_id: str = "project-intake",
    *,
    status: str = "in-progress",
    step: str | None = "collect-platforms",
    context: dict[str, object] | None = None,
    sequence: int | None = 1,
) -> WorkflowProgress:
    return WorkflowProgress(
        workflow_id=workflow_id,
        workflow_type="guided-intake",
        status=status,
        current_step=step,
        context=context or {"answered": 3, "pending": ["engine", "platforms"]},
        source_event_sequence=sequence,
        updated_at=_FIXED_TIME,
    )


def indexed_entity(
    source_path: RepositoryPath,
    source_digest: str,
    *,
    entity_type: str = "asset",
    entity_id: str = "prop-counter",
    revision: int = 1,
    status: str = "planned",
) -> IndexedEntity:
    return IndexedEntity(
        entity_type=entity_type,
        entity_id=entity_id,
        source_path=source_path,
        source_digest=source_digest,
        revision=revision,
        status=status,
        updated_at=_FIXED_TIME,
    )


def store(tmp_path: Path, **settings: int) -> StateStore:
    return StateStore(ProjectFilesystem(tmp_path), **settings)


def append_event(log: EventLog, event_id: str, event_type: str = "project.created") -> None:
    log.append(
        EventDraft(
            event_type=EventType(event_type),
            correlation_id=CorrelationId("operation-one"),
            payload={"event_id": event_id},
        ),
        event_id=EventId(event_id),
        occurred_at=_FIXED_TIME,
    )


def test_state_store_initializes_strict_wal_schema(tmp_path: Path) -> None:
    state = store(tmp_path)
    database = tmp_path / ".ludowright/state.sqlite3"

    assert state.path == DEFAULT_STATE_STORE_PATH
    assert state.schema_version == 1
    assert database.is_file()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "event_checkpoint",
            "indexed_entity",
            "workflow_progress",
        }.issubset(tables)
    finally:
        connection.close()


def test_state_store_rejects_invalid_configuration(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    with pytest.raises(StateStoreError, match=r"\.sqlite3"):
        StateStore(filesystem, RepositoryPath(".ludowright/state.db"))
    with pytest.raises(StateStoreError, match="positive"):
        StateStore(filesystem, busy_timeout_ms=0)
    with pytest.raises(StateStoreError, match="positive"):
        StateStore(filesystem, source_read_limit=0)


def test_state_store_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    directory = tmp_path / ".ludowright"
    directory.mkdir()
    connection = sqlite3.connect(directory / "state.sqlite3")
    connection.execute("PRAGMA user_version = 99")
    connection.close()

    with pytest.raises(UnsupportedStateSchemaError, match="v99"):
        store(tmp_path)


def test_state_store_rejects_corrupt_database(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    filesystem.write_bytes(DEFAULT_STATE_STORE_PATH, b"not a sqlite database")

    with pytest.raises(StateStoreCorruptionError, match="invalid"):
        StateStore(filesystem)


def test_state_store_rejects_database_symlink(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are unavailable")
    directory = tmp_path / ".ludowright"
    directory.mkdir()
    target = tmp_path / "outside.sqlite3"
    sqlite3.connect(target).close()
    (directory / "state.sqlite3").symlink_to(target)

    with pytest.raises(UnsafeProjectPathError, match="symlink"):
        store(tmp_path)


def test_workflow_round_trip_update_list_and_delete(tmp_path: Path) -> None:
    state = store(tmp_path)
    first = workflow("workflow-b")
    second = workflow("workflow-a", status="waiting-approval", step=None)

    state.save_workflow(first)
    state.save_workflow(second)

    assert state.get_workflow("missing") is None
    assert state.get_workflow(first.workflow_id) == first
    assert [item.workflow_id for item in state.list_workflows()] == [
        "workflow-a",
        "workflow-b",
    ]

    updated = workflow("workflow-b", status="completed", step=None, sequence=2)
    state.save_workflow(updated)
    assert state.get_workflow("workflow-b") == updated
    assert state.delete_workflow("workflow-b") is True
    assert state.delete_workflow("workflow-b") is False


def test_workflow_context_is_deeply_immutable(tmp_path: Path) -> None:
    context = {"answers": [{"id": "platform", "value": "windows"}]}
    progress = workflow(context=context)
    context["answers"] = []

    store(tmp_path).save_workflow(progress)
    loaded = store(tmp_path).get_workflow(progress.workflow_id)

    assert loaded is not None
    assert loaded.context["answers"] == ({"id": "platform", "value": "windows"},)
    with pytest.raises(TypeError):
        loaded.context["new"] = True  # type: ignore[index]


def test_workflow_validation_rejects_invalid_values() -> None:
    with pytest.raises(StateStoreError, match="workflow ID"):
        workflow("Not Canonical")
    with pytest.raises(StateStoreError, match="source event sequence"):
        workflow(sequence=0)
    with pytest.raises(Exception, match="non-finite"):
        workflow(context={"value": float("nan")})


def test_corrupt_workflow_row_is_detected(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.save_workflow(workflow())
    connection = sqlite3.connect(tmp_path / ".ludowright/state.sqlite3")
    connection.execute(
        "UPDATE workflow_progress SET context_json = ? WHERE workflow_id = ?",
        ("[]", "project-intake"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(StateStoreCorruptionError, match="JSON object"):
        state.get_workflow("project-intake")


def test_entity_round_trip_filter_update_and_delete(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    source_a = RepositoryPath("data/assets/prop-counter.json")
    source_b = RepositoryPath("data/projects/locadora.json")
    payload_a = b'{"id":"prop-counter"}\n'
    payload_b = b'{"id":"locadora-2000"}\n'
    filesystem.write_bytes(source_a, payload_a)
    filesystem.write_bytes(source_b, payload_b)
    state = StateStore(filesystem)
    asset = indexed_entity(source_a, hashlib.sha256(payload_a).hexdigest())
    project = indexed_entity(
        source_b,
        hashlib.sha256(payload_b).hexdigest(),
        entity_type="project",
        entity_id="locadora-2000",
        status="active",
    )

    state.index_entity(project)
    state.index_entity(asset)

    assert state.get_entity("asset", "missing") is None
    assert state.get_entity("asset", "prop-counter") == asset
    assert [(item.entity_type, item.entity_id) for item in state.list_entities()] == [
        ("asset", "prop-counter"),
        ("project", "locadora-2000"),
    ]
    assert state.list_entities(entity_type="project") == (project,)

    updated = indexed_entity(
        source_a,
        hashlib.sha256(payload_a).hexdigest(),
        revision=2,
        status="approved",
    )
    state.index_entity(updated)
    assert state.get_entity("asset", "prop-counter") == updated
    assert state.delete_entity("asset", "prop-counter") is True
    assert state.delete_entity("asset", "prop-counter") is False


def test_entity_validation_rejects_invalid_digest_and_revision(tmp_path: Path) -> None:
    path = RepositoryPath("data/item.json")

    with pytest.raises(StateStoreError, match="SHA-256"):
        indexed_entity(path, "bad")
    with pytest.raises(StateStoreError, match="positive integer"):
        indexed_entity(path, "0" * 64, revision=0)


def test_source_consistency_reports_matching_changed_and_missing(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    path_matching = RepositoryPath("data/matching.json")
    path_changed = RepositoryPath("data/changed.json")
    path_missing = RepositoryPath("data/missing.json")
    filesystem.write_bytes(path_matching, b"matching")
    filesystem.write_bytes(path_changed, b"original")
    state = StateStore(filesystem)
    state.index_entity(
        indexed_entity(
            path_matching,
            hashlib.sha256(b"matching").hexdigest(),
            entity_id="matching",
        )
    )
    state.index_entity(
        indexed_entity(
            path_changed,
            hashlib.sha256(b"original").hexdigest(),
            entity_id="changed",
        )
    )
    state.index_entity(
        indexed_entity(
            path_missing,
            hashlib.sha256(b"missing").hexdigest(),
            entity_id="missing",
        )
    )
    filesystem.write_bytes(path_changed, b"modified")

    report = state.check_consistency(EventLog(filesystem).replay())
    states = {source.entity_id: source.state for source in report.sources}

    assert states == {
        "changed": SourceIndexState.CHANGED,
        "matching": SourceIndexState.IN_SYNC,
        "missing": SourceIndexState.MISSING,
    }
    assert report.is_consistent is False


def test_source_consistency_reports_symlink_and_nonfile(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are unavailable")
    filesystem = ProjectFilesystem(tmp_path)
    symlink_path = RepositoryPath("data/symlink.json")
    directory_path = RepositoryPath("data/directory.json")
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    filesystem.ensure_directory(RepositoryPath("data"))
    (tmp_path / "data/symlink.json").symlink_to(outside)
    (tmp_path / "data/directory.json").mkdir()
    state = StateStore(filesystem)
    state.index_entity(
        indexed_entity(
            symlink_path,
            hashlib.sha256(b"outside").hexdigest(),
            entity_id="symlink",
        )
    )
    state.index_entity(
        indexed_entity(
            directory_path,
            hashlib.sha256(b"directory").hexdigest(),
            entity_id="directory",
        )
    )

    report = state.check_consistency(EventLog(filesystem).replay())
    states = {source.entity_id: source.state for source in report.sources}

    assert states["symlink"] is SourceIndexState.INVALID_PATH
    assert states["directory"] is SourceIndexState.UNREADABLE


def test_empty_log_without_checkpoint_is_consistent(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    report = StateStore(filesystem).check_consistency(EventLog(filesystem).replay())

    assert report.event_state is EventIndexState.IN_SYNC
    assert report.is_consistent is True


def test_nonempty_log_without_checkpoint_reports_empty_index(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    log = EventLog(filesystem)
    append_event(log, "event-one")

    report = StateStore(filesystem).check_consistency(log.replay())

    assert report.event_state is EventIndexState.EMPTY_INDEX
    assert report.is_consistent is False


def test_event_checkpoint_in_sync_and_behind(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    log = EventLog(filesystem)
    append_event(log, "event-one")
    first_snapshot = log.replay()
    state = StateStore(filesystem)
    checkpoint = state.record_event_checkpoint(first_snapshot, updated_at=_FIXED_TIME)

    assert checkpoint == state.get_event_checkpoint()
    assert state.check_consistency(first_snapshot).event_state is EventIndexState.IN_SYNC

    append_event(log, "event-two", "project.changed")
    report = state.check_consistency(log.replay())

    assert report.event_state is EventIndexState.BEHIND
    assert "stops at event 1" in report.event_detail


def test_event_checkpoint_detects_divergent_history(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_filesystem = ProjectFilesystem(first_root)
    second_filesystem = ProjectFilesystem(second_root)
    first_log = EventLog(first_filesystem)
    second_log = EventLog(second_filesystem)
    append_event(first_log, "event-one", "project.created")
    append_event(second_log, "event-other", "project.created")
    state = StateStore(first_filesystem)
    state.record_event_checkpoint(first_log.replay(), updated_at=_FIXED_TIME)

    report = state.check_consistency(second_log.replay())

    assert report.event_state is EventIndexState.DIVERGED
    assert "hash" in report.event_detail


def test_event_checkpoint_ahead_of_log_is_divergent(tmp_path: Path) -> None:
    long_root = tmp_path / "long"
    short_root = tmp_path / "short"
    long_root.mkdir()
    short_root.mkdir()
    long_filesystem = ProjectFilesystem(long_root)
    short_filesystem = ProjectFilesystem(short_root)
    long_log = EventLog(long_filesystem)
    append_event(long_log, "event-one")
    append_event(long_log, "event-two", "project.changed")
    state = StateStore(long_filesystem)
    state.record_event_checkpoint(long_log.replay(), updated_at=_FIXED_TIME)

    report = state.check_consistency(EventLog(short_filesystem).replay())

    assert report.event_state is EventIndexState.DIVERGED
    assert "ahead" in report.event_detail


def test_state_database_is_rebuildable_without_canonical_data_loss(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    canonical_path = RepositoryPath("data/project.json")
    canonical_payload = b'{"id":"locadora-2000"}\n'
    filesystem.write_bytes(canonical_path, canonical_payload)
    log = EventLog(filesystem)
    append_event(log, "event-one")
    state = StateStore(filesystem)
    state.save_workflow(workflow())
    state.index_entity(
        indexed_entity(
            canonical_path,
            hashlib.sha256(canonical_payload).hexdigest(),
            entity_type="project",
            entity_id="locadora-2000",
        )
    )
    state.record_event_checkpoint(log.replay(), updated_at=_FIXED_TIME)

    database = tmp_path / ".ludowright/state.sqlite3"
    for suffix in ("-shm", "-wal"):
        Path(f"{database}{suffix}").unlink(missing_ok=True)
    database.unlink()
    rebuilt = StateStore(filesystem)

    assert rebuilt.list_workflows() == ()
    assert rebuilt.list_entities() == ()
    assert rebuilt.get_event_checkpoint() is None
    assert filesystem.read_bytes(canonical_path) == canonical_payload
    assert len(log.replay().events) == 1


def test_concurrent_workflow_writes_remain_transactional(tmp_path: Path) -> None:
    state = store(tmp_path, busy_timeout_ms=10_000)

    def save(index: int) -> None:
        state.save_workflow(
            workflow(
                f"workflow-{index}",
                context={"index": index},
                sequence=index,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save, range(1, 17)))

    workflows = state.list_workflows()
    assert len(workflows) == 16
    assert {item.workflow_id for item in workflows} == {
        f"workflow-{index}" for index in range(1, 17)
    }


def test_context_is_stored_as_canonical_json(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.save_workflow(workflow(context={"z": 1, "a": [2, 3]}))
    connection = sqlite3.connect(tmp_path / ".ludowright/state.sqlite3")
    try:
        stored = connection.execute(
            "SELECT context_json FROM workflow_progress WHERE workflow_id = ?",
            ("project-intake",),
        ).fetchone()[0]
    finally:
        connection.close()

    assert stored == json.dumps(
        {"a": [2, 3], "z": 1},
        separators=(",", ":"),
        sort_keys=True,
    )
