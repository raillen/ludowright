"""Tests for the safe Codex ImageGen execution boundary."""

from __future__ import annotations

import hashlib
import json
import struct
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from integrations.codex import (
    ImageGenConflictError,
    ImageGenExecutionError,
    ImageGenExecutor,
    ImageGenProvider,
    ImageGenProviderError,
    ImageGenProviderMetadata,
    ImageGenRequest,
)
from pydantic import ValidationError

from ludowright.contracts import GenerationOutputContract, ImageGenOperationContract
from ludowright.domain import (
    AssetId,
    DisplayName,
    JobId,
    ProfileVersion,
    ReferenceRole,
    ReferenceTarget,
    SubjectRevision,
    VisualJob,
)
from ludowright.infrastructure import (
    GenerationReceiptRepository,
    ProjectFilesystem,
    RepositoryPath,
    UnsafeProjectPathError,
)

PROMPT_FIXTURE = Path("tests/fixtures/contracts/v1/compiled-prompt.json")


def make_job(
    *,
    asset_id: str = "hero",
    roles: tuple[ReferenceRole, ...] = (ReferenceRole.IDENTITY,),
) -> VisualJob:
    return VisualJob(
        id=JobId("job-hero-front-v1"),
        name=DisplayName("Hero front view"),
        target=ReferenceTarget(AssetId(asset_id)),
        profile_version=ProfileVersion(1),
        request_revision=SubjectRevision("sha256:job-request"),
        input_reference_ids=(),
        output_roles=roles,
        expected_output_count=len(roles),
    )


def make_prompt():
    from ludowright.contracts import CompiledPromptContract

    return CompiledPromptContract.model_validate(
        json.loads(PROMPT_FIXTURE.read_text(encoding="utf-8"))
    ).to_domain()


def make_filesystem(root: Path) -> ProjectFilesystem:
    root.mkdir()
    marker = root / ".ludowright"
    marker.mkdir()
    (marker / "project.json").write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(root)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def png_payload(*, animated: bool = False) -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    chunks = [png_chunk(b"IHDR", header)]
    if animated:
        chunks.append(png_chunk(b"acTL", struct.pack(">II", 1, 1)))
    chunks.extend(
        (
            png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00")),
            png_chunk(b"IEND", b""),
        )
    )
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


class FakeImageGenProvider:
    def __init__(self, *, fail_at: int | None = None, payload: bytes | None = None) -> None:
        self.fail_at = fail_at
        self.payload = payload or png_payload()
        self.calls: list[int] = []
        self._lock = threading.Lock()

    def generate(self, request: ImageGenRequest) -> bytes:
        output = request.output
        with self._lock:
            self.calls.append(output.index)
            if self.fail_at == output.index:
                raise RuntimeError("provider failure")
        return self.payload


def test_prepare_is_deterministic_and_records_prompt_and_inputs() -> None:
    executor = ImageGenExecutor()
    first = executor.prepare(
        make_job(roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION)),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    second = executor.prepare(
        make_job(roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION)),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )

    assert first == second
    assert first.contract.input_reference_ids == ()
    assert first.contract.positive_prompt
    assert first.contract.outputs[0].path.endswith("01-identity.png")
    assert first.contract.outputs[1].path.endswith("02-construction.png")
    assert first.manifest_path.value.endswith("operation.json")


def test_prepare_rejects_mismatched_prompt_target_or_inputs() -> None:
    executor = ImageGenExecutor()
    prompt = make_prompt()

    with pytest.raises(ImageGenExecutionError, match="target"):
        executor.prepare(
            make_job(asset_id="other-asset"), prompt, RepositoryPath("references/hero")
        )


def test_dry_run_does_not_call_provider_or_write_files(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero/job-hero-front-v1")
    )
    provider = FakeImageGenProvider()

    result = ImageGenExecutor().execute(filesystem, operation, object(), dry_run=True)

    assert result.state == "planned"
    assert result.dry_run is True
    assert provider.calls == []
    assert not (filesystem.root / "references").exists()
    assert not (filesystem.root / ".ludowright" / "generation-receipts").exists()


