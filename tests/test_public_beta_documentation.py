"""Executable checks for the public-beta documentation audit."""

from __future__ import annotations

from pathlib import Path

from ludowright.application import AtlasGenerator, DocumentationAuditor

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOCUMENT = REPOSITORY_ROOT / "docs/quality/PUBLIC_BETA_DOCUMENTATION_AUDIT.md"


def test_public_beta_audit_is_registered_and_matches_current_documentation() -> None:
    audit_document = AUDIT_DOCUMENT.read_text(encoding="utf-8")

    for expected in (
        "Atual",
        "ludowright atlas --check",
        "ludowright docs audit --check",
        "mkdocs build --strict --clean",
        "tests/test_example_cli_smoke.py",
        "compatibilidade inicial",
        "feedback de uso em projetos reais",
        "release candidate",
        "Não há mudança de API pública",
    ):
        assert expected in audit_document

    atlas = AtlasGenerator(REPOSITORY_ROOT).generate()
    documentation_audit = DocumentationAuditor(REPOSITORY_ROOT).generate()

    assert atlas.valid
    assert any(
        document.path == "quality/PUBLIC_BETA_DOCUMENTATION_AUDIT.md"
        for document in atlas.report.documents
    )
    assert documentation_audit.valid
