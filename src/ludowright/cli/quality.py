"""CLI commands for repository quality and release verification."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

import typer
from rich.console import Console

from ludowright import __version__
from ludowright.cli.runtime import (
    CliExitCode,
    CliFailure,
    canonical_json,
    command_console,
    emit_failure,
    json_requested,
)
from ludowright.contracts.cli import CliErrorCode, CliResponseContract
from ludowright.quality import QUALITY_CHECKS, RELEASE_CHECKS, CheckResult, CheckSpec, run_checks

quality_app = typer.Typer(
    help="Run deterministic engineering and release-quality gates.",
    no_args_is_help=True,
)


def _run_group(
    context: typer.Context,
    mode: str,
    checks: Sequence[CheckSpec],
    *,
    local_json: bool,
    dry_run: bool,
) -> None:
    results = run_checks(checks, dry_run=dry_run)
    passed = all(result.passed for result in results)
    payload: dict[str, object] = {
        "checks": [result.to_dict() for result in results],
        "dry_run": dry_run,
        "mode": mode,
        "passed": passed,
    }
    command = "quality check" if mode == "quality" else "quality release"
    json_output = json_requested(context, local_json)

    if json_output:
        if passed:
            response = CliResponseContract.success(
                command=command,
                data=payload,
                ludowright_version=__version__,
            )
            typer.echo(canonical_json(response))
            return
        failed_checks = [result.name for result in results if not result.passed]
        emit_failure(
            command=command,
            failure=CliFailure(
                CliErrorCode.CHECKS_FAILED,
                "One or more quality checks failed.",
                exit_code=CliExitCode.CHECKS_FAILED,
                details={"failed_checks": failed_checks},
                data=payload,
            ),
            json_output=True,
            context=context,
        )

    _print_results(
        command_console(context),
        mode,
        results,
        dry_run=dry_run,
    )
    if not passed:
        raise typer.Exit(code=int(CliExitCode.CHECKS_FAILED))


def _print_results(
    console: Console,
    mode: str,
    results: Sequence[CheckResult],
    *,
    dry_run: bool,
) -> None:
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
    context: typer.Context,
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
    _run_group(
        context,
        "quality",
        QUALITY_CHECKS,
        local_json=json_output,
        dry_run=dry_run,
    )


@quality_app.command("release")
def release(
    context: typer.Context,
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
    _run_group(
        context,
        "release",
        RELEASE_CHECKS,
        local_json=json_output,
        dry_run=dry_run,
    )
