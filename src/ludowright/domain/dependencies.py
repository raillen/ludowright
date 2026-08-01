"""Typed dependency graph, stale propagation, and impact explanation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self

from ludowright.domain.errors import (
    DependencyCycleError,
    DependencyRefreshError,
    InvalidDependencyGraphError,
)
from ludowright.domain.names import validate_slug
from ludowright.domain.versions import RevisionVersion

_MAX_GRAPH_NODES = 100_000
_MAX_GRAPH_EDGES = 500_000
_MAX_INVALIDATIONS_PER_NODE = 256


class DependencyNodeKind(StrEnum):
    """Stable kinds of canonical or derived project items."""

    PROJECT = "project"
    DECISION = "decision"
    APPROVAL = "approval"
    DOCUMENT = "document"
    ASSET = "asset"
    COMPONENT = "component"
    VARIANT = "variant"
    ASSET_STATE = "asset-state"
    REFERENCE = "reference"
    CAPTURE_PROFILE = "capture-profile"
    VISUAL_JOB = "visual-job"
    GENERATION_RECEIPT = "generation-receipt"
    VISUAL_REVIEW = "visual-review"
    TECHNICAL_SHEET = "technical-sheet"
    WORKBOOK = "workbook"
    PACKAGE = "package"
    RELEASE = "release"
    OTHER = "other"


class DependencyRelation(StrEnum):
    """Meaning of a dependency from one source to one dependent target."""

    REQUIRES = "requires"
    DERIVES_FROM = "derives-from"
    REFERENCES = "references"
    GENERATED_FROM = "generated-from"
    ASSEMBLED_FROM = "assembled-from"
    APPROVED_BY = "approved-by"
    PACKAGES = "packages"
    SUPERSEDES = "supersedes"
    OTHER = "other"


class InvalidationMode(StrEnum):
    """How a source problem affects a dependent target."""

    STALE = "stale"
    REVIEW = "review"
    NONE = "none"


class FreshnessState(StrEnum):
    """Current usability of a node relative to its dependencies."""

    FRESH = "fresh"
    REVIEW_REQUIRED = "review-required"
    STALE = "stale"


_FRESHNESS_SEVERITY = {
    FreshnessState.FRESH: 0,
    FreshnessState.REVIEW_REQUIRED: 1,
    FreshnessState.STALE: 2,
}


@dataclass(frozen=True, order=True, slots=True)
class DependencyKey:
    """Typed identity of one dependency-graph node."""

    kind: DependencyNodeKind
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DependencyNodeKind):
            raise InvalidDependencyGraphError("a dependency key requires a valid node kind")
        if not isinstance(self.id, str):
            raise InvalidDependencyGraphError("a dependency key ID must be a string")
        try:
            validate_slug(self.id)
        except ValueError as error:
            raise InvalidDependencyGraphError("a dependency key ID must be canonical") from error

    @property
    def token(self) -> str:
        return f"{self.kind.value}:{self.id}"

    def __str__(self) -> str:
        return self.token


@dataclass(frozen=True, order=True, slots=True)
class InvalidationReason:
    """Extensible canonical reason for an invalidation operation."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidDependencyGraphError("an invalidation reason must be a string")
        try:
            validate_slug(self.value)
        except ValueError as error:
            raise InvalidDependencyGraphError(
                "an invalidation reason must be a canonical slug"
            ) from error

    def __str__(self) -> str:
        return self.value


SOURCE_CHANGED = InvalidationReason("source-changed")
SOURCE_REMOVED = InvalidationReason("source-removed")
SOURCE_REJECTED = InvalidationReason("source-rejected")
APPROVAL_REVOKED = InvalidationReason("approval-revoked")
MANUAL_INVALIDATION = InvalidationReason("manual-invalidation")


