"""Command-line interface for LudoWright."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ludowright import __version__
from ludowright.application import ProjectStatusCorruptError, ProjectStatusService
from ludowright.cli.diagnostics import collect_diagnostics, render_diagnostics
from ludowright.cli.quality import quality_app
from ludowright.cli.runtime import (
    CliExitCode,
    CliFailure,
    CliSettings,
    canonical_json,
    run_command,
)
from ludowright.contracts.cli import CliErrorCode, CliResponseContract

app = typer.Typer(
    name="ludowright",
    help="Plan, document, visualize, validate, and package game projects.",
    no_args_is_help=True,
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(quality_app, name="quality")


@app.callback()
def root(
    context: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed LudoWright version and exit.",
            is_eager=True,
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Return stable machine-readable responses for the selected command.",
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored human-readable output."),
    ] = False,
) -> None:
    """Run the LudoWright command-line interface."""
    settings = CliSettings(json_output=json_output, no_color=no_color)
    context.obj = settings
    if version:
        if json_output:
            response = CliResponseContract.success(
                command="version",
                data={"version": __version__},
                ludowright_version=__version__,
            )
            typer.echo(canonical_json(response))
        else:
            typer.echo(__version__)
        raise typer.Exit()


@app.command()
def status(
    context: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(help="Diretório ou arquivo a partir do qual descobrir o projeto."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Show the current project readiness and consistency status."""

    def action() -> dict[str, object]:
        try:
            return ProjectStatusService().inspect(path).as_data()
        except ProjectStatusCorruptError as error:
            raise CliFailure(
                CliErrorCode.CORRUPT_STATE,
                str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error

    def render(console: Console, data: dict[str, object]) -> None:
        project = _mapping(data, "project")
        readiness = _mapping(data, "readiness")
        console.print(f"[bold]Project status: {readiness['state']}[/bold]")
        console.print(f"Project: {project['name']} ({project['id']})")
        console.print(f"Directory: {data['project_directory']}")
        console.print(f"Stage: {project['stage']} | Lifecycle: {project['lifecycle']}")

        components = data["components"]
        if isinstance(components, list):
            table = Table(title="Components")
            table.add_column("Component", style="bold")
            table.add_column("State")
            table.add_column("Detail")
            for component in components:
                if isinstance(component, dict):
                    table.add_row(
                        str(component["name"]),
                        str(component["state"]),
                        str(component["detail"]),
                    )
            console.print(table)

        blockers = data["blockers"]
        if isinstance(blockers, list) and blockers:
            console.print("[bold red]Blockers:[/bold red]")
            for blocker in blockers:
                if isinstance(blocker, dict):
                    console.print(f"- {blocker['code']}: {blocker['detail']}")

        stale_outputs = data["stale_outputs"]
        if isinstance(stale_outputs, list) and stale_outputs:
            console.print(f"Stale or review-required outputs: {len(stale_outputs)}")

        actions = data["recommended_actions"]
        if isinstance(actions, list) and actions:
            console.print("Recommended next action:")
            first_action = actions[0]
            if isinstance(first_action, dict):
                console.print(f"- {first_action['code']}: {first_action['detail']}")

    run_command(
        context=context,
        command="status",
        local_json=json_output,
        action=action,
        render_human=render,
    )


def _mapping(data: dict[str, object], key: str) -> dict[str, object]:
    value = data[key]
    if not isinstance(value, dict):
        raise TypeError(f"status field {key!r} must be an object")
    return value


@app.command()
def diagnostics(
    context: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Inspect the runtime environment and nearest project without changing files."""
    run_command(
        context=context,
        command="diagnostics",
        local_json=json_output,
        action=collect_diagnostics,
        render_human=render_diagnostics,
    )


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
