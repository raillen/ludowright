"""CLI presentation for deterministic package manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ludowright.application import (
    PackageBuilderConflictError,
    PackageBuilderError,
    PackageBuilderInputError,
    PackageBuilderRollbackError,
    PackageBuilderService,
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


@package_app.command("build")
def build_package(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    manifest_path: Annotated[
        str,
        typer.Argument(help="Project-relative package-manifest JSON path."),
    ],
    release_directory: Annotated[
        str,
        typer.Argument(help="Project-relative directory for the ZIP release."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the release without writing files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Build a reproducible ZIP and package index from a manifest."""

    def action() -> dict[str, object]:
        try:
            service = PackageBuilderService(ProjectFilesystem.discover(project))
            return service.build(
                RepositoryPath.parse(manifest_path),
                RepositoryPath.parse(release_directory),
                dry_run=dry_run,
            ).as_data()
        except PackageBuilderConflictError as error:
            raise CliFailure(
                code=CliErrorCode.CONFLICT,
                message=str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except PackageBuilderRollbackError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error
        except (PackageBuilderInputError, PackageBuilderError, ValidationError) as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

    run_command(
        context=context,
        command="package build",
        local_json=json_output,
        action=action,
        render_human=_render_human,
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
    title = "Package build" if data["kind"] == "package-build-report" else "Package manifest"
    console.print(f"[bold]{title}[/bold]")
    console.print(f"State: {data['state']} | Dry run: {data['dry_run']}")
    console.print(f"Project: {data['project_id']} | Package: {data['package_id']}")
    if "output_path" in data:
        console.print(f"Output: {data['output_path']}")
    else:
        console.print(f"Archive: {data['archive_path']}")
        console.print(f"Index: {data['index_path']}")
        console.print(f"Archive SHA-256: {data['archive_sha256']}")
        console.print(f"Archive bytes: {data['archive_size_bytes']}")
    table = Table("Category", "Count")
    if "included_file_count" in data:
        table.add_row("Included files", str(data["included_file_count"]))
        table.add_row("Excluded paths", str(data["excluded_path_count"]))
        table.add_row("Missing items", str(data["missing_item_count"]))
    else:
        index = data["index"]
        if isinstance(index, dict):
            table.add_row("Archive members", str(index["archive_member_count"]))
            table.add_row("Payload bytes", str(index["payload_size_bytes"]))
    console.print(table)
    warnings = data.get("warnings")
    if isinstance(warnings, list) and warnings:
        console.print("Warnings:")
        for warning in warnings:
            console.print(f"- {warning}")


__all__ = ["create_package_manifest", "package_app"]
