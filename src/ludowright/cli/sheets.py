"""CLI presentation for deterministic technical-sheet assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ludowright.application.technical_sheets import TechnicalSheetService
from ludowright.cli.runtime import run_command
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath

sheets_app = typer.Typer(
    name="sheets",
    help="Assemble deterministic technical sheets from approved images.",
    no_args_is_help=True,
)


@sheets_app.command("assemble")
def assemble_command(
    context: typer.Context,
    request_path: Annotated[
        str,
        typer.Argument(help="Project-relative technical-sheet request JSON."),
    ],
    output_directory: Annotated[
        str,
        typer.Argument(help="Project-relative directory for the assembled sheet."),
    ],
    project: Annotated[
        str,
        typer.Argument(help="Project directory containing the LudoWright marker."),
    ] = ".",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and plan without writing files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return the published CLI response envelope."),
    ] = False,
) -> None:
    """Assemble one deterministic technical sheet from approved PNG inputs."""

    def action() -> dict[str, object]:
        filesystem = ProjectFilesystem.discover(Path(project))
        request = _project_relative_path(filesystem, request_path)
        output = _project_relative_path(filesystem, output_directory)
        return (
            TechnicalSheetService(filesystem)
            .assemble(
                request,
                output,
                dry_run=dry_run,
            )
            .as_data()
        )

    def render(console: Console, data: dict[str, object]) -> None:
        console.print("[bold]Technical sheet assembly[/bold]")
        console.print(f"State: {data['state']}")
        console.print(f"Sheet kind: {data['sheet_kind']}")
        console.print(f"Template: {data['template_id']} v{data['template_version']}")
        console.print(f"Output: {data['output_path']}")
        console.print(f"Report: {data['report_path']}")

    run_command(
        context=context,
        command="sheets assemble",
        local_json=json_output,
        action=action,
        render_human=render,
    )


def _project_relative_path(filesystem: ProjectFilesystem, raw_path: str) -> RepositoryPath:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve(strict=False).relative_to(filesystem.root)
        except ValueError as error:
            raise ValueError("technical-sheet paths must be inside the selected project") from error
    return RepositoryPath.parse(candidate.as_posix())


__all__ = ["assemble_command", "sheets_app"]
