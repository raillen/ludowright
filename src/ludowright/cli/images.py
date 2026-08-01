"""CLI presentation for image normalization."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ludowright.application.image_normalization import ImageNormalizationService
from ludowright.cli.runtime import run_command
from ludowright.infrastructure import ImageNormalizationOptions, ProjectFilesystem, RepositoryPath

images_app = typer.Typer(
    name="images",
    help="Normalize visual artifacts into deterministic PNG outputs.",
    no_args_is_help=True,
)


@images_app.command("normalize")
def normalize_command(
    context: typer.Context,
    input_path: Annotated[str, typer.Argument(help="Project-relative source image.")],
    output_directory: Annotated[
        str,
        typer.Argument(help="Project-relative directory for normalized outputs."),
    ],
    project: Annotated[
        str,
        typer.Argument(help="Project directory containing the LudoWright marker."),
    ] = ".",
    width: Annotated[
        int,
        typer.Option("--width", min=64, max=16_384, help="Normalized canvas width."),
    ] = 1_024,
    height: Annotated[
        int,
        typer.Option("--height", min=64, max=16_384, help="Normalized canvas height."),
    ] = 1_024,
    padding: Annotated[
        int,
        typer.Option("--padding", min=0, help="Minimum canvas padding in pixels."),
    ] = 64,
    thumbnail_size: Annotated[
        int,
        typer.Option("--thumbnail-size", min=16, max=4_096, help="Thumbnail side length."),
    ] = 256,
    neutral_background: Annotated[
        str,
        typer.Option("--neutral-background", help="Uppercase #RRGGBB neutral background."),
    ] = "#F2F2F2",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan and validate without writing files."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return the published CLI response envelope."),
    ] = False,
) -> None:
    """Create normalized, neutral, thumbnail, and alignment-guide PNGs."""

    def action() -> dict[str, object]:
        filesystem = ProjectFilesystem.discover(Path(project))
        source = _project_relative_path(filesystem, input_path)
        output = _project_relative_path(filesystem, output_directory)
        result = ImageNormalizationService(filesystem).normalize(
            source,
            output,
            options=ImageNormalizationOptions(
                canvas_width=width,
                canvas_height=height,
                padding=padding,
                thumbnail_size=thumbnail_size,
                neutral_background=neutral_background,
            ),
            dry_run=dry_run,
        )
        return result.as_data()

    def render(console: Console, data: dict[str, object]) -> None:
        console.print("[bold]Image normalization[/bold]")
        console.print(f"State: {data['state']}")
        console.print(f"Source: {data['source_path']}")
        console.print(f"Report: {data['report_path']}")
        outputs = data["output_paths"]
        if isinstance(outputs, list):
            console.print(f"Outputs: {len(outputs)}")
            for output in outputs:
                console.print(f"  {output}")

    run_command(
        context=context,
        command="images normalize",
        local_json=json_output,
        action=action,
        render_human=render,
    )


def _project_relative_path(filesystem: ProjectFilesystem, raw_path: str) -> RepositoryPath:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve(strict=False).relative_to(filesystem.root)
        except ValueError as error:
            raise ValueError("image path must be inside the selected project") from error
    return RepositoryPath.parse(candidate.as_posix())


__all__ = ["images_app", "normalize_command"]
