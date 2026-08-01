"""Versioned contract for reproducible package indexes."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import ContractModel, NonNegativeRevision, Sha256Text, Slug
from ludowright.contracts.package_manifest import PackagePathText

PACKAGE_MANIFEST_ARCHIVE_PATH = "__ludowright__/package-manifest.json"
PACKAGE_INDEX_ARCHIVE_PATH = "__ludowright__/package-index.json"
PACKAGE_ZIP_TIMESTAMP = "1980-01-01T00:00:00"


class PackageIndexEntryContract(ContractModel):
    """One deterministic member described by the package index."""

    path: PackagePathText
    source_path: PackagePathText
    kind: Literal["project-file", "package-manifest"]
    size_bytes: int = Field(ge=0, le=1_073_741_824)
    sha256: Sha256Text


class PackageIndexContract(ContractModel):
    """Published index for one reproducible ZIP package."""

    schema_version: Literal[1] = 1
    kind: Literal["package-index"] = "package-index"
    package_id: Slug
    project_id: Slug
    manifest_path: PackagePathText
    manifest_sha256: Sha256Text
    archive_path: PackagePathText
    index_path: PackagePathText
    archive_manifest_path: Literal["__ludowright__/package-manifest.json"] = (
        "__ludowright__/package-manifest.json"
    )
    archive_index_path: Literal["__ludowright__/package-index.json"] = (
        "__ludowright__/package-index.json"
    )
    compression: Literal["deflate"] = "deflate"
    zip_timestamp: Literal["1980-01-01T00:00:00"] = "1980-01-01T00:00:00"
    entries: tuple[PackageIndexEntryContract, ...] = ()
    archive_member_count: NonNegativeRevision
    payload_size_bytes: int = Field(ge=0, le=1_073_741_824 + 16 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_index(self) -> Self:
        paths = tuple(entry.path for entry in self.entries)
        if len(paths) != len(set(paths)):
            raise ValueError("package index member paths must be unique")
        if paths != tuple(sorted(paths)):
            raise ValueError("package index member paths must be sorted")
        if self.archive_index_path in paths:
            raise ValueError("package index cannot describe itself as a payload entry")
        if self.archive_manifest_path not in paths:
            raise ValueError("package index must describe the archived package manifest")
        manifest_entries = tuple(
            entry for entry in self.entries if entry.kind == "package-manifest"
        )
        if len(manifest_entries) != 1:
            raise ValueError("package index must contain exactly one archived package manifest")
        if self.archive_path == self.index_path:
            raise ValueError("package archive and index paths must be different")
        if self.archive_path == self.manifest_path or self.index_path == self.manifest_path:
            raise ValueError("package outputs cannot replace the source manifest")
        for entry in self.entries:
            if entry.kind == "package-manifest" and entry.source_path != self.manifest_path:
                raise ValueError("package manifest index entry has an invalid source path")
            if entry.kind == "project-file" and entry.source_path != entry.path:
                raise ValueError("project-file index entries must preserve their source path")
            if entry.kind == "project-file" and entry.path == self.manifest_path:
                raise ValueError("package manifest cannot also be a project-file entry")
        if self.archive_member_count != len(self.entries) + 1:
            raise ValueError("package archive member count must include the index member")
        if self.payload_size_bytes != sum(entry.size_bytes for entry in self.entries):
            raise ValueError("package payload size does not match index entries")
        return self


__all__ = [
    "PACKAGE_INDEX_ARCHIVE_PATH",
    "PACKAGE_MANIFEST_ARCHIVE_PATH",
    "PACKAGE_ZIP_TIMESTAMP",
    "PackageIndexContract",
    "PackageIndexEntryContract",
]
