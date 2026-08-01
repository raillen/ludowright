"""Transactional application workflow for image normalization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from ludowright.contracts import ImageNormalizationReportContract
from ludowright.infrastructure import (
    IMAGE_NORMALIZATION_LOCK,
    MAX_INPUT_IMAGE_BYTES,
    ImageNormalizationError,
    ImageNormalizationOptions,
    ImageNormalizationValidationError,
    ImageNormalizer,
    PreparedImageNormalization,
    ProjectFilesystem,
    RepositoryPath,
)
from ludowright.infrastructure.structured import JsonDocumentRepository


class ImageNormalizationConflictError(ImageNormalizationError):
    """Raised when normalization would overwrite an existing artifact."""


class ImageNormalizationRollbackError(ImageNormalizationError):
    """Raised when a failed normalization cannot clean its own artifacts."""


ImageNormalizationState = Literal["planned", "applied", "unchanged"]


@dataclass(frozen=True, slots=True)
class ImageNormalizationResult:
    """Stable result returned by the normalization use case."""

    report: ImageNormalizationReportContract
    report_path: RepositoryPath
    state: ImageNormalizationState
    dry_run: bool

    def as_data(self) -> dict[str, object]:
        """Return JSON-compatible result data for the CLI envelope."""
        return {
            "dry_run": self.dry_run,
            "output_paths": [output.path for output in self.report.outputs],
            "report": self.report.model_dump(mode="json"),
            "report_path": self.report_path.value,
            "source_path": self.report.source_path,
            "state": self.state,
        }


class ImageNormalizationService:
    """Prepare and persist one image normalization transaction."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        self._filesystem = filesystem
        self._normalizer = ImageNormalizer()

    def normalize(
        self,
        source_path: RepositoryPath,
        output_directory: RepositoryPath,
        *,
        options: ImageNormalizationOptions | None = None,
        dry_run: bool = False,
    ) -> ImageNormalizationResult:
        """Normalize one source image, or only plan it when dry-run is enabled."""
        if not isinstance(source_path, RepositoryPath):
            raise TypeError("source path must be a RepositoryPath")
        if not isinstance(output_directory, RepositoryPath):
            raise TypeError("output directory must be a RepositoryPath")
        if dry_run:
            prepared = self._prepare(source_path, output_directory, options)
            state = self._existing_state(prepared)
            return ImageNormalizationResult(
                report=prepared.report,
                report_path=prepared.report_path,
                state="unchanged" if state == "unchanged" else "planned",
                dry_run=True,
            )

        with self._filesystem.lock(IMAGE_NORMALIZATION_LOCK, timeout=5.0):
            prepared = self._prepare(source_path, output_directory, options)
            state = self._existing_state(prepared)
            if state == "unchanged":
                return ImageNormalizationResult(
                    report=prepared.report,
                    report_path=prepared.report_path,
                    state="unchanged",
                    dry_run=False,
                )
            self._persist(prepared)
            return ImageNormalizationResult(
                report=prepared.report,
                report_path=prepared.report_path,
                state="applied",
                dry_run=False,
            )

    def _prepare(
        self,
        source_path: RepositoryPath,
        output_directory: RepositoryPath,
        options: ImageNormalizationOptions | None,
    ) -> PreparedImageNormalization:
        try:
            payload = self._filesystem.read_bytes(source_path, max_bytes=MAX_INPUT_IMAGE_BYTES)
        except FileNotFoundError as error:
            raise ImageNormalizationValidationError(
                f"source image does not exist: {source_path.value}"
            ) from error
        return self._normalizer.prepare(
            payload,
            source_path=source_path,
            output_directory=output_directory,
            options=options,
        )

    def _existing_state(self, prepared: PreparedImageNormalization) -> Literal["new", "unchanged"]:
        paths = (*tuple(artifact.path for artifact in prepared.artifacts), prepared.report_path)
        existing = [os.path.lexists(self._filesystem.resolve(path)) for path in paths]
        if not any(existing):
            return "new"
        if not all(existing):
            raise ImageNormalizationConflictError(
                f"normalization target is partially present: {prepared.report_path.parent}"
            )
        for artifact in prepared.artifacts:
            if (
                self._filesystem.read_bytes(
                    artifact.path,
                    max_bytes=len(artifact.payload),
                )
                != artifact.payload
            ):
                raise ImageNormalizationConflictError(
                    f"normalization output already exists with different content: {artifact.path}"
                )
        report_repository = _report_repository(self._filesystem, prepared.report_path)
        if report_repository.canonical_bytes(prepared.report) != self._filesystem.read_bytes(
            prepared.report_path,
            max_bytes=2_000_000,
        ):
            raise ImageNormalizationConflictError(
                "normalization report already exists with different content: "
                f"{prepared.report_path}"
            )
        return "unchanged"

    def _persist(self, prepared: PreparedImageNormalization) -> None:
        output_directory = prepared.report_path.parent
        if output_directory is None:
            raise ImageNormalizationError("normalization report must have an output directory")
        created_directories = _missing_directories(self._filesystem, output_directory)
        created_files: list[RepositoryPath] = []
        try:
            self._filesystem.ensure_directory(output_directory)
            for artifact in prepared.artifacts:
                self._assert_target_absent(artifact.path)
                self._filesystem.write_bytes(artifact.path, artifact.payload)
                created_files.append(artifact.path)
            self._assert_target_absent(prepared.report_path)
            report_repository = _report_repository(self._filesystem, prepared.report_path)
            self._filesystem.write_bytes(
                prepared.report_path,
                report_repository.canonical_bytes(prepared.report),
            )
            created_files.append(prepared.report_path)
        except BaseException as error:
            rollback_errors: list[BaseException] = []
            for path in reversed(created_files):
                try:
                    self._filesystem.remove_file(path)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
            for path in reversed(created_directories):
                try:
                    self._filesystem.remove_empty_directory(path)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise ImageNormalizationRollbackError(
                    f"normalization failed and cleanup also failed: {prepared.report_path}"
                ) from error
            raise

    def _assert_target_absent(self, path: RepositoryPath) -> None:
        if os.path.lexists(self._filesystem.resolve(path)):
            raise ImageNormalizationConflictError(f"normalization target already exists: {path}")


def _report_repository(
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
) -> JsonDocumentRepository[ImageNormalizationReportContract]:
    return JsonDocumentRepository(filesystem, path, ImageNormalizationReportContract)


def _missing_directories(
    filesystem: ProjectFilesystem,
    directory: RepositoryPath,
) -> tuple[RepositoryPath, ...]:
    missing: list[RepositoryPath] = []
    for index in range(1, len(directory.parts) + 1):
        candidate = RepositoryPath("/".join(directory.parts[:index]))
        if not os.path.lexists(filesystem.resolve(candidate)):
            missing.append(candidate)
    return tuple(missing)


__all__ = [
    "ImageNormalizationConflictError",
    "ImageNormalizationResult",
    "ImageNormalizationRollbackError",
    "ImageNormalizationService",
]