def test_execute_writes_one_png_per_view_and_operation_record(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION)),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    provider = FakeImageGenProvider()

    result = ImageGenExecutor().execute(filesystem, operation, provider)

    assert result.state == "executed"
    assert provider.calls == [1, 2]
    manifest = json.loads(filesystem.read_text(operation.manifest_path))
    assert manifest["kind"] == "imagegen-operation"
    assert manifest["positive_prompt"] == operation.contract.positive_prompt
    assert manifest["input_reference_ids"] == []
    assert all(
        filesystem.resolve(path, must_exist=True).is_file() for path in operation.output_paths
    )


def test_execute_persists_success_receipt_references_and_validation(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION)),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    timestamps = iter(
        (
            datetime(2026, 8, 1, 12, 0, 0, 123456, tzinfo=UTC),
            datetime(2026, 8, 1, 12, 0, 1, 123456, tzinfo=UTC),
        )
    )

    result = ImageGenExecutor().execute(
        filesystem,
        operation,
        FakeImageGenProvider(),
        metadata=ImageGenProviderMetadata(
            provider="OpenAI",
            model="Image Model",
            tool="codex-imagegen",
        ),
        clock=lambda: next(timestamps),
    )

    assert result.receipt is not None
    receipt = result.receipt
    assert receipt.status.value == "succeeded"
    assert receipt.prompt_hash == operation.contract.prompt_hash
    assert receipt.tool == "codex-imagegen"
    assert receipt.started_at == "2026-08-01T12:00:00.123456Z"
    assert receipt.completed_at == "2026-08-01T12:00:01.123456Z"
    assert tuple(output.reference_id for output in receipt.outputs) == receipt.output_reference_ids
    assert all(output.validation.format == "png" for output in receipt.outputs)
    assert all(output.validation.animated is False for output in receipt.outputs)
    assert all(
        output.sha256 == hashlib.sha256(png_payload()).hexdigest() for output in receipt.outputs
    )
    assert all(
        (filesystem.root / ".ludowright" / "visual-references" / f"{reference_id}.json").is_file()
        for reference_id in receipt.output_reference_ids
    )

    persisted = GenerationReceiptRepository().list_for_job(filesystem, operation.contract.job_id)
    assert persisted == (receipt,)


def test_execute_refuses_existing_targets_without_overwriting(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    executor = ImageGenExecutor()
    operation = executor.prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero/job-hero-front-v1")
    )
    executor.execute(filesystem, operation, FakeImageGenProvider())
    provider = FakeImageGenProvider()

    with pytest.raises(ImageGenConflictError):
        executor.execute(filesystem, operation, provider)

    assert provider.calls == []
    assert filesystem.read_bytes(operation.output_paths[0]) == png_payload()


def test_provider_failure_rolls_back_manifest_outputs_and_new_directories(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION)),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )

    with pytest.raises(ImageGenProviderError, match="output"):
        ImageGenExecutor().execute(filesystem, operation, FakeImageGenProvider(fail_at=2))

    assert not (filesystem.root / "references").exists()


def test_provider_failure_persists_failed_receipt_after_rollback(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(roles=(ReferenceRole.IDENTITY, ReferenceRole.CONSTRUCTION)),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    timestamps = iter(
        (
            datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 8, 1, 12, 0, 1, tzinfo=UTC),
        )
    )

    with pytest.raises(ImageGenProviderError):
        ImageGenExecutor().execute(
            filesystem,
            operation,
            FakeImageGenProvider(fail_at=2),
            clock=lambda: next(timestamps),
        )

    receipts = GenerationReceiptRepository().list_for_job(filesystem, operation.contract.job_id)
    assert len(receipts) == 1
    assert receipts[0].status.value == "failed"
    assert receipts[0].attempt == 1
    assert receipts[0].output_reference_ids == ()
    assert receipts[0].failure_note is not None
    assert "ImageGenProviderError" in receipts[0].failure_note
    assert not (filesystem.root / "references").exists()


