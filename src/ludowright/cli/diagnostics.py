"""Environment and project-discovery diagnostics for the command-line interface."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ludowright import __version__
from ludowright.infrastructure import (
    ProjectFilesystem,
    ProjectFilesystemError,
    ProjectRootNotFoundError,
)


def collect_diagnostics(start: Path | None = None) -> dict[str, object]:
    """Collect deterministic environment facts without mutating a project."""
    location = (start or Path.cwd()).expanduser()
    project: dict[str, object]
    try:
        filesystem = ProjectFilesystem.discover(location)
    except ProjectRootNotFoundError:
        project = {
            "found": False,
            "status": "not-found",
        }
    except ProjectFilesystemError as error:
        project = {
            "found": False,
            "status": "invalid",
            "message": str(error),
        }
    else:
        project = {
            "found": True,
            "status": "found",
            "root": filesystem.root.as_posix(),
        }

    return {
        "ludowright_version": __version__,
        "platform": {
            "machine": platform.machine() or "unknown",
            "release": platform.release() or "unknown",
            "system": platform.system() or "unknown",
        },
        "project": project,
        "python": {
            "executable": Path(sys.executable).as_posix(),
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
    }


def render_diagnostics(console: Console, data: dict[str, object]) -> None:
    """Render diagnostic data as a compact Rich table."""
    table = Table(title="LudoWright diagnostics", show_header=True)
    table.add_column("Area", style="bold")
    table.add_column("Value")

    python = _object(data, "python")
    platform_data = _object(data, "platform")
    project = _object(data, "project")
    table.add_row("LudoWright", str(data["ludowright_version"]))
    table.add_row(
        "Python",
        f"{python['implementation']} {python['version']} ({python['executable']})",
    )
    table.add_row(
        "Platform",
        f"{platform_data['system']} {platform_data['release']} ({platform_data['machine']})",
    )
    if project["found"]:
        table.add_row("Project", str(project["root"]))
    else:
        table.add_row("Project", str(project["status"]))
    console.print(table)


def _object(data: dict[str, object], key: str) -> dict[str, object]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"diagnostic field {key!r} must be an object")
    return value
