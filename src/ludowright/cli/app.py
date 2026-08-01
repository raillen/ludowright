"""Command-line interface for LudoWright."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from ludowright import __version__
from ludowright.cli.assets import assets_app
from ludowright.cli.atlas import generate_atlas
from ludowright.cli.codex import codex_app
from ludowright.cli.diagnostics import collect_diagnostics, render_diagnostics
from ludowright.cli.docs import docs_app
from ludowright.cli.documents import documents_app
from ludowright.cli.images import images_app
from ludowright.cli.interview import interview_app
from ludowright.cli.packages import package_app
from ludowright.cli.quality import quality_app
from ludowright.cli.review import review_command
from ludowright.cli.runtime import (
    CliSettings,
    canonical_json,
    run_command,
)
from ludowright.cli.sheets import sheets_app
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
app.command("atlas")(generate_atlas)
app.command("review")(review_command)


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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