@dataclass(frozen=True, slots=True)
class InvalidationCause:
    """One explainable path from an invalidation root to an affected node."""

    root: DependencyKey
    affected: DependencyKey
    reason: InvalidationReason
    state: FreshnessState
    path: tuple[DependencyKey, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.root, DependencyKey) or not isinstance(self.affected, DependencyKey):
            raise InvalidDependencyGraphError("an invalidation cause requires typed keys")
        if not isinstance(self.reason, InvalidationReason):
            raise InvalidDependencyGraphError("an invalidation cause requires a typed reason")
        if self.state is FreshnessState.FRESH or not isinstance(self.state, FreshnessState):
            raise InvalidDependencyGraphError("an invalidation cause must be non-fresh")
        if not isinstance(self.path, tuple) or not self.path:
            raise InvalidDependencyGraphError("an invalidation path cannot be empty")
        if any(not isinstance(item, DependencyKey) for item in self.path):
            raise InvalidDependencyGraphError("an invalidation path requires typed keys")
        if self.path[0] != self.root or self.path[-1] != self.affected:
            raise InvalidDependencyGraphError(
                "an invalidation path must begin at its root and end at its affected node"
            )
        if len(self.path) != len(set(self.path)):
            raise InvalidDependencyGraphError("an invalidation path cannot contain a cycle")


@dataclass(frozen=True, slots=True)
class DependencyNode:
    """One versioned project item and its persisted freshness state."""

    key: DependencyKey
    revision: RevisionVersion
    freshness: FreshnessState = FreshnessState.FRESH
    invalidations: tuple[InvalidationCause, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.key, DependencyKey):
            raise InvalidDependencyGraphError("a dependency node requires a typed key")
        if not isinstance(self.revision, RevisionVersion):
            raise InvalidDependencyGraphError("a dependency node requires a revision")
        if not isinstance(self.freshness, FreshnessState):
            raise InvalidDependencyGraphError("a dependency node requires a freshness state")
        if not isinstance(self.invalidations, tuple):
            raise InvalidDependencyGraphError("node invalidations must be immutable")
        if len(self.invalidations) > _MAX_INVALIDATIONS_PER_NODE:
            raise InvalidDependencyGraphError("a dependency node has too many invalidations")
        if any(not isinstance(cause, InvalidationCause) for cause in self.invalidations):
            raise InvalidDependencyGraphError("node invalidations must be canonical")
        if any(cause.affected != self.key for cause in self.invalidations):
            raise InvalidDependencyGraphError(
                "node invalidations must target the containing dependency node"
            )
        identities = tuple((cause.root, cause.reason.value) for cause in self.invalidations)
        if len(identities) != len(set(identities)):
            raise InvalidDependencyGraphError(
                "a node cannot contain duplicate invalidation roots and reasons"
            )
        expected = _freshness_from_causes(self.invalidations)
        if self.freshness is not expected:
            raise InvalidDependencyGraphError(
                "node freshness must equal the strongest persisted invalidation"
            )
        ordered = tuple(sorted(self.invalidations, key=_cause_sort_key))
        object.__setattr__(self, "invalidations", ordered)


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """A typed edge from an input source to one dependent target."""

    source: DependencyKey
    target: DependencyKey
    relation: DependencyRelation
    invalidation_mode: InvalidationMode
    observed_source_revision: RevisionVersion

    def __post_init__(self) -> None:
        if not isinstance(self.source, DependencyKey) or not isinstance(self.target, DependencyKey):
            raise InvalidDependencyGraphError("dependency edges require typed endpoints")
        if self.source == self.target:
            raise InvalidDependencyGraphError("a dependency node cannot depend on itself")
        if not isinstance(self.relation, DependencyRelation):
            raise InvalidDependencyGraphError("a dependency edge requires a relation")
        if not isinstance(self.invalidation_mode, InvalidationMode):
            raise InvalidDependencyGraphError("a dependency edge requires an invalidation mode")
        if not isinstance(self.observed_source_revision, RevisionVersion):
            raise InvalidDependencyGraphError(
                "a dependency edge requires an observed source revision"
            )

    @property
    def identity(self) -> tuple[DependencyKey, DependencyKey, DependencyRelation]:
        return (self.source, self.target, self.relation)


