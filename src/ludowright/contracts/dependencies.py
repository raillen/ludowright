"""Versioned serialization contract for dependency and invalidation graphs."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import ContractModel, PositiveRevision, Slug
from ludowright.domain import (
    DependencyEdge,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    FreshnessState,
    InvalidationCause,
    InvalidationMode,
    InvalidationReason,
    RevisionVersion,
)


class DependencyKeyContract(ContractModel):
    kind: DependencyNodeKind
    id: Slug

    def to_domain(self) -> DependencyKey:
        return DependencyKey(kind=self.kind, id=self.id)

    @classmethod
    def from_domain(cls, value: DependencyKey) -> Self:
        return cls(kind=value.kind, id=value.id)


class InvalidationCauseContract(ContractModel):
    root: DependencyKeyContract
    affected: DependencyKeyContract
    reason: Slug
    state: FreshnessState
    path: Annotated[tuple[DependencyKeyContract, ...], Field(min_length=1, max_length=1_024)]

    def to_domain(self) -> InvalidationCause:
        return InvalidationCause(
            root=self.root.to_domain(),
            affected=self.affected.to_domain(),
            reason=InvalidationReason(self.reason),
            state=self.state,
            path=tuple(item.to_domain() for item in self.path),
        )

    @classmethod
    def from_domain(cls, value: InvalidationCause) -> Self:
        return cls(
            root=DependencyKeyContract.from_domain(value.root),
            affected=DependencyKeyContract.from_domain(value.affected),
            reason=value.reason.value,
            state=value.state,
            path=tuple(DependencyKeyContract.from_domain(item) for item in value.path),
        )


class DependencyNodeContract(ContractModel):
    key: DependencyKeyContract
    revision: PositiveRevision
    freshness: FreshnessState = FreshnessState.FRESH
    invalidations: Annotated[
        tuple[InvalidationCauseContract, ...],
        Field(max_length=256),
    ] = ()

    def to_domain(self) -> DependencyNode:
        return DependencyNode(
            key=self.key.to_domain(),
            revision=RevisionVersion(self.revision),
            freshness=self.freshness,
            invalidations=tuple(item.to_domain() for item in self.invalidations),
        )

    @classmethod
    def from_domain(cls, value: DependencyNode) -> Self:
        return cls(
            key=DependencyKeyContract.from_domain(value.key),
            revision=value.revision.value,
            freshness=value.freshness,
            invalidations=tuple(
                InvalidationCauseContract.from_domain(item)
                for item in value.invalidations
            ),
        )


class DependencyEdgeContract(ContractModel):
    source: DependencyKeyContract
    target: DependencyKeyContract
    relation: DependencyRelation
    invalidation_mode: InvalidationMode
    observed_source_revision: PositiveRevision

    def to_domain(self) -> DependencyEdge:
        return DependencyEdge(
            source=self.source.to_domain(),
            target=self.target.to_domain(),
            relation=self.relation,
            invalidation_mode=self.invalidation_mode,
            observed_source_revision=RevisionVersion(self.observed_source_revision),
        )

    @classmethod
    def from_domain(cls, value: DependencyEdge) -> Self:
        return cls(
            source=DependencyKeyContract.from_domain(value.source),
            target=DependencyKeyContract.from_domain(value.target),
            relation=value.relation,
            invalidation_mode=value.invalidation_mode,
            observed_source_revision=value.observed_source_revision.value,
        )


class DependencyGraphContract(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["dependency-graph"] = "dependency-graph"
    revision: PositiveRevision
    nodes: Annotated[tuple[DependencyNodeContract, ...], Field(max_length=100_000)] = ()
    edges: Annotated[tuple[DependencyEdgeContract, ...], Field(max_length=500_000)] = ()

    def to_domain(self) -> DependencyGraph:
        return DependencyGraph(
            revision=RevisionVersion(self.revision),
            nodes=tuple(node.to_domain() for node in self.nodes),
            edges=tuple(edge.to_domain() for edge in self.edges),
        )

    @classmethod
    def from_domain(cls, value: DependencyGraph) -> Self:
        if not isinstance(value, DependencyGraph):
            raise TypeError("dependency graph serialization requires DependencyGraph")
        return cls(
            revision=value.revision.value,
            nodes=tuple(DependencyNodeContract.from_domain(node) for node in value.nodes),
            edges=tuple(DependencyEdgeContract.from_domain(edge) for edge in value.edges),
        )

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        self.to_domain()
        return self
