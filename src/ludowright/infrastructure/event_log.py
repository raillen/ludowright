"""Hash-chained append-only JSON Lines event storage."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ludowright.domain import (
    CorrelationId,
    EventDraft,
    EventHash,
    EventId,
    EventRecord,
    EventType,
    thaw_json_object,
)
from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath

DEFAULT_EVENT_LOG_PATH = RepositoryPath(".ludowright/events.jsonl")
_DEFAULT_MAX_LOG_BYTES = 64 * 1024 * 1024
_DEFAULT_MAX_LINE_BYTES = 1024 * 1024
_EVENT_LOG_LOCK_NAME = "event-log"
_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "sequence",
        "event_id",
        "event_type",
        "occurred_at",
        "correlation_id",
        "causation_id",
        "payload",
        "previous_hash",
        "hash",
    }
)


class EventLogError(RuntimeError):
    """Base class for event-log persistence and replay failures."""


class CorruptEventLogError(EventLogError):
    """Raised when a complete event-log line or chain is invalid."""


class IncompleteEventLogTailError(EventLogError):
    """Raised when the log ends with bytes that do not form a complete line."""

    def __init__(self, complete_prefix_bytes: int, trailing_bytes: int) -> None:
        self.complete_prefix_bytes = complete_prefix_bytes
        self.trailing_bytes = trailing_bytes
        super().__init__(
            "event log contains an incomplete trailing fragment: "
            f"{trailing_bytes} bytes after a {complete_prefix_bytes}-byte prefix"
        )


@dataclass(frozen=True, slots=True)
class EventLogSnapshot:
    """Validated replay result for one exact event-log revision."""

    events: tuple[EventRecord, ...]
    byte_length: int
    digest: str

    @property
    def last_sequence(self) -> int:
        return self.events[-1].sequence if self.events else 0

    @property
    def last_hash(self) -> EventHash | None:
        return self.events[-1].event_hash if self.events else None


@dataclass(frozen=True, slots=True)
class EventLogRecovery:
    """Result of explicitly removing one incomplete trailing fragment."""

    snapshot: EventLogSnapshot
    removed_bytes: int


class EventLog:
    """Replay and append canonical events under one project-relative lock."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath = DEFAULT_EVENT_LOG_PATH,
        *,
        max_log_bytes: int = _DEFAULT_MAX_LOG_BYTES,
        max_line_bytes: int = _DEFAULT_MAX_LINE_BYTES,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("event log requires ProjectFilesystem")
        if not isinstance(path, RepositoryPath):
            raise TypeError("event log requires RepositoryPath")
        if not path.name.endswith(".jsonl"):
            raise EventLogError("event log path must use the .jsonl extension")
        _validate_positive_limit(max_log_bytes, "event-log byte limit")
        _validate_positive_limit(max_line_bytes, "event-line byte limit")
        if max_line_bytes > max_log_bytes:
            raise EventLogError("event-line byte limit cannot exceed the log limit")

        self._filesystem = filesystem
        self._path = path
        self._max_log_bytes = max_log_bytes
        self._max_line_bytes = max_line_bytes

    @property
    def path(self) -> RepositoryPath:
        return self._path

    def replay(self) -> EventLogSnapshot:
        """Validate and return every complete event in sequence order."""
        payload = self._read_payload()
        return self._replay_payload(payload)

    def append(
        self,
        draft: EventDraft,
        *,
        event_id: EventId | None = None,
        occurred_at: datetime | None = None,
        timeout: float = 0.0,
    ) -> EventRecord:
        """Append one event after validating the entire current log."""
        if not isinstance(draft, EventDraft):
            raise TypeError("event append requires EventDraft")
        assigned_id = event_id or EventId(f"event-{uuid.uuid4().hex}")
        assigned_time = occurred_at or datetime.now(UTC)

        with self._filesystem.lock(_EVENT_LOG_LOCK_NAME, timeout=timeout):
            payload = self._read_payload()
            snapshot = self._replay_payload(payload)
            known_ids = {record.event_id for record in snapshot.events}
            if assigned_id in known_ids:
                raise EventLogError(f"event ID already exists: {assigned_id}")
            if draft.causation_id is not None and draft.causation_id not in known_ids:
                raise EventLogError(
                    f"causation event does not exist earlier in the log: {draft.causation_id}"
                )

            sequence = snapshot.last_sequence + 1
            previous_hash = snapshot.last_hash
            event_hash = _calculate_event_hash(
                sequence=sequence,
                event_id=assigned_id,
                event_type=draft.event_type,
                occurred_at=assigned_time,
                correlation_id=draft.correlation_id,
                causation_id=draft.causation_id,
                payload=thaw_json_object(draft.payload),
                previous_hash=previous_hash,
            )
            record = EventRecord(
                sequence=sequence,
                event_id=assigned_id,
                event_type=draft.event_type,
                occurred_at=assigned_time,
                correlation_id=draft.correlation_id,
                causation_id=draft.causation_id,
                payload=draft.payload,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )
            line = _serialize_record(record)
            if len(line) > self._max_line_bytes:
                raise EventLogError(
                    f"event line exceeds {self._max_line_bytes} bytes: {len(line)}"
                )
            if len(payload) + len(line) > self._max_log_bytes:
                raise EventLogError(
                    f"event log would exceed {self._max_log_bytes} bytes"
                )
            self._filesystem.write_bytes(self._path, payload + line)
            return record

    def recover_incomplete_tail(self, *, timeout: float = 0.0) -> EventLogRecovery:
        """Explicitly truncate only a non-newline-terminated trailing fragment."""
        with self._filesystem.lock(_EVENT_LOG_LOCK_NAME, timeout=timeout):
            payload = self._read_payload()
            prefix_length, trailing_length = _tail_lengths(payload)
            if trailing_length == 0:
                return EventLogRecovery(
                    snapshot=self._replay_payload(payload),
                    removed_bytes=0,
                )
            prefix = payload[:prefix_length]
            snapshot = self._replay_payload(prefix)
            self._filesystem.write_bytes(self._path, prefix)
            return EventLogRecovery(
                snapshot=snapshot,
                removed_bytes=trailing_length,
            )

    def _read_payload(self) -> bytes:
        try:
            return self._filesystem.read_bytes(
                self._path,
                max_bytes=self._max_log_bytes,
            )
        except FileNotFoundError:
            return b""

    def _replay_payload(self, payload: bytes) -> EventLogSnapshot:
        if not payload:
            return EventLogSnapshot(events=(), byte_length=0, digest=_digest(payload))
        prefix_length, trailing_length = _tail_lengths(payload)
        if trailing_length:
            raise IncompleteEventLogTailError(prefix_length, trailing_length)
        if payload.startswith(b"\xef\xbb\xbf"):
            raise CorruptEventLogError("event log cannot contain a UTF-8 BOM")

        records: list[EventRecord] = []
        known_ids: set[EventId] = set()
        expected_previous_hash: EventHash | None = None
        expected_sequence = 1
        for line_number, line in enumerate(payload.splitlines(keepends=True), start=1):
            if line == b"\n":
                raise CorruptEventLogError(
                    f"event log contains a blank line at {line_number}"
                )
            if len(line) > self._max_line_bytes:
                raise CorruptEventLogError(
                    f"event line {line_number} exceeds {self._max_line_bytes} bytes"
                )
            record = _parse_record(line, line_number=line_number)
            if record.sequence != expected_sequence:
                raise CorruptEventLogError(
                    f"event line {line_number} has sequence {record.sequence}; "
                    f"expected {expected_sequence}"
                )
            if record.previous_hash != expected_previous_hash:
                raise CorruptEventLogError(
                    f"event line {line_number} does not reference the previous event hash"
                )
            if record.event_id in known_ids:
                raise CorruptEventLogError(
                    f"event line {line_number} repeats event ID {record.event_id}"
                )
            if record.causation_id is not None and record.causation_id not in known_ids:
                raise CorruptEventLogError(
                    f"event line {line_number} causation does not reference an earlier event"
                )

            records.append(record)
            known_ids.add(record.event_id)
            expected_previous_hash = record.event_hash
            expected_sequence += 1

        return EventLogSnapshot(
            events=tuple(records),
            byte_length=len(payload),
            digest=_digest(payload),
        )


