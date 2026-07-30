"""CLI presentation for canonical asset registry operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ludowright.application import AssetRegistryResult, AssetRegistryService
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import CliErrorCode
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath

assets_app = typer.Typer(
    name="assets",
    help="Create and maintain the canonical asset registry.",
    no_args_is_help=True,
)


@assets_app.command("create")
def create_asset(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    input_path: Annotated[
        str,
        typer.Option("--input", "-i", help="Project-relative asset JSON or YAML path."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the operation without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Create one asset from a validated asset contract document."""
    _run(
        context=context,
        command="assets create",
        project=project,
        local_json=json_output,
        operation=lambda service: service.create(_path(input_path), dry_run=dry_run),
    )


@assets_app.command("update")
def update_asset(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    asset_id: Annotated[str, typer.Argument(help="Existing asset ID.")],
    input_path: Annotated[
        str,
        typer.Option("--input", "-i", help="Project-relative replacement asset path."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the operation without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Replace one asset without changing its ID."""
    _run(
        context=context,
        command="assets update",
        project=project,
        local_json=json_output,
        operation=lambda service: service.update(
            asset_id,
            _path(input_path),
            dry_run=dry_run,
        ),
    )


@assets_app.command("list")
def list_assets(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """List all assets in deterministic ID order."""
    _run(
        context=context,
        command="assets list",
        project=project,
        local_json=json_output,
        operation=lambda service: service.list_assets(),
    )


@assets_app.command("inspect")
def inspect_asset(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    asset_id: Annotated[str, typer.Argument(help="Asset ID to inspect.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Inspect one asset from the canonical registry."""
    _run(
        context=context,
        command="assets inspect",
        project=project,
        local_json=json_output,
        operation=lambda service: service.inspect(asset_id),
    )


@assets_app.command("archive")
def archive_asset(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    asset_id: Annotated[str, typer.Argument(help="Asset ID to archive.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the operation without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Archive a completed or cancelled asset without deleting its record."""
    _run(
        context=context,
        command="assets archive",
        project=project,
        local_json=json_output,
        operation=lambda service: service.archive(asset_id, dry_run=dry_run),
    )


@assets_app.command("validate")
def validate_assets(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    asset_id: Annotated[
        str | None,
        typer.Argument(help="Optional asset ID; omit to validate the complete registry."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Validate registry contracts, taxonomy, and asset domain invariants."""
    _run(
        context=context,
        command="assets validate",
        project=project,
        local_json=json_output,
        operation=lambda service: service.validate(asset_id),
    )


@assets_app.command("import")
def import_assets(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    input_path: Annotated[
        str,
        typer.Argument(help="Project-relative asset-registry JSON or YAML path."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the merge without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Merge a batch asset registry without replacing existing IDs."""
    _run(
        context=context,
        command="assets import",
        project=project,
        local_json=json_output,
        operation=lambda service: service.import_registry(_path(input_path), dry_run=dry_run),
    )


@assets_app.command("export")
def export_assets(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    output_path: Annotated[
        str,
        typer.Argument(help="New project-relative JSON or YAML export path."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the export without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Export a deterministic batch registry without overwriting a file."""
    _run(
        context=context,
        command="assets export",
        project=project,
        local_json=json_output,
        operation=lambda service: service.export_registry(_path(output_path), dry_run=dry_run),
    )


def _run(
    *,
    context: typer.Context,
    command: str,
    project: Path,
    local_json: bool,
    operation: Callable[[AssetRegistryService], AssetRegistryResult],
) -> None:
    def action() -> dict[str, object]:
        try:
            service = AssetRegistryService(ProjectFilesystem.discover(project))
            return operation(service).as_data()
        except (FileNotFoundError, ValidationError) as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

    run_command(
        context=context,
        command=command,
        local_json=local_json,
        action=action,
        render_human=_render_human,
    )


def _path(value: str) -> RepositoryPath:
    return RepositoryPath.parse(value)


def _render_human(console: Console, data: dict[str, object]) -> None:
    console.print("[bold]Asset registry[/bold]")
    console.print(f"Operation: {data['operation']}")
    console.print(f"State: {data['state']} | Dry run: {data['dry_run']}")
    console.print(f"Registry: {data['registry_path']} (v{data['registry_version']})")
    if data.get("output_path") is not None:
        console.print(f"Output: {data['output_path']}")
    assets = data.get("assets")
    if not isinstance(assets, list):
        return
    table = Table("ID", "Name", "Family", "Status", "Priority")
    for value in assets:
        if isinstance(value, dict):
            table.add_row(
                str(value.get("id", "")),
                str(value.get("name", "")),
                str(value.get("family", "")),
                str(value.get("status", "")),
                str(value.get("priority", "")),
            )
    console.print(table)