@dataclass(frozen=True, slots=True)
class InvalidationResult:
    """A new graph plus deterministic impact explanations for one operation."""

    graph: DependencyGraph
    impacts: tuple[InvalidationCause, ...]

    @property
    def affected(self) -> tuple[DependencyKey, ...]:
        return tuple(cause.affected for cause in self.impacts)


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    """Immutable acyclic dependency graph with revision-aware invalidation."""

    revision: RevisionVersion
    nodes: tuple[DependencyNode, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.revision, RevisionVersion):
            raise InvalidDependencyGraphError("a dependency graph requires a revision")
        if not isinstance(self.nodes, tuple) or not isinstance(self.edges, tuple):
            raise InvalidDependencyGraphError("dependency graph collections must be immutable")
        if len(self.nodes) > _MAX_GRAPH_NODES:
            raise InvalidDependencyGraphError("dependency graph node limit exceeded")
        if len(self.edges) > _MAX_GRAPH_EDGES:
            raise InvalidDependencyGraphError("dependency graph edge limit exceeded")
        if any(not isinstance(node, DependencyNode) for node in self.nodes):
            raise InvalidDependencyGraphError("dependency graph nodes must be canonical")
        if any(not isinstance(edge, DependencyEdge) for edge in self.edges):
            raise InvalidDependencyGraphError("dependency graph edges must be canonical")

        ordered_nodes = tuple(sorted(self.nodes, key=lambda node: _key_sort_key(node.key)))
        ordered_edges = tuple(sorted(self.edges, key=_edge_sort_key))
        object.__setattr__(self, "nodes", ordered_nodes)
        object.__setattr__(self, "edges", ordered_edges)

        node_map = {node.key: node for node in ordered_nodes}
        if len(node_map) != len(ordered_nodes):
            raise InvalidDependencyGraphError("dependency graph node keys must be unique")
        identities = tuple(edge.identity for edge in ordered_edges)
        if len(identities) != len(set(identities)):
            raise InvalidDependencyGraphError("dependency graph edges must be unique")

        edge_pairs = {(edge.source, edge.target) for edge in ordered_edges}
        if len(edge_pairs) != len(ordered_edges):
            raise InvalidDependencyGraphError(
                "a dependency graph allows only one edge per source-target pair"
            )
        for edge in ordered_edges:
            if edge.source not in node_map or edge.target not in node_map:
                raise InvalidDependencyGraphError(
                    "dependency edge endpoints must exist in the graph"
                )
            source_revision = node_map[edge.source].revision
            if edge.observed_source_revision > source_revision:
                raise InvalidDependencyGraphError(
                    "an edge cannot observe a source revision newer than the source node"
                )
        _assert_acyclic(tuple(node_map), ordered_edges)

        for node in ordered_nodes:
            for cause in node.invalidations:
                if cause.root not in node_map:
                    raise InvalidDependencyGraphError(
                        "an invalidation root must exist in the dependency graph"
                    )
                for source, target in zip(cause.path, cause.path[1:], strict=False):
                    if (source, target) not in edge_pairs:
                        raise InvalidDependencyGraphError(
                            "an invalidation path must follow dependency edges"
                        )

    @classmethod
    def empty(cls) -> Self:
        return cls(revision=RevisionVersion(1))

    def get_node(self, key: DependencyKey) -> DependencyNode:
        if not isinstance(key, DependencyKey):
            raise TypeError("dependency lookup requires a typed key")
        for node in self.nodes:
            if node.key == key:
                return node
        raise KeyError(key.token)

    def add_node(self, node: DependencyNode) -> Self:
        if not isinstance(node, DependencyNode):
            raise TypeError("dependency graphs require DependencyNode values")
        if any(current.key == node.key for current in self.nodes):
            raise InvalidDependencyGraphError(f"dependency node already exists: {node.key.token}")
        return replace(
            self,
            revision=_next_revision(self.revision),
            nodes=(*self.nodes, node),
        )

    def remove_node(self, key: DependencyKey) -> Self:
        self.get_node(key)
        if any(edge.source == key or edge.target == key for edge in self.edges):
            raise InvalidDependencyGraphError(
                "a dependency node with connected edges cannot be removed"
            )
        return replace(
            self,
            revision=_next_revision(self.revision),
            nodes=tuple(node for node in self.nodes if node.key != key),
        )

    def connect(
        self,
        source: DependencyKey,
        target: DependencyKey,
        relation: DependencyRelation,
        invalidation_mode: InvalidationMode,
    ) -> Self:
        source_node = self.get_node(source)
        self.get_node(target)
        if any(edge.source == source and edge.target == target for edge in self.edges):
            raise InvalidDependencyGraphError(
                f"dependency edge already exists: {source.token} -> {target.token}"
            )
        if (
            invalidation_mode is not InvalidationMode.NONE
            and source_node.freshness is not FreshnessState.FRESH
        ):
            raise InvalidDependencyGraphError(
                "a propagating dependency edge requires a fresh source"
            )
        edge = DependencyEdge(
            source=source,
            target=target,
            relation=relation,
            invalidation_mode=invalidation_mode,
            observed_source_revision=source_node.revision,
        )
        return replace(
            self,
            revision=_next_revision(self.revision),
            edges=(*self.edges, edge),
        )

    def disconnect(
        self,
        source: DependencyKey,
        target: DependencyKey,
        relation: DependencyRelation,
    ) -> Self:
        identity = (source, target, relation)
        if not any(edge.identity == identity for edge in self.edges):
            raise KeyError(f"{source.token}->{target.token}:{relation.value}")
        return replace(
            self,
            revision=_next_revision(self.revision),
            edges=tuple(edge for edge in self.edges if edge.identity != identity),
        )

    def dependencies_of(self, key: DependencyKey) -> tuple[DependencyEdge, ...]:
        self.get_node(key)
        return tuple(edge for edge in self.edges if edge.target == key)

    def dependents_of(
        self,
        key: DependencyKey,
        *,
        transitive: bool = False,
        include_nonpropagating: bool = True,
    ) -> tuple[DependencyKey, ...]:
        self.get_node(key)
        if not transitive:
            return tuple(
                edge.target
                for edge in self.edges
                if edge.source == key
                and (include_nonpropagating or edge.invalidation_mode is not InvalidationMode.NONE)
            )
        visited: set[DependencyKey] = set()
        pending = deque([key])
        while pending:
            current = pending.popleft()
            for edge in self.edges:
                if edge.source != current:
                    continue
                if not include_nonpropagating and edge.invalidation_mode is InvalidationMode.NONE:
                    continue
                if edge.target not in visited:
                    visited.add(edge.target)
                    pending.append(edge.target)
        visited.discard(key)
        return tuple(sorted(visited, key=_key_sort_key))

    def publish_revision(
        self,
        key: DependencyKey,
        revision: RevisionVersion,
        reason: InvalidationReason = SOURCE_CHANGED,
    ) -> InvalidationResult:
        """Publish a newer root-input revision and invalidate outdated dependents."""
        current = self.get_node(key)
        if not isinstance(revision, RevisionVersion):
            raise TypeError("publishing a dependency revision requires RevisionVersion")
        if revision <= current.revision:
            raise InvalidDependencyGraphError(
                "a published dependency revision must advance monotonically"
            )
        if not isinstance(reason, InvalidationReason):
            raise TypeError("publishing a revision requires InvalidationReason")
        propagating_inputs = tuple(
            edge
            for edge in self.dependencies_of(key)
            if edge.invalidation_mode is not InvalidationMode.NONE
        )
        if propagating_inputs:
            raise DependencyRefreshError(
                f"cannot publish dependent node {key.token}; use refresh instead"
            )

        updated = replace(
            current,
            revision=revision,
            freshness=FreshnessState.FRESH,
            invalidations=(),
        )
        graph = self._with_nodes(
            {**self._node_map(), key: updated},
            revision=_next_revision(self.revision),
        )
        eligible = frozenset(
            edge.identity
            for edge in graph.edges
            if edge.source == key
            and edge.invalidation_mode is not InvalidationMode.NONE
            and edge.observed_source_revision < revision
        )
        return graph._propagate(
            root=key,
            reason=reason,
            root_state=None,
            initial_edges=eligible,
        )

    def invalidate(
        self,
        key: DependencyKey,
        reason: InvalidationReason = MANUAL_INVALIDATION,
        *,
        state: FreshnessState = FreshnessState.STALE,
    ) -> InvalidationResult:
        """Mark one node invalid and propagate the strongest downstream impact."""
        self.get_node(key)
        if not isinstance(reason, InvalidationReason):
            raise TypeError("dependency invalidation requires InvalidationReason")
        if state is FreshnessState.FRESH or not isinstance(state, FreshnessState):
            raise InvalidDependencyGraphError("an explicit invalidation must be non-fresh")
        graph = replace(self, revision=_next_revision(self.revision))
        return graph._propagate(
            root=key,
            reason=reason,
            root_state=state,
            initial_edges=None,
        )

    def refresh(
        self,
        key: DependencyKey,
        revision: RevisionVersion,
        reason: InvalidationReason = SOURCE_CHANGED,
    ) -> InvalidationResult:
        """Rebuild a node from current fresh inputs and invalidate its dependents."""
        current = self.get_node(key)
        if not isinstance(revision, RevisionVersion):
            raise TypeError("refresh requires RevisionVersion")
        if revision <= current.revision:
            raise DependencyRefreshError("a refreshed node revision must advance")
        incoming = self.dependencies_of(key)
        blocking = tuple(
            self.get_node(edge.source).key
            for edge in incoming
            if edge.invalidation_mode is not InvalidationMode.NONE
            and self.get_node(edge.source).freshness is not FreshnessState.FRESH
        )
        if blocking:
            names = ", ".join(item.token for item in blocking)
            raise DependencyRefreshError(
                f"cannot refresh {key.token}; dependencies are not fresh: {names}"
            )

        nodes = self._node_map()
        nodes[key] = replace(
            current,
            revision=revision,
            freshness=FreshnessState.FRESH,
            invalidations=(),
        )
        edges = tuple(
            replace(
                edge,
                observed_source_revision=nodes[edge.source].revision,
            )
            if edge.target == key
            else edge
            for edge in self.edges
        )
        graph = DependencyGraph(
            revision=_next_revision(self.revision),
            nodes=tuple(nodes.values()),
            edges=edges,
        )
        eligible = frozenset(
            edge.identity
            for edge in graph.edges
            if edge.source == key
            and edge.invalidation_mode is not InvalidationMode.NONE
            and edge.observed_source_revision < revision
        )
        return graph._propagate(
            root=key,
            reason=reason,
            root_state=None,
            initial_edges=eligible,
        )

    def explain(self, key: DependencyKey) -> tuple[InvalidationCause, ...]:
        """Return persisted deterministic reasons for one node's freshness state."""
        return self.get_node(key).invalidations

    def topological_order(self) -> tuple[DependencyKey, ...]:
        """Return all graph nodes in deterministic dependency order."""
        return _topological_order(tuple(node.key for node in self.nodes), self.edges)

    def _node_map(self) -> dict[DependencyKey, DependencyNode]:
        return {node.key: node for node in self.nodes}

    def _with_nodes(
        self,
        nodes: dict[DependencyKey, DependencyNode],
        *,
        revision: RevisionVersion | None = None,
    ) -> DependencyGraph:
        return DependencyGraph(
            revision=revision or self.revision,
            nodes=tuple(nodes.values()),
            edges=self.edges,
        )

    def _propagate(
        self,
        *,
        root: DependencyKey,
        reason: InvalidationReason,
        root_state: FreshnessState | None,
        initial_edges: frozenset[tuple[DependencyKey, DependencyKey, DependencyRelation]] | None,
    ) -> InvalidationResult:
        nodes = self._node_map()
        best: dict[DependencyKey, tuple[FreshnessState, tuple[DependencyKey, ...]]] = {}
        pending: deque[tuple[DependencyKey, FreshnessState, tuple[DependencyKey, ...]]] = deque()

        if root_state is not None:
            best[root] = (root_state, (root,))
            pending.append((root, root_state, (root,)))
        else:
            pending.append((root, FreshnessState.FRESH, (root,)))

        outgoing: dict[DependencyKey, tuple[DependencyEdge, ...]] = {}
        for source in nodes:
            outgoing[source] = tuple(edge for edge in self.edges if edge.source == source)

        while pending:
            source, source_state, path = pending.popleft()
            for edge in outgoing[source]:
                if edge.invalidation_mode is InvalidationMode.NONE:
                    continue
                if (
                    source == root
                    and initial_edges is not None
                    and edge.identity not in initial_edges
                ):
                    continue
                edge_state = _state_for_mode(edge.invalidation_mode)
                candidate_state = _stronger_state(source_state, edge_state)
                candidate_path = (*path, edge.target)
                current = best.get(edge.target)
                if current is not None and not _better_impact(
                    candidate_state,
                    candidate_path,
                    current[0],
                    current[1],
                ):
                    continue
                best[edge.target] = (candidate_state, candidate_path)
                pending.append((edge.target, candidate_state, candidate_path))

        impacts: list[InvalidationCause] = []
        for affected, (state, path) in best.items():
            cause = InvalidationCause(
                root=root,
                affected=affected,
                reason=reason,
                state=state,
                path=path,
            )
            node = nodes[affected]
            invalidations = _merge_cause(node.invalidations, cause)
            nodes[affected] = replace(
                node,
                freshness=_freshness_from_causes(invalidations),
                invalidations=invalidations,
            )
            impacts.append(cause)

        graph = self._with_nodes(nodes)
        return InvalidationResult(
            graph=graph,
            impacts=tuple(sorted(impacts, key=_cause_sort_key)),
        )


