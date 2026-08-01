"""Tests for deterministic documentation atlas generation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import AtlasGenerationError, AtlasGenerator
from ludowright.cli.app import app
from ludowright.contracts import AtlasMetadataContract

SNAPSHOT = Path("tests/snapshots/atlas/generated-index.md")
runner = CliRunner()


def _write_metadata(root: Path, documents: list[dict[str, str]]) -> None:
    metadata = AtlasMetadataContract(version=1, documents=tuple(documents))
    path = root / "docs" / "atlas.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _write_valid_tree(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text(
        "# Index\n\n[Guide](guide.md#guide)\n[External](https://example.test/guide)\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text("# Guide\n\nA guide.\n", encoding="utf-8")
    _write_metadata(
        root,
        [
            {
                "path": "guide.md",
                "title": "Guide",
                "section": "project",
                "canonical_source": "guide.md",
            },
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            },
        ],
    )


def test_repository_atlas_is_current_and_complete() -> None:
    result = AtlasGenerator(Path(__file__).parents[1]).generate()

    assert result.valid
    assert len(result.report.documents) == 121
    assert result.report.broken_links == ()
    assert result.report.orphan_documents == ()


def test_atlas_generation_is_deterministic_and_matches_snapshot(tmp_path: Path) -> None:
    _write_valid_tree(tmp_path)

    first = AtlasGenerator(tmp_path).generate()
    second = AtlasGenerator(tmp_path).generate()

    assert first == second
    assert first.valid
    assert len(first.report.documents) == 2
    assert len(first.report.links) == 1
    assert first.report.broken_links == ()
    assert first.report.orphan_documents == ()
    assert first.markdown == SNAPSHOT.read_text(encoding="utf-8")


def test_atlas_detects_broken_links_and_orphans(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text(
        "# Index\n\n"
        "[Missing](missing.md)\n"
        "[Missing anchor](index.md#missing)\n"
        "[Unsafe](../outside.md)\n",
        encoding="utf-8",
    )
    (docs / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            }
        ],
    )

    result = AtlasGenerator(tmp_path).generate()

    assert not result.valid
    assert result.report.orphan_documents == ("orphan.md",)
    assert {item.reason for item in result.report.broken_links} == {
        "missing-file",
        "missing-anchor",
        "unsafe-path",
    }


def test_atlas_detects_missing_canonical_source(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n", encoding="utf-8")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "missing.md",
            }
        ],
    )

    result = AtlasGenerator(tmp_path).generate()

    assert [item.reason for item in result.report.broken_links] == ["missing-canonical-source"]
    assert result.report.broken_links[0].target == "missing.md"


def test_atlas_rejects_symlinks_in_document_tree(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("symlink creation requires platform privileges on Windows")
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n", encoding="utf-8")
    (docs / "linked.md").symlink_to(docs / "index.md")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            }
        ],
    )

    with pytest.raises(AtlasGenerationError):
        AtlasGenerator(tmp_path).generate()


def test_atlas_rejects_unsafe_metadata_path(tmp_path: Path) -> None:
    with pytest.raises(AtlasGenerationError):
        AtlasGenerator(tmp_path, metadata_path="../atlas.json")


def test_atlas_cli_supports_human_and_json_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_valid_tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    human = runner.invoke(app, ["--no-color", "atlas"])
    machine = runner.invoke(app, ["--json", "atlas"])

    assert human.exit_code == 0
    assert "Documentation Atlas" in human.stdout
    assert "ATLAS integrity: valid" in human.stdout
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload["command"] == "atlas"
    assert payload["ok"] is True
    assert payload["data"]["valid"] is True
    assert payload["data"]["orphan_documents"] == []


def test_atlas_cli_check_uses_stable_failure_envelope(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n\n[Missing](missing.md)\n", encoding="utf-8")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            }
        ],
    )

    result = runner.invoke(app, ["--json", "atlas", str(tmp_path), "--check"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["valid"] is False
