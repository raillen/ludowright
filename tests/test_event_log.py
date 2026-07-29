"""Tests for immutable events and the hash-chained JSON Lines event log."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ludowright.domain import (
    CorrelationId,
    EventDraft,
    EventId,
    EventType,
    InvalidEventError,
)
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    CorruptEventLogError,
    EventLog,
    EventLogError,
    IncompleteEventLogTailError,
    ProjectFilesystem,
    RepositoryPath,
)

_FIXED_TIME = datetime(2026, 7, 29, 12, 30, 45, 123456, tzinfo=UTC)


def event_draft(
    event_type: str = "project.created",
    *,
    correlation: str = "correlation-one",
    causation: str | None = None,
    payload: dict[str, object] | None = None,
) -> EventDraft:
    return EventDraft(
        event_type=EventType(event_type),
        correlation_id=CorrelationId(correlation),
        causation_id=EventId(causation) if causation is not None else None,
        payload=payload or {"project_id": "locadora-2000"},
    )


def event_log(tmp_path: Path, **limits: int) -> EventLog:
    return EventLog(ProjectFilesystem(tmp_path), **limits)


def read_lines(tmp_path: Path) -> list[dict[str, object]]:
    text = (tmp_path / ".ludowright/events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def canonical_line(raw: dict[str, object]) -> bytes:
    return (
        json.dumps(
            raw,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def rehash(raw: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in raw.items() if key != "hash"}
    raw["hash"] = hashlib.sha256(canonical_line(body)[:-1]).hexdigest()
    return raw


def write_raw_lines(tmp_path: Path, lines: list[dict[str, object]]) -> None:
    payload = b"".join(canonical_line(line) for line in lines)
    ProjectFilesystem(tmp_path).write_bytes(DEFAULT_EVENT_LOG_PATH, payload)


@pytest.mark.parametrize(
    "value",
    [
        "project",
        "Project.created",
        "project_created",
        "project..created",
        ".project",
        "project.",
        "a" * 101,
    ],
)
def test_invalid_event_types_are_rejected(value: str) -> None:
    with pytest.raises(InvalidEventError):
        EventType(value)


def test_event_payload_is_deeply_immutable() -> None:
    source = {"items": [{"id": "one"}], "enabled": True}
    draft = event_draft(payload=source)

    source["enabled"] = False
    source["items"] = []

    assert draft.payload["enabled"] is True
    assert draft.payload["items"] == ({"id": "one"},)
    with pytest.raises(TypeError):
        draft.payload["new"] = "value"  # type: ignore[index]


@pytest.mark.parametrize(
    "payload",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": {"unsupported"}},
        {1: "non-string"},
    ],
)
def test_event_payload_rejects_non_json_values(payload: dict[object, object]) -> None:
    with pytest.raises(InvalidEventError):
        EventDraft(
            event_type=EventType("project.changed"),
            correlation_id=CorrelationId("correlation-one"),
            payload=payload,  # type: ignore[arg-type]
        )


def test_empty_event_log_replays_as_stable_snapshot(tmp_path: Path) -> None:
    snapshot = event_log(tmp_path).replay()

    assert snapshot.events == ()
    assert snapshot.byte_length == 0
    assert snapshot.last_sequence == 0
    assert snapshot.last_hash is None
    assert snapshot.digest == hashlib.sha256(b"").hexdigest()


def test_append_assigns_deterministic_sequence_timestamp_and_hash(tmp_path: Path) -> None:
    log = event_log(tmp_path)

    record = log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    snapshot = log.replay()
    raw = read_lines(tmp_path)[0]

    assert record == snapshot.events[0]
    assert record.sequence == 1
    assert record.previous_hash is None
    assert raw["event_id"] == "event-one"
    assert raw["occurred_at"] == "2026-07-29T12:30:45.123456Z"
    assert raw["hash"] == record.event_hash.value
    assert len(record.event_hash.value) == 64


def test_event_chain_preserves_correlation_and_causation(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    first = log.append(
        event_draft(correlation="operation-one"),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    second = log.append(
        event_draft(
            "project.renamed",
            correlation="operation-one",
            causation="event-one",
            payload={"name": "Locadora 2000"},
        ),
        event_id=EventId("event-two"),
        occurred_at=_FIXED_TIME,
    )

    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert second.causation_id == first.event_id
    assert log.replay().events == (first, second)


def test_append_rejects_missing_causation_event(tmp_path: Path) -> None:
    with pytest.raises(EventLogError, match="does not exist earlier"):
        event_log(tmp_path).append(
            event_draft(causation="event-missing"),
            event_id=EventId("event-one"),
            occurred_at=_FIXED_TIME,
        )


def test_append_rejects_duplicate_event_id(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )

    with pytest.raises(EventLogError, match="already exists"):
        log.append(
            event_draft("project.changed"),
            event_id=EventId("event-one"),
            occurred_at=_FIXED_TIME,
        )


def test_reopened_log_replays_existing_events(tmp_path: Path) -> None:
    first_log = event_log(tmp_path)
    expected = first_log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )

    reopened = event_log(tmp_path)

    assert reopened.replay().events == (expected,)


def test_replay_rejects_tampered_payload_hash(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    raw = read_lines(tmp_path)[0]
    raw["payload"] = {"project_id": "tampered"}
    write_raw_lines(tmp_path, [raw])

    with pytest.raises(CorruptEventLogError, match="hash is invalid"):
        log.replay()


def test_replay_rejects_sequence_gap(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    raw = read_lines(tmp_path)[0]
    raw["sequence"] = 2
    write_raw_lines(tmp_path, [rehash(raw)])

    with pytest.raises(CorruptEventLogError, match="expected 1"):
        log.replay()


def test_replay_rejects_wrong_previous_hash(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    log.append(
        event_draft("project.changed"),
        event_id=EventId("event-two"),
        occurred_at=_FIXED_TIME,
    )
    lines = read_lines(tmp_path)
    lines[1]["previous_hash"] = "0" * 64
    rehash(lines[1])
    write_raw_lines(tmp_path, lines)

    with pytest.raises(CorruptEventLogError, match="previous event hash"):
        log.replay()


def test_replay_rejects_duplicate_event_id(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    log.append(
        event_draft("project.changed"),
        event_id=EventId("event-two"),
        occurred_at=_FIXED_TIME,
    )
    lines = read_lines(tmp_path)
    lines[1]["event_id"] = "event-one"
    rehash(lines[1])
    write_raw_lines(tmp_path, lines)

    with pytest.raises(CorruptEventLogError, match="repeats event ID"):
        log.replay()


def test_replay_rejects_causation_that_is_not_earlier(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    raw = read_lines(tmp_path)[0]
    raw["causation_id"] = "event-future"
    write_raw_lines(tmp_path, [rehash(raw)])

    with pytest.raises(CorruptEventLogError, match="earlier event"):
        log.replay()


def test_replay_rejects_noncanonical_json_spacing(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    raw = read_lines(tmp_path)[0]
    noncanonical = (json.dumps(raw, sort_keys=True) + "\n").encode()
    ProjectFilesystem(tmp_path).write_bytes(DEFAULT_EVENT_LOG_PATH, noncanonical)

    with pytest.raises(CorruptEventLogError, match="not canonical"):
        log.replay()


def test_replay_rejects_unknown_fields(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    raw = read_lines(tmp_path)[0]
    raw["unexpected"] = True
    write_raw_lines(tmp_path, [raw])

    with pytest.raises(CorruptEventLogError, match="invalid field set"):
        log.replay()


def test_replay_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    text = (tmp_path / ".ludowright/events.jsonl").read_text(encoding="utf-8")
    text = text.replace(
        '"schema_version":1',
        '"schema_version":1,"schema_version":1',
        1,
    )
    ProjectFilesystem(tmp_path).write_text(DEFAULT_EVENT_LOG_PATH, text)

    with pytest.raises(CorruptEventLogError, match="duplicate event JSON key"):
        log.replay()


def test_replay_rejects_nonfinite_json_number(tmp_path: Path) -> None:
    ProjectFilesystem(tmp_path).write_text(
        DEFAULT_EVENT_LOG_PATH,
        '{"payload":{"value":NaN}}\n',
    )

    with pytest.raises(CorruptEventLogError, match="non-finite"):
        event_log(tmp_path).replay()


def test_replay_rejects_blank_lines(tmp_path: Path) -> None:
    ProjectFilesystem(tmp_path).write_bytes(DEFAULT_EVENT_LOG_PATH, b"\n")

    with pytest.raises(CorruptEventLogError, match="blank line"):
        event_log(tmp_path).replay()


def test_replay_reports_incomplete_tail(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    filesystem = ProjectFilesystem(tmp_path)
    complete = filesystem.read_bytes(DEFAULT_EVENT_LOG_PATH)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, complete + b'{"partial"')

    with pytest.raises(IncompleteEventLogTailError) as caught:
        log.replay()

    assert caught.value.complete_prefix_bytes == len(complete)
    assert caught.value.trailing_bytes == len(b'{"partial"')


def test_explicit_recovery_removes_only_incomplete_tail(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    expected = log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )
    filesystem = ProjectFilesystem(tmp_path)
    complete = filesystem.read_bytes(DEFAULT_EVENT_LOG_PATH)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, complete + b"partial")

    recovery = log.recover_incomplete_tail()

    assert recovery.removed_bytes == len(b"partial")
    assert recovery.snapshot.events == (expected,)
    assert filesystem.read_bytes(DEFAULT_EVENT_LOG_PATH) == complete


def test_recovery_never_hides_corruption_in_complete_prefix(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    original = b'{"invalid":true}\npartial'
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, original)

    with pytest.raises(CorruptEventLogError):
        event_log(tmp_path).recover_incomplete_tail()

    assert filesystem.read_bytes(DEFAULT_EVENT_LOG_PATH) == original


def test_recovery_is_noop_for_complete_log(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    expected = log.append(
        event_draft(),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )

    recovery = log.recover_incomplete_tail()

    assert recovery.removed_bytes == 0
    assert recovery.snapshot.events == (expected,)


def test_event_log_rejects_invalid_path_and_limits(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    with pytest.raises(EventLogError, match=".jsonl"):
        EventLog(filesystem, RepositoryPath("events.json"))
    with pytest.raises(EventLogError, match="positive"):
        EventLog(filesystem, max_log_bytes=0)
    with pytest.raises(EventLogError, match="cannot exceed"):
        EventLog(filesystem, max_log_bytes=10, max_line_bytes=11)


def test_append_rejects_naive_timestamp(tmp_path: Path) -> None:
    with pytest.raises(EventLogError, match="timezone-aware"):
        event_log(tmp_path).append(
            event_draft(),
            event_id=EventId("event-one"),
            occurred_at=datetime(2026, 7, 29, 12, 0),
        )


def test_event_line_limit_is_enforced(tmp_path: Path) -> None:
    log = event_log(tmp_path, max_log_bytes=4096, max_line_bytes=256)

    with pytest.raises(EventLogError, match="event line exceeds"):
        log.append(
            event_draft(payload={"text": "x" * 1000}),
            event_id=EventId("event-one"),
            occurred_at=_FIXED_TIME,
        )


def test_event_log_limit_is_enforced(tmp_path: Path) -> None:
    log = event_log(tmp_path, max_log_bytes=700, max_line_bytes=600)
    log.append(
        event_draft(payload={"text": "x" * 100}),
        event_id=EventId("event-one"),
        occurred_at=_FIXED_TIME,
    )

    with pytest.raises(EventLogError, match="log would exceed"):
        log.append(
            event_draft("project.changed", payload={"text": "y" * 300}),
            event_id=EventId("event-two"),
            occurred_at=_FIXED_TIME,
        )


def test_concurrent_appends_produce_contiguous_valid_sequence(tmp_path: Path) -> None:
    log = event_log(tmp_path)

    def append(index: int) -> None:
        log.append(
            event_draft(
                "project.changed",
                correlation="parallel-operation",
                payload={"index": index},
            ),
            event_id=EventId(f"event-{index}"),
            occurred_at=_FIXED_TIME,
            timeout=5.0,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(1, 13)))

    snapshot = log.replay()
    assert [event.sequence for event in snapshot.events] == list(range(1, 13))
    assert {event.event_id.value for event in snapshot.events} == {
        f"event-{index}" for index in range(1, 13)
    }
