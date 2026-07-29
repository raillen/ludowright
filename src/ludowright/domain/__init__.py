"""Canonical domain value objects for LudoWright."""

from ludowright.domain.errors import (
    DomainValidationError,
    InvalidIdentifierError,
    InvalidNameError,
    InvalidVersionError,
)
from ludowright.domain.identifiers import (
    AssetId,
    ComponentId,
    DecisionId,
    Identifier,
    JobId,
    PackageId,
    ProjectId,
    ReferenceId,
)
from ludowright.domain.names import DisplayName, slugify, validate_slug
from ludowright.domain.versions import (
    ProfileVersion,
    RevisionVersion,
    SchemaVersion,
    TemplateVersion,
)

__all__ = [
    "AssetId",
    "ComponentId",
    "DecisionId",
    "DisplayName",
    "DomainValidationError",
    "Identifier",
    "InvalidIdentifierError",
    "InvalidNameError",
    "InvalidVersionError",
    "JobId",
    "PackageId",
    "ProfileVersion",
    "ProjectId",
    "ReferenceId",
    "RevisionVersion",
    "SchemaVersion",
    "TemplateVersion",
    "slugify",
    "validate_slug",
]
