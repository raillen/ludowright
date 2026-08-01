"""Deterministic, provider-neutral visual prompt compilation rules."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from ludowright.domain.errors import InvalidPromptCompilationError
from ludowright.domain.governance import SubjectRevision
from ludowright.domain.identifiers import ReferenceId, VisualBibleId
from ludowright.domain.names import validate_slug
from ludowright.domain.references import (
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    VisualReference,
)
from ludowright.domain.versions import TemplateVersion, VisualBibleVersion
from ludowright.domain.visual_bibles import VisualBible, VisualText

MAX_PROMPT_LAYER_LENGTH = 512
MAX_PROMPT_LENGTH = 12_000
MAX_PROMPT_LAYERS = 64
MAX_PROMPT_REFERENCES = 64
_PLACEHOLDER_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_ALLOWED_PLACEHOLDERS = frozenset(
    {
        "target",
        "shape_primary",
        "shape_secondary",
        "shape_avoid",
        "proportions",
        "palette",
        "materials",
        "lighting",
        "camera",
        "detail_level",
        "detail_guidance",
        "constraints",
        "negative_constraints",
        "references",
    }
)
_PROMPT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PromptChannel(StrEnum):
    """Output channel receiving one prompt-template layer."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class PromptLayer:
    """One bounded layer of a versioned prompt template."""

    id: str
    channel: PromptChannel
    template: str

    def __post_init__(self) -> None:
        _validate_slug(self.id, "prompt layer ID")
        if not isinstance(self.channel, PromptChannel):
            raise InvalidPromptCompilationError("prompt layer channel must be canonical")
        _validate_prompt_text(self.template, "prompt layer template", MAX_PROMPT_LAYER_LENGTH)
        placeholders = tuple(
            match.group(1) for match in _PLACEHOLDER_PATTERN.finditer(self.template)
        )
        if any(name not in _ALLOWED_PLACEHOLDERS for name in placeholders):
            raise InvalidPromptCompilationError("prompt layer contains an unsupported placeholder")
        if _PLACEHOLDER_PATTERN.sub("", self.template).count("{"):
            raise InvalidPromptCompilationError("prompt layer contains an invalid opening brace")
        if _PLACEHOLDER_PATTERN.sub("", self.template).count("}"):
            raise InvalidPromptCompilationError("prompt layer contains an invalid closing brace")


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Immutable data-defined prompt template with ordered layers."""

    id: str
    version: TemplateVersion
    layers: tuple[PromptLayer, ...]

    def __post_init__(self) -> None:
        _validate_slug(self.id, "prompt template ID")
        if not isinstance(self.version, TemplateVersion):
            raise InvalidPromptCompilationError("prompt template requires a template version")
        if not isinstance(self.layers, tuple) or not self.layers:
            raise InvalidPromptCompilationError("prompt template requires at least one layer")
        if len(self.layers) > MAX_PROMPT_LAYERS:
            raise InvalidPromptCompilationError(
                f"prompt template cannot exceed {MAX_PROMPT_LAYERS} layers"
            )
        if any(not isinstance(layer, PromptLayer) for layer in self.layers):
            raise InvalidPromptCompilationError("prompt template layers must be canonical")
        layer_ids = tuple(layer.id for layer in self.layers)
        if len(layer_ids) != len(set(layer_ids)):
            raise InvalidPromptCompilationError("prompt template layer IDs must be unique")
        channels = {layer.channel for layer in self.layers}
        if PromptChannel.POSITIVE not in channels or PromptChannel.NEGATIVE not in channels:
            raise InvalidPromptCompilationError(
                "prompt template requires positive and negative layers"
            )


@dataclass(frozen=True, slots=True)
class ResolvedPromptReference:
    """The approved, revision-bound identity included in a compiled prompt."""

    id: ReferenceId
    role: ReferenceRole
    revision: SubjectRevision

    def __post_init__(self) -> None:
        if not isinstance(self.id, ReferenceId):
            raise InvalidPromptCompilationError("compiled references require typed IDs")
        if not isinstance(self.role, ReferenceRole):
            raise InvalidPromptCompilationError("compiled reference roles must be canonical")
        if not isinstance(self.revision, SubjectRevision):
            raise InvalidPromptCompilationError("compiled references require revisions")


@dataclass(frozen=True, slots=True)
class CompiledPrompt:
    """Immutable compilation output whose hash covers every meaningful input."""

    template_id: str
    template_version: TemplateVersion
    visual_bible_id: VisualBibleId
    visual_bible_version: VisualBibleVersion
    target: ReferenceTarget
    layer_ids: tuple[str, ...]
    positive_prompt: str
    negative_prompt: str
    positive_constraints: tuple[VisualText, ...]
    negative_constraints: tuple[VisualText, ...]
    references: tuple[ResolvedPromptReference, ...]
    prompt_hash: str

    def __post_init__(self) -> None:
        _validate_slug(self.template_id, "compiled prompt template ID")
        if not isinstance(self.template_version, TemplateVersion):
            raise InvalidPromptCompilationError("compiled prompt requires a template version")
        if not isinstance(self.visual_bible_id, VisualBibleId):
            raise InvalidPromptCompilationError("compiled prompt requires a visual bible ID")
        if not isinstance(self.visual_bible_version, VisualBibleVersion):
            raise InvalidPromptCompilationError("compiled prompt requires a visual bible version")
        if not isinstance(self.target, ReferenceTarget):
            raise InvalidPromptCompilationError("compiled prompt requires a target")
        if not isinstance(self.layer_ids, tuple) or not self.layer_ids:
            raise InvalidPromptCompilationError("compiled prompt requires layer IDs")
        if any(not isinstance(layer_id, str) for layer_id in self.layer_ids):
            raise InvalidPromptCompilationError("compiled prompt layer IDs must be text")
        for layer_id in self.layer_ids:
            _validate_slug(layer_id, "compiled prompt layer ID")
        if len(self.layer_ids) != len(set(self.layer_ids)):
            raise InvalidPromptCompilationError("compiled prompt layer IDs must be unique")
        _validate_prompt_text(self.positive_prompt, "positive prompt", MAX_PROMPT_LENGTH)
        _validate_prompt_text(self.negative_prompt, "negative prompt", MAX_PROMPT_LENGTH)
        _validate_constraints(self.positive_constraints, "positive constraints")
        _validate_constraints(self.negative_constraints, "negative constraints")
        if not isinstance(self.references, tuple):
            raise InvalidPromptCompilationError("compiled prompt references must be immutable")
        if len(self.references) > MAX_PROMPT_REFERENCES:
            raise InvalidPromptCompilationError(
                f"compiled prompt cannot exceed {MAX_PROMPT_REFERENCES} references"
            )
        if any(not isinstance(reference, ResolvedPromptReference) for reference in self.references):
            raise InvalidPromptCompilationError("compiled prompt references must be canonical")
        reference_ids = tuple(reference.id for reference in self.references)
        if len(reference_ids) != len(set(reference_ids)):
            raise InvalidPromptCompilationError("compiled prompt references must be unique")
        if not isinstance(self.prompt_hash, str) or not _PROMPT_HASH_PATTERN.fullmatch(
            self.prompt_hash
        ):
            raise InvalidPromptCompilationError("compiled prompt hash must be lowercase SHA-256")
        if self.prompt_hash != _calculate_prompt_hash(self):
            raise InvalidPromptCompilationError("compiled prompt hash does not match its content")

    @classmethod
    def create(
        cls,
        *,
        template: PromptTemplate,
        visual_bible: VisualBible,
        target: ReferenceTarget,
        positive_prompt: str,
        negative_prompt: str,
        references: tuple[ResolvedPromptReference, ...],
    ) -> CompiledPrompt:
        """Create a compiled result and calculate its canonical content hash."""
        if not isinstance(template, PromptTemplate):
            raise InvalidPromptCompilationError("compiled prompt requires a template")
        if not isinstance(visual_bible, VisualBible):
            raise InvalidPromptCompilationError("compiled prompt requires a visual bible")
        if not isinstance(target, ReferenceTarget):
            raise InvalidPromptCompilationError("compiled prompt requires a target")
        if not isinstance(references, tuple):
            raise InvalidPromptCompilationError("compiled prompt references must be immutable")
        result = cls.__new__(cls)
        object.__setattr__(result, "template_id", template.id)
        object.__setattr__(result, "template_version", template.version)
        object.__setattr__(result, "visual_bible_id", visual_bible.id)
        object.__setattr__(result, "visual_bible_version", visual_bible.version)
        object.__setattr__(result, "target", target)
        object.__setattr__(result, "layer_ids", tuple(layer.id for layer in template.layers))
        object.__setattr__(result, "positive_prompt", positive_prompt)
        object.__setattr__(result, "negative_prompt", negative_prompt)
        object.__setattr__(result, "positive_constraints", visual_bible.prompt_constraints)
        object.__setattr__(result, "negative_constraints", visual_bible.negative_constraints)
        object.__setattr__(result, "references", references)
        object.__setattr__(result, "prompt_hash", _calculate_prompt_hash(result))
        result.__post_init__()
        return result


def resolve_prompt_references(
    references: tuple[VisualReference, ...],
    requested_ids: tuple[ReferenceId, ...],
    target: ReferenceTarget,
) -> tuple[ResolvedPromptReference, ...]:
    """Resolve explicit reference IDs to approved revisions for one target."""
    if not isinstance(references, tuple) or not isinstance(requested_ids, tuple):
        raise InvalidPromptCompilationError("reference inputs must be immutable tuples")
    if len(requested_ids) > MAX_PROMPT_REFERENCES:
        raise InvalidPromptCompilationError(
            f"compiled prompt cannot request more than {MAX_PROMPT_REFERENCES} references"
        )
    if any(not isinstance(reference_id, ReferenceId) for reference_id in requested_ids):
        raise InvalidPromptCompilationError("requested references must use typed IDs")
    if len(requested_ids) != len(set(requested_ids)):
        raise InvalidPromptCompilationError("requested references must be unique")
    catalog: dict[ReferenceId, VisualReference] = {}
    for reference in references:
        if not isinstance(reference, VisualReference):
            raise InvalidPromptCompilationError("reference catalog entries must be canonical")
        if reference.id in catalog:
            raise InvalidPromptCompilationError("reference catalog IDs must be unique")
        catalog[reference.id] = reference

    resolved: list[ResolvedPromptReference] = []
    for reference_id in sorted(requested_ids, key=lambda value: value.value):
        catalog_reference = catalog.get(reference_id)
        if catalog_reference is None:
            raise InvalidPromptCompilationError(
                f"requested reference is not available: {reference_id}"
            )
        if catalog_reference.status is not ReferenceStatus.APPROVED:
            raise InvalidPromptCompilationError(
                f"requested reference is not approved: {reference_id}"
            )
        if catalog_reference.target != target:
            raise InvalidPromptCompilationError(
                f"requested reference target does not match the prompt target: {reference_id}"
            )
        resolved.append(
            ResolvedPromptReference(
                id=catalog_reference.id,
                role=catalog_reference.role,
                revision=catalog_reference.provenance.content_revision,
            )
        )
    return tuple(resolved)


def compile_prompt(
    template: PromptTemplate,
    visual_bible: VisualBible,
    target: ReferenceTarget,
    references: tuple[ResolvedPromptReference, ...],
) -> CompiledPrompt:
    """Render one template from canonical visual data without provider calls."""
    if not isinstance(template, PromptTemplate):
        raise InvalidPromptCompilationError("prompt compilation requires a template")
    if not isinstance(visual_bible, VisualBible):
        raise InvalidPromptCompilationError("prompt compilation requires a visual bible")
    if not isinstance(target, ReferenceTarget):
        raise InvalidPromptCompilationError("prompt compilation requires a target")
    context = _prompt_context(visual_bible, target, references)
    positive_parts = [
        _render_layer(layer.template, context)
        for layer in template.layers
        if layer.channel is PromptChannel.POSITIVE
    ]
    negative_parts = [
        _render_layer(layer.template, context)
        for layer in template.layers
        if layer.channel is PromptChannel.NEGATIVE
    ]
    return CompiledPrompt.create(
        template=template,
        visual_bible=visual_bible,
        target=target,
        positive_prompt=_join_prompt_parts(positive_parts),
        negative_prompt=_join_prompt_parts(negative_parts),
        references=references,
    )


def _prompt_context(
    visual_bible: VisualBible,
    target: ReferenceTarget,
    references: tuple[ResolvedPromptReference, ...],
) -> dict[str, str]:
    detail_level = visual_bible.level_of_detail.default_level
    detail_rule = next(
        rule for rule in visual_bible.level_of_detail.levels if rule.level is detail_level
    )
    return {
        "target": _format_target(target),
        "shape_primary": str(visual_bible.shape_language.primary),
        "shape_secondary": _join_text(
            str(value) for value in visual_bible.shape_language.secondary
        ),
        "shape_avoid": _join_text(str(value) for value in visual_bible.shape_language.avoid),
        "proportions": _join_text(
            f"{rule.name}: {rule.guidance}" for rule in visual_bible.proportions
        ),
        "palette": _join_text(
            f"{color.name} ({color.role.value}) {color.color}" for color in visual_bible.palette
        ),
        "materials": _join_text(
            f"{rule.name} ({rule.finish.value}): {rule.guidance}" for rule in visual_bible.materials
        ),
        "lighting": (
            f"{visual_bible.lighting.mode.value} lighting with "
            f"{visual_bible.lighting.shadows.value} shadows"
        ),
        "camera": _format_camera(visual_bible),
        "detail_level": detail_level.value,
        "detail_guidance": str(detail_rule.guidance),
        "constraints": _join_text(str(value) for value in visual_bible.prompt_constraints),
        "negative_constraints": _join_text(
            str(value) for value in visual_bible.negative_constraints
        ),
        "references": _join_text(
            f"{reference.id} ({reference.role.value}, {reference.revision})"
            for reference in references
        ),
    }


def _format_target(target: ReferenceTarget) -> str:
    values = [f"asset:{target.asset_id}"]
    for label, identifier in (
        ("component", target.component_id),
        ("variant", target.variant_id),
        ("state", target.state_id),
    ):
        if identifier is not None:
            values.append(f"{label}:{identifier}")
    return ", ".join(values)


def _format_camera(visual_bible: VisualBible) -> str:
    camera = visual_bible.camera
    focal = f", {camera.focal_length_mm}mm focal length" if camera.focal_length_mm else ""
    return (
        f"{camera.projection.value} projection, "
        f"{camera.framing_margin_percent}% framing margin{focal}"
    )


def _render_layer(template: str, context: dict[str, str]) -> str:
    rendered = _PLACEHOLDER_PATTERN.sub(lambda match: context[match.group(1)], template)
    return _join_prompt_parts((rendered,))


def _join_prompt_parts(parts: list[str] | tuple[str, ...]) -> str:
    normalized = [" ".join(part.split()) for part in parts if part.strip()]
    result = " ".join(normalized)
    _validate_prompt_text(result, "compiled prompt", MAX_PROMPT_LENGTH)
    return result


def _join_text(values: Iterable[object]) -> str:
    items = tuple(str(value).rstrip(".") for value in values)
    return "; ".join(items) if items else "none"


def _validate_prompt_text(value: object, field_name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPromptCompilationError(f"{field_name} cannot be empty")
    if len(value) > maximum:
        raise InvalidPromptCompilationError(f"{field_name} cannot exceed {maximum} characters")
    if unicodedata.normalize("NFC", value) != value:
        raise InvalidPromptCompilationError(f"{field_name} must use Unicode NFC")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise InvalidPromptCompilationError(f"{field_name} cannot contain control characters")


def _validate_constraints(values: tuple[VisualText, ...], field_name: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise InvalidPromptCompilationError(f"{field_name} cannot be empty")
    if any(not isinstance(value, VisualText) for value in values):
        raise InvalidPromptCompilationError(f"{field_name} must be canonical")
    if len(values) != len(set(values)):
        raise InvalidPromptCompilationError(f"{field_name} must be unique")


def _validate_slug(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise InvalidPromptCompilationError(f"{field_name} must be a canonical slug")
    try:
        validate_slug(value)
    except ValueError as error:
        raise InvalidPromptCompilationError(f"{field_name} must be a canonical slug") from error


def _calculate_prompt_hash(prompt: CompiledPrompt) -> str:
    payload = {
        "template_id": prompt.template_id,
        "template_version": prompt.template_version.value,
        "visual_bible_id": prompt.visual_bible_id.value,
        "visual_bible_version": prompt.visual_bible_version.value,
        "target": _target_payload(prompt.target),
        "layer_ids": list(prompt.layer_ids),
        "positive_prompt": prompt.positive_prompt,
        "negative_prompt": prompt.negative_prompt,
        "positive_constraints": [str(value) for value in prompt.positive_constraints],
        "negative_constraints": [str(value) for value in prompt.negative_constraints],
        "references": [
            {
                "id": reference.id.value,
                "role": reference.role.value,
                "revision": reference.revision.value,
            }
            for reference in prompt.references
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _target_payload(target: ReferenceTarget) -> dict[str, str | None]:
    return {
        "asset_id": target.asset_id.value,
        "component_id": target.component_id.value if target.component_id else None,
        "variant_id": target.variant_id.value if target.variant_id else None,
        "state_id": target.state_id.value if target.state_id else None,
    }
