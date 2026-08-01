"""Load and route the versioned Codex specialist-agent catalog."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ludowright.contracts import (
    CodexAgentCatalogContract,
    CodexAgentProfileContract,
    CodexAgentRouteContract,
    CodexAgentRouteRuleContract,
    CodexAgentRoutingContextContract,
)

CODEX_AGENT_CATALOG_FILENAME = "agents.json"
CODEX_AGENT_CATALOG_MAX_BYTES = 400_000
_AGENT_DIRECTORY = Path(__file__).parent / "skills" / "ludowright"


class CodexAgentError(RuntimeError):
    """Base error for specialist-agent integration behavior."""


class CodexAgentDefinitionError(CodexAgentError):
    """Raised when packaged agent data is missing or malformed."""


class CodexAgentRoutingError(CodexAgentError):
    """Raised when an agent route cannot be interpreted safely."""


@dataclass(frozen=True, slots=True)
class CodexAgentCatalog:
    """Validated catalog and semantic hash used by the pure router."""

    contract: CodexAgentCatalogContract
    source_hash: str

    def __post_init__(self) -> None:
        if len(self.source_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_hash
        ):
            raise CodexAgentDefinitionError("agent catalog hash must be SHA-256")

    @property
    def id(self) -> str:
        """Return the stable catalog ID."""
        return self.contract.id

    @property
    def version(self) -> int:
        """Return the monotonic catalog revision."""
        return self.contract.version

    def agent(self, agent_id: str) -> CodexAgentProfileContract:
        """Return one declared agent or fail closed for an unknown ID."""
        for agent in self.contract.agents:
            if agent.id == agent_id:
                return agent
        raise CodexAgentRoutingError(f"unknown Codex specialist agent: {agent_id}")

    def route_rule(self, task_id: str) -> CodexAgentRouteRuleContract:
        """Return the one deterministic route for a task."""
        for route in self.contract.routes:
            if route.task_id == task_id:
                return route
        raise CodexAgentRoutingError(f"no Codex specialist route exists for task: {task_id}")


class CodexAgentRouter:
    """Select one specialist from a policy plan without executing it."""

    def __init__(self, catalog: CodexAgentCatalog) -> None:
        self._catalog = catalog

    @property
    def catalog(self) -> CodexAgentCatalog:
        """Return the immutable catalog used by this router."""
        return self._catalog

    def route(
        self,
        context: CodexAgentRoutingContextContract | Mapping[str, object],
    ) -> CodexAgentRouteContract:
        """Return a deterministic route or a fail-closed blocked result."""
        observation = (
            context
            if isinstance(context, CodexAgentRoutingContextContract)
            else CodexAgentRoutingContextContract.model_validate(context)
        )
        plan = observation.plan
        if plan.status_state == "unknown":
            return self._blocked(
                observation,
                "O status canônico precisa ser inspecionado antes de encaminhar um agente.",
            )
        if plan.status_state in {"blocked", "needs-review"}:
            return self._blocked(
                observation,
                "O status canônico exige resolução ou revisão humana antes do encaminhamento.",
            )
        if plan.action.action == "complete":
            return CodexAgentRouteContract(
                catalog_id=self._catalog.id,
                catalog_version=self._catalog.version,
                task_id=observation.task_id,
                action=plan.action.action,
                state="complete",
                requires_human=False,
                reason="O plano canônico já está concluído; nenhum agente deve ser executado.",
            )

        rule = self._catalog.route_rule(observation.task_id)
        agent = self._catalog.agent(rule.agent_id)
        if observation.requested_agent_id is not None and (
            observation.requested_agent_id != agent.id
        ):
            return self._blocked(
                observation,
                "O agente solicitado não corresponde à rota canônica da tarefa.",
            )
        if plan.action.action not in rule.allowed_actions:
            return self._blocked(
                observation,
                "A ação do plano não está autorizada para o agente desta tarefa.",
            )

        missing = tuple(sorted(set(observation.required_capabilities) - set(agent.capabilities)))
        if missing:
            return self._blocked(
                observation,
                "A tarefa exige capacidades que o agente publicado não declara.",
                missing_capabilities=missing,
            )

        return CodexAgentRouteContract(
            catalog_id=self._catalog.id,
            catalog_version=self._catalog.version,
            task_id=observation.task_id,
            agent_id=agent.id,
            action=plan.action.action,
            state="routed",
            requires_human=agent.requires_human_checkpoint or plan.action.requires_human,
            capabilities=agent.capabilities,
            reason=(
                f"Encaminhe a tarefa ao agente {agent.id}; a execução permanece limitada "
                "às ações e escopos publicados."
            ),
        )

    def _blocked(
        self,
        context: CodexAgentRoutingContextContract,
        reason: str,
        *,
        missing_capabilities: tuple[str, ...] = (),
    ) -> CodexAgentRouteContract:
        return CodexAgentRouteContract(
            catalog_id=self._catalog.id,
            catalog_version=self._catalog.version,
            task_id=context.task_id,
            action=context.plan.action.action,
            state="blocked",
            requires_human=context.plan.action.requires_human,
            missing_capabilities=missing_capabilities,
            reason=reason,
        )


def load_codex_agent_catalog() -> CodexAgentCatalog:
    """Load and validate the packaged specialist-agent catalog."""
    path = _AGENT_DIRECTORY / CODEX_AGENT_CATALOG_FILENAME
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise CodexAgentDefinitionError("packaged agent catalog is missing") from error
    if len(payload) > CODEX_AGENT_CATALOG_MAX_BYTES:
        raise CodexAgentDefinitionError("packaged agent catalog exceeds the size limit")
    try:
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        catalog = CodexAgentCatalogContract.model_validate(raw)
    except (UnicodeDecodeError, TypeError, ValueError, ValidationError) as error:
        raise CodexAgentDefinitionError("packaged agent catalog is invalid") from error
    canonical_payload = _canonical_json_bytes(catalog.model_dump(mode="json"))
    return CodexAgentCatalog(
        contract=catalog,
        source_hash=hashlib.sha256(canonical_payload).hexdigest(),
    )


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


__all__ = [
    "CODEX_AGENT_CATALOG_FILENAME",
    "CODEX_AGENT_CATALOG_MAX_BYTES",
    "CodexAgentCatalog",
    "CodexAgentDefinitionError",
    "CodexAgentError",
    "CodexAgentRouter",
    "CodexAgentRoutingError",
    "load_codex_agent_catalog",
]
