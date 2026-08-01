"""Deterministic pixel normalization behind the application boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from ludowright.contracts import (
    ImageNormalizationBoundsContract,
    ImageNormalizationOutputContract,
    ImageNormalizationPaddingContract,
    ImageNormalizationReportContract,
)
from ludowright.infrastructure.filesystem import RepositoryPath
from ludowright.infrastructure.image_artifacts import MAX_PNG_BYTES, validate_png_payload

MAX_INPUT_IMAGE_BYTES = 64 * 1024 * 1024
MAX_INPUT_IMAGE_PIXELS = 64 * 1024 * 1024
MAX_IMAGE_DIMENSION = 16_384
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
DEFAULT_CANVAS_WIDTH = 1_024
DEFAULT_CANVAS_HEIGHT = 1_024
DEFAULT_PADDING = 64
DEFAULT_THUMBNAIL_SIZE = 256
DEFAULT_NEUTRAL_BACKGROUND = "#F2F2F2"
IMAGE_NORMALIZATION_LOCK = "image-normalization"
ImageNormalizationArtifact = Literal["normalized", "neutral", "thumbnail", "alignment-guide"]


class ImageNormalizationError(RuntimeError):
    """Base error for image normalization."""


class ImageNormalizationValidationError(ImageNormalizationError):
    """Raised when input bytes or options cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class ImageNormalizationOptions:
    """Bounded options shared by the application and image adapter."""

    canvas_width: int = DEFAULT_CANVAS_WIDTH
    canvas_height: int = DEFAULT_CANVAS_HEIGHT
    padding: int = DEFAULT_PADDING
    thumbnail_size: int = DEFAULT_THUMBNAIL_SIZE
    neutral_background: str = DEFAULT_NEUTRAL_BACKGROUND

    def __post_init__(self) -> None:
        for label, value in (
            ("canvas width", self.canvas_width),
            ("canvas height", self.canvas_height),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ImageNormalizationValidationError(f"{label} must be an integer")
            if not 64 <= value <= MAX_IMAGE_DIMENSION:
                raise ImageNormalizationValidationError(
                    f"{label} must be between 64 and {MAX_IMAGE_DIMENSION}"
                )
        if isinstance(self.padding, bool) or not isinstance(self.padding, int):
            raise ImageNormalizationValidationError("padding must be an integer")
        if self.padding < 0 or self.padding * 2 >= min(self.canvas_width, self.canvas_height):
            raise ImageNormalizationValidationError(
                "padding must leave at least one pixel for the fitted subject"
            )
        if isinstance(self.thumbnail_size, bool) or not isinstance(self.thumbnail_size, int):
            raise ImageNormalizationValidationError("thumbnail size must be an integer")
        if not 16 <= self.thumbnail_size <= 4_096:
            raise ImageNormalizationValidationError("thumbnail size must be between 16 and 4096")
        if (
            not isinstance(self.neutral_background, str)
            or len(self.neutral_background) != 7
            or self.neutral_background[0] != "#"
            or any(character not in "0123456789ABCDEF" for character in self.neutral_background[1:])
        ):
            raise ImageNormalizationValidationError(
                "neutral background must use uppercase #RRGGBB notation"
            )

    @property
    def cache_key(self) -> str:
        """Return the canonical option representation used in deterministic IDs."""
        return (
            f"{self.canvas_width}x{self.canvas_height}:"
            f"{self.padding}:{self.thumbnail_size}:{self.neutral_background}"
        )


@dataclass(frozen=True, slots=True)
class PreparedImageNormalizationArtifact:
    """One encoded output prepared before any filesystem mutation."""

    artifact: ImageNormalizationArtifact
    path: RepositoryPath
    payload: bytes
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PreparedImageNormalization:
    """Complete deterministic output set held in memory for a transaction."""

    report: ImageNormalizationReportContract
    report_path: RepositoryPath
    artifacts: tuple[PreparedImageNormalizationArtifact, ...]


class ImageNormalizer:
    """Decode, orient, fit, and encode one bounded source image."""

    def prepare(
        self,
        payload: bytes,
        *,
        source_path: RepositoryPath,
        output_directory: RepositoryPath,
        options: ImageNormalizationOptions | None = None,
    ) -> PreparedImageNormalization:
        """Prepare all deterministic PNGs without touching the filesystem."""
        if not isinstance(payload, bytes):
            raise ImageNormalizationValidationError("source image must be immutable bytes")
        if len(payload) > MAX_INPUT_IMAGE_BYTES:
            raise ImageNormalizationValidationError("source image exceeds the 64 MiB limit")
        if not isinstance(source_path, RepositoryPath):
            raise TypeError("source path must be a RepositoryPath")
        if not isinstance(output_directory, RepositoryPath):
            raise TypeError("output directory must be a RepositoryPath")
        selected_options = options or ImageNormalizationOptions()
        image, source_format, source_width, source_height, orientation = _decode_image(payload)
        source_sha256 = hashlib.sha256(payload).hexdigest()
        source_bounds = image.getchannel("A").getbbox()
        if source_bounds is None:
            raise ImageNormalizationValidationError("source image contains no visible pixels")

        left, top, right, bottom = source_bounds
        cropped = image.crop((left, top, right, bottom))
        inner_width = selected_options.canvas_width - selected_options.padding * 2
        inner_height = selected_options.canvas_height - selected_options.padding * 2
        fitted_width, fitted_height = _fit_dimensions(
            cropped.width,
            cropped.height,
            inner_width,
            inner_height,
        )
        fitted = cropped.resize(
            (fitted_width, fitted_height),
            resample=Image.Resampling.LANCZOS,
        )
        offset_left = (selected_options.canvas_width - fitted_width) // 2
        offset_top = (selected_options.canvas_height - fitted_height) // 2
        normalized = Image.new(
            "RGBA",
            (selected_options.canvas_width, selected_options.canvas_height),
            (0, 0, 0, 0),
        )
        normalized.alpha_composite(fitted, (offset_left, offset_top))

        neutral = Image.new(
            "RGBA",
            (selected_options.canvas_width, selected_options.canvas_height),
            (*_rgb(selected_options.neutral_background), 255),
        )
        neutral.alpha_composite(normalized)
        neutral_rgb = neutral.convert("RGB")

        thumbnail = normalized.resize(
            (selected_options.thumbnail_size, selected_options.thumbnail_size),
            resample=Image.Resampling.LANCZOS,
        )
        alignment_guide = normalized.copy()
        _draw_alignment_guides(
            alignment_guide,
            left=offset_left,
            top=offset_top,
            right=offset_left + fitted_width - 1,
            bottom=offset_top + fitted_height - 1,
        )

        operation_id = (
            "norm-"
            + hashlib.sha256(
                f"{source_sha256}:{source_path.value}:{output_directory.value}:"
                f"{selected_options.cache_key}".encode("ascii")
            ).hexdigest()[:32]
        )
        output_images: tuple[tuple[ImageNormalizationArtifact, Image.Image], ...] = (
            ("normalized", normalized),
            ("neutral", neutral_rgb),
            ("thumbnail", thumbnail),
            ("alignment-guide", alignment_guide),
        )
        artifacts: list[PreparedImageNormalizationArtifact] = []
        output_contracts: list[ImageNormalizationOutputContract] = []
        for artifact_name, output_image in output_images:
            encoded = _encode_png(output_image)
            validation = validate_png_payload(encoded)
            output_path = output_directory.child(f"{artifact_name}.png")
            if output_path == source_path:
                raise ImageNormalizationValidationError(
                    "normalized outputs cannot overwrite the source image"
                )
            artifacts.append(
                PreparedImageNormalizationArtifact(
                    artifact=artifact_name,
                    path=output_path,
                    payload=encoded,
                    width=validation.width,
                    height=validation.height,
                )
            )
            output_contracts.append(
                ImageNormalizationOutputContract(
                    artifact=artifact_name,
                    path=output_path.value,
                    sha256=validation.sha256,
                    size_bytes=validation.size_bytes,
                    width=validation.width,
                    height=validation.height,
                )
            )

        report = ImageNormalizationReportContract(
            id=operation_id,
            source_path=source_path.value,
            source_sha256=source_sha256,
            source_format=source_format,
            source_width=source_width,
            source_height=source_height,
            source_orientation=orientation,
            orientation_applied=orientation != 1,
            canvas_width=selected_options.canvas_width,
            canvas_height=selected_options.canvas_height,
            requested_padding=selected_options.padding,
            padding=ImageNormalizationPaddingContract(
                left=offset_left,
                top=offset_top,
                right=selected_options.canvas_width - offset_left - fitted_width,
                bottom=selected_options.canvas_height - offset_top - fitted_height,
            ),
            subject_bounds=ImageNormalizationBoundsContract(
                left=offset_left,
                top=offset_top,
                width=fitted_width,
                height=fitted_height,
            ),
            thumbnail_width=selected_options.thumbnail_size,
            thumbnail_height=selected_options.thumbnail_size,
            neutral_background=selected_options.neutral_background,
            outputs=tuple(output_contracts),
        )
        return PreparedImageNormalization(
            report=report,
            report_path=output_directory.child("normalization.json"),
            artifacts=tuple(artifacts),
        )


def _decode_image(
    payload: bytes,
) -> tuple[Image.Image, Literal["png", "jpeg", "webp"], int, int, int]:
    try:
        with Image.open(BytesIO(payload)) as opened:
            if opened.format not in SUPPORTED_IMAGE_FORMATS:
                raise ImageNormalizationValidationError(
                    "source image format must be PNG, JPEG, or WebP"
                )
            width, height = opened.size
            if (
                width < 1
                or height < 1
                or width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
                or width * height > MAX_INPUT_IMAGE_PIXELS
            ):
                raise ImageNormalizationValidationError(
                    "source image dimensions exceed the supported pixel limits"
                )
            orientation = _read_orientation(opened)
            if getattr(opened, "n_frames", 1) != 1:
                raise ImageNormalizationValidationError("animated images are not supported")
            opened.load()
            oriented = ImageOps.exif_transpose(opened)
            image = oriented.convert("RGBA")
            image.load()
            if opened.format == "PNG":
                image_format: Literal["png", "jpeg", "webp"] = "png"
            elif opened.format == "JPEG":
                image_format = "jpeg"
            else:
                image_format = "webp"
            return image, image_format, width, height, orientation
    except ImageNormalizationValidationError:
        raise
    except (Image.DecompressionBombError, OSError, ValueError, UnidentifiedImageError) as error:
        raise ImageNormalizationValidationError(
            "source image is not a valid supported image"
        ) from error


def _read_orientation(image: Image.Image) -> int:
    try:
        orientation = int(image.getexif().get(274, 1))
    except (TypeError, ValueError, OSError) as error:
        raise ImageNormalizationValidationError(
            "source image orientation metadata is invalid"
        ) from error
    if orientation not in range(1, 9):
        raise ImageNormalizationValidationError("source image orientation metadata is invalid")
    return orientation


def _fit_dimensions(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    scale = min(max_width / width, max_height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _draw_alignment_guides(
    image: Image.Image,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    center_x = image.width // 2
    center_y = image.height // 2
    guide_color = (255, 0, 255, 160)
    bounds_color = (0, 128, 255, 200)
    draw.line((center_x, 0, center_x, image.height - 1), fill=guide_color, width=1)
    draw.line((0, center_y, image.width - 1, center_y), fill=guide_color, width=1)
    draw.rectangle((left, top, right, bottom), outline=bounds_color, width=1)


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    encoded = buffer.getvalue()
    if len(encoded) > MAX_PNG_BYTES:
        raise ImageNormalizationValidationError("normalized PNG exceeds the 64 MiB limit")
    return encoded


__all__ = [
    "DEFAULT_CANVAS_HEIGHT",
    "DEFAULT_CANVAS_WIDTH",
    "DEFAULT_NEUTRAL_BACKGROUND",
    "DEFAULT_PADDING",
    "DEFAULT_THUMBNAIL_SIZE",
    "IMAGE_NORMALIZATION_LOCK",
    "MAX_INPUT_IMAGE_BYTES",
    "MAX_INPUT_IMAGE_PIXELS",
    "ImageNormalizationArtifact",
    "ImageNormalizationError",
    "ImageNormalizationOptions",
    "ImageNormalizationValidationError",
    "ImageNormalizer",
    "PreparedImageNormalization",
    "PreparedImageNormalizationArtifact",
]
