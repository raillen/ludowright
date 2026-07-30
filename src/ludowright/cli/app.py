"""Command-line interface for LudoWright."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ludowright import __version__
from ludowright.application import (
    ProjectInitializationConflictError,
    ProjectInitializationFailureError,
    ProjectInitializationInputError,
    ProjectInitializationService,
)
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
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Show the current framework bootstrap status."""

    def action() -> dict[str, object]:
        return {
            "status": "foundation",
            "version": __version__,
        }

    def render(console: Console, data: dict[str, object]) -> None:
        console.print("[bold]LudoWright[/bold] is in the foundation phase.")
        console.print(f"Version: {data['version']}")

    run_command(
        context=context,
        command="status",
        local_json=json_output,
        action=action,
        render_human=render,
    )


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


@app.command()
def init(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Diretório do novo projeto.")],
    name: Annotated[
        str,
        typer.Option("--name", help="Nome humano do projeto.", min=1),
    ],
    template: Annotated[
        str,
        typer.Option("--template", help="Template inicial versionado."),
    ] = "minimal",
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            help="Executa sem perguntas interativas; --name é obrigatório.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Mostra o plano sem alterar arquivos."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Initialize one new local-first LudoWright project."""
    del non_interactive

    def action() -> dict[str, object]:
        try:
            result = ProjectInitializationService().initialize(
                path,
                name=name,
                template_id=template,
                dry_run=dry_run,
            )
        except ProjectInitializationInputError as error:
            raise CliFailure(
                CliErrorCode.INVALID_INPUT,
                str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error
        except ProjectInitializationConflictError as error:
            raise CliFailure(
                CliErrorCode.CONFLICT,
                str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except ProjectInitializationFailureError as error:
            raise CliFailure(
                CliErrorCode.INTERNAL_ERROR,
                str(error),
                exit_code=CliExitCode.INTERNAL,
            ) from error
        return result.as_data()

    def render(console: Console, data: dict[str, object]) -> None:
        state = data["state"]
        console.print(f"[bold]LudoWright project {state}.[/bold]")
        console.print(f"Directory: {data['project_directory']}")
        console.print(f"ProjectId: {data['project_id']}")
        template_data = data["template"]
        if isinstance(template_data, dict):
            console.print(f"Template: {template_data['id']} v{template_data['version']}")
        files = data["files"]
        if isinstance(files, list):
            console.print(f"Files: {len(files)}")

    run_command(
        context=context,
        command="init",
        local_json=json_output,
        action=action,
        render_human=render,
    )


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
