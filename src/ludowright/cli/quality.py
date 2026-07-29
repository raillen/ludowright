"""CLI commands for repository quality and release verification."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Annotated

import typer
from rich.console import Console

from ludowright.quality import QUALITY_CHECKS, RELEASE_CHECKS, CheckResult, CheckSpec, run_checks

quality_app = typer.Typer(
    help="Run deterministic engineering and release-quality gates.",
    no_args_is_help=True,
)
console = Console()


def _run_group(
    mode: str,
    checks: Sequence[CheckSpec],
    *,
    json_output: bool,
    dry_run: bool,
) -> None:
    results = run_checks(checks, dry_run=dry_run)
    passed = all(result.passed for result in results)
    payload = {
        "checks": [result.to_dict() for result in results],
        "dry_run": dry_run,
        "mode": mode,
        "passed": passed,
        "schema_version": 1,
    }

    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        _print_results(mode, results, dry_run=dry_run)

    if not passed:
        raise typer.Exit(code=1)


def _print_results(mode: str, results: Sequence[CheckResult], *, dry_run: bool) -> None:
    label = "planned" if dry_run else "completed"
    console.print(f"[bold]LudoWright {mode} checks[/bold] {label}:")

    for result in results:
        if result.skipped:
            status = "[yellow]SKIP[/yellow]"
        elif result.passed:
            status = "[green]PASS[/green]"
        else:
            status = f"[red]FAIL ({result.exit_code})[/red]"
        console.print(f"  {status} {result.name}")


@quality_app.command("check")
def check(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List checks without executing them."),
    ] = False,
) -> None:
    """Run the normal pull-request quality gate."""
    _run_group("quality", QUALITY_CHECKS, json_output=json_output, dry_run=dry_run)


@quality_app.command("release")
def release(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List checks without executing them."),
    ] = False,
) -> None:
    """Run quality gates and verify that distribution artifacts build."""
    _run_group("release", RELEASE_CHECKS, json_output=json_output, dry_run=dry_run)
