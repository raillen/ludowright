"""Canonical persistence for decision and approval histories."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass

from ludowright.contracts import ApprovalContract, DecisionContract
from ludowright.domain import Approval, ApprovalId, Decision, DecisionId
from ludowright.infrastructure.filesystem import (
    ProjectFilesystem,
    RepositoryPath,
    UnsafeProjectPathError,
)
from ludowright.infrastructure.structured import (
    JsonDocumentRepository,
    StructuredDocumentSnapshot,
)

DECISIONS_DIRECTORY = RepositoryPath("decisions")
APPROVALS_DIRECTORY = RepositoryPath("approvals")


class GovernanceRecordNotFoundError(FileNotFoundError):
    """Raised when a requested decision or approval file does not exist."""


@dataclass(frozen=True, slots=True)
class DecisionSnapshot:
    """A decision aggregate and its exact canonical file revision."""

    path: RepositoryPath
    decision: Decision
    digest: str


@dataclass(frozen=True, slots=True)
class ApprovalSnapshot:
    """An approval aggregate and its exact canonical file revision."""

    path: RepositoryPath
    approval: Approval
    digest: str


class DecisionRepository:
    """Persist decisions under the canonical ``decisions`` directory."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        directory: RepositoryPath = DECISIONS_DIRECTORY,
    ) -> None:
        self._filesystem = filesystem
        self._directory = directory

    @property
    def directory(self) -> RepositoryPath:
        return self._directory

    def path_for(self, decision_id: DecisionId) -> RepositoryPath:
        if not isinstance(decision_id, DecisionId):
            raise TypeError("decision paths require DecisionId")
        return self._directory.child(f"{decision_id.value}.json")

    def create(self, decision: Decision, *, timeout: float = 0.0) -> DecisionSnapshot:
        path = self.path_for(decision.id)
        snapshot = JsonDocumentRepository(self._filesystem, path, DecisionContract).create(
            DecisionContract.from_domain(decision),
            timeout=timeout,
        )
        return _decision_snapshot(snapshot)

    def load(self, decision_id: DecisionId) -> DecisionSnapshot:
        path = self.path_for(decision_id)
        try:
            snapshot = JsonDocumentRepository(self._filesystem, path, DecisionContract).load()
        except FileNotFoundError as error:
            raise GovernanceRecordNotFoundError(f"decision not found: {decision_id}") from error
        return _decision_snapshot(snapshot)

    def replace(
        self,
        snapshot: DecisionSnapshot,
        decision: Decision,
        *,
        timeout: float = 0.0,
    ) -> DecisionSnapshot:
        if snapshot.path != self.path_for(decision.id):
            raise ValueError("decision snapshot belongs to another decision")
        repository = JsonDocumentRepository(self._filesystem, snapshot.path, DecisionContract)
        updated = repository.replace(
            StructuredDocumentSnapshot(
                path=snapshot.path,
                format=repository.format,
                value=DecisionContract.from_domain(snapshot.decision),
                digest=snapshot.digest,
                canonical=True,
                size_bytes=0,
            ),
            DecisionContract.from_domain(decision),
            timeout=timeout,
        )
        return _decision_snapshot(updated)

    def remove(self, snapshot: DecisionSnapshot) -> None:
        _remove_snapshot(self._filesystem, snapshot.path, snapshot.digest)

    def list(self) -> tuple[DecisionSnapshot, ...]:
        result: list[DecisionSnapshot] = []
        for path in _list_json_paths(self._filesystem, self._directory):
            result.append(
                _decision_snapshot(
                    JsonDocumentRepository(self._filesystem, path, DecisionContract).load()
                )
            )
        return tuple(sorted(result, key=lambda item: item.decision.id.value))


