"""Apply dependency graph review fixes before final validation."""

from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"dependency review marker not found: {label}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, new: str, label: str) -> str:
    if new in text:
        return text
    try:
        start_index = text.index(start)
        end_index = text.index(end, start_index)
    except ValueError as error:
        raise SystemExit(f"dependency review marker not found: {label}") from error
    return text[:start_index] + new + text[end_index:]


def patch_domain() -> None:
    path = "src/ludowright/domain/dependencies.py"
    text = read(path)
    text = replace_once(
        text,
        "        edge_pairs = {(edge.source, edge.target) for edge in ordered_edges}\n"
        "        for edge in ordered_edges:\n",
        "        edge_pairs = {(edge.source, edge.target) for edge in ordered_edges}\n"
        "        if len(edge_pairs) != len(ordered_edges):\n"
        "            raise InvalidDependencyGraphError(\n"
        "                \"a dependency graph allows only one edge per source-target pair\"\n"
        "            )\n"
        "        for edge in ordered_edges:\n",
        "parallel edge validation",
    )

    connect = '''    def connect(
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

'''
    text = replace_between(
        text,
        "    def connect(\n",
        "    def disconnect(\n",
        connect,
        "connect method",
    )

    publish = '''    def publish_revision(
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

'''
    text = replace_between(
        text,
        "    def publish_revision(\n",
        "    def invalidate(\n",
        publish,
        "publish revision method",
    )

    cycle = '''def _assert_acyclic(
    nodes: tuple[DependencyKey, ...],
    edges: tuple[DependencyEdge, ...],
) -> None:
    adjacency: dict[DependencyKey, list[DependencyKey]] = {
        node: [] for node in nodes
    }
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
    visited = 0
    while pending:
        node = pending.popleft()
        visited += 1
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)

    if visited != len(nodes):
        remaining = tuple(
            sorted(
                (node for node, count in indegree.items() if count > 0),
                key=_key_sort_key,
            )
        )
        rendered = ", ".join(node.token for node in remaining[:12])
        suffix = "" if len(remaining) <= 12 else ", ..."
        raise DependencyCycleError(
            f"dependency cycle detected among: {rendered}{suffix}"
        )
'''
    start = "def _assert_acyclic(\n"
    if cycle not in text:
        try:
            start_index = text.index(start)
        except ValueError as error:
            raise SystemExit("dependency review marker not found: cycle function") from error
        text = text[:start_index] + cycle
    write(path, text)


def patch_tests() -> None:
    path = "tests/test_dependencies.py"
    text = read(path)
    marker = "\ndef test_reason_is_extensible_but_canonical() -> None:\n"
    tests = '''
def test_publish_revision_cannot_bypass_dependent_refresh() -> None:
    source = node(DependencyNodeKind.REFERENCE, "maya-front")
    target = node(DependencyNodeKind.VISUAL_JOB, "maya-turnaround")
    graph = DependencyGraph.empty().add_node(source).add_node(target)
    graph = graph.connect(
        source.key,
        target.key,
        DependencyRelation.REQUIRES,
        InvalidationMode.STALE,
    )
    graph = graph.publish_revision(source.key, RevisionVersion(2)).graph

    with pytest.raises(DependencyRefreshError, match="use refresh"):
        graph.publish_revision(target.key, RevisionVersion(2))

    assert graph.get_node(target.key).freshness is FreshnessState.STALE


def test_connect_rejects_nonfresh_propagating_source() -> None:
    source = node(DependencyNodeKind.REFERENCE, "rejected-front")
    target = node(DependencyNodeKind.VISUAL_JOB, "turnaround")
    graph = DependencyGraph.empty().add_node(source).add_node(target)
    graph = graph.invalidate(source.key, SOURCE_REJECTED).graph

    with pytest.raises(InvalidDependencyGraphError, match="requires a fresh source"):
        graph.connect(
            source.key,
            target.key,
            DependencyRelation.REQUIRES,
            InvalidationMode.STALE,
        )

    informational = graph.connect(
        source.key,
        target.key,
        DependencyRelation.REFERENCES,
        InvalidationMode.NONE,
    )
    assert informational.get_node(target.key).freshness is FreshnessState.FRESH


def test_graph_rejects_parallel_edges_for_one_ordered_pair() -> None:
    source = node(DependencyNodeKind.DOCUMENT, "visual-bible")
    target = node(DependencyNodeKind.CAPTURE_PROFILE, "humanoid")
    graph = DependencyGraph.empty().add_node(source).add_node(target)
    graph = graph.connect(
        source.key,
        target.key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.STALE,
    )

    with pytest.raises(InvalidDependencyGraphError, match="already exists"):
        graph.connect(
            source.key,
            target.key,
            DependencyRelation.REFERENCES,
            InvalidationMode.REVIEW,
        )


def test_deep_acyclic_graph_uses_iterative_cycle_validation() -> None:
    nodes = tuple(
        node(DependencyNodeKind.DOCUMENT, f"node-{index:04d}")
        for index in range(1_500)
    )
    edges = tuple(
        DependencyEdge(
            source=nodes[index].key,
            target=nodes[index + 1].key,
            relation=DependencyRelation.REQUIRES,
            invalidation_mode=InvalidationMode.STALE,
            observed_source_revision=RevisionVersion(1),
        )
        for index in range(len(nodes) - 1)
    )

    graph = DependencyGraph(
        revision=RevisionVersion(1),
        nodes=nodes,
        edges=edges,
    )

    assert len(graph.nodes) == 1_500
    assert len(graph.edges) == 1_499

'''
    if "test_publish_revision_cannot_bypass_dependent_refresh" not in text:
        if marker not in text:
            raise SystemExit("dependency review marker not found: regression tests")
        text = text.replace(marker, tests + marker, 1)
    write(path, text)


