"""Versioned report contract for deterministic image normalization."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import ContractModel, RepositoryPathText, Sha256Text, Slug

NormalizationArtifact = Literal["normalized", "neutral", "thumbnail", "alignment-guide"]
ImageFormat = Literal["png", "jpeg", "webp"]
HexColorText = Annotated[str, StringConstraints(pattern=r"^#[0-9A-F]{6}$")]
BoundedDimension = Annotated[int, Field(ge=1, le=16_384)]
CanvasDimension = Annotated[int, Field(ge=64, le=16_384)]


class ImageNormalizationBoundsContract(ContractModel):
    """Subject bounds placed inside the normalized canvas."""

    left: Annotated[int, Field(ge=0, le=16_383)]
    top: Annotated[int, Field(ge=0, le=16_383)]
    width: BoundedDimension
    height: BoundedDimension


class ImageNormalizationPaddingContract(ContractModel):
    """Actual empty padding around the fitted subject in output pixels."""

    left: Annotated[int, Field(ge=0, le=16_384)]
    top: Annotated[int, Field(ge=0, le=16_384)]
    right: Annotated[int, Field(ge=0, le=16_384)]
    bottom: Annotated[int, Field(ge=0, le=16_384)]


class ImageNormalizationOutputContract(ContractModel):
    """One deterministic PNG artifact emitted by normalization."""

    artifact: NormalizationArtifact
    path: RepositoryPathText
    format: Literal["png"] = "png"
    sha256: Sha256Text
    size_bytes: Annotated[int, Field(ge=1, le=64 * 1024 * 1024)]
    width: BoundedDimension
    height: BoundedDimension


class ImageNormalizationReportContract(ContractModel):
    """Canonical metadata for one normalized image set."""

    schema_version: Literal[1] = 1
    kind: Literal["image-normalization"] = "image-normalization"
    id: Slug
    source_path: RepositoryPathText
    source_sha256: Sha256Text
    source_format: ImageFormat
    source_width: BoundedDimension
    source_height: BoundedDimension
    source_orientation: Annotated[int, Field(ge=1, le=8)]
    orientation_applied: bool
    canvas_width: CanvasDimension
    canvas_height: CanvasDimension
    requested_padding: Annotated[int, Field(ge=0, le=8_192)]
    padding: ImageNormalizationPaddingContract
    subject_bounds: ImageNormalizationBoundsContract
    thumbnail_width: Annotated[int, Field(ge=16, le=4_096)]
    thumbnail_height: Annotated[int, Field(ge=16, le=4_096)]
    neutral_background: HexColorText
    outputs: tuple[ImageNormalizationOutputContract, ...]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        expected_artifacts = (
            "normalized",
            "neutral",
            "thumbnail",
            "alignment-guide",
        )
        artifacts = tuple(output.artifact for output in self.outputs)
        if artifacts != expected_artifacts:
            raise ValueError("image normalization outputs must use the canonical artifact order")
        if self.subject_bounds.left + self.subject_bounds.width > self.canvas_width:
            raise ValueError("normalized subject exceeds canvas width")
        if self.subject_bounds.top + self.subject_bounds.height > self.canvas_height:
            raise ValueError("normalized subject exceeds canvas height")
        if self.padding.left + self.subject_bounds.width + self.padding.right != self.canvas_width:
            raise ValueError("horizontal padding does not cover the canvas")
        if (
            self.padding.top + self.subject_bounds.height + self.padding.bottom
            != self.canvas_height
        ):
            raise ValueError("vertical padding does not cover the canvas")
        thumbnail = self.outputs[2]
        if (thumbnail.width, thumbnail.height) != (self.thumbnail_width, self.thumbnail_height):
            raise ValueError("thumbnail dimensions do not match the report")
        if any(output.path == self.source_path for output in self.outputs):
            raise ValueError("normalized outputs cannot overwrite the source path")
        return self


__all__ = [
    "ImageNormalizationBoundsContract",
    "ImageNormalizationOutputContract",
    "ImageNormalizationPaddingContract",
    "ImageNormalizationReportContract",
]
