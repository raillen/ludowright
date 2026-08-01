"""Tests for deterministic image normalization and its CLI boundary."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from ludowright.application import (
    ImageNormalizationConflictError,
    ImageNormalizationService,
)
from ludowright.cli.app import app
from ludowright.infrastructure import (
    ImageNormalizationOptions,
    ProjectFilesystem,
    RepositoryPath,
    UnsafeProjectPathError,
)

runner = CliRunner()
OPTIONS = ImageNormalizationOptions(
    canvas_width=128,
    canvas_height=96,
    padding=8,
    thumbnail_size=32,
)


def _filesystem(root: Path) -> ProjectFilesystem:
    root.mkdir()
    (root / ".ludowright").mkdir()
    (root / ".ludowright/project.json").write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(root)


def _source_png() -> bytes:
    image = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 10, 59, 29), fill=(220, 40, 80, 255))
    return _encode(image)


def _oriented_jpeg() -> bytes:
    image = Image.new("RGB", (40, 20), (230, 230, 230))
    ImageDraw.Draw(image).rectangle((10, 4, 29, 15), fill=(20, 40, 80))
    exif = Image.Exif()
    exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif, quality=95, subsampling=0)
    return buffer.getvalue()


def _encode(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


def _write_source(
    filesystem: ProjectFilesystem,
    payload: bytes,
    path: str = "references/source.png",
) -> None:
    filesystem.write_bytes(RepositoryPath(path), payload)


def _read_image(path: Path) -> Image.Image:
    image = Image.open(path)
    image.load()
    return image


def test_normalization_writes_four_pngs_and_canonical_report(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())

    result = ImageNormalizationService(filesystem).normalize(
        RepositoryPath("references/source.png"),
        RepositoryPath("normalized/source"),
        options=OPTIONS,
    )

    assert result.state == "applied"
    assert result.dry_run is False
    assert result.report.source_format == "png"
    assert result.report.canvas_width == 128
    assert result.report.canvas_height == 96
    assert result.report.requested_padding == 8
    assert result.report.padding.left >= 8
    assert result.report.padding.top >= 8
    assert tuple(output.artifact for output in result.report.outputs) == (
        "normalized",
        "neutral",
        "thumbnail",
        "alignment-guide",
    )
    assert (filesystem.root / "normalized/source/normalization.json").is_file()

    normalized = _read_image(filesystem.root / "normalized/source/normalized.png")
    neutral = _read_image(filesystem.root / "normalized/source/neutral.png")
    thumbnail = _read_image(filesystem.root / "normalized/source/thumbnail.png")
    guide = _read_image(filesystem.root / "normalized/source/alignment-guide.png")
    assert normalized.size == (128, 96)
    assert normalized.mode == "RGBA"
    assert normalized.getpixel((0, 0))[3] == 0
    assert neutral.size == (128, 96)
    assert neutral.mode == "RGB"
    assert neutral.getpixel((0, 0)) == (242, 242, 242)
    assert thumbnail.size == (32, 32)
    assert guide.size == (128, 96)
    assert guide.tobytes() != normalized.tobytes()

    persisted = json.loads(
        (filesystem.root / "normalized/source/normalization.json").read_text(encoding="utf-8")
    )
    assert persisted["kind"] == "image-normalization"
    assert persisted["outputs"][0]["sha256"] == result.report.outputs[0].sha256


def test_orientation_metadata_is_applied_and_not_carried_to_outputs(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _oriented_jpeg(), "references/oriented.jpg")

    result = ImageNormalizationService(filesystem).normalize(
        RepositoryPath("references/oriented.jpg"),
        RepositoryPath("normalized/oriented"),
        options=OPTIONS,
    )

    assert result.report.source_format == "jpeg"
    assert result.report.source_width == 40
    assert result.report.source_height == 20
    assert result.report.source_orientation == 6
    assert result.report.orientation_applied is True
    output = _read_image(filesystem.root / "normalized/oriented/normalized.png")
    assert output.getexif().get(274, 1) == 1


def test_normalization_is_deterministic_and_exact_repeat_is_unchanged(tmp_path: Path) -> None:
    first = _filesystem(tmp_path / "first")
    second = _filesystem(tmp_path / "second")
    payload = _source_png()
    _write_source(first, payload)
    _write_source(second, payload)
    source = RepositoryPath("references/source.png")
    output = RepositoryPath("normalized/source")

    first_result = ImageNormalizationService(first).normalize(source, output, options=OPTIONS)
    second_result = ImageNormalizationService(second).normalize(source, output, options=OPTIONS)
    repeated = ImageNormalizationService(first).normalize(source, output, options=OPTIONS)

    assert first_result.report == second_result.report
    assert first_result.report_path == second_result.report_path
    assert repeated.state == "unchanged"
    for artifact in first_result.report.outputs:
        first_bytes = (first.root / artifact.path).read_bytes()
        second_bytes = (second.root / artifact.path).read_bytes()
        assert first_bytes == second_bytes


def test_dry_run_does_not_create_output_directory(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())

    result = ImageNormalizationService(filesystem).normalize(
        RepositoryPath("references/source.png"),
        RepositoryPath("normalized/dry-run"),
        options=OPTIONS,
        dry_run=True,
    )

    assert result.state == "planned"
    assert result.dry_run is True
    assert not (filesystem.root / "normalized").exists()


def test_existing_artifact_is_never_overwritten(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())
    service = ImageNormalizationService(filesystem)
    source = RepositoryPath("references/source.png")
    output = RepositoryPath("normalized/source")
    service.normalize(source, output, options=OPTIONS)
    original = (filesystem.root / "normalized/source/normalized.png").read_bytes()
    (filesystem.root / "normalized/source/normalized.png").write_bytes(b"external change")

    with pytest.raises(ImageNormalizationConflictError):
        service.normalize(source, output, options=OPTIONS)

    assert (filesystem.root / "normalized/source/normalized.png").read_bytes() == b"external change"
    assert original != b"external change"


def test_partial_target_is_rejected_without_creating_remaining_outputs(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())
    output_directory = filesystem.root / "normalized/partial"
    output_directory.mkdir(parents=True)
    (output_directory / "normalized.png").write_bytes(b"existing")

    with pytest.raises(ImageNormalizationConflictError):
        ImageNormalizationService(filesystem).normalize(
            RepositoryPath("references/source.png"),
            RepositoryPath("normalized/partial"),
            options=OPTIONS,
        )

    assert not (output_directory / "neutral.png").exists()
    assert (output_directory / "normalized.png").read_bytes() == b"existing"


def test_failure_mid_write_rolls_back_only_created_files_and_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())
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
        if writes == 2:
            raise OSError("injected normalization write failure")
        return original_write(instance, path, payload, mode=mode)

    monkeypatch.setattr(ProjectFilesystem, "write_bytes", fail_on_second_write)
    with pytest.raises(OSError, match="injected normalization write failure"):
        ImageNormalizationService(filesystem).normalize(
            RepositoryPath("references/source.png"),
            RepositoryPath("normalized/failure"),
            options=OPTIONS,
        )

    assert not (filesystem.root / "normalized").exists()
    assert (filesystem.root / "references/source.png").is_file()


def test_symlink_source_and_output_are_rejected(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_source = outside / "source.png"
    outside_source.write_bytes(_source_png())
    source_link = filesystem.root / "references/source.png"
    source_link.parent.mkdir()
    try:
        source_link.symlink_to(outside_source)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(UnsafeProjectPathError):
        ImageNormalizationService(filesystem).normalize(
            RepositoryPath("references/source.png"),
            RepositoryPath("normalized/source"),
            options=OPTIONS,
        )


def test_symlink_output_directory_is_rejected(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())
    outside = tmp_path / "outside"
    outside.mkdir()
    output_parent = filesystem.root / "normalized"
    output_parent.mkdir()
    output_link = output_parent / "source"
    try:
        output_link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(UnsafeProjectPathError):
        ImageNormalizationService(filesystem).normalize(
            RepositoryPath("references/source.png"),
            RepositoryPath("normalized/source"),
            options=OPTIONS,
        )
    assert not tuple(outside.iterdir())


def test_concurrent_normalization_serializes_to_one_apply_and_one_unchanged(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    filesystem = _filesystem(root)
    _write_source(filesystem, _source_png())

    def run() -> str:
        result = ImageNormalizationService(ProjectFilesystem(root)).normalize(
            RepositoryPath("references/source.png"),
            RepositoryPath("normalized/concurrent"),
            options=OPTIONS,
        )
        return result.state

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(pool.map(lambda _: run(), range(2)))

    assert sorted(states) == ["applied", "unchanged"]


def test_cli_human_json_and_expected_error_surfaces(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _write_source(filesystem, _source_png())
    project = str(filesystem.root)

    human = runner.invoke(
        app,
        [
            "images",
            "normalize",
            "references/source.png",
            "normalized/cli",
            project,
            "--width",
            "128",
            "--height",
            "96",
            "--padding",
            "8",
            "--thumbnail-size",
            "32",
        ],
    )
    assert human.exit_code == 0
    assert "Image normalization" in human.stdout

    machine = runner.invoke(
        app,
        [
            "--json",
            "images",
            "normalize",
            "references/source.png",
            "normalized/cli-json",
            project,
            "--width",
            "128",
            "--height",
            "96",
            "--padding",
            "8",
            "--thumbnail-size",
            "32",
        ],
    )
    assert machine.exit_code == 0
    machine_payload = json.loads(machine.stdout)
    assert machine_payload["kind"] == "cli-response"
    assert machine_payload["command"] == "images normalize"
    assert machine_payload["ok"] is True
    assert machine_payload["data"]["state"] == "applied"

    error = runner.invoke(
        app,
        ["--json", "images", "normalize", "../outside.png", "normalized/error", project],
    )
    assert error.exit_code == 4
    error_payload = json.loads(error.stdout)
    assert error_payload["ok"] is False
    assert error_payload["error"]["code"] == "invalid-input"
