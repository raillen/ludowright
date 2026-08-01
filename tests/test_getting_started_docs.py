"""Keep the installation and first-project guides executable against the CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ludowright.application import VisualJobPlanner, load_humanoid_profile
from ludowright.cli.app import app
from ludowright.cli.runtime import CliExitCode
from ludowright.contracts import (
    AssetContract,
    CaptureProfileContract,
    VisualReferenceContract,
)
from ludowright.domain import ReferenceId, VisualPlanBlockerCode, VisualPlanTarget

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLATION_GUIDE = REPOSITORY_ROOT / "docs/getting-started/INSTALLATION.md"
FIRST_PROJECT_GUIDE = REPOSITORY_ROOT / "docs/getting-started/FIRST_PROJECT.md"
CHARACTER_WORKFLOW_GUIDE = REPOSITORY_ROOT / "docs/getting-started/CHARACTER_WORKFLOW.md"
TROUBLESHOOTING_GUIDE = REPOSITORY_ROOT / "docs/getting-started/TROUBLESHOOTING.md"


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


def test_character_workflow_uses_current_profile_and_approval_boundaries() -> None:
    guide = CHARACTER_WORKFLOW_GUIDE.read_text(encoding="utf-8")

    assert "Starfall Courier" in guide
    assert "Copper & Forge" in guide
    assert "capture-profile" in guide
    assert "reference-not-approved" in guide
    assert "não existe um catálogo de perfis persistido" in guide

    example_root = REPOSITORY_ROOT / "examples/2d/project"
    asset = AssetContract.model_validate(
        json.loads((example_root / "imports/courier.json").read_text(encoding="utf-8"))
    )
    profile = CaptureProfileContract.model_validate(
        json.loads((example_root / "profiles/courier-sprite.json").read_text(encoding="utf-8"))
    )
    reference = VisualReferenceContract.model_validate(
        json.loads((example_root / "imports/courier-reference.json").read_text(encoding="utf-8"))
    )

    plan = VisualJobPlanner().plan(
        "courier-getting-started-plan",
        "Courier getting started plan",
        (
            VisualPlanTarget(
                asset.to_domain(),
                profile.to_domain(),
                (ReferenceId(reference.id),),
            ),
        ),
        references=(reference.to_domain(),),
    )

    assert plan.jobs
    assert plan.state.value == "blocked"
    assert VisualPlanBlockerCode.REFERENCE_NOT_APPROVED in {
        blocker.code for blocker in plan.blockers
    }

    humanoid = load_humanoid_profile("minimal")
    assert humanoid.to_capture_profile().sheets
    assert humanoid.neutral_representation.mode.value == "neutral-bodysuit"


def test_troubleshooting_guide_matches_current_cli_recovery_contracts(
    tmp_path: Path,
) -> None:
    guide = TROUBLESHOOTING_GUIDE.read_text(encoding="utf-8")

    for expected in (
        "uv sync --all-extras",
        "project-not-found",
        "invalid-input",
        "conflict",
        "checks-failed",
        "corrupt-state",
        "error.code",
        ".ludowright/project.json",
        "stale lock",
        "PowerShell",
    ):
        assert expected in guide

    runner = CliRunner()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("preserve\n", encoding="utf-8")

    conflict = runner.invoke(
        app,
        [
            "--json",
            "init",
            str(occupied),
            "--name",
            "Occupied Game",
            "--non-interactive",
        ],
    )
    conflict_payload = json.loads(conflict.stdout)
    assert conflict.exit_code == int(CliExitCode.CONFLICT)
    assert conflict_payload["error"]["code"] == "conflict"
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "preserve\n"

    missing_project = runner.invoke(
        app,
        ["--json", "codex", "skill", "verify", str(tmp_path / "missing")],
    )
    missing_payload = json.loads(missing_project.stdout)
    assert missing_project.exit_code == int(CliExitCode.NOT_FOUND)
    assert missing_payload["error"]["code"] == "project-not-found"

    quality = runner.invoke(app, ["--json", "quality", "check", "--dry-run"])
    quality_payload = json.loads(quality.stdout)
    assert quality.exit_code == int(CliExitCode.SUCCESS)
    assert quality_payload["data"]["dry_run"] is True


__all__ = []
