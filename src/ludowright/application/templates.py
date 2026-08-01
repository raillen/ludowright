"""Load versioned, data-defined project initialization templates."""

from __future__ import annotations

import json
from importlib import resources

from ludowright.contracts import TemplateDefinitionContract
from ludowright.domain import validate_slug


class TemplateError(RuntimeError):
    """Base error for project template loading."""


class TemplateNotFoundError(TemplateError):
    """Raised when a requested template is not packaged."""


def load_template(template_id: str) -> TemplateDefinitionContract:
    """Load and validate one packaged template by its stable identifier."""
    try:
        validate_slug(template_id)
    except ValueError as error:
        raise TemplateNotFoundError(f"unknown project template: {template_id!r}") from error

    resource = resources.files("ludowright").joinpath("templates", f"{template_id}.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise TemplateNotFoundError(f"unknown project template: {template_id!r}") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TemplateError(f"project template {template_id!r} cannot be read") from error

    try:
        return TemplateDefinitionContract.model_validate(payload)
    except (TypeError, ValueError) as error:
        raise TemplateError(f"project template {template_id!r} is invalid") from error
