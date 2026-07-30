"""Deterministic rendering of data-driven Jinja document templates."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    StrictUndefined,
    TemplateNotFound,
    TemplateSyntaxError,
    UndefinedError,
)
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment
from pydantic import ValidationError

from ludowright.contracts import DocumentTemplateManifestContract
from ludowright.domain import validate_slug
from ludowright.infrastructure import ProjectFilesystem, ProjectFilesystemError, RepositoryPath

_PACKAGE_TEMPLATE_ROOT = "template_data"
_PROJECT_TEMPLATE_ROOT = RepositoryPath(".ludowright/templates")
_MAX_TEMPLATE_BYTES = 200_000
_MAX_CONTEXT_DEPTH = 64
_MAX_CONTEXT_NODES = 100_000
_SAFE_FILTERS = (
    "capitalize",
    "default",
    "dictsort",
    "join",
    "length",
    "lower",
    "replace",
    "sort",
    "string",
    "title",
    "trim",
    "upper",
)

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class DocumentTemplateError(RuntimeError):
    """Base class for template loading and rendering failures."""


class DocumentTemplateNotFoundError(DocumentTemplateError):
    """Raised when a template ID is not available in package data."""


class DocumentTemplateDefinitionError(DocumentTemplateError):
    """Raised when a versioned template package is malformed or incomplete."""


class DocumentTemplateContextError(ValueError):
    """Raised when render context is not a bounded JSON-compatible mapping."""


class DocumentTemplateRenderError(DocumentTemplateError):
    """Raised when a template cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """One deterministic rendering result and its content identity."""

    template_id: str
    template_version: int
    entrypoint: str
    content: str
    digest: str


class DocumentTemplateEngine:
    """Load package templates and safely apply project-local file overrides."""

    def __init__(
        self,
        filesystem: ProjectFilesystem | None = None,
        *,
        max_template_bytes: int = _MAX_TEMPLATE_BYTES,
    ) -> None:
        if max_template_bytes < 1:
            raise ValueError("template byte limit must be positive")
        self._filesystem = filesystem
        self._max_template_bytes = max_template_bytes

    def render(
        self,
        template_id: str,
        context: Mapping[str, object],
        *,
        entrypoint: str | None = None,
    ) -> RenderedDocument:
        """Render one declared entrypoint without writing project files."""
        manifest = load_document_template_manifest(template_id)
        selected_entrypoint = _select_entrypoint(manifest, entrypoint)
        package_root = _package_template_root(manifest.id)
        _validate_package_files(manifest, package_root)
        normalized_context = _normalize_context(context)

        loaders: list[BaseLoader] = []
        if self._filesystem is not None:
            loaders.append(
                _ProjectTemplateLoader(
                    self._filesystem,
                    _PROJECT_TEMPLATE_ROOT.child(manifest.id),
                    frozenset(manifest.files),
                    self._max_template_bytes,
                )
            )
        loaders.append(_PackageTemplateLoader(package_root, frozenset(manifest.files)))
        environment = _build_environment(loaders)

        try:
            template = environment.get_template(selected_entrypoint)
            rendered = template.render(normalized_context)
        except (
            SecurityError,
            TemplateNotFound,
            TemplateSyntaxError,
            UndefinedError,
            ProjectFilesystemError,
        ) as error:
            raise DocumentTemplateRenderError(
                f"template {manifest.id!r} could not be rendered: {error}"
            ) from error

        content = _canonicalize_output(rendered)
        return RenderedDocument(
            template_id=manifest.id,
            template_version=manifest.version,
            entrypoint=selected_entrypoint,
            content=content,
            digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )


def load_document_template_manifest(template_id: str) -> DocumentTemplateManifestContract:
    """Load and validate one versioned manifest from package data."""
    try:
        validate_slug(template_id)
    except ValueError as error:
        raise DocumentTemplateNotFoundError(
            f"document template ID is not canonical: {template_id!r}"
        ) from error

    root = _package_template_root(template_id)
    manifest_resource = root.joinpath("manifest.json")
    try:
        payload = _decode_template_bytes(manifest_resource.read_bytes())
        raw = json.loads(payload, object_pairs_hook=_unique_object)
        return DocumentTemplateManifestContract.model_validate(raw)
    except DocumentTemplateDefinitionError:
        raise
    except ValidationError as error:
        raise DocumentTemplateDefinitionError(
            f"document template manifest is invalid: {template_id!r}"
        ) from error
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise DocumentTemplateNotFoundError(
            f"document template is not available: {template_id!r}"
        ) from error


class _PackageTemplateLoader(BaseLoader):
    def __init__(self, root: Traversable, allowed_paths: frozenset[str]) -> None:
        self._root = root
        self._allowed_paths = allowed_paths

    def get_source(
        self,
        environment: Environment,
        template: str,
    ) -> tuple[str, str, Callable[[], bool]]:
        del environment
        _validate_template_name(template)
        if template not in self._allowed_paths:
            raise TemplateNotFound(template)
        resource = _resource_at(self._root, template)
        try:
            if not resource.is_file():
                raise TemplateNotFound(template)
            source = _decode_template_bytes(resource.read_bytes())
        except (FileNotFoundError, OSError) as error:
            raise TemplateNotFound(template) from error
        return source, f"package:{template}", lambda: True


