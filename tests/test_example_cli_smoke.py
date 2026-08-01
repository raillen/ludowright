"""Compatibility smoke tests for the commands published by public examples."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.cli.app import app
from ludowright.cli.runtime import CliExitCode

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CASES = (
    ("minimal", "Lantern Path", ("imports/lantern.json",)),
    ("2d", "Starfall Courier", ("imports/courier.json",)),
    (
        "low-poly-3d",
        "Copper & Forge",
        ("imports/copper.json", "imports/forge-building.json"),
    ),
    (
        "modular-environment",
        "Mossbridge Commons",
        (
            "imports/commons-building.json",
            "imports/courtyard-kit.json",
            "imports/old-road.json",
            "imports/oak-tree.json",
            "imports/field-plant.json",
        ),
    ),
)

runner = CliRunner()


@pytest.mark.parametrize("example_id,project_name,asset_inputs", EXAMPLE_CASES)
def test_public_example_cli_setup_is_executable(
    tmp_path: Path,
    example_id: str,
    project_name: str,
    asset_inputs: tuple[str, ...],
) -> None:
    project = tmp_path / project_name.lower().replace(" ", "-").replace("&", "and")
    example_root = REPOSITORY_ROOT / "examples" / example_id / "project"

    initialized = runner.invoke(
        app,
        [
            "--json",
            "init",
            str(project),
            "--name",
            project_name,
            "--template",
            "minimal",
            "--non-interactive",
        ],
    )
    assert initialized.exit_code == int(CliExitCode.SUCCESS), initialized.stdout

    shutil.copytree(example_root, project, dirs_exist_ok=True)

    for asset_input in asset_inputs:
        registered = runner.invoke(
            app,
            [
                "--json",
                "assets",
                "create",
                str(project),
                "--input",
                asset_input,
            ],
        )
        assert registered.exit_code == int(CliExitCode.SUCCESS), registered.stdout
        payload = json.loads(registered.stdout)
        assert payload["ok"] is True
        assert payload["data"]["state"] == "created"

    audited = runner.invoke(
        app,
        ["--json", "assets", "audit", str(project), "--check"],
    )
    assert audited.exit_code == int(CliExitCode.SUCCESS), audited.stdout
    audit_payload = json.loads(audited.stdout)
    assert audit_payload["ok"] is True
    assert audit_payload["data"]["valid"] is True

    assert (project / "assets/registry.yaml").is_file()
    assert (project / ".ludowright/project.json").is_file()
