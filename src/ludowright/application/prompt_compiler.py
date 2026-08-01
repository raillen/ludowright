"""Application orchestration for deterministic visual prompt compilation."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from pydantic import ValidationError

from ludowright.contracts import CompiledPromptContract, PromptTemplateContract
from ludowright.domain import (
    CompiledPrompt,
    InvalidPromptCompilationError,
    PromptTemplate,
    ReferenceId,
    ReferenceTarget,
    VisualBible,
    VisualReference,
    compile_prompt,
    resolve_prompt_references,
    validate_slug,
)


class PromptTemplateError(RuntimeError):
    """Base error for package prompt-template loading."""


class PromptTemplateNotFoundError(PromptTemplateError):
    """Raised when a requested template ID is not package data."""


class PromptTemplateDefinitionError(PromptTemplateError):
    """Raised when package prompt-template data is malformed."""


class PromptCompiler:
    """Compile a visual bible and approved references without external side effects."""

    def compile(
        self,
        visual_bible: VisualBible,
        target: ReferenceTarget,
        *,
        template_id: str = "minimal",
        references: tuple[VisualReference, ...] = (),
        reference_ids: tuple[ReferenceId, ...] = (),
    ) -> CompiledPrompt:
        """Return deterministic prompt text and hash for one target."""
        template = load_prompt_template(template_id)
        resolved = resolve_prompt_references(references, reference_ids, target)
        return compile_prompt(template, visual_bible, target, resolved)

    def compile_contract(
        self,
        visual_bible: VisualBible,
        target: ReferenceTarget,
        *,
        template_id: str = "minimal",
        references: tuple[VisualReference, ...] = (),
        reference_ids: tuple[ReferenceId, ...] = (),
    ) -> CompiledPromptContract:
        """Return the published contract representation of a compilation."""
        return CompiledPromptContract.from_domain(
            self.compile(
                visual_bible,
                target,
                template_id=template_id,
                references=references,
                reference_ids=reference_ids,
            )
        )


def load_prompt_template(template_id: str) -> PromptTemplate:
    """Load and validate one versioned prompt template from package data."""
    try:
        validate_slug(template_id)
    except ValueError as error:
        raise PromptTemplateNotFoundError(
            f"prompt template ID is not canonical: {template_id!r}"
        ) from error

    root = resources.files("ludowright").joinpath("prompt_data", template_id)
    try:
        raw = json.loads(
            _decode_prompt_data(root.joinpath("manifest.json").read_bytes()),
            object_pairs_hook=_unique_object,
        )
        contract = PromptTemplateContract.model_validate(raw)
        return contract.to_domain()
    except PromptTemplateError:
        raise
    except InvalidPromptCompilationError as error:
        raise PromptTemplateDefinitionError(
            f"prompt template manifest is invalid: {template_id!r}"
        ) from error
    except ValidationError as error:
        raise PromptTemplateDefinitionError(
            f"prompt template manifest is invalid: {template_id!r}"
        ) from error
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise PromptTemplateNotFoundError(
            f"prompt template is not available: {template_id!r}"
        ) from error


def _decode_prompt_data(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise PromptTemplateDefinitionError("prompt-template data cannot contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PromptTemplateDefinitionError("prompt-template data must be valid UTF-8") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PromptTemplateDefinitionError(
                "prompt-template JSON cannot contain duplicate keys"
            )
        result[key] = value
    return result
