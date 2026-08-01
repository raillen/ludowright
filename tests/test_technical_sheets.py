"""Tests for deterministic technical-sheet assembly."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from ludowright.application import (
    TechnicalSheetConflictError,
    TechnicalSheetRequestError,
    TechnicalSheetService,
)
from ludowright.cli.app import app
from ludowright.contracts import (
    TechnicalSheetInputContract,
    TechnicalSheetKind,
    TechnicalSheetRequestContract,
    VisualReferenceContract,
)
from ludowright.contracts.visual import (
    ReferenceProvenanceContract,
    ReferenceTargetContract,
)
from ludowright.domain import ReferenceOrigin, ReferenceRole, ReferenceStatus
from ludowright.infrastructure import (
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    UnsafeProjectPathError,
    VisualReviewRepository,
)

runner = CliRunner()


def _filesystem(root: Path) -> ProjectFilesystem:
    root.mkdir()
    (root / ".ludowright").mkdir()
    (root / ".ludowright/project.json").write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(root)


def _png(color: tuple[int, int, int, int], *, size: tuple[int, int] = (80, 40)) -> bytes:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((8, 8, size[0] - 9, size[1] - 9), fill=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


def _approved_reference(filesystem: ProjectFilesystem, reference_id: str) -> None:
    reference = VisualReferenceContract(
        id=reference_id,
        name=f"Approved {reference_id}",
        target=ReferenceTargetContract(asset_id="asset-lantern"),
        role=ReferenceRole.OUTPUT,
        provenance=ReferenceProvenanceContract(
            origin=ReferenceOrigin.GENERATED,
            content_revision="sha256:" + "0" * 64,
            source_job_id="job-lantern",
            source_receipt_id="receipt-lantern",
        ),
        status=ReferenceStatus.APPROVED,
        approval_id=f"approval-{reference_id}",
    )
    repository = JsonDocumentRepository(
        filesystem,
        VisualReviewRepository(filesystem).reference_path(reference_id),
        VisualReferenceContract,
    )
    repository.create(reference)


def _request(
    filesystem: ProjectFilesystem,
    *,
    request_id: str = "lantern-turnaround",
    sheet_kind: str = "turnaround",
    items: tuple[tuple[str, str, bytes], ...] | None = None,
    path: str = "requests/lantern.json",
) -> RepositoryPath:
    selected = items or (
        ("front", "Front", _png((220, 40, 80, 255))),
        ("side", "Side", _png((40, 80, 220, 255))),
    )
    inputs: list[TechnicalSheetInputContract] = []
    for input_id, label, payload in selected:
        reference_id = f"ref-{input_id}"
        _approved_reference(filesystem, reference_id)
        image_path = RepositoryPath(f"normalized/{input_id}.png")
        filesystem.write_bytes(image_path, payload)
        inputs.append(
            TechnicalSheetInputContract(
                id=input_id,
                label=label,
                reference_id=reference_id,
                image_path=image_path.value,
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    request = TechnicalSheetRequestContract(
        id=request_id,
        name="Lantern technical sheet",
        template_id="minimal",
        template_version=1,
        sheet_kind=cast(TechnicalSheetKind, sheet_kind),
        inputs=tuple(inputs),
    )
    request_path = RepositoryPath(path)
    JsonDocumentRepository(
        filesystem,
        request_path,
        TechnicalSheetRequestContract,
    ).create(request)
    return request_path


def test_assembly_creates_deterministic_sheet_and_report(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)

    result = TechnicalSheetService(filesystem).assemble(
        request_path,
        RepositoryPath("sheets/lantern"),
    )

    assert result.state == "applied"
    assert result.report.sheet_kind == "turnaround"
    assert result.report.layout.value == "turnaround"
    assert result.report.output.path == "sheets/lantern/sheet.png"
    assert result.report.canvas_width == 1_136
    assert result.report.canvas_height == 344
    assert tuple(item.input_id for item in result.report.placements) == ("front", "side")
    assert (filesystem.root / "sheets/lantern/sheet.png").is_file()
    persisted = json.loads(
        (filesystem.root / "sheets/lantern/technical-sheet.json").read_text(encoding="utf-8")
    )
    assert persisted["kind"] == "technical-sheet"
    assert persisted["output"]["sha256"] == result.report.output.sha256

    image = Image.open(filesystem.root / "sheets/lantern/sheet.png")
    assert image.size == (1_136, 344)
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (242, 242, 242)


@pytest.mark.parametrize("sheet_kind", ["component", "prop", "detail", "scale"])
def test_data_defined_sheet_kinds_select_deterministic_layout(
    tmp_path: Path,
    sheet_kind: str,
) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem, request_id=f"lantern-{sheet_kind}", sheet_kind=sheet_kind)

    result = TechnicalSheetService(filesystem).assemble(
        request_path,
        RepositoryPath(f"sheets/{sheet_kind}"),
    )

    assert result.report.sheet_kind == sheet_kind
    assert result.report.layout.value == "grid"
    assert result.report.template_id == "minimal"


def test_exact_repeat_is_unchanged_and_two_projects_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    first = _filesystem(tmp_path / "first")
    second = _filesystem(tmp_path / "second")
    first_request = _request(first)
    second_request = _request(second)
    first_service = TechnicalSheetService(first)
    second_service = TechnicalSheetService(second)

    first_result = first_service.assemble(first_request, RepositoryPath("sheets/lantern"))
    second_result = second_service.assemble(second_request, RepositoryPath("sheets/lantern"))
    repeated = first_service.assemble(first_request, RepositoryPath("sheets/lantern"))

    assert first_result.report == second_result.report
    assert repeated.state == "unchanged"
    assert (first.root / "sheets/lantern/sheet.png").read_bytes() == (
        second.root / "sheets/lantern/sheet.png"
    ).read_bytes()


def test_dry_run_validates_approved_inputs_without_writing(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)

    result = TechnicalSheetService(filesystem).assemble(
        request_path,
        RepositoryPath("sheets/dry-run"),
        dry_run=True,
    )

    assert result.state == "planned"
    assert result.dry_run is True
    assert not (filesystem.root / "sheets").exists()


def test_unapproved_reference_is_rejected(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)
    reference_path = filesystem.root / ".ludowright/visual-references/ref-front.json"
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    payload["status"] = "candidate"
    payload.pop("approval_id", None)
    reference_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TechnicalSheetRequestError, match="not approved"):
        TechnicalSheetService(filesystem).assemble(
            request_path,
            RepositoryPath("sheets/unapproved"),
        )


def test_declared_input_checksum_is_required(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)
    request_file = filesystem.root / request_path.value
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["inputs"][0]["sha256"] = "f" * 64
    request_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TechnicalSheetRequestError, match="checksum"):
        TechnicalSheetService(filesystem).assemble(
            request_path,
            RepositoryPath("sheets/checksum"),
        )


def test_partial_target_and_modified_target_are_conflicts(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)
    service = TechnicalSheetService(filesystem)
    output = filesystem.root / "sheets/conflict"
    output.mkdir(parents=True)
    (output / "sheet.png").write_bytes(b"external")

    with pytest.raises(TechnicalSheetConflictError):
        service.assemble(request_path, RepositoryPath("sheets/conflict"))
    assert not (output / "technical-sheet.json").exists()
    assert (output / "sheet.png").read_bytes() == b"external"


def test_failure_after_output_write_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)
    original_write = ProjectFilesystem.write_bytes
    writes = 0

    def fail_on_second_write(
        instance: ProjectFilesystem,
        path: RepositoryPath,
        payload: bytes,
        *,
        mode: int | None = None,
    ) -> Path:
        nonlocal writes
        writes += 1
        if writes == 1:
            return original_write(instance, path, payload, mode=mode)
        if writes == 2:
            raise OSError("injected sheet report failure")
        return original_write(instance, path, payload, mode=mode)

    monkeypatch.setattr(ProjectFilesystem, "write_bytes", fail_on_second_write)
    with pytest.raises(OSError, match="injected sheet report failure"):
        TechnicalSheetService(filesystem).assemble(
            request_path,
            RepositoryPath("sheets/rollback"),
        )
    assert not (filesystem.root / "sheets").exists()


def test_symlink_output_is_rejected(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)
    outside = tmp_path / "outside"
    outside.mkdir()
    output_parent = filesystem.root / "sheets"
    output_parent.mkdir()
    output_link = output_parent / "unsafe"
    try:
        output_link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(UnsafeProjectPathError):
        TechnicalSheetService(filesystem).assemble(request_path, RepositoryPath("sheets/unsafe"))
    assert not tuple(outside.iterdir())


def test_concurrent_assembly_has_one_apply_and_one_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "project"
    filesystem = _filesystem(root)
    request_path = _request(filesystem)

    def run() -> str:
        return (
            TechnicalSheetService(ProjectFilesystem(root))
            .assemble(
                request_path,
                RepositoryPath("sheets/concurrent"),
            )
            .state
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(pool.map(lambda _: run(), range(2)))
    assert sorted(states) == ["applied", "unchanged"]


def test_cli_human_json_and_traversal_error(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    request_path = _request(filesystem)
    project = str(filesystem.root)

    human = runner.invoke(
        app,
        ["sheets", "assemble", request_path.value, "sheets/cli", project],
    )
    assert human.exit_code == 0
    assert "Technical sheet assembly" in human.stdout

    machine = runner.invoke(
        app,
        [
            "--json",
            "sheets",
            "assemble",
            request_path.value,
            "sheets/cli-json",
            project,
        ],
    )
    assert machine.exit_code == 0
    machine_payload = json.loads(machine.stdout)
    assert machine_payload["kind"] == "cli-response"
    assert machine_payload["command"] == "sheets assemble"
    assert machine_payload["data"]["state"] == "applied"

    error = runner.invoke(
        app,
        ["--json", "sheets", "assemble", "../outside.json", "sheets/error", project],
    )
    assert error.exit_code == 4
    error_payload = json.loads(error.stdout)
    assert error_payload["ok"] is False
    assert error_payload["error"]["code"] == "invalid-input"


def test_input_symlink_is_rejected(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png((20, 30, 40, 255)))
    source = filesystem.root / "normalized/source.png"
    source.parent.mkdir()
    try:
        source.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    _approved_reference(filesystem, "ref-source")
    request = TechnicalSheetRequestContract(
        id="symlink-sheet",
        name="Symlink sheet",
        template_id="minimal",
        template_version=1,
        sheet_kind="component",
        inputs=(
            TechnicalSheetInputContract(
                id="source",
                label="Source",
                reference_id="ref-source",
                image_path="normalized/source.png",
                sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
            ),
        ),
    )
    request_path = RepositoryPath("requests/symlink.json")
    JsonDocumentRepository(filesystem, request_path, TechnicalSheetRequestContract).create(request)

    with pytest.raises(TechnicalSheetRequestError, match="cannot be read safely"):
        TechnicalSheetService(filesystem).assemble(request_path, RepositoryPath("sheets/symlink"))
