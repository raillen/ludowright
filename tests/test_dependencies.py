"""Tests for typed dependency graphs and deterministic stale propagation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.contracts import DependencyGraphContract
from ludowright.domain import (
    APPROVAL_REVOKED,
    SOURCE_CHANGED,
    SOURCE_REJECTED,
    DependencyCycleError,
    DependencyEdge,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRefreshError,
    DependencyRelation,
    FreshnessState,
    InvalidationCause,
    InvalidationMode,
    InvalidationReason,
    InvalidDependencyGraphError,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DependencyGraphRepository,
    ProjectFilesystem,
    StructuredDocumentConflictError,
)


def key(kind: DependencyNodeKind, value: str) -> DependencyKey:
    return DependencyKey(kind=kind, id=value)


def node(kind: DependencyNodeKind, value: str, revision: int = 1) -> DependencyNode:
    return DependencyNode(key=key(kind, value), revision=RevisionVersion(revision))


def character_graph() -> tuple[
    DependencyGraph,
    DependencyKey,
    DependencyKey,
    DependencyKey,
    DependencyKey,
]:
    body = key(DependencyNodeKind.COMPONENT, "maya-body")
    garment = key(DependencyNodeKind.COMPONENT, "maya-jacket")
    sheet = key(DependencyNodeKind.TECHNICAL_SHEET, "maya-model-sheet")
    portrait = key(DependencyNodeKind.REFERENCE, "maya-portrait")
    graph = DependencyGraph.empty()
    for item in (
        DependencyNode(body, RevisionVersion(1)),
        DependencyNode(garment, RevisionVersion(1)),
        DependencyNode(sheet, RevisionVersion(1)),
        DependencyNode(portrait, RevisionVersion(1)),
    ):
        graph = graph.add_node(item)
    graph = graph.connect(
        body,
        garment,
        DependencyRelation.REQUIRES,
        InvalidationMode.STALE,
    )
    graph = graph.connect(
        garment,
        sheet,
        DependencyRelation.ASSEMBLED_FROM,
        InvalidationMode.STALE,
    )
    graph = graph.connect(
        body,
        portrait,
        DependencyRelation.REFERENCES,
        InvalidationMode.REVIEW,
    )
    return graph, body, garment, sheet, portrait


def test_dependency_key_is_typed_and_canonical() -> None:
    value = key(DependencyNodeKind.ASSET, "maya")

    assert value.token == "asset:maya"
    assert str(value) == "asset:maya"
    with pytest.raises(InvalidDependencyGraphError, match="canonical"):
        DependencyKey(DependencyNodeKind.ASSET, "Maya Character")
    with pytest.raises(InvalidDependencyGraphError, match="valid node kind"):
        DependencyKey("asset", "maya")  # type: ignore[arg-type]


def test_node_freshness_is_derived_from_causes() -> None:
    asset = key(DependencyNodeKind.ASSET, "maya")
    cause = InvalidationCause(
        root=asset,
        affected=asset,
        reason=SOURCE_REJECTED,
        state=FreshnessState.STALE,
        path=(asset,),
    )

    stale = DependencyNode(
        key=asset,
        revision=RevisionVersion(1),
        freshness=FreshnessState.STALE,
        invalidations=(cause,),
    )

    assert stale.invalidations == (cause,)
    with pytest.raises(InvalidDependencyGraphError, match="strongest"):
        DependencyNode(
            key=asset,
            revision=RevisionVersion(1),
            freshness=FreshnessState.FRESH,
            invalidations=(cause,),
        )


def test_graph_orders_nodes_and_edges_deterministically() -> None:
    asset = node(DependencyNodeKind.ASSET, "maya")
    document = node(DependencyNodeKind.DOCUMENT, "gdd")
    edge = DependencyEdge(
        source=document.key,
        target=asset.key,
        relation=DependencyRelation.DERIVES_FROM,
        invalidation_mode=InvalidationMode.REVIEW,
        observed_source_revision=document.revision,
    )

    graph = DependencyGraph(
        revision=RevisionVersion(1),
        nodes=(document, asset),
        edges=(edge,),
    )

    assert tuple(item.key.token for item in graph.nodes) == ("asset:maya", "document:gdd")
    assert graph.edges == (edge,)


def test_graph_rejects_duplicate_nodes_and_missing_endpoints() -> None:
    asset = node(DependencyNodeKind.ASSET, "maya")

    with pytest.raises(InvalidDependencyGraphError, match="unique"):
        DependencyGraph(
            revision=RevisionVersion(1),
            nodes=(asset, asset),
        )

    missing = key(DependencyNodeKind.DOCUMENT, "gdd")
    edge = DependencyEdge(
        source=missing,
        target=asset.key,
        relation=DependencyRelation.DERIVES_FROM,
        invalidation_mode=InvalidationMode.STALE,
        observed_source_revision=RevisionVersion(1),
    )
    with pytest.raises(InvalidDependencyGraphError, match="endpoints"):
        DependencyGraph(
            revision=RevisionVersion(1),
            nodes=(asset,),
            edges=(edge,),
        )


def test_graph_rejects_self_edges_and_directed_cycles() -> None:
    first = node(DependencyNodeKind.DOCUMENT, "product-vision")
    second = node(DependencyNodeKind.DOCUMENT, "gdd")

    with pytest.raises(InvalidDependencyGraphError, match="itself"):
        DependencyEdge(
            source=first.key,
            target=first.key,
            relation=DependencyRelation.REQUIRES,
            invalidation_mode=InvalidationMode.STALE,
            observed_source_revision=first.revision,
        )

    graph = DependencyGraph.empty().add_node(first).add_node(second)
    graph = graph.connect(
        first.key,
        second.key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.STALE,
    )
    with pytest.raises(DependencyCycleError, match="dependency cycle detected"):
        graph.connect(
            second.key,
            first.key,
            DependencyRelation.DERIVES_FROM,
            InvalidationMode.STALE,
        )


def test_connect_records_the_observed_source_revision() -> None:
    source = node(DependencyNodeKind.DOCUMENT, "visual-bible", revision=3)
    target = node(DependencyNodeKind.CAPTURE_PROFILE, "humanoid")
    graph = DependencyGraph.empty().add_node(source).add_node(target)

    graph = graph.connect(
        source.key,
        target.key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.STALE,
    )

    assert graph.edges[0].observed_source_revision == RevisionVersion(3)
    assert graph.revision == RevisionVersion(4)


def test_publish_revision_marks_hard_and_soft_dependents() -> None:
    graph, body, garment, sheet, portrait = character_graph()

    result = graph.publish_revision(body, RevisionVersion(2))

    assert result.graph.get_node(body).revision == RevisionVersion(2)
    assert result.graph.get_node(body).freshness is FreshnessState.FRESH
    assert result.graph.get_node(garment).freshness is FreshnessState.STALE
    assert result.graph.get_node(sheet).freshness is FreshnessState.STALE
    assert result.graph.get_node(portrait).freshness is FreshnessState.REVIEW_REQUIRED
    assert result.affected == (garment, portrait, sheet)

    garment_cause = result.graph.explain(garment)[0]
    sheet_cause = result.graph.explain(sheet)[0]
    portrait_cause = result.graph.explain(portrait)[0]
    assert garment_cause.path == (body, garment)
    assert sheet_cause.path == (body, garment, sheet)
    assert portrait_cause.path == (body, portrait)
    assert all(cause.reason == SOURCE_CHANGED for cause in result.impacts)


def test_nonpropagating_edge_remains_informational() -> None:
    source = node(DependencyNodeKind.DOCUMENT, "market-notes")
    target = node(DependencyNodeKind.DOCUMENT, "product-vision")
    graph = DependencyGraph.empty().add_node(source).add_node(target)
    graph = graph.connect(
        source.key,
        target.key,
        DependencyRelation.REFERENCES,
        InvalidationMode.NONE,
    )

    result = graph.publish_revision(source.key, RevisionVersion(2))

    assert result.impacts == ()
    assert result.graph.get_node(target.key).freshness is FreshnessState.FRESH
    assert graph.dependents_of(source.key) == (target.key,)
    assert (
        graph.dependents_of(
            source.key,
            include_nonpropagating=False,
        )
        == ()
    )


def test_stronger_transitive_path_wins_over_shorter_soft_path() -> None:
    root = node(DependencyNodeKind.DOCUMENT, "visual-bible")
    review = node(DependencyNodeKind.CAPTURE_PROFILE, "character-profile")
    output = node(DependencyNodeKind.TECHNICAL_SHEET, "character-sheet")
    graph = DependencyGraph.empty().add_node(root).add_node(review).add_node(output)
    graph = graph.connect(
        root.key,
        output.key,
        DependencyRelation.REFERENCES,
        InvalidationMode.REVIEW,
    )
    graph = graph.connect(
        root.key,
        review.key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.REVIEW,
    )
    graph = graph.connect(
        review.key,
        output.key,
        DependencyRelation.REQUIRES,
        InvalidationMode.STALE,
    )

    result = graph.publish_revision(root.key, RevisionVersion(2))
    cause = result.graph.explain(output.key)[0]

    assert cause.state is FreshnessState.STALE
    assert cause.path == (root.key, review.key, output.key)


def test_explicit_stale_invalidation_includes_root_and_propagates() -> None:
    graph, body, garment, sheet, portrait = character_graph()

    result = graph.invalidate(body, SOURCE_REJECTED)

    assert result.graph.get_node(body).freshness is FreshnessState.STALE
    assert result.graph.get_node(garment).freshness is FreshnessState.STALE
    assert result.graph.get_node(sheet).freshness is FreshnessState.STALE
    assert result.graph.get_node(portrait).freshness is FreshnessState.STALE
    assert result.graph.explain(body)[0].path == (body,)


def test_multiple_roots_remain_explainable() -> None:
    first = node(DependencyNodeKind.REFERENCE, "front")
    second = node(DependencyNodeKind.REFERENCE, "back")
    sheet = node(DependencyNodeKind.TECHNICAL_SHEET, "model-sheet")
    graph = DependencyGraph.empty().add_node(first).add_node(second).add_node(sheet)
    graph = graph.connect(
        first.key,
        sheet.key,
        DependencyRelation.ASSEMBLED_FROM,
        InvalidationMode.STALE,
    )
    graph = graph.connect(
        second.key,
        sheet.key,
        DependencyRelation.ASSEMBLED_FROM,
        InvalidationMode.STALE,
    )

    graph = graph.publish_revision(first.key, RevisionVersion(2)).graph
    graph = graph.invalidate(second.key, APPROVAL_REVOKED).graph
    causes = graph.explain(sheet.key)

    assert len(causes) == 2
    assert {cause.root for cause in causes} == {first.key, second.key}
    assert {cause.reason for cause in causes} == {SOURCE_CHANGED, APPROVAL_REVOKED}


def test_refresh_reconciles_incoming_revisions_and_reinvalidates_outputs() -> None:
    graph, body, garment, sheet, _portrait = character_graph()
    graph = graph.publish_revision(body, RevisionVersion(2)).graph

    refreshed = graph.refresh(garment, RevisionVersion(2))

    assert refreshed.graph.get_node(garment).freshness is FreshnessState.FRESH
    incoming = refreshed.graph.dependencies_of(garment)
    assert incoming[0].observed_source_revision == RevisionVersion(2)
    assert refreshed.graph.get_node(sheet).freshness is FreshnessState.STALE
    sheet_causes = refreshed.graph.explain(sheet)
    assert any(cause.root == garment for cause in sheet_causes)


def test_refresh_is_blocked_by_nonfresh_inputs() -> None:
    source = node(DependencyNodeKind.REFERENCE, "maya-front")
    target = node(DependencyNodeKind.VISUAL_JOB, "maya-turnaround")
    graph = DependencyGraph.empty().add_node(source).add_node(target)
    graph = graph.connect(
        source.key,
        target.key,
        DependencyRelation.REQUIRES,
        InvalidationMode.STALE,
    )
    graph = graph.invalidate(source.key, SOURCE_REJECTED).graph

    with pytest.raises(DependencyRefreshError, match="dependencies are not fresh"):
        graph.refresh(target.key, RevisionVersion(2))


def test_dependents_are_stable_for_direct_and_transitive_queries() -> None:
    graph, body, garment, sheet, portrait = character_graph()

    assert graph.dependents_of(body) == (garment, portrait)
    assert graph.dependents_of(body, transitive=True) == (garment, portrait, sheet)


def test_connected_nodes_require_explicit_disconnect_before_removal() -> None:
    source = node(DependencyNodeKind.DOCUMENT, "vision")
    target = node(DependencyNodeKind.DOCUMENT, "gdd")
    graph = DependencyGraph.empty().add_node(source).add_node(target)
    graph = graph.connect(
        source.key,
        target.key,
        DependencyRelation.DERIVES_FROM,
        InvalidationMode.STALE,
    )

    with pytest.raises(InvalidDependencyGraphError, match="connected"):
        graph.remove_node(source.key)

    graph = graph.disconnect(
        source.key,
        target.key,
        DependencyRelation.DERIVES_FROM,
    )
    graph = graph.remove_node(source.key)
    assert tuple(item.key for item in graph.nodes) == (target.key,)


def test_contract_round_trip_preserves_impact_paths() -> None:
    graph, body, _garment, sheet, _portrait = character_graph()
    graph = graph.publish_revision(body, RevisionVersion(2)).graph

    contract = DependencyGraphContract.from_domain(graph)
    restored = contract.to_domain()

    assert restored == graph
    assert restored.explain(sheet)[0].path[0] == body
    with pytest.raises(ValidationError):
        DependencyGraphContract.model_validate(
            {
                **contract.model_dump(mode="json"),
                "unexpected": True,
            }
        )


def test_contract_rejects_invalid_persisted_freshness() -> None:
    asset = key(DependencyNodeKind.ASSET, "maya")
    payload = {
        "schema_version": 1,
        "kind": "dependency-graph",
        "revision": 1,
        "nodes": [
            {
                "key": {"kind": "asset", "id": "maya"},
                "revision": 1,
                "freshness": "stale",
                "invalidations": [],
            }
        ],
        "edges": [],
    }

    with pytest.raises(ValidationError, match="strongest"):
        DependencyGraphContract.model_validate(payload)
    assert asset.token == "asset:maya"


def test_repository_create_load_replace_and_conflict(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    repository = DependencyGraphRepository(filesystem)
    graph, body, _garment, _sheet, _portrait = character_graph()

    created = repository.create(graph)
    loaded = repository.load()
    updated = graph.publish_revision(body, RevisionVersion(2)).graph
    replaced = repository.replace(loaded, updated)

    assert created.path == DEFAULT_DEPENDENCY_GRAPH_PATH
    assert created.canonical is True
    assert loaded.graph == graph
    assert replaced.graph == updated
    assert replaced.digest != loaded.digest
    with pytest.raises(StructuredDocumentConflictError, match="changed before save"):
        repository.replace(loaded, graph)


def test_repository_output_is_deterministic_and_canonical(tmp_path: Path) -> None:
    repository = DependencyGraphRepository(ProjectFilesystem(tmp_path))
    graph, _body, _garment, _sheet, _portrait = character_graph()

    first = repository.canonical_bytes(graph)
    second = repository.canonical_bytes(
        DependencyGraphContract.model_validate(json.loads(first)).to_domain()
    )

    assert first == second
    assert first.endswith(b"\n")
    assert json.loads(first)["kind"] == "dependency-graph"


def test_repository_optional_load_returns_none_for_missing_graph(tmp_path: Path) -> None:
    repository = DependencyGraphRepository(ProjectFilesystem(tmp_path))

    assert repository.load_optional() is None


def test_edge_cannot_observe_a_future_source_revision() -> None:
    source = node(DependencyNodeKind.DOCUMENT, "vision")
    target = node(DependencyNodeKind.DOCUMENT, "gdd")
    edge = DependencyEdge(
        source=source.key,
        target=target.key,
        relation=DependencyRelation.DERIVES_FROM,
        invalidation_mode=InvalidationMode.STALE,
        observed_source_revision=RevisionVersion(2),
    )

    with pytest.raises(InvalidDependencyGraphError, match="newer"):
        DependencyGraph(
            revision=RevisionVersion(1),
            nodes=(source, target),
            edges=(edge,),
        )


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
    nodes = tuple(node(DependencyNodeKind.DOCUMENT, f"node-{index:04d}") for index in range(1_500))
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


def test_reason_is_extensible_but_canonical() -> None:
    assert InvalidationReason("palette-changed").value == "palette-changed"
    with pytest.raises(InvalidDependencyGraphError, match="canonical slug"):
        InvalidationReason("Palette changed")
