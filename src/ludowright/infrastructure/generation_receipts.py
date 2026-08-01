"""Durable generation receipts and generated-reference records."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ludowright.contracts import (
    GenerationOutputContract,
    GenerationOutputValidationContract,
    GenerationReceiptContract,
    ImageGenOperationContract,
    VisualReferenceContract,
)
from ludowright.contracts.common import ContractModel
from ludowright.contracts.visual import ReferenceProvenanceContract
from ludowright.domain import ReceiptStatus, ReferenceOrigin, ReferenceRole, ReferenceStatus
from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath
from ludowright.infrastructure.image_artifacts import PngValidation
from ludowright.infrastructure.structured import (
    JsonDocumentRepository,
    StructuredDocumentConflictError,
)

GENERATION_RECEIPT_DIRECTORY = RepositoryPath(".ludowright/generation-receipts")
GENERATED_REFERENCE_DIRECTORY = RepositoryPath(".ludowright/visual-references")
GENERATION_RECEIPT_MAX_BYTES = 2_000_000


class GenerationReceiptError(RuntimeError):
    """Base error for durable receipt persistence."""


class GenerationReceiptConflictError(GenerationReceiptError):
    """Raised when receipt history cannot accept another attempt."""


@dataclass(frozen=True, slots=True)
class GenerationReceiptAttempt:
    """The next immutable attempt number in one job history."""

    attempt: int
    retry_of: str | None


@dataclass(frozen=True, slots=True)
class ValidatedGenerationOutput:
    """One generated output after bounded PNG validation."""

    index: int
    role: ReferenceRole
    path: RepositoryPath
    validation: PngValidation


class GenerationReceiptRepository:
    """Persist append-only receipts and candidate generated references."""

    def load(
        self,
        filesystem: ProjectFilesystem,
        receipt_id: str,
    ) -> GenerationReceiptContract:
        """Load exactly one receipt by its immutable ID."""
        if not isinstance(receipt_id, str) or not receipt_id:
            raise GenerationReceiptError("a receipt lookup requires a non-empty ID")
        matches: list[GenerationReceiptContract] = []
        for path in filesystem.list_files(
            GENERATION_RECEIPT_DIRECTORY,
            suffix=".json",
            max_files=10_000,
        ):
            snapshot = JsonDocumentRepository(
                filesystem,
                path,
                GenerationReceiptContract,
                max_bytes=GENERATION_RECEIPT_MAX_BYTES,
            ).load()
            if snapshot.value.id == receipt_id:
                matches.append(snapshot.value)
        if not matches:
            raise FileNotFoundError(f"generation receipt does not exist: {receipt_id}")
        if len(matches) != 1:
            raise GenerationReceiptError(f"generation receipt ID is not unique: {receipt_id}")
        return matches[0]

    def list_for_job(
        self,
        filesystem: ProjectFilesystem,
        job_id: str,
    ) -> tuple[GenerationReceiptContract, ...]:
        """Load one job's receipt history in deterministic attempt order."""
        directory = GENERATION_RECEIPT_DIRECTORY.child(job_id)
        receipts: list[GenerationReceiptContract] = []
        for path in filesystem.list_files(directory, suffix=".json", max_files=100):
            snapshot = JsonDocumentRepository(
                filesystem,
                path,
                GenerationReceiptContract,
                max_bytes=GENERATION_RECEIPT_MAX_BYTES,
            ).load()
            if snapshot.value.job_id != job_id:
                raise GenerationReceiptError(
                    f"receipt {path} names a different job than its directory"
                )
            receipts.append(snapshot.value)
        receipts.sort(key=lambda receipt: receipt.attempt)
        return tuple(receipts)

    def next_attempt(
        self,
        filesystem: ProjectFilesystem,
        operation: ImageGenOperationContract,
    ) -> GenerationReceiptAttempt:
        """Return the next contiguous attempt without writing any state."""
        receipts = self.list_for_job(filesystem, operation.job_id)
        if not receipts:
            return GenerationReceiptAttempt(attempt=1, retry_of=None)

        expected_attempts = tuple(range(1, len(receipts) + 1))
        actual_attempts = tuple(receipt.attempt for receipt in receipts)
        if actual_attempts != expected_attempts:
            raise GenerationReceiptError("generation receipt attempts are not contiguous")
        if any(receipt.request_revision != operation.job_request_revision for receipt in receipts):
            raise GenerationReceiptError("generation receipt request revisions do not match")

        previous = receipts[-1]
        if previous.status is ReceiptStatus.SUCCEEDED:
            raise GenerationReceiptConflictError(
                f"job already has a successful generation receipt: {previous.id}"
            )
        return GenerationReceiptAttempt(attempt=previous.attempt + 1, retry_of=previous.id)

    def record_success(
        self,
        filesystem: ProjectFilesystem,
        operation: ImageGenOperationContract,
        attempt: GenerationReceiptAttempt,
        *,
        provider: str,
        model: str,
        tool: str | None,
        started_at: str,
        completed_at: str,
        outputs: tuple[ValidatedGenerationOutput, ...],
    ) -> GenerationReceiptContract:
        """Persist generated references before their successful receipt."""
        if len(outputs) != len(operation.outputs):
            raise GenerationReceiptError("receipt output count does not match the operation")
        if tuple(output.index for output in outputs) != tuple(range(1, len(outputs) + 1)):
            raise GenerationReceiptError("receipt outputs must be contiguous and ordered")

        receipt_id = _receipt_id(operation.id, attempt.attempt)
        output_contracts: list[GenerationOutputContract] = []
        reference_contracts: list[VisualReferenceContract] = []
        for operation_output, validated in zip(operation.outputs, outputs, strict=True):
            if (
                operation_output.index != validated.index
                or operation_output.role is not validated.role
            ):
                raise GenerationReceiptError("validated output does not match the operation")
            reference_id = _reference_id(receipt_id, validated)
            output_contracts.append(
                GenerationOutputContract(
                    reference_id=reference_id,
                    role=validated.role,
                    path=validated.path.value,
                    sha256=validated.validation.sha256,
                    size_bytes=validated.validation.size_bytes,
                    validation=GenerationOutputValidationContract(
                        width=validated.validation.width,
                        height=validated.validation.height,
                    ),
                )
            )
            reference_contracts.append(
                VisualReferenceContract(
                    id=reference_id,
                    name=f"{operation.job_id}-{validated.role.value}-{validated.index} output",
                    target=operation.target,
                    role=validated.role,
                    provenance=ReferenceProvenanceContract(
                        origin=ReferenceOrigin.GENERATED,
                        content_revision=f"sha256:{validated.validation.sha256}",
                        source_job_id=operation.job_id,
                        source_receipt_id=receipt_id,
                    ),
                    status=ReferenceStatus.CANDIDATE,
                )
            )

        receipt = GenerationReceiptContract(
            id=receipt_id,
            job_id=operation.job_id,
            attempt=attempt.attempt,
            status=ReceiptStatus.SUCCEEDED,
            provider=provider,
            model=model,
            tool=tool,
            request_revision=operation.job_request_revision,
            operation_id=operation.id,
            prompt_hash=operation.prompt_hash,
            started_at=started_at,
            completed_at=completed_at,
            output_reference_ids=tuple(output.reference_id for output in output_contracts),
            outputs=tuple(output_contracts),
            retry_of=attempt.retry_of,
        )
        reference_paths = tuple(
            GENERATED_REFERENCE_DIRECTORY.child(f"{reference.id}.json")
            for reference in reference_contracts
        )
        receipt_path = self._receipt_path(operation.job_id, receipt.id)
        created_directories = _ensure_directories(
            filesystem,
            (
                GENERATED_REFERENCE_DIRECTORY,
                _required_parent(receipt_path),
            ),
        )
        created_reference_paths: list[RepositoryPath] = []
        try:
            for path, reference in zip(reference_paths, reference_contracts, strict=True):
                _create(
                    filesystem,
                    path,
                    reference,
                    VisualReferenceContract,
                )
                created_reference_paths.append(path)
            _create(filesystem, receipt_path, receipt, GenerationReceiptContract)
        except Exception:
            for path in reversed(created_reference_paths):
                filesystem.remove_file(path)
            _remove_empty_directories(filesystem, created_directories)
            raise
        return receipt

    def record_failure(
        self,
        filesystem: ProjectFilesystem,
        operation: ImageGenOperationContract,
        attempt: GenerationReceiptAttempt,
        *,
        provider: str,
        model: str,
        tool: str | None,
        started_at: str,
        completed_at: str,
        failure_note: str,
    ) -> GenerationReceiptContract:
        """Persist a failed terminal attempt after output rollback."""
        receipt = GenerationReceiptContract(
            id=_receipt_id(operation.id, attempt.attempt),
            job_id=operation.job_id,
            attempt=attempt.attempt,
            status=ReceiptStatus.FAILED,
            provider=provider,
            model=model,
            tool=tool,
            request_revision=operation.job_request_revision,
            operation_id=operation.id,
            prompt_hash=operation.prompt_hash,
            started_at=started_at,
            completed_at=completed_at,
            failure_note=failure_note[:4_000],
            retry_of=attempt.retry_of,
        )
        receipt_path = self._receipt_path(operation.job_id, receipt.id)
        created_directories = _ensure_directories(
            filesystem,
            (_required_parent(receipt_path),),
        )
        try:
            _create(filesystem, receipt_path, receipt, GenerationReceiptContract)
        except Exception:
            _remove_empty_directories(filesystem, created_directories)
            raise
        return receipt

    @staticmethod
    def _receipt_path(job_id: str, receipt_id: str) -> RepositoryPath:
        return GENERATION_RECEIPT_DIRECTORY.child(job_id).child(f"{receipt_id}.json")


