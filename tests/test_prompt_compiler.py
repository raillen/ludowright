"""Tests for deterministic provider-neutral prompt compilation."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    PromptCompiler,
    PromptTemplateNotFoundError,
    load_prompt_template,
)
from ludowright.contracts import CompiledPromptContract, VisualBibleContract
from ludowright.domain import (
    ApprovalId,
    AssetId,
    DisplayName,
    InvalidPromptCompilationError,
    PromptChannel,
    PromptLayer,
    PromptTemplate,
    ReferenceId,
    ReferenceOrigin,
    ReferenceProvenance,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    SourceUri,
    SubjectRevision,
    TemplateVersion,
    VisualReference,
)

VISUAL_BIBLE_FIXTURE = Path("tests/fixtures/contracts/v1/visual-bible.json")
COMPILED_PROMPT_FIXTURE = Path("tests/fixtures/contracts/v1/compiled-prompt.json")


def _visual_bible():
    payload = json.loads(VISUAL_BIBLE_FIXTURE.read_text(encoding="utf-8"))
    return VisualBibleContract.model_validate(payload).to_domain()


def _target(asset_id: str = "hero") -> ReferenceTarget:
    return ReferenceTarget(asset_id=AssetId(asset_id))


def _reference(
    reference_id: str,
    target: ReferenceTarget,
    *,
    status: ReferenceStatus = ReferenceStatus.APPROVED,
) -> VisualReference:
    reference = VisualReference(
        id=ReferenceId(reference_id),
        name=DisplayName(f"Reference {reference_id}"),
        target=target,
        role=ReferenceRole.IDENTITY,
        provenance=ReferenceProvenance(
            origin=ReferenceOrigin.EXTERNAL,
            content_revision=SubjectRevision(f"sha256:{reference_id}"),
            source_uri=SourceUri("https://example.test/reference"),
        ),
    )
    if status is ReferenceStatus.APPROVED:
        return reference.approve(ApprovalId(f"approval-{reference_id}"))
    return replace(reference, status=status)


def test_minimal_template_is_versioned_package_data() -> None:
    template = load_prompt_template("minimal")

    assert template.version == TemplateVersion(1)
    assert tuple(layer.id for layer in template.layers) == (
        "target",
        "shape",
        "proportions",
        "palette-materials",
        "capture-direction",
        "constraints",
        "avoid",
    )


def test_compilation_is_deterministic_and_contains_structured_constraints() -> None:
    compiler = PromptCompiler()
    first = compiler.compile(_visual_bible(), _target())
    second = compiler.compile(_visual_bible(), _target())

    assert first == second
    expected = json.loads(COMPILED_PROMPT_FIXTURE.read_text(encoding="utf-8"))["prompt_hash"]
    assert first.prompt_hash == expected
    assert first.positive_constraints == _visual_bible().prompt_constraints
    assert first.negative_constraints == _visual_bible().negative_constraints
    assert "orthographic projection" in first.positive_prompt
    assert "Negative constraints" in first.negative_prompt


def test_reference_resolution_requires_approved_matching_revisions() -> None:
    target = _target()
    references = (_reference("zeta", target), _reference("alpha", target))

    result = PromptCompiler().compile(
        _visual_bible(),
        target,
        references=references,
        reference_ids=(ReferenceId("zeta"), ReferenceId("alpha")),
    )

    assert tuple(reference.id.value for reference in result.references) == ("alpha", "zeta")
    assert result.references[0].revision == SubjectRevision("sha256:alpha")
    assert "alpha" in result.positive_prompt


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (ReferenceStatus.CANDIDATE, "not approved"),
        (ReferenceStatus.REJECTED, "not approved"),
    ],
)
def test_reference_resolution_rejects_unapproved_references(
    status: ReferenceStatus,
    message: str,
) -> None:
    target = _target()

    with pytest.raises(InvalidPromptCompilationError, match=message):
        PromptCompiler().compile(
            _visual_bible(),
            target,
            references=(_reference("candidate", target, status=status),),
            reference_ids=(ReferenceId("candidate"),),
        )


def test_reference_resolution_rejects_missing_and_wrong_target() -> None:
    target = _target()

    with pytest.raises(InvalidPromptCompilationError, match="not available"):
        PromptCompiler().compile(_visual_bible(), target, reference_ids=(ReferenceId("missing"),))

    with pytest.raises(InvalidPromptCompilationError, match="does not match"):
        PromptCompiler().compile(
            _visual_bible(),
            target,
            references=(_reference("other", _target("other-asset")),),
            reference_ids=(ReferenceId("other"),),
        )


def test_template_rejects_unsafe_placeholders_and_duplicate_layers() -> None:
    with pytest.raises(InvalidPromptCompilationError, match="unsupported placeholder"):
        PromptLayer("unsafe", PromptChannel.POSITIVE, "{provider_secret}")

    with pytest.raises(InvalidPromptCompilationError, match="invalid opening brace"):
        PromptLayer("brace", PromptChannel.POSITIVE, "{{target}")

    layer = PromptLayer("same", PromptChannel.POSITIVE, "{target}")
    with pytest.raises(InvalidPromptCompilationError, match="IDs must be unique"):
        PromptTemplate("invalid", TemplateVersion(1), (layer, layer))


def test_template_requires_both_channels() -> None:
    with pytest.raises(InvalidPromptCompilationError, match="positive and negative"):
        PromptTemplate(
            "positive-only",
            TemplateVersion(1),
            (PromptLayer("only", PromptChannel.POSITIVE, "{target}"),),
        )


def test_compiled_contract_fixture_validates_and_round_trips() -> None:
    payload = json.loads(COMPILED_PROMPT_FIXTURE.read_text(encoding="utf-8"))
    contract = CompiledPromptContract.model_validate(payload)

    assert contract.to_domain().prompt_hash == payload["prompt_hash"]
    assert CompiledPromptContract.from_domain(contract.to_domain()) == contract


def test_compiled_contract_rejects_tampered_hash() -> None:
    payload = json.loads(COMPILED_PROMPT_FIXTURE.read_text(encoding="utf-8"))
    payload["prompt_hash"] = "0" * 64

    with pytest.raises((ValidationError, InvalidPromptCompilationError), match="hash"):
        CompiledPromptContract.model_validate(payload)


def test_compiler_rejects_duplicate_catalog_ids() -> None:
    target = _target()
    duplicate = _reference("same", target)

    with pytest.raises(InvalidPromptCompilationError, match="catalog IDs"):
        PromptCompiler().compile(
            _visual_bible(),
            target,
            references=(duplicate, duplicate),
            reference_ids=(ReferenceId("same"),),
        )


def test_template_loader_reports_unknown_and_malformed_templates() -> None:
    with pytest.raises(PromptTemplateNotFoundError):
        load_prompt_template("missing-template")

    with pytest.raises(PromptTemplateNotFoundError):
        load_prompt_template("../unsafe")

    payload = json.loads(
        Path("src/ludowright/prompt_data/minimal/manifest.json").read_text(encoding="utf-8")
    )
    assert payload["kind"] == "prompt-template"


def test_compiled_contract_rejects_unknown_fields() -> None:
    payload = json.loads(COMPILED_PROMPT_FIXTURE.read_text(encoding="utf-8"))
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        CompiledPromptContract.model_validate(payload)
