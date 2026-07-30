"""Load and validate data-driven project templates."""

from __future__ import annotations

import json
from importlib import resources

from pydantic import ValidationError

from ludowright.contracts import TemplateDefinitionContract
from ludowright.domain import validate_slug


class TemplateNotFoundError(ValueError):
    """Raised when a requested template is not available."""


def load_template(template_id: str) -> TemplateDefinitionContract:
    """Load one versioned template from package data."""
    if not isinstance(template_id, str) or not template_id:
        raise TemplateNotFoundError("template ID cannot be empty")
    try:
        validate_slug(template_id)
    except ValueError as error:
        raise TemplateNotFoundError(f"template ID is not canonical: {template_id}") from error
    try:
        resource = resources.files("ludowright").joinpath("templates", f"{template_id}.json")
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
        raise TemplateNotFoundError(f"template is not available: {template_id}") from error
    try:
        return TemplateDefinitionContract.model_validate(payload)
    except ValidationError as error:
        raise TemplateNotFoundError(f"template is invalid: {template_id}") from error
