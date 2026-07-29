"""Canonical JSON persistence for dependency and invalidation graphs."""

from __future__ import annotations

from dataclasses import dataclass

from ludowright.contracts.dependencies import DependencyGraphContract
from ludowright.domain import DependencyGraph
from ludowright.infrastructure.filesystem import ProjectFilesystem, RepositoryPath
from ludowright.infrastructure.structured import (
    JsonDocumentRepository,
    StructuredDocumentSnapshot,
)

DEFAULT_DEPENDENCY_GRAPH_PATH = RepositoryPath(".ludowright/dependency-graph.json")
_DEFAULT_MAX_GRAPH_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DependencyGraphSnapshot:
    """One validated graph together with its exact persisted identity."""

    path: RepositoryPath
    graph: DependencyGraph
    digest: str
    canonical: bool
    size_bytes: int


class DependencyGraphRepository:
    """Persist one canonical dependency graph with optimistic concurrency."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        path: RepositoryPath = DEFAULT_DEPENDENCY_GRAPH_PATH,
        *,
        max_bytes: int = _DEFAULT_MAX_GRAPH_BYTES,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("dependency graph repositories require ProjectFilesystem")
        if not isinstance(path, RepositoryPath):
            raise TypeError("dependency graph repositories require RepositoryPath")
        self._repository = JsonDocumentRepository(
            filesystem,
            path,
            DependencyGraphContract,
            max_bytes=max_bytes,
        )

    @property
    def path(self) -> RepositoryPath:
        return self._repository.path

    def load(self) -> DependencyGraphSnapshot:
        return _to_domain_snapshot(self._repository.load())

    def load_optional(self) -> DependencyGraphSnapshot | None:
        snapshot = self._repository.load_optional()
        return None if snapshot is None else _to_domain_snapshot(snapshot)

    def create(
        self,
        graph: DependencyGraph,
        *,
        timeout: float = 0.0,
    ) -> DependencyGraphSnapshot:
        contract = DependencyGraphContract.from_domain(graph)
        return _to_domain_snapshot(self._repository.create(contract, timeout=timeout))

    def save(
        self,
        graph: DependencyGraph,
        *,
        expected_digest: str | None = None,
        timeout: float = 0.0,
    ) -> DependencyGraphSnapshot:
        contract = DependencyGraphContract.from_domain(graph)
        return _to_domain_snapshot(
            self._repository.save(
                contract,
                expected_digest=expected_digest,
                timeout=timeout,
            )
        )

    def replace(
        self,
        snapshot: DependencyGraphSnapshot,
        graph: DependencyGraph,
        *,
        timeout: float = 0.0,
    ) -> DependencyGraphSnapshot:
        if not isinstance(snapshot, DependencyGraphSnapshot):
            raise TypeError("dependency graph replacement requires a graph snapshot")
        if snapshot.path != self.path:
            raise ValueError("dependency graph snapshot belongs to another repository")
        return self.save(
            graph,
            expected_digest=snapshot.digest,
            timeout=timeout,
        )

    def canonical_bytes(self, graph: DependencyGraph) -> bytes:
        return self._repository.canonical_bytes(DependencyGraphContract.from_domain(graph))


def _to_domain_snapshot(
    snapshot: StructuredDocumentSnapshot[DependencyGraphContract],
) -> DependencyGraphSnapshot:
    return DependencyGraphSnapshot(
        path=snapshot.path,
        graph=snapshot.value.to_domain(),
        digest=snapshot.digest,
        canonical=snapshot.canonical,
        size_bytes=snapshot.size_bytes,
    )
