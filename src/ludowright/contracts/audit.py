"""Contracts for the read-only structural audit result."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ludowright.contracts.common import ContractModel


class AuditVersionContract(ContractModel):
    """One persisted component version observation."""

    component: str
    expected: int
    observed: int | None
    state: Literal["match", "missing", "mismatch", "unavailable"]


class AuditFindingContract(ContractModel):
    """One stable structural-audit finding and its safe next action."""

    code: str
    severity: Literal["error", "warning"]
    component: str
    path: str | None = None
    detail: str
    repair_code: str


class AuditComponentContract(ContractModel):
    """Inspection state for one canonical project component."""

    name: str
    path: str
    state: Literal["valid", "missing", "corrupt", "unsafe", "unavailable"]
    detail: str


class AuditProjectContract(ContractModel):
    """Optional project identity recovered from a valid manifest."""

    id: str
    name: str


class RepairGuidanceContract(ContractModel):
    """One deterministic, non-automatic repair recommendation."""

    code: str
    description: str
    command: str
    paths: tuple[str, ...] = Field(default_factory=tuple)


class StructuralAuditContract(ContractModel):
    """Stable command data for a structural audit."""

    project_directory: str
    project: AuditProjectContract | None
    state: Literal["clean", "issues-found"]
    read_only: Literal[True] = True
    schema_versions: tuple[AuditVersionContract, ...]
    components: tuple[AuditComponentContract, ...]
    findings: tuple[AuditFindingContract, ...]
    repair_guidance: tuple[RepairGuidanceContract, ...]
