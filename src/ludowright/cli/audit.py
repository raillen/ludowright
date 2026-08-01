"""CLI presentation for the deterministic global project audit."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ludowright.application import (
    ProjectAuditConflictError,
    ProjectAuditCorruptError,
    ProjectAuditError,
    ProjectAuditService,
)
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import CliErrorCode
from ludowright.infrastructure import ProjectFilesystem


def audit_project(
    context: typer.Context,
    project: Annotated[
        Path,
        typer.Argument(help="Project directory or a path below its marker."),
    ],
    check: Annotated[
        bool,
        typer.Option("--check", help="Fail when the project is not release-ready."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report the audit plan without changing files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return the published CLI response envelope."),
    ] = False,
) -> None:
    """Inspect product-to-package readiness without modifying the project."""

    def action() -> dict[str, object]:
        try:
            result = ProjectAuditService(ProjectFilesystem.discover(project)).audit(dry_run=dry_run)
        except ProjectAuditConflictError as error:
            raise CliFailure(
                code=CliErrorCode.CONFLICT,
                message=str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except ProjectAuditCorruptError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error
        except ProjectAuditError as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

        data = result.as_data()
        if check and not result.report.valid:
            raise CliFailure(
                code=CliErrorCode.CHECKS_FAILED,
                message="project audit found unresolved readiness findings",
                exit_code=CliExitCode.CHECKS_FAILED,
                data=data,
            )
        return data

    run_command(
        context=context,
        command="audit",
        local_json=json_output,
        action=action,
        render_human=_render_human,
    )


def _render_human(console: Console, data: dict[str, object]) -> None:
    """Render the report summary and stable finding identifiers."""
    console.print("[bold]LudoWright project audit[/bold]")
    console.print(f"Project: {data['project_name']} ({data['project_id']})")
    console.print(f"State: {data['state']} | Dry run: {data['dry_run']}")
    console.print(f"Source digest: {data['source_digest']}")

    categories = data.get("categories")
    if isinstance(categories, list):
        table = Table("Category", "State", "Items", "Errors", "Warnings")
        for category in categories:
            if isinstance(category, dict):
                table.add_row(
                    str(category["category"]),
                    str(category["state"]),
                    str(category["item_count"]),
                    str(category["error_count"]),
                    str(category["warning_count"]),
                )
        console.print(table)

    findings = data.get("findings")
    if isinstance(findings, list) and findings:
        console.print("Findings:")
        for finding in findings:
            if isinstance(finding, dict):
                console.print(f"- [{finding['severity']}] {finding['code']}: {finding['message']}")
    else:
        console.print("No findings.")


__all__ = ["audit_project"]
