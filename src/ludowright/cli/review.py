"""CLI presentation for the visual review workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ludowright.application.visual_review import VisualReviewService
from ludowright.cli.runtime import run_command
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath


def review_command(
    context: typer.Context,
    input_path: Annotated[
        str,
        typer.Argument(help="Project-relative visual-review JSON contract."),
    ],
    project: Annotated[
        str,
        typer.Argument(help="Project directory containing the LudoWright marker."),
    ] = ".",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and plan without changing project files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return the published CLI response envelope."),
    ] = False,
) -> None:
    """Apply one visual review contract."""

    def action() -> dict[str, object]:
        filesystem = ProjectFilesystem.discover(Path(project))
        review_path = _project_relative_input(filesystem, input_path)
        result = VisualReviewService(filesystem).apply(review_path, dry_run=dry_run)
        return result.as_data()

    def render(console: Console, data: dict[str, object]) -> None:
        console.print("[bold]Visual review[/bold]")
        console.print(f"State: {data['state']}")
        console.print(f"Review: {data['review_id']}")
        console.print(f"Outcome: {data['outcome']}")
        references = data["reference_ids"]
        console.print(
            "References: " + ", ".join(str(reference) for reference in references)
            if isinstance(references, list)
            else "References:"
        )
        if data["approval_id"] is not None:
            console.print(f"Approval: {data['approval_id']}")
        console.print(f"Dependency graph revision: {data['graph_revision']}")
        impacts = data["impacts"]
        if isinstance(impacts, list):
            console.print(f"Impacts: {len(impacts)}")

    run_command(
        context=context,
        command="review",
        local_json=json_output,
        action=action,
        render_human=render,
    )


def _project_relative_input(filesystem: ProjectFilesystem, raw_path: str) -> RepositoryPath:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve(strict=False).relative_to(filesystem.root)
        except ValueError as error:
            raise ValueError("review input must be inside the selected project") from error
    return RepositoryPath.parse(candidate.as_posix())


__all__ = ["review_command"]
