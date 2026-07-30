"""Command-line interface for LudoWright."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ludowright import __version__
from ludowright.application.audit import StructuralAuditService
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
def audit(
    context: typer.Context,
    start: Annotated[
        Path,
        typer.Argument(help="Project directory or descendant to inspect."),
    ] = Path("."),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Audit project structure and derived state without changing files."""

    def action() -> dict[str, object]:
        result = StructuralAuditService().inspect(start)
        data = result.as_data()
        if result.has_findings:
            raise CliFailure(
                CliErrorCode.CHECKS_FAILED,
                "Structural audit found project issues.",
                exit_code=CliExitCode.CHECKS_FAILED,
                details={"finding_codes": list(result.finding_codes)},
                data=data,
            )
        return data

    run_command(
        context=context,
        command="audit",
        local_json=json_output,
        action=action,
        render_human=render_audit,
        render_failure_human=render_audit,
    )


def render_audit(console: Console, data: dict[str, object]) -> None:
    """Render the structural audit consistently for success and failure."""
    console.print("[bold]LudoWright structural audit[/bold]")
    console.print(f"State: {data.get('state', 'unknown')}")
    components = data.get("components", ())
    if isinstance(components, list):
        for component in components:
            if isinstance(component, dict):
                console.print(
                    f"  {component.get('name')}: {component.get('state')} ({component.get('path')})"
                )
    findings = data.get("findings", ())
    if isinstance(findings, list) and findings:
        console.print("Findings:")
        for finding in findings:
            if isinstance(finding, dict):
                console.print(f"  [red]{finding.get('code')}[/red]: {finding.get('detail')}")
    guidance = data.get("repair_guidance", ())
    if isinstance(guidance, list) and guidance:
        console.print("Repair guidance:")
        for action in guidance:
            if isinstance(action, dict):
                console.print(f"  {action.get('code')}: {action.get('command')}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
