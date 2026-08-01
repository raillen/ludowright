"""Transactional application workflow for technical-sheet assembly."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from importlib import resources
from typing import Literal

from pydantic import ValidationError

from ludowright.contracts import (
    TechnicalSheetInputReportContract,
    TechnicalSheetOutputContract,
    TechnicalSheetPlacementContract,
    TechnicalSheetReportContract,
    TechnicalSheetRequestContract,
    TechnicalSheetTemplateContract,
    VisualReferenceContract,
)
from ludowright.domain import ReferenceStatus
from ludowright.infrastructure import (
    MAX_PNG_BYTES,
    TECHNICAL_SHEET_LOCK,
    ImageArtifactError,
    JsonDocumentRepository,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    TechnicalSheetRenderer,
    TechnicalSheetRenderInput,
    TechnicalSheetValidationError,
    VisualReviewRepository,
    validate_png_payload,
)

TECHNICAL_SHEET_MAX_BYTES = 2_000_000
TechnicalSheetState = Literal["planned", "applied", "unchanged"]


class TechnicalSheetError(RuntimeError):
    """Base error for technical-sheet assembly."""


class TechnicalSheetConflictError(TechnicalSheetError):
    """Raised when an output target already contains different content."""


class TechnicalSheetRollbackError(TechnicalSheetError):
    """Raised when cleanup after a failed assembly cannot complete safely."""


class TechnicalSheetRequestError(TechnicalSheetError):
    """Raised when a request or one of its approved inputs is invalid."""


@dataclass(frozen=True, slots=True)
class PreparedTechnicalSheet:
    """Complete rendered sheet and report held before filesystem mutation."""

    report: TechnicalSheetReportContract
    report_path: RepositoryPath
    output_path: RepositoryPath
    output_payload: bytes


@dataclass(frozen=True, slots=True)
class TechnicalSheetResult:
    """Stable application result returned to human and JSON CLI surfaces."""

    report: TechnicalSheetReportContract
    report_path: RepositoryPath
    output_path: RepositoryPath
    state: TechnicalSheetState
    dry_run: bool

    def as_data(self) -> dict[str, object]:
        """Return JSON-compatible result data for the CLI envelope."""
        return {
            "dry_run": self.dry_run,
            "output_path": self.output_path.value,
            "report": self.report.model_dump(mode="json"),
            "report_path": self.report_path.value,
            "sheet_kind": self.report.sheet_kind,
            "state": self.state,
            "template_id": self.report.template_id,
            "template_version": self.report.template_version,
            "warnings": list(self.report.warnings),
        }


class TechnicalSheetService:
    """Assemble approved PNG references into one deterministic sheet."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        renderer: TechnicalSheetRenderer | None = None,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("technical-sheet services require ProjectFilesystem")
        self._filesystem = filesystem
        self._renderer = renderer or TechnicalSheetRenderer()
        self._references = VisualReviewRepository(filesystem)

    def assemble(
        self,
        request_path: RepositoryPath,
        output_directory: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> TechnicalSheetResult:
        """Render one request, or only validate and plan it in dry-run mode."""
        if not isinstance(request_path, RepositoryPath):
            raise TypeError("technical-sheet requests require RepositoryPath")
        if not isinstance(output_directory, RepositoryPath):
            raise TypeError("technical-sheet outputs require RepositoryPath")
        if dry_run:
            prepared = self._prepare(request_path, output_directory)
            state = self._existing_state(prepared)
            return self._result(
                prepared,
                state="unchanged" if state == "unchanged" else "planned",
                dry_run=True,
            )

        with self._filesystem.lock(TECHNICAL_SHEET_LOCK, timeout=5.0):
            prepared = self._prepare(request_path, output_directory)
            state = self._existing_state(prepared)
            if state == "unchanged":
                return self._result(prepared, state="unchanged", dry_run=False)
            self._persist(prepared)
            return self._result(prepared, state="applied", dry_run=False)

    def _prepare(
        self,
        request_path: RepositoryPath,
        output_directory: RepositoryPath,
    ) -> PreparedTechnicalSheet:
        request_repository = JsonDocumentRepository(
            self._filesystem,
            request_path,
            TechnicalSheetRequestContract,
            max_bytes=TECHNICAL_SHEET_MAX_BYTES,
        )
        try:
            request_snapshot = request_repository.load()
        except FileNotFoundError as error:
            raise TechnicalSheetRequestError(
                f"technical-sheet request does not exist: {request_path}"
            ) from error
        except ValidationError as error:
            raise TechnicalSheetRequestError(
                f"technical-sheet request is invalid: {request_path}"
            ) from error

        request = request_snapshot.value
        template = _load_template(request.template_id, request.template_version)
        layout = next(item for item in template.layouts if item.sheet_kind == request.sheet_kind)
        output_path = output_directory.child("sheet.png")
        report_path = output_directory.child("technical-sheet.json")
        if request_path in {output_path, report_path}:
            raise TechnicalSheetRequestError(
                "technical-sheet request cannot be inside its own output targets"
            )

        render_inputs: list[TechnicalSheetRenderInput] = []
        input_reports: list[TechnicalSheetInputReportContract] = []
        for item in request.inputs:
            image_path = RepositoryPath(item.image_path)
            if image_path in {output_path, report_path}:
                raise TechnicalSheetRequestError(
                    f"technical-sheet input cannot be one of its output targets: {item.image_path}"
                )
            reference = self._load_approved_reference(item.reference_id)
            payload = self._read_input(image_path)
            try:
                validation = validate_png_payload(payload)
            except ImageArtifactError as error:
                raise TechnicalSheetRequestError(
                    f"technical-sheet input is not a valid PNG: {item.id}"
                ) from error
            if validation.sha256 != item.sha256:
                raise TechnicalSheetRequestError(
                    f"technical-sheet input checksum does not match its declaration: {item.id}"
                )
            if validation.width > 16_384 or validation.height > 16_384:
                raise TechnicalSheetRequestError(
                    f"technical-sheet input dimensions exceed the supported limit: {item.id}"
                )
            render_inputs.append(
                TechnicalSheetRenderInput(
                    input_id=item.id,
                    label=item.label,
                    payload=payload,
                    validation=validation,
                )
            )
            input_reports.append(
                TechnicalSheetInputReportContract(
                    id=item.id,
                    reference_id=reference.id,
                    image_path=image_path.value,
                    sha256=validation.sha256,
                    width=validation.width,
                    height=validation.height,
                )
            )

        try:
            rendered = self._renderer.render(
                tuple(render_inputs),
                layout,
                background=template.background,
            )
        except TechnicalSheetValidationError as error:
            raise TechnicalSheetRequestError(str(error)) from error

        output_validation = rendered.validation
        report = TechnicalSheetReportContract(
            id=request.id,
            name=request.name,
            request_path=request_path.value,
            request_sha256=hashlib.sha256(request_repository.canonical_bytes(request)).hexdigest(),
            template_id=template.template_id,
            template_version=template.template_version,
            sheet_kind=request.sheet_kind,
            layout=rendered.layout,
            background=rendered.background,
            canvas_width=rendered.canvas_width,
            canvas_height=rendered.canvas_height,
            cell_width=rendered.cell_width,
            cell_height=rendered.cell_height,
            margin=rendered.margin,
            gutter=rendered.gutter,
            label_height=rendered.label_height,
            inputs=tuple(input_reports),
            placements=tuple(
                TechnicalSheetPlacementContract(
                    index=placement.index,
                    input_id=placement.input_id,
                    label=placement.label,
                    x=placement.x,
                    y=placement.y,
                    width=placement.width,
                    height=placement.height,
                )
                for placement in rendered.placements
            ),
            output=TechnicalSheetOutputContract(
                path=output_path.value,
                sha256=output_validation.sha256,
                size_bytes=output_validation.size_bytes,
                width=output_validation.width,
                height=output_validation.height,
            ),
        )
        return PreparedTechnicalSheet(
            report=report,
            report_path=report_path,
            output_path=output_path,
            output_payload=rendered.payload,
        )

    def _load_approved_reference(self, reference_id: str) -> VisualReferenceContract:
        try:
            snapshot = self._references.load_reference(reference_id)
        except FileNotFoundError as error:
            raise TechnicalSheetRequestError(
                f"technical-sheet reference does not exist: {reference_id}"
            ) from error
        reference = snapshot.value
        if reference.status is not ReferenceStatus.APPROVED or reference.approval_id is None:
            raise TechnicalSheetRequestError(
                f"technical-sheet input reference is not approved: {reference_id}"
            )
        return reference

    def _read_input(self, path: RepositoryPath) -> bytes:
        try:
            return self._filesystem.read_bytes(path, max_bytes=MAX_PNG_BYTES)
        except FileNotFoundError as error:
            raise TechnicalSheetRequestError(
                f"technical-sheet input image does not exist: {path}"
            ) from error
        except ProjectFilesystemError as error:
            raise TechnicalSheetRequestError(
                f"technical-sheet input image cannot be read safely: {path}"
            ) from error

    def _existing_state(self, prepared: PreparedTechnicalSheet) -> Literal["new", "unchanged"]:
        paths = (prepared.output_path, prepared.report_path)
        existing = [os.path.lexists(self._filesystem.resolve(path)) for path in paths]
        if not any(existing):
            return "new"
        if not all(existing):
            raise TechnicalSheetConflictError(
                f"technical-sheet target is partially present: {prepared.report_path.parent}"
            )
        if (
            self._filesystem.read_bytes(
                prepared.output_path,
                max_bytes=len(prepared.output_payload),
            )
            != prepared.output_payload
        ):
            raise TechnicalSheetConflictError(
                "technical-sheet output already exists with different content: "
                f"{prepared.output_path}"
            )
        report_repository = JsonDocumentRepository(
            self._filesystem,
            prepared.report_path,
            TechnicalSheetReportContract,
            max_bytes=TECHNICAL_SHEET_MAX_BYTES,
        )
        if report_repository.canonical_bytes(prepared.report) != self._filesystem.read_bytes(
            prepared.report_path,
            max_bytes=TECHNICAL_SHEET_MAX_BYTES,
        ):
            raise TechnicalSheetConflictError(
                "technical-sheet report already exists with different content: "
                f"{prepared.report_path}"
            )
        return "unchanged"

    def _persist(self, prepared: PreparedTechnicalSheet) -> None:
        output_directory = prepared.report_path.parent
        if output_directory is None:
            raise TechnicalSheetError("technical-sheet output requires a parent directory")
        created_directories = _missing_directories(self._filesystem, output_directory)
        created_files: list[RepositoryPath] = []
        try:
            self._filesystem.ensure_directory(output_directory)
            _assert_absent(self._filesystem, prepared.output_path)
            self._filesystem.write_bytes(prepared.output_path, prepared.output_payload)
            created_files.append(prepared.output_path)
            _assert_absent(self._filesystem, prepared.report_path)
            report_repository = JsonDocumentRepository(
                self._filesystem,
                prepared.report_path,
                TechnicalSheetReportContract,
                max_bytes=TECHNICAL_SHEET_MAX_BYTES,
            )
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
                raise TechnicalSheetRollbackError(
                    "technical-sheet assembly failed and cleanup also failed: "
                    f"{prepared.report_path}"
                ) from error
            raise

    @staticmethod
    def _result(
        prepared: PreparedTechnicalSheet,
        *,
        state: TechnicalSheetState,
        dry_run: bool,
    ) -> TechnicalSheetResult:
        return TechnicalSheetResult(
            report=prepared.report,
            report_path=prepared.report_path,
            output_path=prepared.output_path,
            state=state,
            dry_run=dry_run,
        )


def _load_template(template_id: str, template_version: int) -> TechnicalSheetTemplateContract:
    resource_name = f"{template_id}.json"
    try:
        resource = resources.files("ludowright.sheet_data").joinpath(resource_name)
        template = TechnicalSheetTemplateContract.model_validate(
            json.loads(resource.read_text(encoding="utf-8"))
        )
    except (OSError, TypeError, ValueError, ValidationError) as error:
        raise TechnicalSheetRequestError(
            f"technical-sheet template is invalid: {template_id}"
        ) from error
    if template.template_id != template_id or template.template_version != template_version:
        raise TechnicalSheetRequestError(
            f"technical-sheet template revision is unavailable: {template_id} v{template_version}"
        )
    return template


def _assert_absent(filesystem: ProjectFilesystem, path: RepositoryPath) -> None:
    if os.path.lexists(filesystem.resolve(path)):
        raise TechnicalSheetConflictError(f"technical-sheet target already exists: {path}")


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
    "PreparedTechnicalSheet",
    "TechnicalSheetConflictError",
    "TechnicalSheetError",
    "TechnicalSheetRequestError",
    "TechnicalSheetResult",
    "TechnicalSheetRollbackError",
    "TechnicalSheetService",
]
