"""Contracts for deterministic derived asset workbooks."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    NonNegativeRevision,
    PositiveRevision,
    RepositoryPathText,
    ReviewText,
    Sha256Text,
    Slug,
)

WorkbookExportState = Literal["planned", "exported"]
WorkbookGraphState = Literal["current", "absent"]
WorkbookSheetName = Literal[
    "Overview",
    "Components",
    "References",
    "Status",
    "Priority",
    "Dependencies",
]
TemplateFieldId = Annotated[
    str,
    Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]


class AssetWorkbookColumnContract(ContractModel):
    """One data-defined column in a workbook view."""

    id: TemplateFieldId
    label: DisplayText


class AssetWorkbookSheetContract(ContractModel):
    """One ordered workbook sheet definition."""

    id: Slug
    name: WorkbookSheetName
    columns: tuple[AssetWorkbookColumnContract, ...]

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        column_ids = tuple(column.id for column in self.columns)
        if not column_ids:
            raise ValueError("an asset workbook sheet requires columns")
        if len(column_ids) != len(set(column_ids)):
            raise ValueError("asset workbook sheet column IDs must be unique")
        return self


class AssetWorkbookTemplateContract(ContractModel):
    """Versioned packaged data defining the asset workbook views."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-workbook-template"] = "asset-workbook-template"
    template_id: Slug
    template_version: PositiveRevision
    sheets: tuple[AssetWorkbookSheetContract, ...]

    @model_validator(mode="after")
    def validate_sheets(self) -> Self:
        sheet_ids = tuple(sheet.id for sheet in self.sheets)
        sheet_names = tuple(sheet.name for sheet in self.sheets)
        required_names = (
            "Overview",
            "Components",
            "References",
            "Status",
            "Priority",
            "Dependencies",
        )
        if sheet_names != required_names:
            raise ValueError("asset workbook template must define the six canonical sheets")
        if len(sheet_ids) != len(set(sheet_ids)):
            raise ValueError("asset workbook sheet IDs must be unique")
        if len(sheet_names) != len(set(sheet_names)):
            raise ValueError("asset workbook sheet names must be unique")
        return self


class AssetWorkbookSheetRowCountContract(ContractModel):
    """Deterministic row count for one exported sheet."""

    sheet: WorkbookSheetName
    rows: Annotated[int, Field(ge=0, le=500_000)]


class AssetWorkbookExportReportContract(ContractModel):
    """Stable report for an ODS export or dry-run plan."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-workbook-export-report"] = "asset-workbook-export-report"
    state: WorkbookExportState
    dry_run: bool
    output_path: RepositoryPathText
    template_id: Slug
    template_version: PositiveRevision
    sheet_names: tuple[WorkbookSheetName, ...]
    sheet_row_counts: tuple[AssetWorkbookSheetRowCountContract, ...]
    registry_path: RepositoryPathText
    registry_version: PositiveRevision
    state_store_schema_version: PositiveRevision
    dependency_graph_path: RepositoryPathText
    dependency_graph_revision: NonNegativeRevision
    dependency_graph_state: WorkbookGraphState
    asset_count: Annotated[int, Field(ge=0, le=100_000)]
    source_digest: Sha256Text
    output_sha256: Sha256Text
    warnings: tuple[ReviewText, ...] = ()
    valid: bool = True

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        expected_names = tuple(item.sheet for item in self.sheet_row_counts)
        if expected_names != self.sheet_names:
            raise ValueError("workbook report sheet counts must follow template order")
        if tuple(sorted(self.warnings)) != self.warnings:
            raise ValueError("workbook report warnings must be sorted")
        if self.dependency_graph_state == "absent" and self.dependency_graph_revision != 0:
            raise ValueError("an absent dependency graph must have revision zero")
        if self.dependency_graph_state == "current" and self.dependency_graph_revision < 1:
            raise ValueError("a current dependency graph requires a positive revision")
        return self
