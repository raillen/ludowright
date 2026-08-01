"""Safe deterministic OpenDocument Spreadsheet generation."""

from __future__ import annotations

import hashlib
import io
import os
import threading
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath

ODS_MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"
ODS_LOCK_NAME = "asset-workbook"
_ODS_MAX_BYTES = 64 * 1024 * 1024
_ODS_MAX_ENTRIES = 128
_TABLE_NAMESPACE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_RENDER_LOCK = threading.Lock()

OdsCell = str | int | bool | None


class OdsWorkbookError(RuntimeError):
    """Base failure for workbook generation or validation."""


class OdsWorkbookConflictError(OdsWorkbookError):
    """Raised when an ODS target already exists."""


@dataclass(frozen=True, slots=True)
class OdsSheet:
    """One deterministic sheet ready for rendering."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[OdsCell, ...], ...]
    preamble: tuple[tuple[OdsCell, ...], ...] = ()

    def __post_init__(self) -> None:
        if not self.name or not self.columns:
            raise OdsWorkbookError("an ODS sheet requires a name and columns")
        if len(self.columns) != len(set(self.columns)):
            raise OdsWorkbookError("ODS sheet columns must be unique")
        for row in (*self.preamble, *self.rows):
            if len(row) > len(self.columns):
                raise OdsWorkbookError("an ODS row cannot exceed the sheet column count")


@dataclass(frozen=True, slots=True)
class OdsWorkbook:
    """A complete deterministic workbook projection."""

    sheets: tuple[OdsSheet, ...]

    def __post_init__(self) -> None:
        names = tuple(sheet.name for sheet in self.sheets)
        if not names or len(names) != len(set(names)):
            raise OdsWorkbookError("an ODS workbook requires unique sheets")


@dataclass(frozen=True, slots=True)
class OdsValidation:
    """Validation facts extracted from one generated ODS package."""

    sheet_names: tuple[str, ...]
    package_sha256: str
    size_bytes: int


class OdsWorkbookWriter:
    """Render and safely create deterministic ODS files."""

    def render(self, workbook: OdsWorkbook) -> bytes:
        """Render one workbook into canonical ZIP bytes without writing files."""
        with _RENDER_LOCK:
            raw = _render_with_odfpy(workbook)
        payload = _canonicalize_zip(raw)
        self.validate(payload, expected_sheet_names=tuple(sheet.name for sheet in workbook.sheets))
        return payload

    def validate(
        self,
        payload: bytes,
        *,
        expected_sheet_names: tuple[str, ...],
    ) -> OdsValidation:
        """Validate package safety, required parts, and canonical sheet order."""
        if not isinstance(payload, bytes) or not payload:
            raise OdsWorkbookError("an ODS package must contain bytes")
        if len(payload) > _ODS_MAX_BYTES:
            raise OdsWorkbookError(f"an ODS package cannot exceed {_ODS_MAX_BYTES} bytes")
        try:
            with ZipFile(io.BytesIO(payload)) as archive:
                infos = archive.infolist()
                names = tuple(info.filename for info in infos)
                if len(names) != len(set(names)):
                    raise OdsWorkbookError("an ODS package cannot contain duplicate entries")
                if len(names) > _ODS_MAX_ENTRIES:
                    raise OdsWorkbookError("an ODS package contains too many entries")
                if not names or names[0] != "mimetype":
                    raise OdsWorkbookError("an ODS package must start with mimetype")
                if archive.getinfo("mimetype").compress_type != ZIP_STORED:
                    raise OdsWorkbookError("the ODS mimetype entry must be uncompressed")
                if archive.read("mimetype").decode("ascii") != ODS_MIMETYPE:
                    raise OdsWorkbookError("the ODS mimetype entry is invalid")
                required = {
                    "mimetype",
                    "content.xml",
                    "styles.xml",
                    "meta.xml",
                    "META-INF/manifest.xml",
                }
                if not required.issubset(names):
                    missing = ", ".join(sorted(required.difference(names)))
                    raise OdsWorkbookError(f"an ODS package is missing entries: {missing}")
                total_uncompressed = 0
                for info in infos:
                    if info.file_size > _ODS_MAX_BYTES:
                        raise OdsWorkbookError("an ODS entry exceeds the package size limit")
                    total_uncompressed += info.file_size
                if total_uncompressed > _ODS_MAX_BYTES:
                    raise OdsWorkbookError("uncompressed ODS content exceeds the package limit")
                root = ElementTree.fromstring(archive.read("content.xml"))
        except (BadZipFile, KeyError, UnicodeDecodeError, ElementTree.ParseError) as error:
            raise OdsWorkbookError("the generated ODS package is malformed") from error

        tables = tuple(root.findall(f".//{{{_TABLE_NAMESPACE}}}table"))
        actual_sheet_names = tuple(
            table.attrib.get(f"{{{_TABLE_NAMESPACE}}}name", "") for table in tables
        )
        if actual_sheet_names != expected_sheet_names:
            raise OdsWorkbookError("ODS sheet names or order differ from the workbook template")
        return OdsValidation(
            sheet_names=actual_sheet_names,
            package_sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    def create(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath,
        payload: bytes,
        *,
        timeout: float = 5.0,
    ) -> None:
        """Create an ODS target atomically without replacing an existing file."""
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("ODS creation requires ProjectFilesystem")
        if not isinstance(path, RepositoryPath):
            raise TypeError("ODS creation requires RepositoryPath")
        if not path.name.endswith(".ods"):
            raise OdsWorkbookError("ODS output paths must use the .ods extension")
        self.validate(payload, expected_sheet_names=self._sheet_names(payload))
        with filesystem.lock(ODS_LOCK_NAME, timeout=timeout):
            try:
                filesystem.read_bytes(path, max_bytes=_ODS_MAX_BYTES)
            except FileNotFoundError:
                created_parents = _missing_parent_directories(filesystem, path)
                try:
                    filesystem.write_bytes(path, payload)
                except BaseException:
                    _remove_empty_directories(created_parents)
                    raise
                return
            raise OdsWorkbookConflictError(
                f"ODS output already exists and will not be overwritten: {path}"
            )

    def _sheet_names(self, payload: bytes) -> tuple[str, ...]:
        try:
            with ZipFile(io.BytesIO(payload)) as archive:
                root = ElementTree.fromstring(archive.read("content.xml"))
        except (BadZipFile, KeyError, ElementTree.ParseError) as error:
            raise OdsWorkbookError("the generated ODS package is malformed") from error
        return tuple(
            table.attrib.get(f"{{{_TABLE_NAMESPACE}}}name", "")
            for table in root.findall(f".//{{{_TABLE_NAMESPACE}}}table")
        )


def _render_with_odfpy(workbook: OdsWorkbook) -> bytes:
    """Build ODF elements through a dynamic import because ODFPy has no stubs."""
    document_module = import_module("odf.opendocument")
    style_module = import_module("odf.style")
    table_module = import_module("odf.table")
    text_module = import_module("odf.text")
    element_module = import_module("odf.element")

    element_class = element_module.Element
    element_class.namespaces.clear()
    open_document = _callable(document_module.OpenDocumentSpreadsheet)
    style = _callable(style_module.Style)
    text_properties = _callable(style_module.TextProperties)
    table = _callable(table_module.Table)
    table_column = _callable(table_module.TableColumn)
    table_row = _callable(table_module.TableRow)
    table_cell = _callable(table_module.TableCell)
    paragraph = _callable(text_module.P)

    document: Any = open_document()
    header_style: Any = style(name="HeaderCell", family="table-cell")
    header_style.addElement(text_properties(fontweight="bold"))
    document.automaticstyles.addElement(header_style)

    for sheet in workbook.sheets:
        table_element: Any = table(name=sheet.name)
        for _ in sheet.columns:
            table_element.addElement(table_column())
        ordered_rows = (
            *((row, False) for row in sheet.preamble),
            ((tuple(sheet.columns)), True),
            *((row, False) for row in sheet.rows),
        )
        for row, is_header in ordered_rows:
            row_element: Any = table_row()
            for _index, value in enumerate(row):
                row_element.addElement(
                    _cell(
                        table_cell,
                        paragraph,
                        value,
                        style_name="HeaderCell" if is_header else None,
                    )
                )
            for _ in range(len(row), len(sheet.columns)):
                row_element.addElement(_cell(table_cell, paragraph, None))
            table_element.addElement(row_element)
        document.spreadsheet.addElement(table_element)

    output = io.BytesIO()
    document.write(output)
    return output.getvalue()


def _cell(
    table_cell: Callable[..., Any],
    paragraph: Callable[..., Any],
    value: OdsCell,
    *,
    style_name: str | None = None,
) -> Any:
    if isinstance(value, bool):
        cell = table_cell(
            valuetype="boolean",
            booleanvalue="true" if value else "false",
            stylename=style_name,
        )
        text = "true" if value else "false"
    elif isinstance(value, int):
        cell = table_cell(valuetype="float", value=str(value), stylename=style_name)
        text = str(value)
    else:
        cell = table_cell(valuetype="string", stylename=style_name)
        text = "" if value is None else value
    cell.addElement(paragraph(text=text))
    return cell


def _canonicalize_zip(payload: bytes) -> bytes:
    try:
        with ZipFile(io.BytesIO(payload)) as source:
            names = source.namelist()
            ordered_names = ("mimetype", *sorted(name for name in names if name != "mimetype"))
            output = io.BytesIO()
            with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as target:
                for name in ordered_names:
                    info = ZipInfo(name, _FIXED_ZIP_TIMESTAMP)
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    info.compress_type = ZIP_STORED if name == "mimetype" else ZIP_DEFLATED
                    target.writestr(info, source.read(name))
            return output.getvalue()
    except (BadZipFile, KeyError) as error:
        raise OdsWorkbookError("ODFPy produced an invalid ZIP package") from error


def _callable(value: object) -> Callable[..., Any]:
    if not callable(value):
        raise OdsWorkbookError("ODFPy is missing a required constructor")
    return value


def _missing_parent_directories(
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
) -> tuple[os.PathLike[str], ...]:
    """Record parent directories that this create operation may need to add."""
    if path.parent is None:
        return ()
    current = filesystem.root
    missing: list[os.PathLike[str]] = []
    for segment in path.parent.parts:
        current = current / segment
        if not os.path.lexists(current):
            missing.append(current)
    return tuple(missing)


def _remove_empty_directories(directories: tuple[os.PathLike[str], ...]) -> None:
    """Remove only empty directories known to have been absent before a write."""
    for directory in reversed(directories):
        try:
            os.rmdir(directory)
        except OSError:
            break
