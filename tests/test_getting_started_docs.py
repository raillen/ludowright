"""Keep the installation and first-project guides executable against the CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ludowright.cli.app import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLATION_GUIDE = REPOSITORY_ROOT / "docs/getting-started/INSTALLATION.md"
FIRST_PROJECT_GUIDE = REPOSITORY_ROOT / "docs/getting-started/FIRST_PROJECT.md"


def test_installation_guide_covers_supported_platforms_and_verification() -> None:
    guide = INSTALLATION_GUIDE.read_text(encoding="utf-8")

    assert "Linux e macOS" in guide
    assert "Windows" in guide
    assert "uv python install 3.12" in guide
    assert "uv sync" in guide
    assert "uv run ludowright --version" in guide
    assert "uv run ludowright --json diagnostics" in guide


def test_first_project_guide_matches_the_non_interactive_cli_flow(tmp_path: Path) -> None:
    guide = FIRST_PROJECT_GUIDE.read_text(encoding="utf-8")
    assert "ludowright init" in guide
    assert "--non-interactive" in guide
    assert "--dry-run" in guide
    assert "codex skill install" in guide

    runner = CliRunner()
    preview = tmp_path / "my-game-preview"
    preview_result = runner.invoke(
        app,
        [
            "--json",
            "init",
            str(preview),
            "--name",
            "My Game",
            "--template",
            "minimal",
            "--non-interactive",
            "--dry-run",
        ],
    )

    assert preview_result.exit_code == 0
    preview_payload = json.loads(preview_result.stdout)
    assert preview_payload["ok"] is True
    assert preview_payload["data"]["dry_run"] is True
    assert not preview.exists()

    project = tmp_path / "my-game"
    init_result = runner.invoke(
        app,
        [
            "init",
            str(project),
            "--name",
            "My Game",
            "--template",
            "minimal",
            "--non-interactive",
        ],
    )
    assert init_result.exit_code == 0
    assert (project / ".ludowright/project.json").is_file()
    assert (project / ".ludowright/events.jsonl").is_file()
    assert (project / ".ludowright/dependency-graph.json").is_file()
    assert (project / ".ludowright/state.sqlite3").is_file()

    install_result = runner.invoke(
        app,
        ["codex", "skill", "install", str(project)],
    )
    assert install_result.exit_code == 0

    verify_result = runner.invoke(
        app,
        ["--json", "codex", "skill", "verify", str(project)],
    )
    assert verify_result.exit_code == 0
    verify_payload = json.loads(verify_result.stdout)
    assert verify_payload["ok"] is True
    assert verify_payload["data"]["valid"] is True


def test_first_project_guide_documents_create_only_behavior() -> None:
    guide = FIRST_PROJECT_GUIDE.read_text(encoding="utf-8")

    assert "não cria diretórios" in guide
    assert "recusa um diretório não vazio" in guide
    assert "conflict" in guide
    assert "arquivos desconhecidos são preservados" in guide


__all__ = []
