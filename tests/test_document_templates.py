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


def _context() -> dict[str, object]:
    return {
        "title": "Echoes",
        "sections": [
            {"title": "Summary", "body": "A small local-first game."},
            {"title": "Scope", "body": "One auditable slice."},
        ],
    }


def test_minimal_manifest_is_versioned_and_loaded_from_package_data() -> None:
    manifest = load_document_template_manifest("minimal")

    assert manifest.id == "minimal"
    assert manifest.version == 1
    assert manifest.entrypoint == "document.md.jinja"
    assert manifest.files == ("base.md.jinja", "document.md.jinja")


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
