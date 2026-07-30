"""Smoke, response-contract, and exit-code tests for the CLI."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ludowright import __version__
from ludowright.cli import quality as quality_cli
from ludowright.cli.app import app
from ludowright.cli.runtime import CliExitCode, canonical_json
from ludowright.contracts.cli import (
    CliErrorCode,
    CliErrorContract,
    CliMetaContract,
    CliResponseContract,
)
from ludowright.quality import CheckResult, CheckSpec

runner = CliRunner()


def json_response(arguments: list[str]) -> tuple[dict[str, object], int, str]:
    result = runner.invoke(app, arguments)
    return json.loads(result.stdout), result.exit_code, result.stdout.strip()


def test_version_option_human_output() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert result.stdout.strip() == __version__


def test_version_option_json_envelope() -> None:
    payload, exit_code, raw = json_response(["--json", "--version"])

    assert exit_code == int(CliExitCode.SUCCESS)
    assert payload == {
        "command": "version",
        "data": {"version": __version__},
        "error": None,
        "kind": "cli-response",
        "meta": {
            "ludowright_version": __version__,
            "output": "json",
        },
        "ok": True,
        "schema_version": 1,
    }
    assert ": " not in raw


def test_status_local_json_contract() -> None:
    payload, exit_code, _raw = json_response(["status", "--json"])

    assert exit_code == int(CliExitCode.SUCCESS)
    assert payload["schema_version"] == 1
    assert payload["kind"] == "cli-response"
    assert payload["command"] == "status"
    assert payload["ok"] is True
    assert payload["data"] == {
        "status": "foundation",
        "version": __version__,
    }
    assert payload["error"] is None


def test_status_inherits_global_json_option() -> None:
    payload, exit_code, _raw = json_response(["--json", "status"])

    assert exit_code == int(CliExitCode.SUCCESS)
    assert payload["command"] == "status"
    assert payload["ok"] is True


def test_status_human_output() -> None:
    result = runner.invoke(app, ["status"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "LudoWright is in the foundation phase." in result.stdout
    assert f"Version: {__version__}" in result.stdout


def test_no_color_disables_ansi_sequences() -> None:
    result = runner.invoke(app, ["--no-color", "status"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "\x1b[" not in result.stdout


def test_diagnostics_json_outside_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    payload, exit_code, _raw = json_response(["diagnostics", "--json"])

    assert exit_code == int(CliExitCode.SUCCESS)
    assert payload["command"] == "diagnostics"
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["ludowright_version"] == __version__
    project = data["project"]
    assert isinstance(project, dict)
    assert project == {"found": False, "status": "not-found"}
    assert isinstance(data["python"], dict)
    assert isinstance(data["platform"], dict)


def test_diagnostics_discovers_nearest_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    marker = Path(".ludowright/project.json")
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    payload, exit_code, _raw = json_response(["--json", "diagnostics"])
    expected_root = tmp_path.resolve().as_posix()

    assert exit_code == int(CliExitCode.SUCCESS)
    data = payload["data"]
    assert isinstance(data, dict)
    project = data["project"]
    assert isinstance(project, dict)
    assert project == {
        "found": True,
        "root": expected_root,
        "status": "found",
    }


def test_diagnostics_human_output_uses_rich_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["diagnostics"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "LudoWright diagnostics" in result.stdout
    assert "Python" in result.stdout
    assert "Project" in result.stdout


def test_quality_dry_run_json_contract() -> None:
    payload, exit_code, _raw = json_response(["quality", "check", "--dry-run", "--json"])

    assert exit_code == int(CliExitCode.SUCCESS)
    assert payload["command"] == "quality check"
    assert payload["ok"] is True
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["mode"] == "quality"
    assert data["dry_run"] is True
    assert data["passed"] is True
    checks = data["checks"]
    assert isinstance(checks, list)
    assert [check["name"] for check in checks] == [
        "pre-commit",
        "tests",
        "schema-publication",
        "atlas",
        "documentation",
        "dependency-audit",
    ]
    assert all(check["skipped"] is True for check in checks)


def test_quality_failure_json_contains_data_and_stable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_checks(
        checks: Sequence[CheckSpec],
        *,
        dry_run: bool = False,
    ) -> tuple[CheckResult, ...]:
        assert checks
        assert dry_run is False
        return (
            CheckResult(
                name="tests",
                command=("uv", "run", "pytest"),
                exit_code=9,
            ),
        )

    monkeypatch.setattr(quality_cli, "run_checks", failed_checks)

    payload, exit_code, _raw = json_response(["quality", "check", "--json"])

    assert exit_code == int(CliExitCode.CHECKS_FAILED)
    assert payload["ok"] is False
    assert payload["command"] == "quality check"
    assert payload["data"] == {
        "checks": [
            {
                "command": ["uv", "run", "pytest"],
                "exit_code": 9,
                "name": "tests",
                "passed": False,
                "skipped": False,
            }
        ],
        "dry_run": False,
        "mode": "quality",
        "passed": False,
    }
    error = payload["error"]
    assert isinstance(error, dict)
    assert error == {
        "code": "checks-failed",
        "details": {"failed_checks": ["tests"]},
        "message": "One or more quality checks failed.",
    }


def test_release_dry_run_human_output() -> None:
    result = runner.invoke(app, ["quality", "release", "--dry-run"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "LudoWright release checks planned:" in result.stdout
    assert "package-build" in result.stdout


def test_unknown_command_uses_stable_usage_exit_code() -> None:
    result = runner.invoke(app, ["unknown-command"])

    assert result.exit_code == int(CliExitCode.USAGE)


def test_response_contract_enforces_success_and_failure_states() -> None:
    meta = CliMetaContract(ludowright_version=__version__)
    error = CliErrorContract(
        code=CliErrorCode.BLOCKED,
        message="A required approval is missing.",
    )

    with pytest.raises(ValidationError, match="successful CLI response"):
        CliResponseContract(
            command="status",
            ok=True,
            data={},
            error=error,
            meta=meta,
        )
    with pytest.raises(ValidationError, match="failed CLI response"):
        CliResponseContract(
            command="status",
            ok=False,
            data={},
            error=None,
            meta=meta,
        )


def test_response_contract_rejects_non_json_values() -> None:
    with pytest.raises(ValidationError, match="non-finite"):
        CliResponseContract.success(
            command="status",
            data={"ratio": float("inf")},
            ludowright_version=__version__,
        )
    with pytest.raises(ValidationError, match="cannot contain set"):
        CliResponseContract.success(
            command="status",
            data={"values": {"invalid"}},
            ludowright_version=__version__,
        )


def test_canonical_json_is_deterministic() -> None:
    response = CliResponseContract.success(
        command="status",
        data={"z": 2, "a": 1},
        ludowright_version=__version__,
    )

    assert canonical_json(response) == canonical_json(response)
    assert canonical_json(response).index('"a"') < canonical_json(response).index('"z"')