def test_retry_persists_contiguous_attempt_and_previous_receipt(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    executor = ImageGenExecutor()
    operation = executor.prepare(
        make_job(),
        make_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    first_times = iter(
        (
            datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 8, 1, 12, 0, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(ImageGenProviderError):
        executor.execute(
            filesystem,
            operation,
            FakeImageGenProvider(fail_at=1),
            clock=lambda: next(first_times),
        )

    second_times = iter(
        (
            datetime(2026, 8, 1, 12, 0, 2, tzinfo=UTC),
            datetime(2026, 8, 1, 12, 0, 3, tzinfo=UTC),
        )
    )
    result = executor.execute(
        filesystem,
        operation,
        FakeImageGenProvider(),
        clock=lambda: next(second_times),
    )

    assert result.receipt is not None
    receipts = GenerationReceiptRepository().list_for_job(filesystem, operation.contract.job_id)
    assert tuple(receipt.attempt for receipt in receipts) == (1, 2)
    assert result.receipt.attempt == 2
    assert result.receipt.retry_of == receipts[0].id


def test_invalid_or_animated_provider_payload_is_rejected_and_cleaned(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero")
    )

    with pytest.raises(ImageGenProviderError):
        ImageGenExecutor().execute(
            filesystem,
            operation,
            FakeImageGenProvider(payload=png_payload(animated=True)),
        )

    assert not (filesystem.root / "references").exists()


def test_symlink_output_directory_is_rejected_without_writing_outside(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = filesystem.root / "references"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    operation = ImageGenExecutor().prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero")
    )

    with pytest.raises(UnsafeProjectPathError):
        ImageGenExecutor().execute(filesystem, operation, FakeImageGenProvider())

    assert not list(outside.iterdir())


def test_concurrent_execution_allows_one_writer(tmp_path: Path) -> None:
    root = tmp_path / "project"
    filesystem = make_filesystem(root)
    operation = ImageGenExecutor().prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero")
    )

    def run() -> str:
        try:
            ImageGenExecutor().execute(ProjectFilesystem(root), operation, FakeImageGenProvider())
        except ImageGenConflictError:
            return "conflict"
        return "executed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = tuple(executor.map(lambda _: run(), range(2)))

    assert sorted(states) == ["conflict", "executed"]
    assert (filesystem.root / "references/hero/operation.json").is_file()
    assert (
        len(GenerationReceiptRepository().list_for_job(filesystem, operation.contract.job_id)) == 1
    )


def test_operation_contract_rejects_tampered_revision_and_traversal() -> None:
    operation = (
        ImageGenExecutor()
        .prepare(make_job(), make_prompt(), RepositoryPath("references/hero"))
        .contract
    )
    payload = operation.model_dump(mode="json")
    payload["operation_revision"] = "0" * 64

    with pytest.raises(ValidationError, match="revision"):
        ImageGenOperationContract.model_validate(payload)

    payload = operation.model_dump(mode="json")
    payload["output_directory"] = "../outside"
    with pytest.raises(ValidationError, match="relative path"):
        ImageGenOperationContract.model_validate(payload)


def test_generation_output_contract_rejects_traversal() -> None:
    with pytest.raises(ValidationError, match="normalized relative paths"):
        GenerationOutputContract(
            reference_id="ref-output",
            role=ReferenceRole.OUTPUT,
            path="../outside.png",
            sha256="a" * 64,
            size_bytes=10,
            validation={"width": 1, "height": 1},
        )


def test_operation_rejects_manifest_outside_output_directory() -> None:
    operation = ImageGenExecutor().prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero")
    )

    with pytest.raises(ImageGenExecutionError, match="manifest path"):
        type(operation)(operation.contract, RepositoryPath("other/operation.json"))


def test_provider_payload_must_be_bytes(tmp_path: Path) -> None:
    filesystem = make_filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        make_job(), make_prompt(), RepositoryPath("references/hero")
    )

    class NonBytesProvider:
        def generate(self, request: object) -> object:
            return "not an image"

    with pytest.raises(ImageGenProviderError):
        ImageGenExecutor().execute(
            filesystem,
            operation,
            cast(ImageGenProvider, NonBytesProvider()),
        )