def patch_docs() -> None:
    path = "docs/contracts/DEPENDENCY_GRAPH.md"
    text = read(path)
    text = replace_once(
        text,
        "If the body advances to revision 5, the edge is outdated and its target is invalidated according to the edge policy.\n\n"
        "An edge cannot claim to have observed a revision newer than its source node.\n",
        "If the body advances to revision 5, the edge is outdated and its target is invalidated according to the edge policy.\n\n"
        "An edge cannot claim to have observed a revision newer than its source node. A propagating edge can only be connected while its source is fresh; informational `none` edges may still describe non-fresh sources.\n",
        "fresh source connection docs",
    )
    text = replace_once(
        text,
        "`publish_revision(key, revision)` requires a strictly newer node revision.\n",
        "`publish_revision(key, revision)` requires a strictly newer node revision and is reserved for root inputs without propagating incoming dependencies. Derived nodes must use `refresh()` so their consumed input revisions are reconciled instead of bypassed.\n",
        "root-only publish docs",
    )
    text = replace_once(
        text,
        "Node and edge identities are unique.\n\n"
        "A connected node cannot be removed.",
        "Node identities are unique. The graph allows at most one edge for each ordered source-target pair, so relation and invalidation policy cannot become ambiguous across parallel edges.\n\n"
        "A connected node cannot be removed.",
        "single ordered edge docs",
    )
    text = replace_once(
        text,
        "Rejecting all cycles keeps topological planning, stale propagation, impact explanations, and future rebuild ordering deterministic.\n",
        "Rejecting all cycles keeps topological planning, stale propagation, impact explanations, and future rebuild ordering deterministic. Cycle validation uses iterative topological traversal so valid deep DAGs remain supported within the published resource limits.\n",
        "iterative cycle docs",
    )
    write(path, text)

    path = "docs/decisions/0013-versioned-acyclic-dependency-invalidation-graph.md"
    text = read(path)
    marker = "### Positive\n\n"
    additions = (
        "- Propagating edges require fresh sources, preventing new dependents from starting from already invalid inputs.\n"
        "- Root publication and derived refresh are separate operations, so consumed input revisions cannot be bypassed.\n"
        "- One edge per ordered node pair keeps invalidation policy unambiguous.\n"
        "- Iterative cycle validation supports deep valid DAGs without Python recursion limits.\n"
    )
    if additions not in text:
        if marker not in text:
            raise SystemExit("dependency review marker not found: ADR consequences")
        text = text.replace(marker, marker + additions, 1)
    write(path, text)


if __name__ == "__main__":
    patch_domain()
    patch_tests()
    patch_docs()