class ApprovalRepository:
    """Persist approvals under the canonical ``approvals`` directory."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        directory: RepositoryPath = APPROVALS_DIRECTORY,
    ) -> None:
        self._filesystem = filesystem
        self._directory = directory

    @property
    def directory(self) -> RepositoryPath:
        return self._directory

    def path_for(self, approval_id: ApprovalId) -> RepositoryPath:
        if not isinstance(approval_id, ApprovalId):
            raise TypeError("approval paths require ApprovalId")
        return self._directory.child(f"{approval_id.value}.json")

    def create(self, approval: Approval, *, timeout: float = 0.0) -> ApprovalSnapshot:
        path = self.path_for(approval.id)
        snapshot = JsonDocumentRepository(self._filesystem, path, ApprovalContract).create(
            ApprovalContract.from_domain(approval),
            timeout=timeout,
        )
        return _approval_snapshot(snapshot)

    def load(self, approval_id: ApprovalId) -> ApprovalSnapshot:
        path = self.path_for(approval_id)
        try:
            snapshot = JsonDocumentRepository(self._filesystem, path, ApprovalContract).load()
        except FileNotFoundError as error:
            raise GovernanceRecordNotFoundError(f"approval not found: {approval_id}") from error
        return _approval_snapshot(snapshot)

    def replace(
        self,
        snapshot: ApprovalSnapshot,
        approval: Approval,
        *,
        timeout: float = 0.0,
    ) -> ApprovalSnapshot:
        if snapshot.path != self.path_for(approval.id):
            raise ValueError("approval snapshot belongs to another approval")
        repository = JsonDocumentRepository(self._filesystem, snapshot.path, ApprovalContract)
        updated = repository.replace(
            StructuredDocumentSnapshot(
                path=snapshot.path,
                format=repository.format,
                value=ApprovalContract.from_domain(snapshot.approval),
                digest=snapshot.digest,
                canonical=True,
                size_bytes=0,
            ),
            ApprovalContract.from_domain(approval),
            timeout=timeout,
        )
        return _approval_snapshot(updated)

    def remove(self, snapshot: ApprovalSnapshot) -> None:
        _remove_snapshot(self._filesystem, snapshot.path, snapshot.digest)

    def list(self) -> tuple[ApprovalSnapshot, ...]:
        result: list[ApprovalSnapshot] = []
        for path in _list_json_paths(self._filesystem, self._directory):
            result.append(
                _approval_snapshot(
                    JsonDocumentRepository(self._filesystem, path, ApprovalContract).load()
                )
            )
        return tuple(sorted(result, key=lambda item: item.approval.id.value))


def _decision_snapshot(snapshot: StructuredDocumentSnapshot[DecisionContract]) -> DecisionSnapshot:
    return DecisionSnapshot(
        path=snapshot.path,
        decision=snapshot.value.to_domain(),
        digest=snapshot.digest,
    )


def _approval_snapshot(snapshot: StructuredDocumentSnapshot[ApprovalContract]) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        path=snapshot.path,
        approval=snapshot.value.to_domain(),
        digest=snapshot.digest,
    )


def _list_json_paths(
    filesystem: ProjectFilesystem,
    directory: RepositoryPath,
) -> tuple[RepositoryPath, ...]:
    try:
        resolved = filesystem.resolve(directory, must_exist=True)
    except FileNotFoundError:
        return ()
    if not resolved.is_dir():
        raise UnsafeProjectPathError(f"governance path must be a directory: {directory}")

    paths: list[RepositoryPath] = []
    for entry in resolved.iterdir():
        entry_stat = os.lstat(entry)
        if stat.S_ISLNK(entry_stat.st_mode):
            raise UnsafeProjectPathError(f"governance directory contains a symlink: {entry}")
        if not stat.S_ISREG(entry_stat.st_mode):
            continue
        if not entry.name.endswith(".json"):
            continue
        try:
            paths.append(directory.child(entry.name))
        except UnsafeProjectPathError as error:
            raise UnsafeProjectPathError(
                f"governance directory contains an unsafe file name: {entry.name!r}"
            ) from error
    return tuple(sorted(paths, key=lambda path: path.value))


def _remove_snapshot(filesystem: ProjectFilesystem, path: RepositoryPath, digest: str) -> None:
    """Remove one exact file during a failed multi-resource operation."""
    repository_path = filesystem.resolve(path, must_exist=True)
    payload = filesystem.read_bytes(path)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise RuntimeError(f"cannot roll back changed governance file: {path}")
    target_stat = os.lstat(repository_path)
    if stat.S_ISLNK(target_stat.st_mode) or not stat.S_ISREG(target_stat.st_mode):
        raise UnsafeProjectPathError(f"governance rollback target is not a regular file: {path}")
    repository_path.unlink()
