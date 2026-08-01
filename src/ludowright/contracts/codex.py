"""Contracts for the project-local Codex skill package."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    RepositoryPathText,
    ReviewText,
    Sha256Text,
    Slug,
)

SkillFilename = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
SkillInvocation = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=81,
        pattern=r"^\$[a-z][a-z0-9-]{0,79}$",
    ),
]
LudoWrightVersionText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^\d+(?:\.\d+){1,3}(?:[.-](?:dev|a|b|rc)\d+)?$",
    ),
]
SkillOperation = Literal["install", "update", "verify", "remove"]
SkillState = Literal[
    "planned",
    "installed",
    "already-installed",
    "updated",
    "already-up-to-date",
    "verified",
    "removed",
    "not-installed",
    "outdated",
    "modified",
    "invalid",
    "unsupported",
    "incompatible",
    "conflict",
]
OrchestrationStatus = Literal["unknown", "ready", "needs-review", "blocked"]
OrchestrationPlanState = Literal[
    "continue",
    "awaiting-input",
    "review-required",
    "blocked",
    "approval-required",
    "complete",
]
OrchestrationActionType = Literal[
    "inspect-status",
    "report-blockers",
    "review-status",
    "ask-question",
    "record-decision",
    "run-validations",
    "resolve-validation",
    "await-approval",
    "resume-workflow",
    "execute-phase",
    "complete",
]


class CodexOrchestrationPhaseContract(ContractModel):
    """One ordered phase in the declarative Codex orchestration policy."""

    id: Slug
    order: PositiveRevision
    name: DisplayText
    purpose: ReviewText
    checkpoint_id: Slug | None = None


class CodexOrchestrationValidationContract(ContractModel):
    """One validation command the policy may require before continuing."""

    id: Slug
    command: DisplayText
    blocking: bool = True


class CodexOrchestrationCheckpointContract(ContractModel):
    """One evidence checkpoint that protects a durable workflow boundary."""

    id: Slug
    trigger: DisplayText
    requires_human: bool
    evidence: Annotated[tuple[Slug, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def validate_evidence_order(self) -> Self:
        _validate_sorted_unique(self.evidence, label="orchestration checkpoint evidence")
        return self


class CodexOrchestrationPolicyContract(ContractModel):
    """Versioned declarative rules for one Codex orchestration adapter."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-orchestration-policy"] = "codex-orchestration-policy"
    id: Slug
    version: PositiveRevision
    skill_id: Slug
    phases: Annotated[tuple[CodexOrchestrationPhaseContract, ...], Field(min_length=1)]
    validations: Annotated[
        tuple[CodexOrchestrationValidationContract, ...], Field(min_length=1, max_length=32)
    ]
    checkpoints: Annotated[
        tuple[CodexOrchestrationCheckpointContract, ...], Field(min_length=1, max_length=16)
    ]
    ask_only_unresolved: Literal[True] = True
    record_decisions: Literal[True] = True
    require_approval_checkpoints: Literal[True] = True
    resume_from_durable_state: Literal[True] = True

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        phase_ids = tuple(phase.id for phase in self.phases)
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("orchestration phases must be unique")
        orders = tuple(phase.order for phase in self.phases)
        if orders != tuple(range(1, len(orders) + 1)):
            raise ValueError("orchestration phase orders must be contiguous and ordered")

        validation_ids = tuple(validation.id for validation in self.validations)
        _validate_sorted_unique(validation_ids, label="orchestration validations")
        checkpoint_ids = tuple(checkpoint.id for checkpoint in self.checkpoints)
        _validate_sorted_unique(checkpoint_ids, label="orchestration checkpoints")
        known_checkpoints = set(checkpoint_ids)
        if any(
            phase.checkpoint_id is not None and phase.checkpoint_id not in known_checkpoints
            for phase in self.phases
        ):
            raise ValueError("orchestration phases must reference known checkpoints")
        return self


