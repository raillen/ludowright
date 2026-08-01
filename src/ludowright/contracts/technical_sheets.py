"""Versioned contracts for deterministic technical-sheet assembly."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    RepositoryPathText,
    Sha256Text,
    Slug,
)
from ludowright.domain import SheetLayout

TechnicalSheetKind = Literal["turnaround", "component", "prop", "detail", "scale"]
TechnicalSheetKinds = (
    "turnaround",
    "component",
    "prop",
    "detail",
    "scale",
)
HexColorText = Annotated[str, StringConstraints(pattern=r"^#[0-9A-F]{6}$")]
CanvasDimension = Annotated[int, Field(ge=64, le=16_384)]
CellDimension = Annotated[int, Field(ge=64, le=4_096)]
Coordinate = Annotated[int, Field(ge=0, le=16_383)]
PositiveSize = Annotated[int, Field(ge=1, le=16_384)]


class TechnicalSheetTemplateLayoutContract(ContractModel):
    """One data-defined layout rule selected by a sheet kind."""

    sheet_kind: TechnicalSheetKind
    layout: SheetLayout
    columns: Annotated[int, Field(ge=1, le=16)]
    cell_width: CellDimension
    cell_height: CellDimension
    margin: Annotated[int, Field(ge=0, le=512)]
    gutter: Annotated[int, Field(ge=0, le=512)]
    label_height: Annotated[int, Field(ge=0, le=512)]


class TechnicalSheetTemplateContract(ContractModel):
    """Versioned data pack for the supported technical-sheet layouts."""

    schema_version: Literal[1] = 1
    kind: Literal["technical-sheet-template"] = "technical-sheet-template"
    template_id: Slug
    template_version: PositiveRevision
    name: DisplayText
    background: HexColorText
    layouts: tuple[TechnicalSheetTemplateLayoutContract, ...]

    @model_validator(mode="after")
    def validate_template(self) -> Self:
        expected = TechnicalSheetKinds
        actual = tuple(layout.sheet_kind for layout in self.layouts)
        if actual != expected:
            raise ValueError("technical-sheet template layouts must use canonical kind order")
        return self


class TechnicalSheetInputContract(ContractModel):
    """One approved reference and its exact normalized PNG input."""

    id: Slug
    label: DisplayText
    reference_id: Slug
    image_path: RepositoryPathText
    sha256: Sha256Text

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if not self.image_path.endswith(".png"):
            raise ValueError("technical-sheet inputs must use PNG image paths")
        return self


class TechnicalSheetRequestContract(ContractModel):
    """Canonical request consumed by the local sheet assembler."""

    schema_version: Literal[1] = 1
    kind: Literal["technical-sheet-request"] = "technical-sheet-request"
    id: Slug
    name: DisplayText
    template_id: Slug
    template_version: PositiveRevision
    sheet_kind: TechnicalSheetKind
    inputs: tuple[TechnicalSheetInputContract, ...]

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not self.inputs:
            raise ValueError("technical-sheet requests require at least one input")
        input_ids = tuple(item.id for item in self.inputs)
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("technical-sheet input IDs must be unique")
        reference_ids = tuple(item.reference_id for item in self.inputs)
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("technical-sheet reference IDs must be unique")
        image_paths = tuple(item.image_path for item in self.inputs)
        if len(image_paths) != len(set(image_paths)):
            raise ValueError("technical-sheet image paths must be unique")
        return self


class TechnicalSheetInputReportContract(ContractModel):
    """Validated facts for one input used by an assembled sheet."""

    id: Slug
    reference_id: Slug
    image_path: RepositoryPathText
    sha256: Sha256Text
    width: PositiveSize
    height: PositiveSize


class TechnicalSheetPlacementContract(ContractModel):
    """Deterministic position of one input inside the output canvas."""

    index: Annotated[int, Field(ge=1, le=64)]
    input_id: Slug
    label: DisplayText
    x: Coordinate
    y: Coordinate
    width: PositiveSize
    height: PositiveSize


class TechnicalSheetOutputContract(ContractModel):
    """The atomically-created PNG sheet artifact."""

    path: RepositoryPathText
    format: Literal["png"] = "png"
    sha256: Sha256Text
    size_bytes: Annotated[int, Field(ge=1, le=64 * 1024 * 1024)]
    width: PositiveSize
    height: PositiveSize


class TechnicalSheetReportContract(ContractModel):
    """Canonical provenance and placement report for one technical sheet."""

    schema_version: Literal[1] = 1
    kind: Literal["technical-sheet"] = "technical-sheet"
    id: Slug
    name: DisplayText
    request_path: RepositoryPathText
    request_sha256: Sha256Text
    template_id: Slug
    template_version: PositiveRevision
    sheet_kind: TechnicalSheetKind
    layout: SheetLayout
    background: HexColorText
    canvas_width: CanvasDimension
    canvas_height: CanvasDimension
    cell_width: CellDimension
    cell_height: CellDimension
    margin: Annotated[int, Field(ge=0, le=512)]
    gutter: Annotated[int, Field(ge=0, le=512)]
    label_height: Annotated[int, Field(ge=0, le=512)]
    inputs: tuple[TechnicalSheetInputReportContract, ...]
    placements: tuple[TechnicalSheetPlacementContract, ...]
    output: TechnicalSheetOutputContract
    warnings: tuple[DisplayText, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if (self.output.width, self.output.height) != (self.canvas_width, self.canvas_height):
            raise ValueError("technical-sheet output dimensions must match the canvas")
        input_ids = tuple(item.id for item in self.inputs)
        placement_ids = tuple(item.input_id for item in self.placements)
        if not input_ids or input_ids != placement_ids:
            raise ValueError("technical-sheet placements must follow input order")
        if tuple(item.index for item in self.placements) != tuple(
            range(1, len(self.placements) + 1)
        ):
            raise ValueError("technical-sheet placement indexes must be contiguous")
        for placement in self.placements:
            if placement.x + placement.width > self.canvas_width:
                raise ValueError("technical-sheet placement exceeds canvas width")
            if placement.y + placement.height > self.canvas_height:
                raise ValueError("technical-sheet placement exceeds canvas height")
        return self


__all__ = [
    "TechnicalSheetInputContract",
    "TechnicalSheetInputReportContract",
    "TechnicalSheetKind",
    "TechnicalSheetKinds",
    "TechnicalSheetOutputContract",
    "TechnicalSheetPlacementContract",
    "TechnicalSheetReportContract",
    "TechnicalSheetRequestContract",
    "TechnicalSheetTemplateContract",
    "TechnicalSheetTemplateLayoutContract",
]
