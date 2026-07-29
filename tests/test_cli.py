"""Smoke and contract tests for the command-line interface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from ludowright import __version__
from ludowright.cli.app import app

runner = CliRunner()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_status_json_contract() -> None:
    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "schema_version": 1,
        "status": "foundation",
        "version": __version__,
    }


def test_status_human_output() -> None:
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "LudoWright is in the foundation phase." in result.stdout
    assert f"Version: {__version__}" in result.stdout


def test_quality_dry_run_json_contract() -> None:
    result = runner.invoke(app, ["quality", "check", "--dry-run", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["mode"] == "quality"
    assert payload["dry_run"] is True
    assert payload["passed"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "pre-commit",
        "tests",
        "documentation",
        "dependency-audit",
    ]
    assert all(check["skipped"] is True for check in payload["checks"])


def test_release_dry_run_human_output() -> None:
    result = runner.invoke(app, ["quality", "release", "--dry-run"])

    assert result.exit_code == 0
    assert "LudoWright release checks planned:" in result.stdout
    assert "package-build" in result.stdout
