"""CLI presentation for local release verification."""

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
    ReleaseVerificationConflictError,
    ReleaseVerificationCorruptError,
    ReleaseVerificationError,
    ReleaseVerificationInputError,
    ReleaseVerificationService,
)
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import CliErrorCode
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath

release_app = typer.Typer(
    name="release",
    help="Verify local package releases without publishing them.",
    no_args_is_help=True,
)


@release_app.command("verify")
def verify_release(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")],
    release_directory: Annotated[
        str,
        typer.Argument(help="Project-relative directory containing the package release."),
    ],
    package_id: Annotated[
        str | None,
        typer.Option(
            "--package-id",
            help="Package ID when the release directory has several packages.",
        ),
    ] = None,
    allow_warnings: Annotated[
        bool,
        typer.Option("--allow-warnings", help="Allow audit warnings in the release result."),
    ] = False,
    check: Annotated[
        bool,
        typer.Option("--check", help="Fail when release verification is not valid."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Prepare the verification without writing a manifest."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Verify a package archive and prepare its checksum manifest."""

    def action() -> dict[str, object]:
        try:
            result = ReleaseVerificationService(ProjectFilesystem.discover(project)).verify(
                RepositoryPath.parse(release_directory),
                package_id=package_id,
                allow_warnings=allow_warnings,
                dry_run=dry_run,
            )
        except (ProjectAuditConflictError, ReleaseVerificationConflictError) as error:
            raise CliFailure(
                code=CliErrorCode.CONFLICT,
                message=str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except (ProjectAuditCorruptError, ReleaseVerificationCorruptError) as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error
        except (
            ProjectAuditError,
            ReleaseVerificationInputError,
            ReleaseVerificationError,
        ) as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error

        data = result.as_data()
        if check and not result.report.valid:
            raise CliFailure(
                code=CliErrorCode.CHECKS_FAILED,
                message="release verification found unresolved gates",
                exit_code=CliExitCode.CHECKS_FAILED,
                data=data,
            )
        return data

    run_command(
        context=context,
        command="release verify",
        local_json=json_output,
        action=action,
        render_human=_render_human,
    )


def _render_human(console: Console, data: dict[str, object]) -> None:
    """Render stable gate and checksum facts for interactive use."""
    console.print("[bold]LudoWright release verification[/bold]")
    console.print(
        f"Project: {data['project_name']} ({data['project_id']}) | Package: {data['package_id']}"
    )
    console.print(
        f"State: {data['state']} | Warning policy: {data['warning_policy']} | "
        f"Dry run: {data['dry_run']}"
    )
    console.print(f"Release manifest: {data['release_manifest_path']}")

    gates = data.get("gates")
    if isinstance(gates, list):
        table = Table("Gate", "State", "Detail")
        for gate in gates:
            if isinstance(gate, dict):
                table.add_row(str(gate["code"]), str(gate["state"]), str(gate["detail"]))
        console.print(table)

    manifest = data.get("release_manifest")
    if isinstance(manifest, dict):
        summary = data.get("summary")
        if isinstance(summary, dict):
            console.print(
                f"Artifacts: {summary['artifact_count']} | "
                f"Archive members: {summary['archive_member_count']} | "
                f"Archive bytes: {summary['archive_size_bytes']}"
            )
        console.print(f"Manifest state: {data['manifest_state']}")
    else:
        console.print("No checksum manifest was prepared.")


__all__ = ["release_app", "verify_release"]
