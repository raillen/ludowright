"""CLI presentation for incremental document refresh."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ludowright.application import (
    DocumentRefreshError,
    DocumentRefreshRequest,
    DocumentRefreshRollbackError,
    DocumentRefreshService,
)
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import (
    CliErrorCode,
    DocumentRefreshRequestContract,
)
from ludowright.infrastructure import JsonDocumentRepository, ProjectFilesystem, RepositoryPath

documents_app = typer.Typer(
    name="documents",
    help="Plan and refresh generated project documents.",
    no_args_is_help=True,
)


@documents_app.command("refresh")
def refresh_documents(
    context: typer.Context,
    request: Annotated[
        str,
        typer.Argument(help="Project-relative document refresh request JSON path."),
    ],
    project: Annotated[
        Path,
        typer.Argument(help="Project directory or a path below it."),
    ] = Path("."),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan the refresh without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Refresh only documents whose sources or generated output are stale."""

    def action() -> dict[str, object]:
        try:
            filesystem = ProjectFilesystem.discover(project)
            request_path = RepositoryPath.parse(request)
            snapshot = JsonDocumentRepository(
                filesystem,
                request_path,
                DocumentRefreshRequestContract,
            ).load()
            result = DocumentRefreshService(filesystem).refresh(
                [DocumentRefreshRequest.from_contract(snapshot.value)],
                dry_run=dry_run,
            )
            return result.as_data()
        except DocumentRefreshRollbackError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error
        except (DocumentRefreshError, ValidationError, FileNotFoundError) as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

    run_command(
        context=context,
        command="documents refresh",
        local_json=json_output,
        action=action,
        render_human=_render_human,
    )


def _render_human(console: Console, data: dict[str, object]) -> None:
    console.print("[bold]Document refresh[/bold]")
    console.print(f"Dry run: {data['dry_run']}")
    affected = data.get("affected_documents")
    refreshed = data.get("refreshed_documents")
    console.print(f"Affected: {len(affected) if isinstance(affected, list) else 0}")
    console.print(f"Refreshed: {len(refreshed) if isinstance(refreshed, list) else 0}")
    plans = data.get("plans")
    if not isinstance(plans, list):
        return
    table = Table("Document", "Status", "Sources", "Reasons")
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        changed_sources = plan.get("changed_sources")
        reasons = plan.get("reasons")
        table.add_row(
            str(plan.get("document_id", "")),
            str(plan.get("status", "")),
            ", ".join(str(item) for item in changed_sources)
            if isinstance(changed_sources, list)
            else "",
            ", ".join(str(item) for item in reasons) if isinstance(reasons, list) else "",
        )
    console.print(table)
