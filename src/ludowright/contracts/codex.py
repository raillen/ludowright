"""Contracts for the project-local Codex skill package."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    RepositoryPathText,
    ReviewText,
    Sha256Text,
    Slug,
)

SkillFilename = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
SkillInvocation = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=81,
        pattern=r"^\$[a-z][a-z0-9-]{0,79}$",
    ),
]
LudoWrightVersionText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^\d+(?:\.\d+){1,3}(?:[.-](?:dev|a|b|rc)\d+)?$",
    ),
]
SkillOperation = Literal["install", "update", "verify", "remove"]
SkillState = Literal[
    "planned",
    "installed",
    "already-installed",
    "updated",
    "already-up-to-date",
    "verified",
    "removed",
    "not-installed",
    "outdated",
    "modified",
    "invalid",
    "unsupported",
    "incompatible",
    "conflict",
]


class CodexSkillFileContract(ContractModel):
    """One case-sensitive file shipped by a Codex skill."""

    path: SkillFilename
    sha256: Sha256Text


class CodexSkillManifestContract(ContractModel):
    """Versioned metadata for one installable project-local Codex skill."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-skill-manifest"] = "codex-skill-manifest"
    id: Slug
    invocation: SkillInvocation
    version: PositiveRevision
    description: DisplayText
    install_path: RepositoryPathText
    entrypoint: SkillFilename
    minimum_ludowright_version: LudoWrightVersionText
    files: Annotated[tuple[CodexSkillFileContract, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        file_paths = tuple(item.path for item in self.files)
        if len(file_paths) != len(set(file_paths)):
            raise ValueError("Codex skill files must be unique")
        if self.entrypoint not in file_paths:
            raise ValueError("Codex skill entrypoint must be declared in files")
        if self.entrypoint == "manifest.json":
            raise ValueError("Codex skill entrypoint cannot be the installer manifest")
        if "manifest.json" in file_paths:
            raise ValueError("manifest.json is reserved for the installer manifest")
        if self.invocation != f"${self.id}":
            raise ValueError("Codex skill invocation must match its ID")
        return self


class CodexSkillReportContract(ContractModel):
    """Stable report returned by Codex skill lifecycle commands."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-skill-report"] = "codex-skill-report"
    operation: SkillOperation
    state: SkillState
    dry_run: bool
    skill_id: Slug
    skill_version: PositiveRevision
    installed_version: PositiveRevision | None = None
    install_path: RepositoryPathText
    framework_version: LudoWrightVersionText
    files: Annotated[tuple[CodexSkillFileContract, ...], Field(min_length=1, max_length=33)]
    warnings: tuple[ReviewText, ...] = ()
    valid: bool

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("Codex skill report files must be unique")
        if tuple(sorted(paths)) != paths:
            raise ValueError("Codex skill report files must be sorted")
        if tuple(sorted(self.warnings)) != self.warnings:
            raise ValueError("Codex skill report warnings must be sorted")
        return self
