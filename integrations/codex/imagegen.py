"""Safe execution boundary for one ready visual job through ImageGen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from ludowright.contracts import (
    GenerationReceiptContract,
    ImageGenOperationContract,
    ImageGenOutputContract,
)
from ludowright.contracts.visual import ReferenceTargetContract
from ludowright.domain import CompiledPrompt, VisualJob
from ludowright.infrastructure import (
    GenerationReceiptAttempt,
    GenerationReceiptRepository,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StructuredDocumentConflictError,
    ValidatedGenerationOutput,
    validate_png_payload,
)

IMAGEGEN_LOCK_NAME = "imagegen-execution"
IMAGEGEN_OPERATION_FILENAME = "operation.json"
IMAGEGEN_MAX_OPERATION_BYTES = 2_000_000
ImageGenExecutionState = Literal["planned", "executed"]


class ImageGenExecutionError(RuntimeError):
    """Base error for provider-bound ImageGen execution."""


class ImageGenConflictError(ImageGenExecutionError):
    """Raised when an operation or output would be overwritten."""


class ImageGenProviderError(ImageGenExecutionError):
    """Raised when a provider fails or returns an invalid image payload."""


class ImageGenRollbackError(ImageGenExecutionError):
    """Raised when execution failed and cleanup could not restore the target."""


class ImageGenReceiptError(ImageGenExecutionError):
    """Raised when a terminal execution result could not be persisted."""


@dataclass(frozen=True, slots=True)
class ImageGenProviderMetadata:
    """Provider identity supplied by the host when it is available."""

    provider: str = "unspecified"
    model: str = "unspecified"
    tool: str | None = None

    def __post_init__(self) -> None:
        for label, value in (("provider", self.provider), ("model", self.model)):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"ImageGen {label} metadata must be non-empty text")
            if len(value) > 120:
                raise ValueError(f"ImageGen {label} metadata cannot exceed 120 characters")
        if self.tool is not None and (
            not isinstance(self.tool, str) or not self.tool or self.tool != self.tool.strip()
        ):
            raise ValueError("ImageGen tool metadata must be non-empty text when provided")
        if self.tool is not None and len(self.tool) > 120:
            raise ValueError("ImageGen tool metadata cannot exceed 120 characters")


class ImageGenProvider(Protocol):
    """Minimal provider boundary owned by the Codex integration."""

    def generate(self, request: ImageGenRequest) -> bytes:
        """Generate exactly one PNG for the requested output view."""


@dataclass(frozen=True, slots=True)
class ImageGenRequest:
    """One provider call containing one operation and one output view."""

    operation: ImageGenOperationContract
    output: ImageGenOutputContract


@dataclass(frozen=True, slots=True)
class ImageGenOperation:
    """Prepared immutable operation and its project-relative manifest path."""

    contract: ImageGenOperationContract
    manifest_path: RepositoryPath

    def __post_init__(self) -> None:
        if not isinstance(self.contract, ImageGenOperationContract):
            raise TypeError("ImageGen operation requires its published contract")
        if not isinstance(self.manifest_path, RepositoryPath):
            raise TypeError("ImageGen operation requires a RepositoryPath manifest")
        expected_manifest = RepositoryPath(self.contract.output_directory).child(
            IMAGEGEN_OPERATION_FILENAME
        )
        if self.manifest_path != expected_manifest:
            raise ImageGenExecutionError(
                "ImageGen manifest path must be inside the operation output directory"
            )

    @property
    def output_paths(self) -> tuple[RepositoryPath, ...]:
        """Return output paths in deterministic view order."""
        return tuple(RepositoryPath(output.path) for output in self.contract.outputs)


@dataclass(frozen=True, slots=True)
class ImageGenExecutionResult:
    """Stable result of planning or completing one ImageGen operation."""

    operation: ImageGenOperation
    state: ImageGenExecutionState
    dry_run: bool
    receipt: GenerationReceiptContract | None = None

    def as_data(self) -> dict[str, object]:
        """Return JSON-compatible execution data without provider payloads."""
        return {
            "dry_run": self.dry_run,
            "manifest_path": self.operation.manifest_path.value,
            "operation": self.operation.contract.model_dump(mode="json"),
            "output_paths": [path.value for path in self.operation.output_paths],
            "state": self.state,
            "receipt": self.receipt.model_dump(mode="json") if self.receipt is not None else None,
        }


class ImageGenExecutor:
    """Prepare and execute one immutable visual job through an injected provider."""

    def prepare(
        self,
        job: VisualJob,
        prompt: CompiledPrompt,
        output_directory: RepositoryPath,
    ) -> ImageGenOperation:
        """Translate one matching job and compiled prompt into a safe operation."""
        if not isinstance(job, VisualJob):
            raise TypeError("ImageGen execution requires a VisualJob")
        if not isinstance(prompt, CompiledPrompt):
            raise TypeError("ImageGen execution requires a CompiledPrompt")
        if not isinstance(output_directory, RepositoryPath):
            raise TypeError("ImageGen output directory requires RepositoryPath")
        if prompt.target != job.target:
            raise ImageGenExecutionError("compiled prompt target must match the visual job target")

        job_reference_ids = tuple(sorted(item.value for item in job.input_reference_ids))
        prompt_reference_ids = tuple(sorted(item.id.value for item in prompt.references))
        if prompt_reference_ids != job_reference_ids:
            raise ImageGenExecutionError(
                "compiled prompt references must exactly match the visual job inputs"
            )

        outputs = tuple(
            ImageGenOutputContract(
                index=index,
                role=role,
                path=output_directory.child(f"{index:02d}-{role.value}.png").value,
            )
            for index, role in enumerate(job.output_roles, start=1)
        )
        contract = ImageGenOperationContract.create(
            job_id=job.id.value,
            target=ReferenceTargetContract.from_domain(job.target),
            profile_version=job.profile_version.value,
            job_request_revision=job.request_revision.value,
            prompt_hash=prompt.prompt_hash,
            positive_prompt=prompt.positive_prompt,
            negative_prompt=prompt.negative_prompt,
            input_reference_ids=job_reference_ids,
            output_directory=output_directory.value,
            outputs=outputs,
        )
        return ImageGenOperation(
            contract=contract,
            manifest_path=output_directory.child(IMAGEGEN_OPERATION_FILENAME),
        )

    def execute(
        self,
        filesystem: ProjectFilesystem,
        operation: ImageGenOperation,
        provider: ImageGenProvider,
        *,
        dry_run: bool = False,
        timeout: float = 5.0,
        metadata: ImageGenProviderMetadata | None = None,
        clock: Callable[[], datetime] | None = None,
        receipt_repository: GenerationReceiptRepository | None = None,
    ) -> ImageGenExecutionResult:
        """Execute one PNG request per view and persist its terminal receipt."""
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("ImageGen execution requires ProjectFilesystem")
        if not isinstance(operation, ImageGenOperation):
            raise TypeError("ImageGen execution requires a prepared operation")
        if dry_run:
            return ImageGenExecutionResult(operation=operation, state="planned", dry_run=True)
        if not hasattr(provider, "generate") or not callable(provider.generate):
            raise TypeError("ImageGen execution requires a provider with generate()")
        if metadata is not None and not isinstance(metadata, ImageGenProviderMetadata):
            raise TypeError("ImageGen metadata requires ImageGenProviderMetadata")
        metadata = metadata or ImageGenProviderMetadata()
        if clock is not None and not callable(clock):
            raise TypeError("ImageGen clock must be callable")
        clock = clock or (lambda: datetime.now(UTC))
        receipt_repository = receipt_repository or GenerationReceiptRepository()

        created_directories: tuple[RepositoryPath, ...] = ()
        created_outputs: list[RepositoryPath] = []
        validated_outputs: list[ValidatedGenerationOutput] = []
        manifest_created = False
        attempt: GenerationReceiptAttempt | None = None
        started_at: str | None = None
        receipt: GenerationReceiptContract | None = None
        with filesystem.lock(IMAGEGEN_LOCK_NAME, timeout=timeout):
            try:
                created_directories = _ensure_output_directory(
                    filesystem,
                    RepositoryPath(operation.contract.output_directory),
                )
                _assert_missing(filesystem, operation.manifest_path)
                for output_path in operation.output_paths:
                    _assert_missing(filesystem, output_path)

                repository = JsonDocumentRepository(
                    filesystem,
                    operation.manifest_path,
                    ImageGenOperationContract,
                    max_bytes=IMAGEGEN_MAX_OPERATION_BYTES,
                )
                try:
                    repository.create(operation.contract)
                except StructuredDocumentConflictError as error:
                    raise ImageGenConflictError(
                        f"ImageGen operation already exists: {operation.manifest_path}"
                    ) from error
                manifest_created = True
                started_at = _format_timestamp(clock())
                attempt = receipt_repository.next_attempt(filesystem, operation.contract)

                for output in operation.contract.outputs:
                    request = ImageGenRequest(operation=operation.contract, output=output)
                    try:
                        payload = provider.generate(request)
                        validation = validate_png_payload(payload)
                    except Exception as error:
                        raise ImageGenProviderError(
                            f"ImageGen provider failed for output {output.path}"
                        ) from error
                    output_path = RepositoryPath(output.path)
                    _assert_missing(filesystem, output_path)
                    filesystem.write_bytes(output_path, payload)
                    created_outputs.append(output_path)
                    validated_outputs.append(
                        ValidatedGenerationOutput(
                            index=output.index,
                            role=output.role,
                            path=output_path,
                            validation=validation,
                        )
                    )

                if attempt is None or started_at is None:
                    raise ImageGenExecutionError("ImageGen receipt attempt was not prepared")
                receipt = receipt_repository.record_success(
                    filesystem,
                    operation.contract,
                    attempt,
                    provider=metadata.provider,
                    model=metadata.model,
                    tool=metadata.tool,
                    started_at=started_at,
                    completed_at=_format_timestamp(clock()),
                    outputs=tuple(validated_outputs),
                )
            except Exception as error:
                rollback_error = _rollback(
                    filesystem,
                    manifest_path=operation.manifest_path if manifest_created else None,
                    output_paths=tuple(created_outputs),
                    directories=created_directories,
                )
                receipt_error: Exception | None = None
                if attempt is not None and receipt is None and started_at is not None:
                    try:
                        receipt = receipt_repository.record_failure(
                            filesystem,
                            operation.contract,
                            attempt,
                            provider=metadata.provider,
                            model=metadata.model,
                            tool=metadata.tool,
                            started_at=started_at,
                            completed_at=_failure_timestamp(clock),
                            failure_note=_failure_note(error),
                        )
                    except Exception as persistence_error:
                        receipt_error = persistence_error
                if rollback_error is not None:
                    raise ImageGenRollbackError(
                        "ImageGen execution failed and cleanup was incomplete"
                    ) from error
                if receipt_error is not None:
                    raise ImageGenReceiptError(
                        "ImageGen execution failed and its receipt could not be persisted"
                    ) from error
                raise

        return ImageGenExecutionResult(
            operation=operation,
            state="executed",
            dry_run=False,
            receipt=receipt,
        )


def _ensure_output_directory(
    filesystem: ProjectFilesystem,
    directory: RepositoryPath,
) -> tuple[RepositoryPath, ...]:
    missing: list[RepositoryPath] = []
    current = RepositoryPath(directory.parts[0])
    if not filesystem.directory_exists(current):
        missing.append(current)
    for segment in directory.parts[1:]:
        current = current.child(segment)
        if not filesystem.directory_exists(current):
            missing.append(current)
    filesystem.ensure_directory(directory)
    return tuple(missing)


def _assert_missing(filesystem: ProjectFilesystem, path: RepositoryPath) -> None:
    try:
        filesystem.resolve(path, must_exist=True)
    except FileNotFoundError:
        return
    raise ImageGenConflictError(f"ImageGen target already exists: {path}")


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ImageGenExecutionError("ImageGen timestamps must be timezone-aware")
    normalized = value.astimezone(UTC)
    return normalized.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _failure_timestamp(clock: Callable[[], datetime]) -> str:
    try:
        return _format_timestamp(clock())
    except Exception:
        return _format_timestamp(datetime.now(UTC))


def _failure_note(error: Exception) -> str:
    message = str(error).strip()
    detail = f"{type(error).__name__}: {message}" if message else type(error).__name__
    return detail[:4_000]


def _rollback(
    filesystem: ProjectFilesystem,
    *,
    manifest_path: RepositoryPath | None,
    output_paths: tuple[RepositoryPath, ...],
    directories: tuple[RepositoryPath, ...],
) -> Exception | None:
    failure: Exception | None = None
    paths = list(output_paths)
    if manifest_path is not None:
        paths.append(manifest_path)
    for path in paths:
        try:
            filesystem.remove_file(path)
        except Exception as error:
            failure = failure or error
    for directory in reversed(directories):
        try:
            filesystem.remove_empty_directory(directory)
        except Exception as error:
            failure = failure or error
    return failure


__all__ = [
    "IMAGEGEN_LOCK_NAME",
    "IMAGEGEN_MAX_OPERATION_BYTES",
    "IMAGEGEN_OPERATION_FILENAME",
    "ImageGenConflictError",
    "ImageGenExecutionError",
    "ImageGenExecutionResult",
    "ImageGenExecutor",
    "ImageGenOperation",
    "ImageGenProvider",
    "ImageGenProviderError",
    "ImageGenProviderMetadata",
    "ImageGenReceiptError",
    "ImageGenRequest",
    "ImageGenRollbackError",
]