def _create[TContract: ContractModel](
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
    value: TContract,
    model: type[TContract],
) -> None:
    try:
        JsonDocumentRepository(
            filesystem,
            path,
            model,
            max_bytes=GENERATION_RECEIPT_MAX_BYTES,
        ).create(value)
    except StructuredDocumentConflictError as error:
        raise GenerationReceiptConflictError(f"receipt target already exists: {path}") from error


def _ensure_directories(
    filesystem: ProjectFilesystem,
    directories: tuple[RepositoryPath, ...],
) -> tuple[RepositoryPath, ...]:
    created: list[RepositoryPath] = []
    for directory in directories:
        missing: list[RepositoryPath] = []
        current = RepositoryPath(directory.parts[0])
        if not filesystem.directory_exists(current):
            missing.append(current)
        for segment in directory.parts[1:]:
            current = current.child(segment)
            if not filesystem.directory_exists(current):
                missing.append(current)
        filesystem.ensure_directory(directory)
        created.extend(missing)
    return tuple(dict.fromkeys(created))


def _remove_empty_directories(
    filesystem: ProjectFilesystem,
    directories: tuple[RepositoryPath, ...],
) -> None:
    for directory in reversed(directories):
        filesystem.remove_empty_directory(directory)


def _receipt_id(operation_id: str, attempt: int) -> str:
    digest = hashlib.sha256(f"{operation_id}:{attempt}".encode("ascii")).hexdigest()
    return f"receipt-{digest[:32]}"


def _reference_id(receipt_id: str, output: ValidatedGenerationOutput) -> str:
    digest = hashlib.sha256(
        f"{receipt_id}:{output.index}:{output.validation.sha256}".encode("ascii")
    ).hexdigest()
    return f"ref-{digest[:32]}"


def _required_parent(path: RepositoryPath) -> RepositoryPath:
    parent = path.parent
    if parent is None:
        raise GenerationReceiptError(f"receipt path requires a parent directory: {path}")
    return parent


__all__ = [
    "GENERATED_REFERENCE_DIRECTORY",
    "GENERATION_RECEIPT_DIRECTORY",
    "GENERATION_RECEIPT_MAX_BYTES",
    "GenerationReceiptAttempt",
    "GenerationReceiptConflictError",
    "GenerationReceiptError",
    "GenerationReceiptRepository",
    "ValidatedGenerationOutput",
]