def _parse_record(line: bytes, *, line_number: int) -> EventRecord:
    if not line.endswith(b"\n"):
        raise CorruptEventLogError(f"event line {line_number} is incomplete")
    try:
        text = line[:-1].decode("utf-8")
    except UnicodeDecodeError as error:
        raise CorruptEventLogError(
            f"event line {line_number} is not UTF-8"
        ) from error
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except CorruptEventLogError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise CorruptEventLogError(
            f"event line {line_number} is invalid JSON"
        ) from error
    if not isinstance(raw, dict):
        raise CorruptEventLogError(f"event line {line_number} must be a JSON object")
    if frozenset(raw) != _EVENT_KEYS:
        missing = sorted(_EVENT_KEYS - frozenset(raw))
        extra = sorted(frozenset(raw) - _EVENT_KEYS)
        raise CorruptEventLogError(
            f"event line {line_number} has an invalid field set; "
            f"missing={missing}, extra={extra}"
        )
    if raw["schema_version"] != EventRecord.schema_version:
        raise CorruptEventLogError(
            f"event line {line_number} uses unsupported schema version"
        )
    if not isinstance(raw["payload"], dict):
        raise CorruptEventLogError(f"event line {line_number} payload must be an object")

    try:
        record = EventRecord(
            sequence=raw["sequence"],
            event_id=EventId(raw["event_id"]),
            event_type=EventType(raw["event_type"]),
            occurred_at=_parse_timestamp(raw["occurred_at"]),
            correlation_id=CorrelationId(raw["correlation_id"]),
            causation_id=(
                EventId(raw["causation_id"])
                if raw["causation_id"] is not None
                else None
            ),
            payload=raw["payload"],
            previous_hash=(
                EventHash(raw["previous_hash"])
                if raw["previous_hash"] is not None
                else None
            ),
            event_hash=EventHash(raw["hash"]),
        )
    except (TypeError, ValueError) as error:
        raise CorruptEventLogError(
            f"event line {line_number} violates the event contract"
        ) from error

    expected_hash = _calculate_event_hash(
        sequence=record.sequence,
        event_id=record.event_id,
        event_type=record.event_type,
        occurred_at=record.occurred_at,
        correlation_id=record.correlation_id,
        causation_id=record.causation_id,
        payload=thaw_json_object(record.payload),
        previous_hash=record.previous_hash,
    )
    if not secrets.compare_digest(expected_hash.value, record.event_hash.value):
        raise CorruptEventLogError(f"event line {line_number} hash is invalid")
    if line != _serialize_record(record):
        raise CorruptEventLogError(f"event line {line_number} is not canonical")
    return record


