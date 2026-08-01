"""Published contract for one provider-bound ImageGen operation."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    PositiveRevision,
    RepositoryPathText,
    RevisionText,
    Sha256Text,
    Slug,
)
from ludowright.contracts.visual import ReferenceTargetContract
from ludowright.domain import ReferenceRole

ImageGenPromptText = Annotated[str, StringConstraints(min_length=1, max_length=12_000)]
ImageGenOutputIndex = Annotated[int, Field(ge=1, le=64)]


class ImageGenOutputContract(ContractModel):
    """One output request, representing exactly one visual view."""

    index: ImageGenOutputIndex
    role: ReferenceRole
    path: RepositoryPathText

    @model_validator(mode="after")
    def validate_output_path(self) -> Self:
        if not self.path.endswith(".png"):
            raise ValueError("ImageGen output paths must use the .png extension")
        return self


class ImageGenOperationContract(ContractModel):
    """Immutable provider request recorded before one ImageGen execution."""

    schema_version: Literal[1] = 1
    kind: Literal["imagegen-operation"] = "imagegen-operation"
    id: Slug
    job_id: Slug
    target: ReferenceTargetContract
    profile_version: PositiveRevision
    job_request_revision: RevisionText
    prompt_hash: Sha256Text
    positive_prompt: ImageGenPromptText
    negative_prompt: ImageGenPromptText
    input_reference_ids: Annotated[tuple[Slug, ...], Field(max_length=64)] = ()
    output_directory: RepositoryPathText
    outputs: Annotated[tuple[ImageGenOutputContract, ...], Field(min_length=1, max_length=64)]
    operation_revision: Sha256Text

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        target: ReferenceTargetContract,
        profile_version: int,
        job_request_revision: str,
        prompt_hash: str,
        positive_prompt: str,
        negative_prompt: str,
        input_reference_ids: tuple[str, ...],
        output_directory: str,
        outputs: tuple[ImageGenOutputContract, ...],
    ) -> Self:
        """Create an operation with deterministic ID and content revision."""
        pending = cls.model_construct(
            id="imagegen-pending",
            job_id=job_id,
            target=target,
            profile_version=profile_version,
            job_request_revision=job_request_revision,
            prompt_hash=prompt_hash,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            input_reference_ids=input_reference_ids,
            output_directory=output_directory,
            outputs=outputs,
            operation_revision="0" * 64,
        )
        digest = _operation_digest(pending)
        return cls(
            **pending.model_dump(mode="python", exclude={"id", "operation_revision"}),
            id=f"imagegen-{digest[:32]}",
            operation_revision=digest,
        )

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        _validate_safe_path(self.output_directory, "ImageGen output directory")
        input_ids = tuple(self.input_reference_ids)
        if input_ids != tuple(sorted(set(input_ids))):
            raise ValueError("ImageGen input reference IDs must be sorted and unique")

        indexes = tuple(output.index for output in self.outputs)
        if indexes != tuple(range(1, len(indexes) + 1)):
            raise ValueError("ImageGen output indexes must be contiguous and ordered")

        paths = tuple(output.path for output in self.outputs)
        if len(paths) != len(set(paths)):
            raise ValueError("ImageGen output paths must be unique")
        for path in paths:
            _validate_safe_path(path, "ImageGen output path")
        expected_parent = PurePosixPath(self.output_directory)
        if any(PurePosixPath(output.path).parent != expected_parent for output in self.outputs):
            raise ValueError("ImageGen outputs must remain in the output directory")

        digest = _operation_digest(self)
        if self.operation_revision != digest:
            raise ValueError("ImageGen operation revision does not match its content")
        if self.id != f"imagegen-{digest[:32]}":
            raise ValueError("ImageGen operation ID does not match its content revision")
        return self


def _operation_digest(value: ImageGenOperationContract) -> str:
    payload = value.model_dump(mode="json", exclude={"id", "operation_revision"})
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_safe_path(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(segment in {".", ".."} for segment in path.parts)
    ):
        raise ValueError(f"{label} must be a normalized relative path")


__all__ = ["ImageGenOperationContract", "ImageGenOutputContract"]