class CodexOrchestrationContextContract(ContractModel):
    """Validated read-only observation consumed by the policy planner."""

    status_inspected: bool = False
    status_state: OrchestrationStatus = "unknown"
    status_blockers: tuple[ReviewText, ...] = ()
    unresolved_questions: tuple[Slug, ...] = ()
    decisions_to_record: tuple[Slug, ...] = ()
    pending_validations: tuple[Slug, ...] = ()
    failed_validations: tuple[Slug, ...] = ()
    pending_approvals: tuple[Slug, ...] = ()
    resume_workflow_id: Slug | None = None
    resume_phase_id: Slug | None = None
    completed_phases: tuple[Slug, ...] = ()

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.status_inspected and self.status_state == "unknown":
            raise ValueError("an inspected orchestration context requires a known status")
        if not self.status_inspected and self.status_state != "unknown":
            raise ValueError("an uninspected orchestration context must use unknown status")
        if (self.resume_workflow_id is None) != (self.resume_phase_id is None):
            raise ValueError("a resumable workflow requires both workflow and phase IDs")
        _validate_sorted_unique(self.status_blockers, label="orchestration status blockers")
        _validate_sorted_unique(self.unresolved_questions, label="orchestration questions")
        _validate_sorted_unique(self.decisions_to_record, label="orchestration decisions")
        _validate_sorted_unique(self.pending_validations, label="orchestration pending validations")
        _validate_sorted_unique(self.failed_validations, label="orchestration failed validations")
        _validate_sorted_unique(self.pending_approvals, label="orchestration approvals")
        _validate_sorted_unique(self.completed_phases, label="orchestration completed phases")
        return self


class CodexOrchestrationActionContract(ContractModel):
    """One deterministic action selected by the orchestration policy."""

    action: OrchestrationActionType
    phase_id: Slug | None = None
    subject_id: Slug | None = None
    requires_human: bool = False
    reason: ReviewText


class CodexOrchestrationPlanContract(ContractModel):
    """Stable result of evaluating one orchestration observation."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-orchestration-plan"] = "codex-orchestration-plan"
    policy_id: Slug
    policy_version: PositiveRevision
    state: OrchestrationPlanState
    status_state: OrchestrationStatus
    action: CodexOrchestrationActionContract
    status_blockers: tuple[ReviewText, ...] = ()
    unresolved_questions: tuple[Slug, ...] = ()
    pending_validations: tuple[Slug, ...] = ()
    failed_validations: tuple[Slug, ...] = ()
    pending_approvals: tuple[Slug, ...] = ()
    resume_workflow_id: Slug | None = None

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        _validate_sorted_unique(self.status_blockers, label="orchestration plan blockers")
        _validate_sorted_unique(self.unresolved_questions, label="orchestration plan questions")
        _validate_sorted_unique(
            self.pending_validations,
            label="orchestration plan pending validations",
        )
        _validate_sorted_unique(
            self.failed_validations,
            label="orchestration plan failed validations",
        )
        _validate_sorted_unique(self.pending_approvals, label="orchestration plan approvals")
        return self


def _validate_sorted_unique(values: tuple[str, ...], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    if tuple(sorted(values)) != values:
        raise ValueError(f"{label} must be sorted")


class CodexSkillFileContract(ContractModel):
    """One case-sensitive file shipped by a Codex skill."""

    path: SkillFilename
    sha256: Sha256Text


class CodexSkillManifestContract(ContractModel):
    """Versioned metadata for one installable project-local Codex skill."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-skill-manifest"] = "codex-skill-manifest"
    id: Slug
    invocation: SkillInvocation
    version: PositiveRevision
    description: DisplayText
    install_path: RepositoryPathText
    entrypoint: SkillFilename
    minimum_ludowright_version: LudoWrightVersionText
    files: Annotated[tuple[CodexSkillFileContract, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        file_paths = tuple(item.path for item in self.files)
        if len(file_paths) != len(set(file_paths)):
            raise ValueError("Codex skill files must be unique")
        if self.entrypoint not in file_paths:
            raise ValueError("Codex skill entrypoint must be declared in files")
        if self.entrypoint == "manifest.json":
            raise ValueError("Codex skill entrypoint cannot be the installer manifest")
        if "manifest.json" in file_paths:
            raise ValueError("manifest.json is reserved for the installer manifest")
        if self.invocation != f"${self.id}":
            raise ValueError("Codex skill invocation must match its ID")
        return self


class CodexSkillReportContract(ContractModel):
    """Stable report returned by Codex skill lifecycle commands."""

    schema_version: Literal[1] = 1
    kind: Literal["codex-skill-report"] = "codex-skill-report"
    operation: SkillOperation
    state: SkillState
    dry_run: bool
    skill_id: Slug
    skill_version: PositiveRevision
    installed_version: PositiveRevision | None = None
    install_path: RepositoryPathText
    framework_version: LudoWrightVersionText
    files: Annotated[tuple[CodexSkillFileContract, ...], Field(min_length=1, max_length=33)]
    warnings: tuple[ReviewText, ...] = ()
    valid: bool

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("Codex skill report files must be unique")
        if tuple(sorted(paths)) != paths:
            raise ValueError("Codex skill report files must be sorted")
        if tuple(sorted(self.warnings)) != self.warnings:
            raise ValueError("Codex skill report warnings must be sorted")
        return self
