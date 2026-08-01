"""Tests for the deterministic document template engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.application import (
    DocumentTemplateContextError,
    DocumentTemplateDefinitionError,
    DocumentTemplateEngine,
    DocumentTemplateNotFoundError,
    DocumentTemplateRenderError,
    load_document_template_manifest,
)
from ludowright.contracts import DocumentTemplateManifestContract
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath

SNAPSHOT = Path("tests/snapshots/templates/minimal-document.md")
PRODUCT_ENTRYPOINTS = (
    "audience.md.jinja",
    "loops.md.jinja",
    "pillars.md.jinja",
    "platform.md.jinja",
    "risk.md.jinja",
    "scope.md.jinja",
    "success.md.jinja",
    "vision.md.jinja",
)
ARCHITECTURE_ENTRYPOINTS = (
    "adrs.md.jinja",
    "contracts.md.jinja",
    "implementation.md.jinja",
    "modules.md.jinja",
    "operations.md.jinja",
    "plans.md.jinja",
    "quality.md.jinja",
    "security.md.jinja",
    "system-overview.md.jinja",
    "ui-ux.md.jinja",
)


def _context() -> dict[str, object]:
    return {
        "title": "Echoes",
        "sections": [
            {"title": "Summary", "body": "A small local-first game."},
            {"title": "Scope", "body": "One auditable slice."},
        ],
    }


def _product_context() -> dict[str, object]:
    return {
        "title": "Echoes Product Brief",
        "vision": "Make a small game idea concrete and auditable.",
        "mission": "Turn decisions into a focused production plan.",
        "primary_users": ["Independent game developers", "Small game teams"],
        "secondary_users": ["Students", "Game-jam teams"],
        "pillars": [
            {
                "name": "Structured planning",
                "description": "Keep canonical facts in modular documents.",
            },
            {
                "name": "Auditable delivery",
                "description": "Make every output traceable to its inputs.",
            },
        ],
        "loops": [
            {
                "name": "Design loop",
                "steps": ["Ask", "Decide", "Validate"],
            },
            {
                "name": "Production loop",
                "steps": ["Plan", "Create", "Review"],
            },
        ],
        "in_scope": ["Canonical game documentation", "Traceable production data"],
        "out_of_scope": ["Game engine runtime", "Cloud-only collaboration"],
        "risks": [
            {
                "name": "Scope drift",
                "impact": "The project becomes too large to finish.",
                "mitigation": "Record boundaries and review them at each milestone.",
            },
            {
                "name": "Stale documents",
                "impact": "Teams follow an outdated plan.",
                "mitigation": "Track source digests and refresh affected outputs.",
            },
        ],
        "platforms": [
            {"name": "Desktop", "notes": "Primary local-first development target."},
            {"name": "Web reference", "notes": "Optional published documentation view."},
        ],
        "measures": [
            {
                "name": "Resumable intake",
                "description": "A creator can continue after leaving the repository.",
            },
            {
                "name": "Reproducible output",
                "description": "The same inputs produce the same document bytes.",
            },
        ],
    }


def _architecture_context() -> dict[str, object]:
    return {
        "title": "Echoes Architecture Brief",
        "goal": "Keep product truth deterministic, local-first, and reviewable.",
        "layers": [
            {"name": "Domain", "description": "Owns invariants and state transitions."},
            {"name": "Application", "description": "Coordinates explicit use cases."},
        ],
        "boundaries": [
            "Domain does not import infrastructure.",
            "Codex does not become the source of truth.",
        ],
        "contracts": [
            {"name": "JSON Schemas", "purpose": "Publish machine-readable boundaries."},
            {"name": "CLI Envelope", "purpose": "Keep automation output stable."},
        ],
        "modules": [
            {"name": "Domain", "responsibility": "Validate business invariants."},
            {"name": "Infrastructure", "responsibility": "Provide safe local adapters."},
        ],
        "principles": ["Show state before action", "Keep complexity progressive"],
        "flows": [
            {"name": "Intake", "steps": ["Inspect", "Ask", "Record"]},
            {"name": "Review", "steps": ["Plan", "Validate", "Approve"]},
        ],
        "accessibility": ["Keyboard-friendly commands", "Readable error summaries"],
        "phases": [
            {"name": "Foundation", "outcome": "Safe storage and contracts exist."},
            {"name": "Guided documentation", "outcome": "Structured documents can be resumed."},
        ],
        "validation": ["Run focused tests", "Run the full quality gate"],
        "gates": ["Lint and format", "Strict type checking", "Contract publication"],
        "failure_policy": "Quality failures block publication until the cause is understood.",
        "controls": [
            "Reject traversal and symlinks.",
            "Write canonical files atomically.",
        ],
        "open_questions": ["Which release artifacts need signing?"],
        "commands": ["uv run ludowright quality check", "uv run mkdocs build --strict --clean"],
        "recovery": [
            "Preserve the original failure cause.",
            "Restore the last canonical snapshot.",
        ],
        "decisions": [
            {"id": "ADR0014", "title": "Stable CLI surfaces", "status": "accepted"},
            {"id": "ADR0017", "title": "Deterministic templates", "status": "accepted"},
        ],
        "plans": [
            {"name": "Implementation plan", "scope": "Ordered bounded PRs to 1.0."},
            {"name": "Roadmap", "scope": "Product capability and release direction."},
        ],
    }


def test_minimal_manifest_is_versioned_and_loaded_from_package_data() -> None:
    manifest = load_document_template_manifest("minimal")

    assert manifest.id == "minimal"
    assert manifest.version == 1
    assert manifest.entrypoint == "document.md.jinja"
    assert manifest.files == ("base.md.jinja", "document.md.jinja")


def test_product_manifest_declares_the_complete_document_set() -> None:
    manifest = load_document_template_manifest("product")

    assert manifest.entrypoint == "vision.md.jinja"
    assert tuple(path for path in manifest.files if path.endswith(".md.jinja")) == (
        "audience.md.jinja",
        "base.md.jinja",
        "loops.md.jinja",
        "pillars.md.jinja",
        "platform.md.jinja",
        "risk.md.jinja",
        "scope.md.jinja",
        "success.md.jinja",
        "vision.md.jinja",
    )


def test_architecture_manifest_declares_the_complete_document_set() -> None:
    manifest = load_document_template_manifest("architecture")

    assert manifest.entrypoint == "system-overview.md.jinja"
    assert tuple(path for path in manifest.files if path.endswith(".md.jinja")) == (
        "adrs.md.jinja",
        "base.md.jinja",
        "contracts.md.jinja",
        "implementation.md.jinja",
        "modules.md.jinja",
        "operations.md.jinja",
        "plans.md.jinja",
        "quality.md.jinja",
        "security.md.jinja",
        "system-overview.md.jinja",
        "ui-ux.md.jinja",
    )


def test_minimal_template_uses_inheritance_and_matches_snapshot() -> None:
    result = DocumentTemplateEngine().render("minimal", _context())

    assert result.content == SNAPSHOT.read_text(encoding="utf-8")
    assert result.content.endswith("\n")
    assert result.digest


def test_rendering_is_deterministic_and_digested() -> None:
    engine = DocumentTemplateEngine()

    first = engine.render("minimal", _context())
    second = engine.render("minimal", dict(reversed(tuple(_context().items()))))

    assert first == second


def test_declared_entrypoint_can_be_selected() -> None:
    result = DocumentTemplateEngine().render(
        "minimal",
        {"title": "Base", "body": "Body", "sections": []},
        entrypoint="base.md.jinja",
    )

    assert result.entrypoint == "base.md.jinja"
    assert result.content == "# Base\n"


@pytest.mark.parametrize("entrypoint", PRODUCT_ENTRYPOINTS)
def test_product_document_set_matches_snapshots(entrypoint: str) -> None:
    result = DocumentTemplateEngine().render(
        "product",
        _product_context(),
        entrypoint=entrypoint,
    )
    snapshot = Path("tests/snapshots/templates/product") / entrypoint.removesuffix(".jinja")

    assert result.entrypoint == entrypoint
    assert result.content == snapshot.read_text(encoding="utf-8")


def test_product_default_entrypoint_is_vision() -> None:
    result = DocumentTemplateEngine().render("product", _product_context())

    assert result.entrypoint == "vision.md.jinja"
    assert result.content == (
        Path("tests/snapshots/templates/product/vision.md").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("entrypoint", ARCHITECTURE_ENTRYPOINTS)
def test_architecture_document_set_matches_snapshots(entrypoint: str) -> None:
    result = DocumentTemplateEngine().render(
        "architecture",
        _architecture_context(),
        entrypoint=entrypoint,
    )
    snapshot = Path("tests/snapshots/templates/architecture") / entrypoint.removesuffix(".jinja")

    assert result.entrypoint == entrypoint
    assert result.content == snapshot.read_text(encoding="utf-8")


def test_architecture_default_entrypoint_is_system_overview() -> None:
    result = DocumentTemplateEngine().render("architecture", _architecture_context())

    assert result.entrypoint == "system-overview.md.jinja"
    assert result.content == Path(
        "tests/snapshots/templates/architecture/system-overview.md"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("entrypoint", ["outside.md.jinja", "../base.md.jinja", ""])
def test_undeclared_entrypoint_is_rejected(entrypoint: str) -> None:
    with pytest.raises(DocumentTemplateRenderError):
        DocumentTemplateEngine().render(
            "minimal",
            {"title": "Base", "body": "Body", "sections": []},
            entrypoint=entrypoint,
        )


def test_project_override_replaces_only_declared_template_file(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    override = RepositoryPath(".ludowright/templates/minimal/base.md.jinja")
    filesystem.write_text(
        override,
        "{% block document -%}\n# {{ title }} — custom\n{%- endblock document %}\n",
    )

    result = DocumentTemplateEngine(filesystem).render(
        "minimal",
        {"title": "Override", "body": "Body", "sections": []},
    )

    assert result.content == "# Override — custom\n"


def test_missing_project_override_falls_back_to_package_template(tmp_path: Path) -> None:
    result = DocumentTemplateEngine(ProjectFilesystem(tmp_path)).render("minimal", _context())

    assert result.content == SNAPSHOT.read_text(encoding="utf-8")
    assert not (tmp_path / ".ludowright").exists()


@pytest.mark.parametrize("template_id", ["", "../minimal", "Minimal", "con"])
def test_invalid_template_id_is_rejected(template_id: str) -> None:
    with pytest.raises(DocumentTemplateNotFoundError):
        load_document_template_manifest(template_id)


def test_missing_context_is_a_typed_render_error() -> None:
    with pytest.raises(DocumentTemplateRenderError):
        DocumentTemplateEngine().render("minimal", {"title": "Missing sections"})


@pytest.mark.parametrize(
    "context",
    [
        {"title": "bad", "sections": {1: "not a string key"}},
        {"title": "bad", "sections": {"value": float("nan")}},
        {"title": "bad", "sections": object()},
    ],
)
def test_context_rejects_non_json_values(context: dict[str, object]) -> None:
    with pytest.raises(DocumentTemplateContextError):
        DocumentTemplateEngine().render("minimal", context)


def test_project_template_symlink_is_rejected(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    target = tmp_path / "outside.jinja"
    target.write_text("unsafe", encoding="utf-8")
    override = tmp_path / ".ludowright" / "templates" / "minimal"
    override.mkdir(parents=True)
    link = override / "base.md.jinja"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(DocumentTemplateRenderError) as error:
        DocumentTemplateEngine(filesystem).render(
            "minimal",
            {"title": "Unsafe", "body": "Body", "sections": []},
        )

    assert "could not be rendered" in str(error.value)


def test_project_override_cannot_extend_an_undeclared_file(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    filesystem.write_text(
        RepositoryPath(".ludowright/templates/minimal/document.md.jinja"),
        '{% extends "outside.md.jinja" %}\n',
    )

    with pytest.raises(DocumentTemplateRenderError):
        DocumentTemplateEngine(filesystem).render("minimal", _context())


def test_project_override_cannot_access_python_object_internals(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    filesystem.write_text(
        RepositoryPath(".ludowright/templates/minimal/base.md.jinja"),
        "{{ title.__class__.__mro__ }}\n",
    )

    with pytest.raises(DocumentTemplateRenderError, match="could not be rendered"):
        DocumentTemplateEngine(filesystem).render(
            "minimal",
            {"title": "Unsafe", "body": "Body", "sections": []},
        )


def test_manifest_rejects_undeclared_entrypoint_and_traversal() -> None:
    with pytest.raises(ValidationError):
        DocumentTemplateManifestContract(
            id="minimal",
            version=1,
            entrypoint="missing.md.jinja",
            files=("../outside.jinja",),
        )


def test_manifest_fixture_is_json_and_contract_compatible() -> None:
    payload = json.loads(Path("tests/fixtures/contracts/v1/document-template.json").read_text())

    assert DocumentTemplateManifestContract.model_validate(payload).id == "minimal"


def test_declared_package_file_missing_is_a_definition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ludowright.application.document_templates as module

    manifest = module.DocumentTemplateManifestContract(
        id="minimal",
        version=1,
        entrypoint="missing.md.jinja",
        files=("missing.md.jinja",),
    )
    monkeypatch.setattr(module, "load_document_template_manifest", lambda _template_id: manifest)

    with pytest.raises(DocumentTemplateDefinitionError):
        DocumentTemplateEngine().render("minimal", _context())
