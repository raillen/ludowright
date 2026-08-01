"""Versioned prompt-template and compiled-prompt contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    PositiveRevision,
    RevisionText,
    Sha256Text,
    Slug,
)
from ludowright.contracts.visual import ReferenceTargetContract
from ludowright.domain import (
    CompiledPrompt,
    PromptChannel,
    PromptLayer,
    PromptTemplate,
    ReferenceId,
    ReferenceRole,
    ResolvedPromptReference,
    SubjectRevision,
    TemplateVersion,
    VisualBibleId,
    VisualBibleVersion,
    VisualText,
)

PromptTemplateText = Annotated[str, StringConstraints(min_length=1, max_length=512)]
CompiledPromptText = Annotated[str, StringConstraints(min_length=1, max_length=12_000)]


class PromptLayerContract(ContractModel):
    """One safe, ordered prompt-template layer."""

    id: Slug
    channel: PromptChannel
    text: PromptTemplateText

    def to_domain(self) -> PromptLayer:
        return PromptLayer(id=self.id, channel=self.channel, template=self.text)


class PromptTemplateContract(ContractModel):
    """Versioned package-data manifest for a provider-neutral prompt template."""

    schema_version: Literal[1] = 1
    kind: Literal["prompt-template"] = "prompt-template"
    id: Slug
    version: PositiveRevision
    layers: Annotated[tuple[PromptLayerContract, ...], Field(min_length=1)]

    def to_domain(self) -> PromptTemplate:
        return PromptTemplate(
            id=self.id,
            version=TemplateVersion(self.version),
            layers=tuple(layer.to_domain() for layer in self.layers),
        )

    @model_validator(mode="after")
    def validate_template(self) -> Self:
        self.to_domain()
        return self


class CompiledPromptReferenceContract(ContractModel):
    """One approved reference revision captured by a compiled prompt."""

    id: Slug
    role: ReferenceRole
    revision: RevisionText

    def to_domain(self) -> ResolvedPromptReference:
        return ResolvedPromptReference(
            id=ReferenceId(self.id),
            role=self.role,
            revision=SubjectRevision(self.revision),
        )


class CompiledPromptContract(ContractModel):
    """Immutable v1 prompt output with an integrity hash over its content."""

    schema_version: Literal[1] = 1
    kind: Literal["compiled-prompt"] = "compiled-prompt"
    template_id: Slug
    template_version: PositiveRevision
    visual_bible_id: Slug
    visual_bible_version: PositiveRevision
    target: ReferenceTargetContract
    layer_ids: Annotated[tuple[Slug, ...], Field(min_length=1)]
    positive_prompt: CompiledPromptText
    negative_prompt: CompiledPromptText
    positive_constraints: Annotated[tuple[CompiledPromptText, ...], Field(min_length=1)]
    negative_constraints: Annotated[tuple[CompiledPromptText, ...], Field(min_length=1)]
    references: tuple[CompiledPromptReferenceContract, ...] = ()
    prompt_hash: Sha256Text

    @classmethod
    def from_domain(cls, value: CompiledPrompt) -> CompiledPromptContract:
        return cls(
            template_id=value.template_id,
            template_version=value.template_version.value,
            visual_bible_id=value.visual_bible_id.value,
            visual_bible_version=value.visual_bible_version.value,
            target=ReferenceTargetContract(
                asset_id=value.target.asset_id.value,
                component_id=(
                    value.target.component_id.value
                    if value.target.component_id is not None
                    else None
                ),
                variant_id=(
                    value.target.variant_id.value if value.target.variant_id is not None else None
                ),
                state_id=(
                    value.target.state_id.value if value.target.state_id is not None else None
                ),
            ),
            layer_ids=value.layer_ids,
            positive_prompt=value.positive_prompt,
            negative_prompt=value.negative_prompt,
            positive_constraints=tuple(str(item) for item in value.positive_constraints),
            negative_constraints=tuple(str(item) for item in value.negative_constraints),
            references=tuple(
                CompiledPromptReferenceContract(
                    id=item.id.value,
                    role=item.role,
                    revision=item.revision.value,
                )
                for item in value.references
            ),
            prompt_hash=value.prompt_hash,
        )

    def to_domain(self) -> CompiledPrompt:
        return CompiledPrompt(
            template_id=self.template_id,
            template_version=TemplateVersion(self.template_version),
            visual_bible_id=VisualBibleId(self.visual_bible_id),
            visual_bible_version=VisualBibleVersion(self.visual_bible_version),
            target=self.target.to_domain(),
            layer_ids=tuple(self.layer_ids),
            positive_prompt=self.positive_prompt,
            negative_prompt=self.negative_prompt,
            positive_constraints=tuple(VisualText(value) for value in self.positive_constraints),
            negative_constraints=tuple(VisualText(value) for value in self.negative_constraints),
            references=tuple(reference.to_domain() for reference in self.references),
            prompt_hash=self.prompt_hash,
        )

    @model_validator(mode="after")
    def validate_compiled_prompt(self) -> Self:
        self.to_domain()
        return self
