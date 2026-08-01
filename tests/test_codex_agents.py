"""Tests for the versioned Codex specialist-agent catalog and router."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from integrations.codex import (
    CodexAgentRouter,
    CodexAgentRoutingError,
    load_codex_agent_catalog,
)

from ludowright.contracts import (
    CodexAgentRoutingContextContract,
    CodexOrchestrationPlanContract,
)


def make_plan(
    action: str,
    *,
    status_state: str = "ready",
    plan_state: str = "continue",
    requires_human: bool = False,
) -> CodexOrchestrationPlanContract:
    return CodexOrchestrationPlanContract.model_validate(
        {
            "policy_id": "default",
            "policy_version": 1,
            "state": plan_state,
            "status_state": status_state,
            "action": {
                "action": action,
                "requires_human": requires_human,
                "reason": "Test action.",
            },
        }
    )


def route_context(
    task_id: str,
    action: str,
    *,
    status_state: str = "ready",
    plan_state: str = "continue",
    requires_human: bool = False,
    required_capabilities: tuple[str, ...] = (),
    requested_agent_id: str | None = None,
) -> CodexAgentRoutingContextContract:
    return CodexAgentRoutingContextContract(
        task_id=task_id,
        plan=make_plan(
            action,
            status_state=status_state,
            plan_state=plan_state,
            requires_human=requires_human,
        ),
        required_capabilities=required_capabilities,
        requested_agent_id=requested_agent_id,
    )


def test_packaged_catalog_declares_all_specialists_and_is_versioned() -> None:
    catalog = load_codex_agent_catalog()

    assert catalog.id == "default"
    assert catalog.version == 1
    assert {agent.id for agent in catalog.contract.agents} == {
        "asset-planner",
        "consistency-reviewer",
        "game-design-architect",
        "generation-operator",
        "interviewer",
        "quality-auditor",
        "release-verifier",
        "technical-architect",
        "visual-director",
    }
    assert tuple(agent.id for agent in catalog.contract.agents) == tuple(
        sorted(agent.id for agent in catalog.contract.agents)
    )
    assert len(catalog.contract.agents) == 9
    assert len(catalog.contract.routes) == 9
    assert all(agent.can_approve is False for agent in catalog.contract.agents)
    assert all(
        {"approve-reference", "invent-decision", "overwrite-approved-artifact"}.issubset(
            agent.forbidden_actions
        )
        for agent in catalog.contract.agents
    )


def test_every_declared_task_routes_to_its_declared_agent() -> None:
    catalog = load_codex_agent_catalog()
    router = CodexAgentRouter(catalog)

    results = []
    for rule in catalog.contract.routes:
        result = router.route(route_context(rule.task_id, rule.allowed_actions[0]))
        results.append(result.model_dump(mode="json"))
        assert result.state == "routed"
        assert result.agent_id == rule.agent_id
        assert result.can_approve is False
        assert result.requires_human is True

    repeated = router.route(
        route_context(
            catalog.contract.routes[0].task_id,
            catalog.contract.routes[0].allowed_actions[0],
        )
    ).model_dump(mode="json")
    assert repeated == results[0]


def test_route_is_deterministic_for_the_same_policy_plan() -> None:
    router = CodexAgentRouter(load_codex_agent_catalog())
    context = route_context(
        "visual-direction",
        "await-approval",
        requires_human=True,
    )

    first = router.route(context).model_dump(mode="json")
    second = router.route(context).model_dump(mode="json")

    assert first == second
    assert first["agent_id"] == "visual-director"
    assert first["requires_human"] is True
    assert first["can_approve"] is False


def test_router_blocks_before_status_inspection() -> None:
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        route_context("interview", "inspect-status", status_state="unknown")
    )

    assert result.state == "blocked"
    assert result.agent_id is None
    assert result.action == "inspect-status"


def test_router_blocks_project_status_that_needs_resolution() -> None:
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        route_context(
            "quality-audit",
            "report-blockers",
            status_state="blocked",
            plan_state="blocked",
        )
    )

    assert result.state == "blocked"
    assert result.agent_id is None


def test_router_returns_complete_without_selecting_an_agent() -> None:
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        route_context("release-verification", "complete", plan_state="complete")
    )

    assert result.state == "complete"
    assert result.agent_id is None
    assert result.requires_human is False


def test_router_blocks_missing_capabilities_without_fallback() -> None:
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        route_context(
            "asset-planning",
            "execute-phase",
            required_capabilities=("unpublished-capability",),
        )
    )

    assert result.state == "blocked"
    assert result.agent_id is None
    assert result.missing_capabilities == ("unpublished-capability",)


def test_router_blocks_action_not_allowed_for_task() -> None:
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        route_context("generation", "run-validations")
    )

    assert result.state == "blocked"
    assert result.agent_id is None


def test_router_blocks_a_noncanonical_requested_agent() -> None:
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        route_context(
            "interview",
            "ask-question",
            requested_agent_id="generation-operator",
        )
    )

    assert result.state == "blocked"
    assert result.agent_id is None


def test_unknown_task_is_a_routing_error() -> None:
    with pytest.raises(CodexAgentRoutingError, match="no Codex specialist route"):
        CodexAgentRouter(load_codex_agent_catalog()).route(
            route_context("unknown-task", "execute-phase")
        )


def test_skill_manifest_includes_the_agent_catalog() -> None:
    manifest = json.loads(
        Path("integrations/codex/skills/ludowright/manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["version"] == 3
    assert {item["path"] for item in manifest["files"]} == {
        "SKILL.md",
        "agents.json",
        "orchestration.json",
    }