class _ProjectTemplateLoader(BaseLoader):
    def __init__(
        self,
        filesystem: ProjectFilesystem,
        root: RepositoryPath,
        allowed_paths: frozenset[str],
        max_bytes: int,
    ) -> None:
        self._filesystem = filesystem
        self._root = root
        self._allowed_paths = allowed_paths
        self._max_bytes = max_bytes

    def get_source(
        self,
        environment: Environment,
        template: str,
    ) -> tuple[str, str, Callable[[], bool]]:
        del environment
        _validate_template_name(template)
        if template not in self._allowed_paths:
            raise TemplateNotFound(template)
        path = self._root.child(*template.split("/"))
        try:
            payload = self._filesystem.read_bytes(path, max_bytes=self._max_bytes)
        except FileNotFoundError as error:
            raise TemplateNotFound(template) from error
        source = _decode_template_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()

        def is_current() -> bool:
            try:
                current = self._filesystem.read_bytes(path, max_bytes=self._max_bytes)
            except (FileNotFoundError, ProjectFilesystemError, OSError):
                return False
            return hashlib.sha256(current).hexdigest() == digest

        return source, path.value, is_current


def _build_environment(loaders: list[BaseLoader]) -> Environment:
    environment = SandboxedEnvironment(
        loader=ChoiceLoader(loaders),
        autoescape=False,
        keep_trailing_newline=True,
        lstrip_blocks=False,
        trim_blocks=False,
        undefined=StrictUndefined,
    )
    environment.globals.clear()
    environment.filters = {
        name: environment.filters[name] for name in _SAFE_FILTERS if name in environment.filters
    }
    return environment


def _select_entrypoint(
    manifest: DocumentTemplateManifestContract,
    requested: str | None,
) -> str:
    selected = manifest.entrypoint if requested is None else requested
    try:
        _validate_template_name(selected)
    except TemplateNotFound as error:
        raise DocumentTemplateRenderError(
            f"template entrypoint is not a safe declared path: {selected!r}"
        ) from error
    if selected not in manifest.files:
        raise DocumentTemplateRenderError(
            f"template entrypoint is not declared by {manifest.id!r}: {selected}"
        )
    return selected


def _package_template_root(template_id: str) -> Traversable:
    return resources.files("ludowright").joinpath(_PACKAGE_TEMPLATE_ROOT, template_id)


def _validate_package_files(
    manifest: DocumentTemplateManifestContract,
    root: Traversable,
) -> None:
    for path in manifest.files:
        resource = _resource_at(root, path)
        try:
            if not resource.is_file():
                raise FileNotFoundError(path)
            _decode_template_bytes(resource.read_bytes())
        except (FileNotFoundError, OSError, UnicodeError) as error:
            raise DocumentTemplateDefinitionError(
                f"document template {manifest.id!r} is missing declared file: {path}"
            ) from error


def _resource_at(root: Traversable, path: str) -> Traversable:
    resource = root
    for segment in path.split("/"):
        resource = resource.joinpath(segment)
    return resource


def _validate_template_name(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TemplateNotFound(value)
    if "\\" in value or any(segment in {".", ".."} for segment in value.split("/")):
        raise TemplateNotFound(value)
    if any(
        not segment
        or any(
            not ((character.isascii() and character.isalnum()) or character in "._-")
            for character in segment
        )
        for segment in value.split("/")
    ):
        raise TemplateNotFound(value)


def _decode_template_bytes(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise DocumentTemplateDefinitionError("template files cannot contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as error:
        raise DocumentTemplateDefinitionError("template files must be valid UTF-8") from error


def _canonicalize_output(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip("\n") + "\n"


def _normalize_context(context: Mapping[str, object]) -> dict[str, JsonValue]:
    if not isinstance(context, Mapping):
        raise DocumentTemplateContextError("template context must be a mapping")
    counter = [0]
    normalized = _normalize_value(context, path="context", depth=0, counter=counter)
    if not isinstance(normalized, dict):
        raise DocumentTemplateContextError("template context must be an object")
    return normalized


def _normalize_value(
    value: object,
    *,
    path: str,
    depth: int,
    counter: list[int],
) -> JsonValue:
    counter[0] += 1
    if counter[0] > _MAX_CONTEXT_NODES:
        raise DocumentTemplateContextError("template context exceeds the node limit")
    if depth > _MAX_CONTEXT_DEPTH:
        raise DocumentTemplateContextError("template context exceeds the nesting limit")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DocumentTemplateContextError(
                f"template context contains a non-finite number: {path}"
            )
        return value
    if isinstance(value, Mapping):
        items: list[tuple[str, JsonValue]] = []
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str):
                raise DocumentTemplateContextError(f"template context keys must be strings: {path}")
            items.append(
                (
                    key,
                    _normalize_value(
                        value[key],
                        path=f"{path}.{key}",
                        depth=depth + 1,
                        counter=counter,
                    ),
                )
            )
        return dict(items)
    if isinstance(value, (list, tuple)):
        return [
            _normalize_value(item, path=f"{path}[{index}]", depth=depth + 1, counter=counter)
            for index, item in enumerate(value)
        ]
    raise DocumentTemplateContextError(
        f"template context contains unsupported value at {path}: {type(value).__name__}"
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentTemplateDefinitionError(f"duplicate manifest key: {key!r}")
        result[key] = value
    return result
