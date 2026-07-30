"""Canonical persistence for incremental document refresh state."""

from __future__ import annotations

from dataclasses import dataclass

from ludowright.contracts import DocumentRefreshStateContract
from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath
from ludowright.infrastructure.structured import (
    JsonDocumentRepository,
    StructuredDocumentSnapshot,
)

DEFAULT_DOCUMENT_DIRECTORY = RepositoryPath(".ludowright/documents")
_DEFAULT_MAX_DOCUMENT_STATE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DocumentRefreshSnapshot:
    """One validated refresh state and its exact persisted identity."""

    path: RepositoryPath
    value: DocumentRefreshStateContract
    digest: str
    canonical: bool
    size_bytes: int


class DocumentRefreshRepository:
    """Persist one document refresh state using the shared JSON repository."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        document_id: str,
        *,
        max_bytes: int = _DEFAULT_MAX_DOCUMENT_STATE_BYTES,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("document refresh repositories require ProjectFilesystem")
        self._path = DEFAULT_DOCUMENT_DIRECTORY.child(f"{document_id}.json")
        self._repository = JsonDocumentRepository(
            filesystem,
            self._path,
            DocumentRefreshStateContract,
            max_bytes=max_bytes,
        )

    @property
    def path(self) -> RepositoryPath:
        """Return the canonical state path for this document."""
        return self._path

    def load(self) -> DocumentRefreshSnapshot:
        """Load and validate the current refresh state."""
        return _to_snapshot(self._repository.load())

    def load_optional(self) -> DocumentRefreshSnapshot | None:
        """Return no state when the document has not been refreshed yet."""
        snapshot = self._repository.load_optional()
        return None if snapshot is None else _to_snapshot(snapshot)

    def create(
        self,
        value: DocumentRefreshStateContract,
        *,
        timeout: float = 0.0,
    ) -> DocumentRefreshSnapshot:
        """Create state without replacing an existing revision."""
        return _to_snapshot(self._repository.create(value, timeout=timeout))

    def save(
        self,
        value: DocumentRefreshStateContract,
        *,
        expected_digest: str | None = None,
        timeout: float = 0.0,
    ) -> DocumentRefreshSnapshot:
        """Atomically save state with optional optimistic concurrency."""
        return _to_snapshot(
            self._repository.save(
                value,
                expected_digest=expected_digest,
                timeout=timeout,
            )
        )


def _to_snapshot(
    snapshot: StructuredDocumentSnapshot[DocumentRefreshStateContract],
) -> DocumentRefreshSnapshot:
    return DocumentRefreshSnapshot(
        path=snapshot.path,
        value=snapshot.value,
        digest=snapshot.digest,
        canonical=snapshot.canonical,
        size_bytes=snapshot.size_bytes,
    )
