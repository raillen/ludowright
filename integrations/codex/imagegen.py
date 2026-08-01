"""Safe execution boundary for one ready visual job through ImageGen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ludowright.contracts import (
    ImageGenOperationContract,
    ImageGenOutputContract,
)
from ludowright.contracts.visual import ReferenceTargetContract
from ludowright.domain import CompiledPrompt, VisualJob
from ludowright.infrastructure import (
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StructuredDocumentConflictError,
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

    def as_data(self) -> dict[str, object]:
        """Return JSON-compatible execution data without provider payloads."""
        return {
            "dry_run": self.dry_run,
            "manifest_path": self.operation.manifest_path.value,
            "operation": self.operation.contract.model_dump(mode="json"),
            "output_paths": [path.value for path in self.operation.output_paths],
            "state": self.state,
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
    ) -> ImageGenExecutionResult:
        """Execute one PNG request per view and record the immutable operation."""
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("ImageGen execution requires ProjectFilesystem")
        if not isinstance(operation, ImageGenOperation):
            raise TypeError("ImageGen execution requires a prepared operation")
        if dry_run:
            return ImageGenExecutionResult(operation=operation, state="planned", dry_run=True)
        if not hasattr(provider, "generate") or not callable(provider.generate):
            raise TypeError("ImageGen execution requires a provider with generate()")

        created_directories: tuple[RepositoryPath, ...] = ()
        created_outputs: list[RepositoryPath] = []
        manifest_created = False
        try:
            with filesystem.lock(IMAGEGEN_LOCK_NAME, timeout=timeout):
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

                for output in operation.contract.outputs:
                    request = ImageGenRequest(operation=operation.contract, output=output)
                    try:
                        payload = provider.generate(request)
                        validate_png_payload(payload)
                    except Exception as error:
                        raise ImageGenProviderError(
                            f"ImageGen provider failed for output {output.path}"
                        ) from error
                    output_path = RepositoryPath(output.path)
                    _assert_missing(filesystem, output_path)
                    filesystem.write_bytes(output_path, payload)
                    created_outputs.append(output_path)

            return ImageGenExecutionResult(operation=operation, state="executed", dry_run=False)
        except Exception as error:
            rollback_error = _rollback(
                filesystem,
                manifest_path=operation.manifest_path if manifest_created else None,
                output_paths=tuple(created_outputs),
                directories=created_directories,
            )
            if rollback_error is not None:
                raise ImageGenRollbackError(
                    "ImageGen execution failed and cleanup was incomplete"
                ) from error
            raise


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
    "ImageGenRequest",
    "ImageGenRollbackError",
]
