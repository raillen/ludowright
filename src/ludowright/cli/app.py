"""Command-line interface for LudoWright."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ludowright import __version__
from ludowright.application.initialization import (
    ProjectInitializationConflictError,
    ProjectInitializationError,
    ProjectInitializationFailureError,
    ProjectInitializationInputError,
    ProjectInitializationService,
)
from ludowright.cli.assets import assets_app
from ludowright.cli.atlas import generate_atlas
from ludowright.cli.audit import audit_project
from ludowright.cli.codex import codex_app
from ludowright.cli.diagnostics import collect_diagnostics, render_diagnostics
from ludowright.cli.docs import docs_app
from ludowright.cli.documents import documents_app
from ludowright.cli.images import images_app
from ludowright.cli.interview import interview_app
from ludowright.cli.packages import package_app
from ludowright.cli.quality import quality_app
from ludowright.cli.release import release_app
from ludowright.cli.review import review_command
from ludowright.cli.runtime import (
    CliExitCode,
    CliFailure,
    CliSettings,
    canonical_json,
    run_command,
)
from ludowright.cli.sheets import sheets_app
from ludowright.contracts import CliErrorCode
from ludowright.contracts.cli import CliResponseContract

app = typer.Typer(
    name="ludowright",
    help="Plan, document, visualize, validate, and package game projects.",
    no_args_is_help=True,
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(quality_app, name="quality")
app.add_typer(codex_app, name="codex")
app.add_typer(assets_app, name="assets")
app.add_typer(interview_app, name="interview")
app.add_typer(images_app, name="images")
app.add_typer(sheets_app, name="sheets")
app.add_typer(documents_app, name="documents")
app.add_typer(package_app, name="package")
app.add_typer(docs_app, name="docs")
app.add_typer(release_app, name="release")
app.command("atlas")(generate_atlas)
app.command("review")(review_command)
app.command("audit")(audit_project)


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
            "status": "beta-preparation",
            "version": __version__,
        }

    def render(console: Console, data: dict[str, object]) -> None:
        console.print("[bold]LudoWright[/bold] is in the beta-preparation phase.")
        console.print(f"Version: {data['version']}")

    run_command(
        context=context,
        command="status",
        local_json=json_output,
        action=action,
        render_human=render,
    )


@app.command()
def init(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Directory for the new project.")],
    name: Annotated[
        str,
        typer.Option("--name", help="Human-readable project name."),
    ],
    template: Annotated[
        str,
        typer.Option("--template", help="Versioned starter template identifier."),
    ] = "minimal",
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            help="Do not prompt; all required values must be supplied as options.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the project without writing files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Initialize a new local-first LudoWright project."""
    del non_interactive  # The command never prompts when required options are present.

    def action() -> dict[str, object]:
        try:
            result = ProjectInitializationService().initialize(
                path,
                name=name,
                template_id=template,
                dry_run=dry_run,
            )
            return result.as_data()
        except ProjectInitializationConflictError as error:
            raise CliFailure(
                code=CliErrorCode.CONFLICT,
                message=str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except ProjectInitializationFailureError as error:
            raise CliFailure(
                code=CliErrorCode.INTERNAL_ERROR,
                message=str(error),
                exit_code=CliExitCode.INTERNAL,
            ) from error
        except (ProjectInitializationInputError, ProjectInitializationError) as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

    run_command(
        context=context,
        command="init",
        local_json=json_output,
        action=action,
        render_human=_render_init_human,
    )


def _render_init_human(console: Console, data: dict[str, object]) -> None:
    """Render the initialization summary without exposing unstable internals."""
    state = data["state"]
    console.print(f"[bold]LudoWright project {state}.[/bold]")
    console.print(f"Directory: {data['project_directory']}")
    console.print(f"ProjectId: {data['project_id']}")
    template = data["template"]
    if isinstance(template, dict):
        console.print(f"Template: {template['id']} v{template['version']}")
    files = data["files"]
    file_count = len(files) if isinstance(files, list) else 0
    console.print(f"Files: {file_count}")


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
