"""Canonical, bounded JSON and YAML repositories over the project filesystem."""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

import yaml
from pydantic import ValidationError
from yaml.composer import ComposerError
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode

from ludowright.contracts.common import ContractModel
from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath

_DEFAULT_MAX_BYTES = 2_000_000
_MAX_STRUCTURE_DEPTH = 100
_MAX_STRUCTURE_NODES = 100_000
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

TContract = TypeVar("TContract", bound=ContractModel)


class StructuredDocumentError(RuntimeError):
    """Base class for persisted structured-document failures."""


class StructuredDocumentFormatError(StructuredDocumentError):
    """Raised when a document does not use the required canonical format."""


class StructuredDocumentParseError(StructuredDocumentError):
    """Raised when bounded JSON or YAML input cannot be parsed safely."""


class StructuredDocumentConflictError(StructuredDocumentError):
    """Raised when optimistic concurrency detects a changed document."""


class StructuredDocumentFormat(StrEnum):
    JSON = "json"
    YAML = "yaml"


@dataclass(frozen=True, slots=True)
class StructuredDocumentSnapshot(Generic[TContract]):
    """One validated document together with its exact persisted identity."""

    path: RepositoryPath
    format: StructuredDocumentFormat
    value: TContract
    digest: str
    canonical: bool
    size_bytes: int


class StructuredDocumentRepository(Generic[TContract]):
    """Persist one strict Pydantic contract in canonical JSON or YAML."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath,
        model: type[TContract],
        *,
        format: StructuredDocumentFormat,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("structured repositories require ProjectFilesystem")
        if not isinstance(path, RepositoryPath):
            raise TypeError("structured repositories require RepositoryPath")
        if not isinstance(model, type) or not issubclass(model, ContractModel):
            raise TypeError("structured repositories require a ContractModel type")
        if not isinstance(format, StructuredDocumentFormat):
            raise TypeError("structured repositories require a canonical document format")
        _validate_max_bytes(max_bytes)
        _validate_extension(path, format)

        self._filesystem = filesystem
        self._path = path
        self._model = model
        self._format = format
        self._max_bytes = max_bytes
        path_digest = hashlib.sha256(path.value.encode("ascii")).hexdigest()[:24]
        self._lock_name = f"document-{path_digest}"

    @property
    def path(self) -> RepositoryPath:
        return self._path

    @property
    def format(self) -> StructuredDocumentFormat:
        return self._format

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def load(self) -> StructuredDocumentSnapshot[TContract]:
        """Read, parse, validate, and fingerprint the current document."""
        payload = self._filesystem.read_bytes(self._path, max_bytes=self._max_bytes)
        value = self._parse_and_validate(payload)
        canonical_payload = self._serialize(value)
        return StructuredDocumentSnapshot(
            path=self._path,
            format=self._format,
            value=value,
            digest=_digest(payload),
            canonical=payload == canonical_payload,
            size_bytes=len(payload),
        )

    def load_optional(self) -> StructuredDocumentSnapshot[TContract] | None:
        """Return no snapshot when the document does not exist."""
        try:
            return self.load()
        except FileNotFoundError:
            return None

    def create(
        self,
        value: TContract,
        *,
        timeout: float = 0.0,
    ) -> StructuredDocumentSnapshot[TContract]:
        """Create a document only when no file currently exists."""
        validated = self._validate_instance(value)
        payload = self._serialize(validated)
        with self._filesystem.lock(self._lock_name, timeout=timeout):
            if self._current_digest() is not None:
                raise StructuredDocumentConflictError(
                    f"structured document already exists: {self._path}"
                )
            self._filesystem.write_bytes(self._path, payload)
        return self._snapshot(validated, payload)

    def save(
        self,
        value: TContract,
        *,
        expected_digest: str | None = None,
        timeout: float = 0.0,
    ) -> StructuredDocumentSnapshot[TContract]:
        """Atomically save a canonical document with optional conflict detection."""
        validated = self._validate_instance(value)
        if expected_digest is not None:
            _validate_digest(expected_digest)
        payload = self._serialize(validated)

        with self._filesystem.lock(self._lock_name, timeout=timeout):
            current_digest = self._current_digest()
            if expected_digest is not None and not _digests_equal(
                current_digest, expected_digest
            ):
                raise StructuredDocumentConflictError(
                    f"structured document changed before save: {self._path}; "
                    f"expected {expected_digest}, found {current_digest or 'missing'}"
                )
            self._filesystem.write_bytes(self._path, payload)
        return self._snapshot(validated, payload)

    def replace(
        self,
        snapshot: StructuredDocumentSnapshot[TContract],
        value: TContract,
        *,
        timeout: float = 0.0,
    ) -> StructuredDocumentSnapshot[TContract]:
        """Replace exactly the revision represented by a prior snapshot."""
        if not isinstance(snapshot, StructuredDocumentSnapshot):
            raise TypeError("replace requires a structured document snapshot")
        if snapshot.path != self._path or snapshot.format is not self._format:
            raise StructuredDocumentConflictError(
                "snapshot belongs to a different structured repository"
            )
        return self.save(value, expected_digest=snapshot.digest, timeout=timeout)

    def canonical_bytes(self, value: TContract) -> bytes:
        """Render one validated value without writing it."""
        return self._serialize(self._validate_instance(value))

    def _validate_instance(self, value: TContract) -> TContract:
        if not isinstance(value, self._model):
            raise TypeError(
                f"structured repository requires {self._model.__name__}, "
                f"not {type(value).__name__}"
            )
        return value

    def _parse_and_validate(self, payload: bytes) -> TContract:
        text = _decode_utf8(payload)
        parsed = _parse_json(text) if self._format is StructuredDocumentFormat.JSON else _parse_yaml(text)
        _validate_json_compatible_structure(parsed)
        try:
            return self._model.model_validate(parsed)
        except ValidationError:
            raise
        except (TypeError, ValueError) as error:
            raise StructuredDocumentParseError(
                f"document could not be validated as {self._model.__name__}: {self._path}"
            ) from error

    def _serialize(self, value: TContract) -> bytes:
        data = value.model_dump(mode="json", exclude_none=True)
        _validate_json_compatible_structure(data)
        if self._format is StructuredDocumentFormat.JSON:
            text = json.dumps(
                data,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            return f"{text}\n".encode("utf-8")
        text = yaml.dump(
            data,
            Dumper=_CanonicalYamlDumper,
            allow_unicode=True,
            default_flow_style=False,
            indent=2,
            sort_keys=True,
            width=100,
        )
        if not text.endswith("\n"):
            text += "\n"
        return text.encode("utf-8")

    def _current_digest(self) -> str | None:
        try:
            payload = self._filesystem.read_bytes(self._path, max_bytes=self._max_bytes)
        except FileNotFoundError:
            return None
        return _digest(payload)

    def _snapshot(
        self,
        value: TContract,
        payload: bytes,
    ) -> StructuredDocumentSnapshot[TContract]:
        return StructuredDocumentSnapshot(
            path=self._path,
            format=self._format,
            value=value,
            digest=_digest(payload),
            canonical=True,
            size_bytes=len(payload),
        )


class JsonDocumentRepository(StructuredDocumentRepository[TContract]):
    """Canonical JSON repository for one strict contract type."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath,
        model: type[TContract],
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        super().__init__(
            filesystem,
            path,
            model,
            format=StructuredDocumentFormat.JSON,
            max_bytes=max_bytes,
        )