def _calculate_event_hash(
    *,
    sequence: int,
    event_id: EventId,
    event_type: EventType,
    occurred_at: datetime,
    correlation_id: CorrelationId,
    causation_id: EventId | None,
    payload: dict[str, object],
    previous_hash: EventHash | None,
) -> EventHash:
    body = _event_body(
        sequence=sequence,
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload,
        previous_hash=previous_hash,
    )
    return EventHash(hashlib.sha256(_canonical_json(body)).hexdigest())


def _serialize_record(record: EventRecord) -> bytes:
    body = _event_body(
        sequence=record.sequence,
        event_id=record.event_id,
        event_type=record.event_type,
        occurred_at=record.occurred_at,
        correlation_id=record.correlation_id,
        causation_id=record.causation_id,
        payload=thaw_json_object(record.payload),
        previous_hash=record.previous_hash,
    )
    body["hash"] = record.event_hash.value
    return _canonical_json(body) + b"\n"


def _event_body(
    *,
    sequence: int,
    event_id: EventId,
    event_type: EventType,
    occurred_at: datetime,
    correlation_id: CorrelationId,
    causation_id: EventId | None,
    payload: dict[str, object],
    previous_hash: EventHash | None,
) -> dict[str, object]:
    return {
        "schema_version": EventRecord.schema_version,
        "sequence": sequence,
        "event_id": event_id.value,
        "event_type": event_type.value,
        "occurred_at": _format_timestamp(occurred_at),
        "correlation_id": correlation_id.value,
        "causation_id": causation_id.value if causation_id is not None else None,
        "payload": payload,
        "previous_hash": previous_hash.value if previous_hash is not None else None,
    }


def _canonical_json(value: dict[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as error:
        raise EventLogError("event cannot be serialized as canonical JSON") from error


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EventLogError("event timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise CorruptEventLogError("event timestamp must be a string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise CorruptEventLogError("event timestamp is not canonical UTC") from error
    if _format_timestamp(parsed) != value:
        raise CorruptEventLogError("event timestamp is not canonical UTC")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorruptEventLogError(f"duplicate event JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise CorruptEventLogError(f"non-finite event number is not allowed: {value}")


def _tail_lengths(payload: bytes) -> tuple[int, int]:
    if not payload or payload.endswith(b"\n"):
        return len(payload), 0
    last_newline = payload.rfind(b"\n")
    prefix_length = last_newline + 1
    return prefix_length, len(payload) - prefix_length


def _validate_positive_limit(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EventLogError(f"{label} must be a positive integer")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
