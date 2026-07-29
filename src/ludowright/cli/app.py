"""Command-line interface for LudoWright."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from ludowright import __version__

app = typer.Typer(
    name="ludowright",
    help="Plan, document, visualize, validate, and package game projects.",
    no_args_is_help=True,
    invoke_without_command=True,
)
console = Console()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", help="Show the installed LudoWright version and exit."),
    ] = False,
) -> None:
    """Run the LudoWright command-line interface."""
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command()
def status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Show the current bootstrap status."""
    payload = {
        "schema_version": 1,
        "status": "foundation",
        "version": __version__,
    }

    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
        return

    console.print("[bold]LudoWright[/bold] is in the foundation phase.")
    console.print(f"Version: {__version__}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