def _key_sort_key(key: DependencyKey) -> tuple[str, str]:
    return (key.kind.value, key.id)


def _edge_sort_key(
    edge: DependencyEdge,
) -> tuple[str, str, str, str, str]:
    return (
        edge.source.kind.value,
        edge.source.id,
        edge.target.kind.value,
        edge.target.id,
        edge.relation.value,
    )


def _cause_sort_key(
    cause: InvalidationCause,
) -> tuple[str, str, str, str, tuple[str, ...]]:
    return (
        cause.affected.kind.value,
        cause.affected.id,
        cause.root.kind.value,
        cause.root.id,
        tuple(item.token for item in cause.path),
    )


def _freshness_from_causes(
    causes: tuple[InvalidationCause, ...],
) -> FreshnessState:
    if not causes:
        return FreshnessState.FRESH
    return max((cause.state for cause in causes), key=_FRESHNESS_SEVERITY.__getitem__)


def _state_for_mode(mode: InvalidationMode) -> FreshnessState:
    if mode is InvalidationMode.STALE:
        return FreshnessState.STALE
    if mode is InvalidationMode.REVIEW:
        return FreshnessState.REVIEW_REQUIRED
    raise InvalidDependencyGraphError("non-propagating edges do not have an impact state")


def _stronger_state(
    left: FreshnessState,
    right: FreshnessState,
) -> FreshnessState:
    return left if _FRESHNESS_SEVERITY[left] >= _FRESHNESS_SEVERITY[right] else right


