"""Versioned contract for deterministic project package manifests."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    HttpsUriText,
    NonNegativeRevision,
    PositiveRevision,
    RevisionText,
    Sha256Text,
    Slug,
)
from ludowright.domain import ReferenceOrigin, ReferenceStatus

_MAX_PACKAGE_PATH_LENGTH = 1_024
_MAX_PACKAGE_PATH_SEGMENT_LENGTH = 255
_PACKAGE_PATH_SEGMENT_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
_RESERVED_WINDOWS_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def validate_package_path(value: str) -> str:
    """Validate one normalized, portable path stored in a package manifest."""
    if not isinstance(value, str):
        raise ValueError("package paths must be strings")
    if not value or value != value.strip():
        raise ValueError("package paths must be non-empty and trimmed")
    if len(value) > _MAX_PACKAGE_PATH_LENGTH:
        raise ValueError(f"package paths cannot exceed {_MAX_PACKAGE_PATH_LENGTH} characters")
    if not value.isascii():
        raise ValueError("package paths must contain ASCII characters only")
    if "\\" in value:
        raise ValueError("package paths must use forward slashes")

    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ValueError("package paths must be relative and already normalized")
    for segment in path.parts:
        if not segment or len(segment) > _MAX_PACKAGE_PATH_SEGMENT_LENGTH:
            raise ValueError("package path segments have an invalid length")
        if segment in {".", ".."}:
            raise ValueError("package paths cannot contain dot traversal")
        if any(character not in _PACKAGE_PATH_SEGMENT_CHARACTERS for character in segment):
            raise ValueError("package path segments contain an unsupported character")
        if segment.endswith("."):
            raise ValueError("package path segments cannot end with a dot")
        if segment.split(".", maxsplit=1)[0].lower() in _RESERVED_WINDOWS_NAMES:
            raise ValueError(f"package path segment {segment!r} is reserved on Windows")
    return value


PackagePathText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=_MAX_PACKAGE_PATH_LENGTH,
        pattern=r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$",
    ),
    AfterValidator(validate_package_path),
]


class PackageFileContract(ContractModel):
    """One included regular file and its exact content identity."""

    path: PackagePathText
    size_bytes: int = Field(ge=0, le=1_073_741_824)
    sha256: Sha256Text


class PackageSourceVersionContract(ContractModel):
    """Version and digest facts for one canonical or derived source."""

    path: PackagePathText
    kind: Slug
    schema_version: PositiveRevision | None = None
    revision: NonNegativeRevision | None = None
    sha256: Sha256Text | None = None


class PackageProvenanceContract(ContractModel):
    """Traceability fields copied from a persisted visual reference."""

    path: PackagePathText
    reference_id: Slug
    status: ReferenceStatus
    approval_id: Slug | None = None
    origin: ReferenceOrigin
    content_revision: RevisionText
    source_uri: HttpsUriText | None = None
    source_job_id: Slug | None = None
    source_receipt_id: Slug | None = None
    parent_reference_ids: tuple[Slug, ...] = ()
    creator: DisplayText | None = None
    license_label: DisplayText | None = None


class PackageLicenseContract(ContractModel):
    """One distinct license label and the references that declare it."""

    label: DisplayText
    reference_ids: tuple[Slug, ...] = ()


class PackageMissingItemContract(ContractModel):
    """A known source that is absent from the project at scan time."""

    path: PackagePathText
    reason: Literal["required-source", "optional-source"]
    detail: DisplayText


class PackageExcludedPathContract(ContractModel):
    """A path deliberately excluded from package contents."""

    path: PackagePathText
    reason: Literal[
        "manifest-output",
        "derived-state",
        "transient",
        "tool-cache",
    ]


class PackageManifestContract(ContractModel):
    """Canonical v1 package inventory, independent of ZIP generation."""

    schema_version: Literal[1] = 1
    kind: Literal["package-manifest"] = "package-manifest"
    package_id: Slug
    project_id: Slug
    manifest_path: PackagePathText
    included_files: tuple[PackageFileContract, ...] = ()
    source_versions: tuple[PackageSourceVersionContract, ...] = ()
    provenance: tuple[PackageProvenanceContract, ...] = ()
    licenses: tuple[PackageLicenseContract, ...] = ()
    missing: tuple[PackageMissingItemContract, ...] = ()
    excluded: tuple[PackageExcludedPathContract, ...] = ()

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if any(item.path == self.manifest_path for item in self.included_files):
            raise ValueError("the package manifest cannot include itself")
        included_paths = tuple(item.path for item in self.included_files)
        if len(included_paths) != len(set(included_paths)):
            raise ValueError("package manifest file paths must be unique")
        if included_paths != tuple(sorted(included_paths)):
            raise ValueError("package manifest file paths must be sorted")
        source_paths = tuple(item.path for item in self.source_versions)
        if len(source_paths) != len(set(source_paths)):
            raise ValueError("package manifest source paths must be unique")
        if source_paths != tuple(sorted(source_paths)):
            raise ValueError("package manifest source paths must be sorted")
        provenance_ids = tuple(item.reference_id for item in self.provenance)
        if len(provenance_ids) != len(set(provenance_ids)):
            raise ValueError("package provenance reference IDs must be unique")
        provenance_paths = tuple(item.path for item in self.provenance)
        if provenance_paths != tuple(sorted(provenance_paths)):
            raise ValueError("package provenance paths must be sorted")
        license_labels = tuple(item.label for item in self.licenses)
        if len(license_labels) != len(set(license_labels)):
            raise ValueError("package license labels must be unique")
        if license_labels != tuple(sorted(license_labels)):
            raise ValueError("package license labels must be sorted")
        if any(item.reference_ids != tuple(sorted(item.reference_ids)) for item in self.licenses):
            raise ValueError("package license reference IDs must be sorted")
        missing_paths = tuple(item.path for item in self.missing)
        if missing_paths != tuple(sorted(missing_paths)):
            raise ValueError("package missing paths must be sorted")
        excluded_paths = tuple(item.path for item in self.excluded)
        if excluded_paths != tuple(sorted(excluded_paths)):
            raise ValueError("package excluded paths must be sorted")
        return self


__all__ = [
    "PackageExcludedPathContract",
    "PackageFileContract",
    "PackageLicenseContract",
    "PackageManifestContract",
    "PackageMissingItemContract",
    "PackagePathText",
    "PackageProvenanceContract",
    "PackageSourceVersionContract",
    "validate_package_path",
]
