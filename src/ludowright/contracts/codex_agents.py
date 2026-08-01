"""Contracts for versioned Codex specialist agents and routing."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.codex import (
    CodexOrchestrationPlanContract,
    OrchestrationActionType,
)
from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    ProfileGuidanceText,
    ReviewText,
    Slug,
)

AgentCapability = Slug
AgentScope = Slug
AgentRouteState = Literal["routed", "blocked", "complete"]


class CodexAgentProfileContract(ContractModel):
    """One data-defined specialist role in the local Codex adapter."""

    id: Slug
    version: PositiveRevision
    name: DisplayText
    purpose: ReviewText
    phase_ids: Annotated[tuple[Slug, ...], Field(min_length=1, max_length=8)]
    capabilities: Annotated[tuple[AgentCapability, ...], Field(min_length=1, max_length=32)]
    reads: Annotated[tuple[AgentScope, ...], Field(min_length=1, max_length=32)]
    writes: Annotated[tuple[AgentScope, ...], Field(max_length=32)] = ()
    guidance: Annotated[tuple[ProfileGuidanceText, ...], Field(min_length=1, max_length=8)]
    allowed_actions: Annotated[
        tuple[OrchestrationActionType, ...], Field(min_length=1, max_length=16)
    ]
    forbidden_actions: Annotated[tuple[Slug, ...], Field(min_length=1, max_length=16)]
    requires_human_checkpoint: bool = True
    can_approve: Literal[False] = False

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        _validate_sorted_unique(self.phase_ids, label="agent phase IDs")
        _validate_sorted_unique(self.capabilities, label="agent capabilities")
        _validate_sorted_unique(self.reads, label="agent read scopes")
        _validate_sorted_unique(self.writes, label="agent write scopes")
        _validate_sorted_unique(self.allowed_actions, label="agent allowed actions")
        _validate_sorted_unique(self.forbidden_actions, label="agent forbidden actions")
        required_boundaries = {
            "approve-reference",
            "invent-decision",
            "overwrite-approved-artifact",
        }
        if not required_boundaries.issubset(self.forbidden_actions):
            raise ValueError("specialist agents must declare the approval and overwrite boundaries")
        if set(self.reads) & set(self.writes):
            raise ValueError("agent read and write scopes must be disjoint")
        return self


class CodexAgentRouteRuleContract(ContractModel):
    """Deterministic task-to-agent route declared by the catalog."""

    task_id: Slug
    agent_id: Slug
    allowed_actions: Annotated[
        tuple[OrchestrationActionType, ...], Field(min_length=1, max_length=16)
    ]

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        _validate_sorted_unique(self.allowed_actions, label="agent route actions")
        return self


class CodexAgentCatalogContract(ContractModel):
    """Versioned catalog shipped with the project-local Codex skill."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-agent-catalog"] = "codex-agent-catalog"
    id: Slug
    version: PositiveRevision
    skill_id: Slug
    agents: Annotated[tuple[CodexAgentProfileContract, ...], Field(min_length=1, max_length=32)]
    routes: Annotated[tuple[CodexAgentRouteRuleContract, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        agent_ids = tuple(agent.id for agent in self.agents)
        route_ids = tuple(route.task_id for route in self.routes)
        _validate_sorted_unique(agent_ids, label="Codex agent IDs")
        _validate_sorted_unique(route_ids, label="Codex agent route task IDs")
        agents_by_id = {agent.id: agent for agent in self.agents}
        for route in self.routes:
            agent = agents_by_id.get(route.agent_id)
            if agent is None:
                raise ValueError(f"agent route references unknown agent: {route.agent_id}")
            if not set(route.allowed_actions).issubset(agent.allowed_actions):
                raise ValueError(f"agent route exceeds allowed actions: {route.task_id}")
        return self


class CodexAgentRoutingContextContract(ContractModel):
    """Read-only routing input combining a policy plan and a task request."""

    task_id: Slug
    plan: CodexOrchestrationPlanContract
    required_capabilities: tuple[AgentCapability, ...] = ()
    requested_agent_id: Slug | None = None

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        _validate_sorted_unique(self.required_capabilities, label="required agent capabilities")
        return self


class CodexAgentRouteContract(ContractModel):
    """Stable result of selecting a specialist without executing it."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-agent-route"] = "codex-agent-route"
    catalog_id: Slug
    catalog_version: Annotated[int, Field(ge=1, le=2_147_483_647)]
    task_id: Slug
    agent_id: Slug | None = None
    action: OrchestrationActionType
    state: AgentRouteState
    requires_human: bool
    can_approve: Literal[False] = False
    capabilities: tuple[AgentCapability, ...] = ()
    missing_capabilities: tuple[AgentCapability, ...] = ()
    reason: ReviewText

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        _validate_sorted_unique(self.capabilities, label="routed agent capabilities")
        _validate_sorted_unique(self.missing_capabilities, label="missing agent capabilities")
        if self.state == "routed" and self.agent_id is None:
            raise ValueError("a routed result must identify an agent")
        if self.state != "routed" and self.agent_id is not None:
            raise ValueError("a non-routed result cannot select an agent")
        if self.state != "blocked" and self.missing_capabilities:
            raise ValueError("missing capabilities are only valid for blocked routes")
        return self


def _validate_sorted_unique(values: tuple[str, ...], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    if tuple(sorted(values)) != values:
        raise ValueError(f"{label} must be sorted")


__all__ = [
    "CodexAgentCatalogContract",
    "CodexAgentProfileContract",
    "CodexAgentRouteContract",
    "CodexAgentRouteRuleContract",
    "CodexAgentRoutingContextContract",
]