def _better_impact(
    candidate_state: FreshnessState,
    candidate_path: tuple[DependencyKey, ...],
    current_state: FreshnessState,
    current_path: tuple[DependencyKey, ...],
) -> bool:
    candidate_severity = _FRESHNESS_SEVERITY[candidate_state]
    current_severity = _FRESHNESS_SEVERITY[current_state]
    if candidate_severity != current_severity:
        return candidate_severity > current_severity
    if len(candidate_path) != len(current_path):
        return len(candidate_path) < len(current_path)
    return tuple(item.token for item in candidate_path) < tuple(item.token for item in current_path)


def _merge_cause(
    causes: tuple[InvalidationCause, ...],
    candidate: InvalidationCause,
) -> tuple[InvalidationCause, ...]:
    identity = (candidate.root, candidate.reason.value)
    retained: list[InvalidationCause] = []
    existing: InvalidationCause | None = None
    for cause in causes:
        if (cause.root, cause.reason.value) == identity:
            existing = cause
        else:
            retained.append(cause)
    if existing is not None and not _better_impact(
        candidate.state,
        candidate.path,
        existing.state,
        existing.path,
    ):
        retained.append(existing)
    else:
        retained.append(candidate)
    if len(retained) > _MAX_INVALIDATIONS_PER_NODE:
        raise InvalidDependencyGraphError("a dependency node has too many invalidations")
    return tuple(sorted(retained, key=_cause_sort_key))


