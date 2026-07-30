"""Human and JSON presentation for documentation atlas generation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from ludowright.application import AtlasGenerationError, AtlasGenerator
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts.cli import CliErrorCode


def generate_atlas(
    context: typer.Context,
    root: Annotated[
        Path,
        typer.Argument(help="Repository root containing the docs directory."),
    ] = Path("."),
    metadata: Annotated[
        str,
        typer.Option("--metadata", help="Repository-relative ATLAS metadata JSON path."),
    ] = "docs/atlas.json",
    docs_directory: Annotated[
        str,
        typer.Option("--docs-directory", help="Repository-relative Markdown directory."),
    ] = "docs",
    check: Annotated[
        bool,
        typer.Option("--check", help="Fail when broken links or orphan documents are found."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Generate a deterministic documentation index and integrity report."""

    def action() -> dict[str, object]:
        try:
            generation = AtlasGenerator(
                root,
                docs_directory=docs_directory,
                metadata_path=metadata,
            ).generate()
        except AtlasGenerationError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error

        data = generation.report.model_dump(mode="json")
        data.update(
            {
                "markdown": generation.markdown,
                "valid": generation.valid,
            }
        )
        if check and not generation.valid:
            raise CliFailure(
                code=CliErrorCode.CHECKS_FAILED,
                message="ATLAS integrity checks failed.",
                exit_code=CliExitCode.CHECKS_FAILED,
                details={
                    "broken_links": len(generation.report.broken_links),
                    "orphan_documents": len(generation.report.orphan_documents),
                },
                data=data,
            )
        return data

    run_command(
        context=context,
        command="atlas",
        local_json=json_output,
        action=action,
        render_human=_render_human,
    )


def _render_human(console: Console, data: dict[str, object]) -> None:
    documents = data.get("documents")
    links = data.get("links")
    console.print("[bold]Documentation Atlas[/bold]")
    console.print(f"Documents: {len(documents) if isinstance(documents, list) else 0}")
    console.print(f"Links: {len(links) if isinstance(links, list) else 0}")
    console.print(f"Broken links: {_count(data.get('broken_links'))}")
    console.print(f"Orphan documents: {_count(data.get('orphan_documents'))}")
    if data["valid"]:
        console.print("[green]ATLAS integrity: valid[/green]")
    else:
        console.print("[bold red]ATLAS integrity: invalid[/bold red]")
    console.print(Markdown(str(data["markdown"])))


def _count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0