class YamlDocumentRepository(StructuredDocumentRepository[TContract]):
    """Canonical YAML repository for one strict contract type."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath,
        model: type[TContract],
        *,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        super().__init__(
            filesystem,
            path,
            model,
            format=StructuredDocumentFormat.YAML,
            max_bytes=max_bytes,
        )


class _StrictYamlLoader(yaml.SafeLoader):
    """Safe loader that additionally rejects aliases and duplicate keys."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            event = self.peek_event()
            raise ComposerError(
                "while composing a strict document",
                None,
                "YAML aliases are not allowed",
                event.start_mark,
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "expected a mapping node", node.start_mark)
        mapping: dict[str, Any] = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise ConstructorError(
                    "while constructing a strict mapping",
                    node.start_mark,
                    "YAML merge keys are not allowed",
                    key_node.start_mark,
                )
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConstructorError(
                    "while constructing a strict mapping",
                    node.start_mark,
                    "YAML mapping keys must be strings",
                    key_node.start_mark,
                )
            if key in mapping:
                raise ConstructorError(
                    "while constructing a strict mapping",
                    node.start_mark,
                    f"duplicate YAML mapping key: {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


class _CanonicalYamlDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _parse_json(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except StructuredDocumentParseError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise StructuredDocumentParseError("invalid JSON document") from error


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StructuredDocumentParseError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise StructuredDocumentParseError(f"non-finite JSON number is not allowed: {value}")


def _parse_yaml(text: str) -> Any:
    try:
        documents = list(yaml.load_all(text, Loader=_StrictYamlLoader))
    except StructuredDocumentParseError:
        raise
    except (yaml.YAMLError, RecursionError, ValueError) as error:
        raise StructuredDocumentParseError("invalid or unsafe YAML document") from error
    if len(documents) != 1:
        raise StructuredDocumentParseError("YAML input must contain exactly one document")
    if documents[0] is None:
        raise StructuredDocumentParseError("structured documents cannot be empty")
    return documents[0]


def _decode_utf8(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise StructuredDocumentFormatError("structured documents cannot contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StructuredDocumentFormatError("structured documents must use UTF-8") from error


def _validate_json_compatible_structure(value: Any) -> None:
    remaining = [_MAX_STRUCTURE_NODES]

    def visit(item: Any, depth: int) -> None:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise StructuredDocumentParseError(
                f"structured document exceeds {_MAX_STRUCTURE_NODES} values"
            )
        if depth > _MAX_STRUCTURE_DEPTH:
            raise StructuredDocumentParseError(
                f"structured document exceeds {_MAX_STRUCTURE_DEPTH} nesting levels"
            )
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise StructuredDocumentParseError("non-finite numbers are not allowed")
            return
        if isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise StructuredDocumentParseError(
                        "structured document mapping keys must be strings"
                    )
                visit(child, depth + 1)
            return
        raise StructuredDocumentParseError(
            f"structured documents cannot contain {type(item).__name__} values"
        )

    visit(value, 0)


def _validate_max_bytes(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("structured document byte limit must be a positive integer")


def _validate_extension(path: RepositoryPath, format: StructuredDocumentFormat) -> None:
    expected = ".json" if format is StructuredDocumentFormat.JSON else ".yaml"
    if not path.name.endswith(expected):
        raise StructuredDocumentFormatError(
            f"{format.value} repositories require the {expected} extension: {path}"
        )


def _validate_digest(value: str) -> None:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError("expected document digest must be lowercase SHA-256")


def _digests_equal(current: str | None, expected: str) -> bool:
    return current is not None and secrets.compare_digest(current, expected)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