def _next_revision(current: RevisionVersion) -> RevisionVersion:
    return RevisionVersion(current.value + 1)


def _assert_acyclic(
    nodes: tuple[DependencyKey, ...],
    edges: tuple[DependencyEdge, ...],
) -> None:
    _topological_order(nodes, edges)


def _topological_order(
    nodes: tuple[DependencyKey, ...],
    edges: tuple[DependencyEdge, ...],
) -> tuple[DependencyKey, ...]:
    adjacency: dict[DependencyKey, list[DependencyKey]] = {node: [] for node in nodes}
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1
    for targets in adjacency.values():
        targets.sort(key=_key_sort_key)

    pending = deque(
        sorted(
            (node for node, count in indegree.items() if count == 0),
            key=_key_sort_key,
        )
    )
    ordered: list[DependencyKey] = []
    while pending:
        node = pending.popleft()
        ordered.append(node)
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)

    if len(ordered) != len(nodes):
        remaining = tuple(
            sorted(
                (node for node, count in indegree.items() if count > 0),
                key=_key_sort_key,
            )
        )
        rendered = ", ".join(node.token for node in remaining[:12])
        suffix = "" if len(remaining) <= 12 else ", ..."
        raise DependencyCycleError(f"dependency cycle detected among: {rendered}{suffix}")
    return tuple(ordered)
