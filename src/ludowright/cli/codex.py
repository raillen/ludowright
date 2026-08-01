"""CLI presentation for the project-local Codex skill lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from integrations.codex import (
    CodexSkillCompatibilityError,
    CodexSkillConflictError,
    CodexSkillDefinitionError,
    CodexSkillError,
    CodexSkillNotInstalledError,
    CodexSkillOperationError,
    CodexSkillResult,
    CodexSkillService,
)
from rich.console import Console

from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import CliErrorCode
from ludowright.infrastructure import ProjectFilesystem

codex_app = typer.Typer(
    name="codex",
    help="Install and inspect project-local Codex integrations.",
    no_args_is_help=True,
)
skill_app = typer.Typer(
    name="skill",
    help="Manage the project-local $ludowright skill.",
    no_args_is_help=True,
)
codex_app.add_typer(skill_app, name="skill")

SkillOperation = Callable[[CodexSkillService], CodexSkillResult]


@skill_app.command("install")
def install_skill(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Projeto LudoWright existente.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Planeja a instalação sem alterar arquivos."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Retorna uma resposta estável em JSON."),
    ] = False,
) -> None:
    """Install the packaged $ludowright skill into one project."""
    _run_skill_command(
        context=context,
        command="codex skill install",
        project=project,
        local_json=json_output,
        operation=lambda service: service.install(dry_run=dry_run),
    )


@skill_app.command("update")
def update_skill(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Projeto LudoWright existente.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Planeja a atualização sem alterar arquivos."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Retorna uma resposta estável em JSON."),
    ] = False,
) -> None:
    """Update an intact older $ludowright skill installation."""
    _run_skill_command(
        context=context,
        command="codex skill update",
        project=project,
        local_json=json_output,
        operation=lambda service: service.update(dry_run=dry_run),
    )


@skill_app.command("verify")
def verify_skill(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Projeto LudoWright existente.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Retorna uma resposta estável em JSON."),
    ] = False,
) -> None:
    """Verify skill identity, files, checksums, and version compatibility."""

    def operation(service: CodexSkillService) -> CodexSkillResult:
        result = service.verify()
        if not result.report.valid:
            raise CliFailure(
                code=CliErrorCode.CHECKS_FAILED,
                message=f"Codex skill verification failed: {result.report.state}.",
                exit_code=CliExitCode.CHECKS_FAILED,
                details={"state": result.report.state},
                data=result.as_data(),
            )
        return result

    _run_skill_command(
        context=context,
        command="codex skill verify",
        project=project,
        local_json=json_output,
        operation=operation,
    )


@skill_app.command("remove")
def remove_skill(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Projeto LudoWright existente.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Planeja a remoção sem alterar arquivos."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Retorna uma resposta estável em JSON."),
    ] = False,
) -> None:
    """Remove an intact $ludowright skill without touching unrelated files."""
    _run_skill_command(
        context=context,
        command="codex skill remove",
        project=project,
        local_json=json_output,
        operation=lambda service: service.remove(dry_run=dry_run),
    )


def _run_skill_command(
    *,
    context: typer.Context,
    command: str,
    project: Path,
    local_json: bool,
    operation: SkillOperation,
) -> None:
    def action() -> dict[str, object]:
        try:
            result = operation(CodexSkillService(ProjectFilesystem.discover(project)))
        except CodexSkillNotInstalledError as error:
            raise CliFailure(
                code=CliErrorCode.RESOURCE_NOT_FOUND,
                message=str(error),
                exit_code=CliExitCode.NOT_FOUND,
            ) from error
        except CodexSkillConflictError as error:
            raise CliFailure(
                code=CliErrorCode.CONFLICT,
                message=str(error),
                exit_code=CliExitCode.CONFLICT,
            ) from error
        except CodexSkillCompatibilityError as error:
            raise CliFailure(
                code=CliErrorCode.BLOCKED,
                message=str(error),
                exit_code=CliExitCode.BLOCKED,
            ) from error
        except CodexSkillDefinitionError as error:
            raise CliFailure(
                code=CliErrorCode.INTERNAL_ERROR,
                message=str(error),
                exit_code=CliExitCode.INTERNAL,
            ) from error
        except CodexSkillOperationError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error
        except CodexSkillError as error:
            raise CliFailure(
                code=CliErrorCode.INVALID_INPUT,
                message=str(error),
                exit_code=CliExitCode.VALIDATION,
            ) from error
        return result.as_data()

    run_command(
        context=context,
        command=command,
        local_json=local_json,
        action=action,
        render_human=_render_skill_human,
    )


def _render_skill_human(console: Console, data: dict[str, object]) -> None:
    """Render one compact Rich status without making prose part of the API."""
    state = data["state"]
    operation = data["operation"]
    console.print(f"[bold]Codex skill {operation}: {state}.[/bold]")
    console.print(f"Skill: ${data['skill_id']} v{data['skill_version']}")
    console.print(f"Path: {data['install_path']}")
    warnings = data.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")
