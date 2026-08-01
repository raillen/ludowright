"""Clean-room installation checks for published LudoWright distributions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for variable in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(variable, None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _run_successfully(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        check=False,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"command failed with exit code {completed.returncode}: {command!r}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    return completed


def _python_in(virtual_environment: Path) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    return virtual_environment / ("Scripts" if os.name == "nt" else "bin") / executable


def _console_script_in(virtual_environment: Path) -> Path:
    script_directory = virtual_environment / ("Scripts" if os.name == "nt" else "bin")
    candidates = (
        script_directory / "ludowright",
        script_directory / "ludowright.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise AssertionError(f"installed ludowright console script is missing in {script_directory}")


@pytest.mark.clean_installation
def test_published_wheel_and_sdist_run_from_clean_environments(tmp_path: Path) -> None:
    """Build, install, and execute every publishable distribution format."""
    environment = _clean_environment()
    isolated_cwd = tmp_path / "outside-checkout"
    isolated_cwd.mkdir()
    distribution_directory = tmp_path / "distributions"

    _run_successfully(
        (
            "uv",
            "build",
            "--wheel",
            "--sdist",
            "--out-dir",
            str(distribution_directory),
        ),
        cwd=REPOSITORY_ROOT,
        environment=environment,
    )

    artifacts = sorted(distribution_directory.iterdir())
    wheels = [artifact for artifact in artifacts if artifact.suffix == ".whl"]
    sdists = [artifact for artifact in artifacts if artifact.name.endswith(".tar.gz")]
    assert len(wheels) == 1
    assert len(sdists) == 1

    for artifact in (wheels[0], sdists[0]):
        artifact_kind = "wheel" if artifact.suffix == ".whl" else "sdist"
        virtual_environment = tmp_path / f"venv-{artifact_kind}"
        _run_successfully(
            (
                "uv",
                "venv",
                "--no-project",
                "--python",
                sys.executable,
                str(virtual_environment),
            ),
            cwd=isolated_cwd,
            environment=environment,
        )
        python = _python_in(virtual_environment)
        _run_successfully(
            ("uv", "pip", "install", "--strict", "--python", str(python), str(artifact)),
            cwd=isolated_cwd,
            environment=environment,
        )

        launcher = _console_script_in(virtual_environment)
        version = _run_successfully(
            (str(launcher), "--version"),
            cwd=isolated_cwd,
            environment=environment,
        )
        assert version.stdout.strip() == "0.1.0.dev0"

        diagnostics = _run_successfully(
            (str(launcher), "--json", "diagnostics"),
            cwd=isolated_cwd,
            environment=environment,
        )
        response = json.loads(diagnostics.stdout)
        assert response["kind"] == "cli-response"
        assert response["ok"] is True
        assert response["data"]["project"] == {"found": False, "status": "not-found"}
