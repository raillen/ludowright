"""Executable checks for the release-candidate readiness checklist."""

from __future__ import annotations

from pathlib import Path

from ludowright.application import AtlasGenerator, DocumentationAuditor

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = REPOSITORY_ROOT / "docs/quality/RELEASE_CANDIDATE_CHECKLIST.md"


def test_release_candidate_checklist_is_canonical_and_explicitly_blocked() -> None:
    checklist = CHECKLIST.read_text(encoding="utf-8")

    for expected in (
        "Bloqueado",
        "uv run ludowright quality release",
        "uv run pytest -m clean_installation --no-cov",
        "uv run pytest -m end_to_end --no-cov",
        "uv run pre-commit run detect-secrets --all-files",
        "Projeto real externo",
        "revisão humana",
        "substitui feedback externo",
    ):
        assert expected in checklist

    atlas = AtlasGenerator(REPOSITORY_ROOT).generate()
    documentation_audit = DocumentationAuditor(REPOSITORY_ROOT).generate()

    assert atlas.valid
    assert any(
        document.path == "quality/RELEASE_CANDIDATE_CHECKLIST.md"
        for document in atlas.report.documents
    )
    assert documentation_audit.valid


__all__ = []
