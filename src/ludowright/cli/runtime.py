"""Shared output, errors, settings, and command execution for the CLI."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import IntEnum

import typer
from rich.console import Console

from ludowright import __version__
from ludowright.application.asset_registry import (
    AssetRegistryError,
    AssetRegistryNotFoundError,
    AssetRegistryRollbackError,
)
from ludowright.application.asset_workbook import AssetWorkbookError
from ludowright.application.document_refresh import DocumentRefreshError
from ludowright.application.documentation_audit import DocumentationAuditError
from ludowright.application.image_normalization import (
    ImageNormalizationConflictError,
    ImageNormalizationRollbackError,
)
from ludowright.application.package_manifest import (
    PackageManifestConflictError,
    PackageManifestError,
    PackageManifestInputError,
)
from ludowright.application.technical_sheets import (
    TechnicalSheetConflictError,
    TechnicalSheetError,
    TechnicalSheetRequestError,
    TechnicalSheetRollbackError,
)
from ludowright.application.visual_review import (
    VisualReviewConflictError,
    VisualReviewError,
    VisualReviewRollbackError,
    VisualReviewValidationError,
)
from ludowright.contracts.cli import (
    CliErrorCode,
    CliErrorContract,
    CliResponseContract,
)
from ludowright.domain import DomainValidationError
from ludowright.infrastructure import (
    CorruptEventLogError,
    EventLogError,
    ImageNormalizationError,
    ImageNormalizationValidationError,
    OdsWorkbookConflictError,
    OdsWorkbookError,
    ProjectFilesystemError,
    ProjectLockTimeoutError,
    ProjectRootNotFoundError,
    StateStoreCorruptionError,
    StructuredDocumentConflictError,
    StructuredDocumentParseError,
    UnsafeProjectPathError,
)


class CliExitCode(IntEnum):
    """Stable process exit codes for parsed LudoWright commands."""

    SUCCESS = 0
    CHECKS_FAILED = 1
    USAGE = 2
    NOT_FOUND = 3
    VALIDATION = 4
    CONFLICT = 5
    CORRUPT_STATE = 6
    BLOCKED = 7
    INTERNAL = 70


@dataclass(frozen=True, slots=True)
class CliSettings:
    """Global presentation settings inherited by subcommands."""

    json_output: bool = False
    no_color: bool = False


class CliFailure(RuntimeError):
    """Expected command failure that can be rendered without a traceback."""

    def __init__(
        self,
        code: CliErrorCode,
        message: str,
        *,
        exit_code: CliExitCode,
        details: Mapping[str, object] | None = None,
        data: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = dict(details or {})
        self.data = dict(data or {})


CommandData = dict[str, object]
DataFactory = Callable[[], CommandData]
HumanRenderer = Callable[[Console, CommandData], None]


def settings_from_context(context: typer.Context) -> CliSettings:
    """Return root CLI settings from a command or subcommand context."""
    root = context.find_root()
    return root.obj if isinstance(root.obj, CliSettings) else CliSettings()


def json_requested(context: typer.Context, local_json: bool) -> bool:
    """Combine the global and command-local JSON switches."""
    return local_json or settings_from_context(context).json_output


def command_console(context: typer.Context, *, stderr: bool = False) -> Console:
    """Create a Rich console that follows the global color policy."""
    settings = settings_from_context(context)
    return Console(stderr=stderr, no_color=settings.no_color)


def run_command(
    *,
    context: typer.Context,
    command: str,
    local_json: bool,
    action: DataFactory,
    render_human: HumanRenderer,
) -> None:
    """Execute one command and render a stable success or expected failure."""
    json_output = json_requested(context, local_json)
    try:
        data = action()
    except CliFailure as expected_failure:
        emit_failure(
            command=command,
            failure=expected_failure,
            json_output=json_output,
            context=context,
        )
    except Exception as error:
        mapped_failure = _known_failure(error)
        if mapped_failure is None:
            raise
        emit_failure(
            command=command,
            failure=mapped_failure,
            json_output=json_output,
            context=context,
        )
    else:
        if json_output:
            response = CliResponseContract.success(
                command=command,
                data=data,
                ludowright_version=__version__,
            )
            typer.echo(canonical_json(response))
        else:
            render_human(command_console(context), data)


def emit_failure(
    *,
    command: str,
    failure: CliFailure,
    json_output: bool,
    context: typer.Context,
) -> None:
    """Render one expected error and terminate with its stable exit code."""
    if json_output:
        response = CliResponseContract.failure(
            command=command,
            data=failure.data,
            error=CliErrorContract(
                code=failure.code,
                message=failure.message,
                details=failure.details,
            ),
            ludowright_version=__version__,
        )
        typer.echo(canonical_json(response))
    else:
        console = command_console(context, stderr=True)
        console.print(f"[bold red]Error:[/bold red] {failure.message}")
        if failure.details:
            for key, value in sorted(failure.details.items()):
                console.print(f"  [dim]{key}:[/dim] {value}")
    raise typer.Exit(code=int(failure.exit_code))


def canonical_json(response: CliResponseContract) -> str:
    """Serialize a response as deterministic compact UTF-8 JSON."""
    return json.dumps(
        response.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _known_failure(error: Exception) -> CliFailure | None:
    if isinstance(error, ProjectRootNotFoundError):
        return CliFailure(
            CliErrorCode.PROJECT_NOT_FOUND,
            str(error),
            exit_code=CliExitCode.NOT_FOUND,
        )
    if isinstance(error, AssetRegistryNotFoundError):
        return CliFailure(
            CliErrorCode.RESOURCE_NOT_FOUND,
            str(error),
            exit_code=CliExitCode.NOT_FOUND,
        )
    if isinstance(error, UnsafeProjectPathError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, ProjectLockTimeoutError):
        return CliFailure(
            CliErrorCode.BLOCKED,
            str(error),
            exit_code=CliExitCode.BLOCKED,
        )
    if isinstance(error, OdsWorkbookConflictError):
        return CliFailure(
            CliErrorCode.CONFLICT,
            str(error),
            exit_code=CliExitCode.CONFLICT,
        )
    if isinstance(error, ProjectFilesystemError):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, StructuredDocumentConflictError):
        return CliFailure(
            CliErrorCode.CONFLICT,
            str(error),
            exit_code=CliExitCode.CONFLICT,
        )
    if isinstance(error, VisualReviewConflictError):
        return CliFailure(
            CliErrorCode.CONFLICT,
            str(error),
            exit_code=CliExitCode.CONFLICT,
        )
    if isinstance(error, VisualReviewRollbackError):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, VisualReviewValidationError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, VisualReviewError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, ImageNormalizationConflictError):
        return CliFailure(
            CliErrorCode.CONFLICT,
            str(error),
            exit_code=CliExitCode.CONFLICT,
        )
    if isinstance(error, ImageNormalizationRollbackError):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, ImageNormalizationValidationError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, ImageNormalizationError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, PackageManifestConflictError):
        return CliFailure(
            CliErrorCode.CONFLICT,
            str(error),
            exit_code=CliExitCode.CONFLICT,
        )
    if isinstance(error, PackageManifestInputError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, PackageManifestError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, TechnicalSheetConflictError):
        return CliFailure(
            CliErrorCode.CONFLICT,
            str(error),
            exit_code=CliExitCode.CONFLICT,
        )
    if isinstance(error, TechnicalSheetRollbackError):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, (TechnicalSheetRequestError, TechnicalSheetError)):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(
        error,
        (
            CorruptEventLogError,
            EventLogError,
            StateStoreCorruptionError,
            StructuredDocumentParseError,
        ),
    ):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, DomainValidationError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, (AssetWorkbookError, OdsWorkbookError)):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, DocumentRefreshError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    if isinstance(error, DocumentationAuditError):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, AssetRegistryRollbackError):
        return CliFailure(
            CliErrorCode.CORRUPT_STATE,
            str(error),
            exit_code=CliExitCode.CORRUPT_STATE,
        )
    if isinstance(error, AssetRegistryError):
        return CliFailure(
            CliErrorCode.INVALID_INPUT,
            str(error),
            exit_code=CliExitCode.VALIDATION,
        )
    return None
