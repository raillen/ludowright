"""Bounded validation for generated image artifacts."""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 64 * 1024 * 1024


class ImageArtifactError(RuntimeError):
    """Raised when an image payload is not a safe supported artifact."""


@dataclass(frozen=True, slots=True)
class PngValidation:
    """Validated facts needed to persist one generated PNG receipt."""

    sha256: str
    size_bytes: int
    width: int
    height: int


def validate_png_payload(
    payload: bytes,
    *,
    max_bytes: int = MAX_PNG_BYTES,
) -> PngValidation:
    """Validate one bounded, non-animated PNG payload without decoding pixels."""
    if not isinstance(payload, bytes):
        raise ImageArtifactError("ImageGen providers must return immutable bytes")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("PNG size limit must be a positive integer")
    if len(payload) > max_bytes:
        raise ImageArtifactError(f"PNG payload exceeds the {max_bytes}-byte limit")
    if not payload.startswith(PNG_SIGNATURE):
        raise ImageArtifactError("ImageGen provider did not return a PNG payload")

    offset = len(PNG_SIGNATURE)
    saw_header = False
    saw_data = False
    saw_end = False
    width = 0
    height = 0
    while offset < len(payload):
        if len(payload) - offset < 12:
            raise ImageArtifactError("PNG payload ends inside a chunk")
        length = struct.unpack_from(">I", payload, offset)[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + length
        crc_end = chunk_end + 4
        if crc_end > len(payload):
            raise ImageArtifactError("PNG chunk exceeds the payload boundary")
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_data = payload[chunk_start:chunk_end]
        expected_crc = struct.unpack_from(">I", payload, chunk_end)[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ImageArtifactError("PNG chunk checksum is invalid")

        if not saw_header and chunk_type != b"IHDR":
            raise ImageArtifactError("PNG must begin with an IHDR chunk")
        if chunk_type == b"IHDR":
            if saw_header or len(chunk_data) != 13:
                raise ImageArtifactError("PNG must contain exactly one valid IHDR chunk")
            width, height = struct.unpack_from(">II", chunk_data)
            if width == 0 or height == 0:
                raise ImageArtifactError("PNG dimensions must be positive")
            saw_header = True
        elif chunk_type == b"IDAT":
            if not saw_header or saw_end:
                raise ImageArtifactError("PNG IDAT chunk is out of order")
            saw_data = True
        elif chunk_type == b"acTL":
            raise ImageArtifactError("animated PNG payloads are not allowed")
        elif chunk_type == b"IEND":
            if not saw_header or not saw_data or len(chunk_data) != 0 or saw_end:
                raise ImageArtifactError("PNG IEND chunk is invalid")
            saw_end = True

        offset = crc_end
        if saw_end:
            if offset != len(payload):
                raise ImageArtifactError("PNG payload contains trailing bytes")
            break

    if not saw_header or not saw_data or not saw_end:
        raise ImageArtifactError("PNG payload is incomplete")
    return PngValidation(
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        width=width,
        height=height,
    )


__all__ = [
    "MAX_PNG_BYTES",
    "PNG_SIGNATURE",
    "ImageArtifactError",
    "PngValidation",
    "validate_png_payload",
]
