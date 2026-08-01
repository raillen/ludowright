"""Deterministic, provider-neutral Codex orchestration policy planning."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ludowright.contracts import (
    CodexOrchestrationActionContract,
    CodexOrchestrationContextContract,
    CodexOrchestrationPhaseContract,
    CodexOrchestrationPlanContract,
    CodexOrchestrationPolicyContract,
)
from ludowright.contracts.codex import OrchestrationPlanState

CODEX_ORCHESTRATION_POLICY_FILENAME = "orchestration.json"
CODEX_ORCHESTRATION_POLICY_MAX_BYTES = 200_000
_POLICY_DIRECTORY = Path(__file__).parent / "skills" / "ludowright"


class CodexOrchestrationError(RuntimeError):
    """Base error for the Codex orchestration policy."""


class CodexOrchestrationDefinitionError(CodexOrchestrationError):
    """Raised when packaged orchestration data is malformed."""


@dataclass(frozen=True, slots=True)
class CodexOrchestrationPolicy:
    """Validated policy data with a pure next-action planner."""

    contract: CodexOrchestrationPolicyContract
    source_hash: str

    def __post_init__(self) -> None:
        if len(self.source_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_hash
        ):
            raise CodexOrchestrationDefinitionError("orchestration policy hash must be SHA-256")

    @property
    def id(self) -> str:
        """Return the stable policy ID."""
        return self.contract.id

    @property
    def version(self) -> int:
        """Return the monotonic policy revision."""
        return self.contract.version

    def plan(
        self,
        context: CodexOrchestrationContextContract | Mapping[str, object],
    ) -> CodexOrchestrationPlanContract:
        """Select one safe next action without changing project state."""
        observation = (
            context
            if isinstance(context, CodexOrchestrationContextContract)
            else CodexOrchestrationContextContract.model_validate(context)
        )
        self._validate_context_references(observation)

        if not observation.status_inspected:
            return self._plan(
                observation,
                state="continue",
                action=CodexOrchestrationActionContract(
                    action="inspect-status",
                    requires_human=False,
                    reason="Inspecione o status canônico antes de propor ou executar uma ação.",
                ),
            )
        if observation.status_state == "blocked":
            return self._plan(
                observation,
                state="blocked",
                action=CodexOrchestrationActionContract(
                    action="report-blockers",
                    requires_human=False,
                    reason=(
                        "O status canônico contém bloqueios que precisam ser "
                        "preservados e reportados."
                    ),
                ),
            )
        if observation.status_state == "needs-review":
            return self._plan(
                observation,
                state="review-required",
                action=CodexOrchestrationActionContract(
                    action="review-status",
                    requires_human=True,
                    reason="O status canônico exige revisão antes de continuar o fluxo.",
                ),
            )
        if observation.unresolved_questions:
            question_id = observation.unresolved_questions[0]
            return self._plan(
                observation,
                state="awaiting-input",
                action=CodexOrchestrationActionContract(
                    action="ask-question",
                    subject_id=question_id,
                    requires_human=True,
                    reason="Pergunte somente a primeira questão ainda não resolvida.",
                ),
            )
        if observation.decisions_to_record:
            decision_id = observation.decisions_to_record[0]
            return self._plan(
                observation,
                state="continue",
                action=CodexOrchestrationActionContract(
                    action="record-decision",
                    subject_id=decision_id,
                    reason="Registre a decisão canônica antes de prosseguir.",
                ),
            )
        if observation.failed_validations:
            validation_id = observation.failed_validations[0]
            return self._plan(
                observation,
                state="blocked",
                action=CodexOrchestrationActionContract(
                    action="resolve-validation",
                    subject_id=validation_id,
                    reason="Uma validação obrigatória falhou; corrija a causa antes de continuar.",
                ),
            )
        if observation.pending_validations:
            return self._plan(
                observation,
                state="continue",
                action=CodexOrchestrationActionContract(
                    action="run-validations",
                    subject_id=observation.pending_validations[0],
                    reason=(
                        "Execute as validações obrigatórias antes de produzir ou alterar artefatos."
                    ),
                ),
            )
        if observation.pending_approvals:
            approval_id = observation.pending_approvals[0]
            return self._plan(
                observation,
                state="approval-required",
                action=CodexOrchestrationActionContract(
                    action="await-approval",
                    subject_id=approval_id,
                    requires_human=True,
                    reason="A aprovação humana explícita é necessária neste checkpoint.",
                ),
            )
        if observation.resume_workflow_id is not None:
            return self._plan(
                observation,
                state="continue",
                action=CodexOrchestrationActionContract(
                    action="resume-workflow",
                    phase_id=observation.resume_phase_id,
                    subject_id=observation.resume_workflow_id,
                    reason="Retome o cursor durável depois de revalidar o estado do projeto.",
                ),
            )

        phase = self._next_phase(observation.completed_phases)
        if phase is not None:
            return self._plan(
                observation,
                state="continue",
                action=CodexOrchestrationActionContract(
                    action="execute-phase",
                    phase_id=phase.id,
                    reason=phase.purpose,
                ),
            )
        return self._plan(
            observation,
            state="complete",
            action=CodexOrchestrationActionContract(
                action="complete",
                reason="Todas as fases, validações e checkpoints obrigatórios foram satisfeitos.",
            ),
        )

    def _plan(
        self,
        context: CodexOrchestrationContextContract,
        *,
        state: OrchestrationPlanState,
        action: CodexOrchestrationActionContract,
    ) -> CodexOrchestrationPlanContract:
        return CodexOrchestrationPlanContract(
            policy_id=self.contract.id,
            policy_version=self.contract.version,
            state=state,
            status_state=context.status_state,
            action=action,
            status_blockers=context.status_blockers,
            unresolved_questions=context.unresolved_questions,
            pending_validations=context.pending_validations,
            failed_validations=context.failed_validations,
            pending_approvals=context.pending_approvals,
            resume_workflow_id=context.resume_workflow_id,
        )

    def _next_phase(
        self,
        completed_phases: tuple[str, ...],
    ) -> CodexOrchestrationPhaseContract | None:
        completed = set(completed_phases)
        return next((phase for phase in self.contract.phases if phase.id not in completed), None)

    def _validate_context_references(self, context: CodexOrchestrationContextContract) -> None:
        phase_ids = {phase.id for phase in self.contract.phases}
        known_validation_ids = {validation.id for validation in self.contract.validations}
        unknown_phases = set(context.completed_phases) - phase_ids
        if context.resume_phase_id is not None and context.resume_phase_id not in phase_ids:
            unknown_phases.add(context.resume_phase_id)
        if unknown_phases:
            raise CodexOrchestrationError(
                "orchestration context references unknown phase(s): "
                + ", ".join(sorted(unknown_phases))
            )
        unknown_validations = (
            set(context.pending_validations) | set(context.failed_validations)
        ) - known_validation_ids
        if unknown_validations:
            raise CodexOrchestrationError(
                "orchestration context references unknown validation(s): "
                + ", ".join(sorted(unknown_validations))
            )


def load_codex_orchestration_policy() -> CodexOrchestrationPolicy:
    """Load the packaged policy and derive its canonical semantic hash."""
    path = _POLICY_DIRECTORY / CODEX_ORCHESTRATION_POLICY_FILENAME
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise CodexOrchestrationDefinitionError(
            "packaged orchestration policy is missing"
        ) from error
    if len(payload) > CODEX_ORCHESTRATION_POLICY_MAX_BYTES:
        raise CodexOrchestrationDefinitionError(
            "packaged orchestration policy exceeds the size limit"
        )
    try:
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        policy = CodexOrchestrationPolicyContract.model_validate(raw)
    except (UnicodeDecodeError, TypeError, ValueError, ValidationError) as error:
        raise CodexOrchestrationDefinitionError(
            "packaged orchestration policy is invalid"
        ) from error
    canonical_payload = _canonical_json_bytes(policy.model_dump(mode="json"))
    return CodexOrchestrationPolicy(
        contract=policy,
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
    "CODEX_ORCHESTRATION_POLICY_FILENAME",
    "CodexOrchestrationDefinitionError",
    "CodexOrchestrationError",
    "CodexOrchestrationPolicy",
    "load_codex_orchestration_policy",
]
