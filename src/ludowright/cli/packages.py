"""CLI presentation for deterministic package manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ludowright.application import (
    PackageManifestConflictError,
    PackageManifestError,
    PackageManifestInputError,
    PackageManifestService,
)
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import CliErrorCode
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath

package_app = typer.Typer(
    name="package",
    help="Inspect and prepare reproducible project packages.",
    no_args_is_help=True,
)


@package_app.command("manifest")
def create_package_manifest(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    output_path: Annotated[
        str,
        typer.Argument(help="Project-relative JSON path for the package manifest."),
    ],
    package_id: Annotated[
        str,
        typer.Option("--package-id", help="Stable package identifier."),
    ] = "default",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the manifest without writing files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Create or plan one deterministic package manifest."""

    def action() -> dict[str, object]:
        try:
            service = PackageManifestService(ProjectFilesystem.discover(project))
            return service.create(
                RepositoryPath.parse(output_path),
                package_id=package_id,
                dry_run=dry_run,
            ).as_data()
        except PackageManifestConflictError as error:
            raise CliFailure(
                code=CliErrorCode.CONFLICT,
                message=str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except (PackageManifestInputError, PackageManifestError, ValidationError) as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

    run_command(
        context=context,
        command="package manifest",
        local_json=json_output,
        action=action,
        render_human=_render_human,
    )


def _render_human(console: Console, data: dict[str, object]) -> None:
    """Render concise manifest facts while retaining structured detail in JSON."""
    console.print("[bold]Package manifest[/bold]")
    console.print(f"State: {data['state']} | Dry run: {data['dry_run']}")
    console.print(f"Project: {data['project_id']} | Package: {data['package_id']}")
    console.print(f"Output: {data['output_path']}")
    table = Table("Category", "Count")
    table.add_row("Included files", str(data["included_file_count"]))
    table.add_row("Excluded paths", str(data["excluded_path_count"]))
    table.add_row("Missing items", str(data["missing_item_count"]))
    console.print(table)
    warnings = data.get("warnings")
    if isinstance(warnings, list) and warnings:
        console.print("Warnings:")
        for warning in warnings:
            console.print(f"- {warning}")


__all__ = ["create_package_manifest", "package_app"]
