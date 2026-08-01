"""Deterministic PNG rendering for technical-sheet assembly."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from ludowright.contracts import TechnicalSheetTemplateLayoutContract
from ludowright.domain import SheetLayout
from ludowright.infrastructure.image_artifacts import (
    MAX_PNG_BYTES,
    PngValidation,
    validate_png_payload,
)

MAX_TECHNICAL_SHEET_INPUTS = 64
TECHNICAL_SHEET_LOCK = "technical-sheet-assembly"


class TechnicalSheetError(RuntimeError):
    """Base error for technical-sheet rendering."""


class TechnicalSheetValidationError(TechnicalSheetError):
    """Raised when an input image or layout cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class TechnicalSheetRenderInput:
    """One already-validated PNG payload supplied to the renderer."""

    input_id: str
    label: str
    payload: bytes
    validation: PngValidation


@dataclass(frozen=True, slots=True)
class TechnicalSheetPlacement:
    """One deterministic image slot in the rendered canvas."""

    index: int
    input_id: str
    label: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RenderedTechnicalSheet:
    """Encoded sheet output and the facts needed for its report."""

    payload: bytes
    validation: PngValidation
    layout: SheetLayout
    background: str
    canvas_width: int
    canvas_height: int
    cell_width: int
    cell_height: int
    margin: int
    gutter: int
    label_height: int
    placements: tuple[TechnicalSheetPlacement, ...]


class TechnicalSheetRenderer:
    """Render an ordered set of PNGs through one versioned layout rule."""

    def render(
        self,
        inputs: tuple[TechnicalSheetRenderInput, ...],
        layout: TechnicalSheetTemplateLayoutContract,
        *,
        background: str,
    ) -> RenderedTechnicalSheet:
        """Render all inputs in memory without filesystem side effects."""
        if not inputs:
            raise TechnicalSheetValidationError("technical sheets require at least one input")
        if len(inputs) > MAX_TECHNICAL_SHEET_INPUTS:
            raise TechnicalSheetValidationError(
                f"technical sheets support at most {MAX_TECHNICAL_SHEET_INPUTS} inputs"
            )
        images = tuple(_decode_png(item.payload) for item in inputs)
        rows = (len(inputs) + layout.columns - 1) // layout.columns
        slot_height = layout.cell_height + layout.label_height
        canvas_width = (
            layout.margin * 2
            + layout.columns * layout.cell_width
            + max(0, layout.columns - 1) * layout.gutter
        )
        canvas_height = layout.margin * 2 + rows * slot_height + max(0, rows - 1) * layout.gutter
        if canvas_width > 16_384 or canvas_height > 16_384:
            raise TechnicalSheetValidationError("technical-sheet canvas exceeds 16384 pixels")

        rgb_background = _rgb(background)
        canvas = Image.new("RGB", (canvas_width, canvas_height), rgb_background)
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        placements: list[TechnicalSheetPlacement] = []
        for index, (source, image) in enumerate(zip(inputs, images, strict=True), start=1):
            column = (index - 1) % layout.columns
            row = (index - 1) // layout.columns
            x = layout.margin + column * (layout.cell_width + layout.gutter)
            y = layout.margin + row * (slot_height + layout.gutter)
            fitted = ImageOps.contain(
                image,
                (layout.cell_width, layout.cell_height),
                method=Image.Resampling.LANCZOS,
            )
            image_x = x + (layout.cell_width - fitted.width) // 2
            image_y = y + (layout.cell_height - fitted.height) // 2
            canvas.paste(fitted, (image_x, image_y), fitted)
            draw.rectangle(
                (x, y, x + layout.cell_width - 1, y + layout.cell_height - 1),
                outline=(190, 190, 190),
                width=1,
            )
            label = _fit_label(draw, source.label, font, layout.cell_width)
            draw.text(
                (x, y + layout.cell_height + 4),
                label,
                fill=(32, 32, 32),
                font=font,
            )
            placements.append(
                TechnicalSheetPlacement(
                    index=index,
                    input_id=source.input_id,
                    label=source.label,
                    x=x,
                    y=y,
                    width=layout.cell_width,
                    height=layout.cell_height,
                )
            )

        payload = _encode_png(canvas)
        validation = validate_png_payload(payload)
        return RenderedTechnicalSheet(
            payload=payload,
            validation=validation,
            layout=layout.layout,
            background=background,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            cell_width=layout.cell_width,
            cell_height=layout.cell_height,
            margin=layout.margin,
            gutter=layout.gutter,
            label_height=layout.label_height,
            placements=tuple(placements),
        )


def _decode_png(payload: bytes) -> Image.Image:
    if not isinstance(payload, bytes):
        raise TechnicalSheetValidationError("technical-sheet inputs must be immutable bytes")
    if len(payload) > MAX_PNG_BYTES:
        raise TechnicalSheetValidationError("technical-sheet input exceeds the 64 MiB limit")
    try:
        with Image.open(BytesIO(payload)) as opened:
            if opened.format != "PNG":
                raise TechnicalSheetValidationError("technical-sheet inputs must be PNG images")
            if getattr(opened, "n_frames", 1) != 1:
                raise TechnicalSheetValidationError(
                    "animated technical-sheet inputs are not allowed"
                )
            opened.load()
            image = ImageOps.exif_transpose(opened).convert("RGBA")
            image.load()
            return image
    except TechnicalSheetValidationError:
        raise
    except (Image.DecompressionBombError, OSError, ValueError, UnidentifiedImageError) as error:
        raise TechnicalSheetValidationError("technical-sheet input is not a valid PNG") from error


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    payload = buffer.getvalue()
    if len(payload) > MAX_PNG_BYTES:
        raise TechnicalSheetValidationError("technical-sheet output exceeds the 64 MiB limit")
    return payload


def _rgb(color: str) -> tuple[int, int, int]:
    if (
        not isinstance(color, str)
        or len(color) != 7
        or color[0] != "#"
        or any(character not in "0123456789ABCDEF" for character in color[1:])
    ):
        raise TechnicalSheetValidationError("technical-sheet background must use #RRGGBB")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _fit_label(
    draw: ImageDraw.ImageDraw,
    label: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: int,
) -> str:
    if draw.textbbox((0, 0), label, font=font)[2] <= width:
        return label
    truncated = label
    while truncated and draw.textbbox((0, 0), f"{truncated}…", font=font)[2] > width:
        truncated = truncated[:-1]
    return f"{truncated}…" if truncated else "…"


__all__ = [
    "MAX_TECHNICAL_SHEET_INPUTS",
    "TECHNICAL_SHEET_LOCK",
    "RenderedTechnicalSheet",
    "TechnicalSheetError",
    "TechnicalSheetPlacement",
    "TechnicalSheetRenderInput",
    "TechnicalSheetRenderer",
    "TechnicalSheetValidationError",
]
