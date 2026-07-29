"""Immutable event values used by the append-only project event log."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import ClassVar

from ludowright.domain.errors import InvalidEventError
from ludowright.domain.identifiers import CorrelationId, EventId

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
_EVENT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_EVENT_TYPE_LENGTH = 100
_MAX_PAYLOAD_DEPTH = 64
_MAX_PAYLOAD_VALUES = 50_000


type FrozenJsonScalar = None | bool | int | float | str
type FrozenJsonValue = (
    FrozenJsonScalar | tuple["FrozenJsonValue", ...] | Mapping[str, "FrozenJsonValue"]
)


@dataclass(frozen=True, slots=True)
class EventType:
    """Namespaced canonical event type such as ``project.created``."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidEventError("event type must be a string")
        if not 3 <= len(self.value) <= _MAX_EVENT_TYPE_LENGTH:
            raise InvalidEventError(
                f"event type must contain 3 to {_MAX_EVENT_TYPE_LENGTH} characters"
            )
        if _EVENT_TYPE_PATTERN.fullmatch(self.value) is None:
            raise InvalidEventError(
                "event type must be namespaced lowercase words separated by dots or hyphens"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EventHash:
    """Lowercase SHA-256 identity for one canonical event line."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _EVENT_HASH_PATTERN.fullmatch(self.value) is None:
            raise InvalidEventError("event hash must be lowercase SHA-256")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EventDraft:
    """Validated event content before sequence, timestamp, ID, and hash assignment."""

    event_type: EventType
    correlation_id: CorrelationId
    payload: Mapping[str, FrozenJsonValue]
    causation_id: EventId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise InvalidEventError("event draft requires a canonical event type")
        if not isinstance(self.correlation_id, CorrelationId):
            raise InvalidEventError("event draft requires a correlation ID")
        if self.causation_id is not None and not isinstance(self.causation_id, EventId):
            raise InvalidEventError("event causation must reference an event ID")
        object.__setattr__(self, "payload", freeze_json_object(self.payload))


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One immutable event record stored in sequence order."""

    schema_version: ClassVar[int] = 1

    sequence: int
    event_id: EventId
    event_type: EventType
    occurred_at: datetime
    correlation_id: CorrelationId
    payload: Mapping[str, FrozenJsonValue]
    previous_hash: EventHash | None
    event_hash: EventHash
    causation_id: EventId | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise InvalidEventError("event sequence must be a positive integer")
        if not isinstance(self.event_id, EventId):
            raise InvalidEventError("event record requires an event ID")
        if not isinstance(self.event_type, EventType):
            raise InvalidEventError("event record requires a canonical event type")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise InvalidEventError("event timestamp must be timezone-aware")
        normalized_timestamp = self.occurred_at.astimezone(UTC)
        if not isinstance(self.correlation_id, CorrelationId):
            raise InvalidEventError("event record requires a correlation ID")
        if self.causation_id is not None and not isinstance(self.causation_id, EventId):
            raise InvalidEventError("event causation must reference an event ID")
        if self.causation_id == self.event_id:
            raise InvalidEventError("an event cannot cause itself")
        if self.previous_hash is not None and not isinstance(self.previous_hash, EventHash):
            raise InvalidEventError("event previous hash must be canonical")
        if not isinstance(self.event_hash, EventHash):
            raise InvalidEventError("event record requires a canonical hash")

        object.__setattr__(self, "occurred_at", normalized_timestamp)
        object.__setattr__(self, "payload", freeze_json_object(self.payload))


def freeze_json_object(
    value: Mapping[str, object] | Mapping[str, FrozenJsonValue],
) -> Mapping[str, FrozenJsonValue]:
    """Return an immutable, bounded, JSON-compatible mapping."""
    if not isinstance(value, Mapping):
        raise InvalidEventError("event payload must be a JSON object")
    remaining = [_MAX_PAYLOAD_VALUES]
    frozen = _freeze_json(value, depth=0, remaining=remaining)
    if not isinstance(frozen, Mapping):
        raise InvalidEventError("event payload must be a JSON object")
    return frozen


def thaw_json_object(value: Mapping[str, FrozenJsonValue]) -> dict[str, object]:
    """Convert an immutable payload into ordinary JSON-compatible containers."""
    thawed = _thaw_json(value)
    if not isinstance(thawed, dict):
        raise InvalidEventError("event payload must be a JSON object")
    return thawed


def _freeze_json(value: object, *, depth: int, remaining: list[int]) -> FrozenJsonValue:
    remaining[0] -= 1
    if remaining[0] < 0:
        raise InvalidEventError(
            f"event payload cannot exceed {_MAX_PAYLOAD_VALUES} values"
        )
    if depth > _MAX_PAYLOAD_DEPTH:
        raise InvalidEventError(
            f"event payload cannot exceed {_MAX_PAYLOAD_DEPTH} nesting levels"
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidEventError("event payload cannot contain non-finite numbers")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, depth=depth + 1, remaining=remaining) for item in value
        )
    if isinstance(value, Mapping):
        result: dict[str, FrozenJsonValue] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise InvalidEventError("event payload object keys must be strings")
            result[key] = _freeze_json(
                value[key],
                depth=depth + 1,
                remaining=remaining,
            )
        return MappingProxyType(result)
    raise InvalidEventError(
        f"event payload cannot contain {type(value).__name__} values"
    )


def _thaw_json(value: FrozenJsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value
