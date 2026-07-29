"""Persisted contract for migration backups and rollback metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import ContractModel, PositiveRevision, Slug

Sha256Text = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
RepositoryPathText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=1_024,
        pattern=r"^[a-z0-9._-]+(?:/[a-z0-9._-]+)*$",
    ),
]
UtcTimestampText = Annotated[
    str,
    StringConstraints(
        min_length=27,
        max_length=27,
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$",
    ),
]
FailureText = Annotated[str, StringConstraints(min_length=1, max_length=4_000)]


class MigrationRunStatus(StrEnum):
    PREPARED = "prepared"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled-back"


class MigrationReceiptContract(ContractModel):
    """Exact backup, execution, and rollback metadata for one migration run."""

    schema_version: Literal[1] = 1
    kind: Literal["migration-receipt"] = "migration-receipt"
    run_id: Slug
    status: MigrationRunStatus
    database_path: RepositoryPathText
    backup_path: RepositoryPathText
    source_version: PositiveRevision
    target_version: PositiveRevision
    migration_ids: Annotated[tuple[Slug, ...], Field(min_length=1)]
    started_at: UtcTimestampText
    completed_at: UtcTimestampText | None = None
    rolled_back_at: UtcTimestampText | None = None
    before_digest: Sha256Text
    backup_digest: Sha256Text
    after_digest: Sha256Text | None = None
    pre_rollback_digest: Sha256Text | None = None
    failure: FailureText | None = None

    @model_validator(mode="after")
    def validate_receipt_state(self) -> Self:
        if self.target_version <= self.source_version:
            raise ValueError("migration target version must be newer than source version")
        if len(self.migration_ids) != len(set(self.migration_ids)):
            raise ValueError("migration IDs must be unique")
        if self.status is MigrationRunStatus.PREPARED:
            if any(
                value is not None
                for value in (
                    self.completed_at,
                    self.rolled_back_at,
                    self.after_digest,
                    self.pre_rollback_digest,
                    self.failure,
                )
            ):
                raise ValueError("prepared migration receipt contains terminal fields")
        elif self.status is MigrationRunStatus.COMPLETED:
            if self.completed_at is None or self.after_digest is None:
                raise ValueError("completed migration receipt requires completion metadata")
            if any(
                value is not None
                for value in (
                    self.rolled_back_at,
                    self.pre_rollback_digest,
                    self.failure,
                )
            ):
                raise ValueError("completed migration receipt contains invalid fields")
        elif self.status is MigrationRunStatus.FAILED:
            if self.completed_at is None or self.failure is None:
                raise ValueError("failed migration receipt requires timestamp and failure")
            if any(
                value is not None
                for value in (
                    self.rolled_back_at,
                    self.after_digest,
                    self.pre_rollback_digest,
                )
            ):
                raise ValueError("failed migration receipt contains invalid fields")
        elif self.status is MigrationRunStatus.ROLLED_BACK:
            required = (
                self.completed_at,
                self.rolled_back_at,
                self.after_digest,
                self.pre_rollback_digest,
            )
            if any(value is None for value in required):
                raise ValueError("rolled-back migration receipt requires rollback metadata")
            if self.failure is not None:
                raise ValueError("rolled-back migration receipt cannot contain failure")
        return self
