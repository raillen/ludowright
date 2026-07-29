"""Smoke tests for the initial command-line interface."""

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
