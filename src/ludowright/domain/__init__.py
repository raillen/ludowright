"""Canonical domain value objects for LudoWright."""

from ludowright.domain.errors import (
    DomainValidationError,
    InvalidIdentifierError,
    InvalidNameError,
    InvalidProjectError,
    InvalidProjectTransitionError,
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
from ludowright.domain.project import (
    EngineSpec,
    PlatformFamily,
    Project,
    ProjectDimension,
    ProjectIdentity,
    ProjectLifecycle,
    ProjectStage,
    ProjectTarget,
)
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
    "EngineSpec",
    "Identifier",
    "InvalidIdentifierError",
    "InvalidNameError",
    "InvalidProjectError",
    "InvalidProjectTransitionError",
    "InvalidVersionError",
    "JobId",
    "PackageId",
    "PlatformFamily",
    "ProfileVersion",
    "Project",
    "ProjectDimension",
    "ProjectId",
    "ProjectIdentity",
    "ProjectLifecycle",
    "ProjectStage",
    "ProjectTarget",
    "ReferenceId",
    "RevisionVersion",
    "SchemaVersion",
    "TemplateVersion",
    "slugify",
    "validate_slug",
]
