"""Offline conformance evaluations for the versioned Codex specialist agents."""

from __future__ import annotations

import json
import struct
import threading
import zlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from integrations.codex import (
    CodexAgentRouter,
    ImageGenExecutor,
    ImageGenRequest,
    load_codex_agent_catalog,
    load_codex_orchestration_policy,
)

from ludowright.application import (
    PromptCompiler,
    VisualReviewService,
    VisualReviewValidationError,
)
from ludowright.contracts import (
    CodexAgentRoutingContextContract,
    CodexOrchestrationPlanContract,
    CompiledPromptContract,
    VisualBibleContract,
    VisualReferenceContract,
)
from ludowright.domain import (
    ApprovalId,
    AssetId,
    DisplayName,
    InvalidPromptCompilationError,
    JobId,
    ProfileVersion,
    ReferenceId,
    ReferenceOrigin,
    ReferenceProvenance,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    SourceUri,
    SubjectRevision,
    VisualJob,
    VisualReference,
)
from ludowright.infrastructure import (
    GenerationReceiptRepository,
    ProjectFilesystem,
    RepositoryPath,
)

EVAL_FIXTURE = Path("tests/fixtures/codex-agent-evals.json")
PROMPT_FIXTURE = Path("tests/fixtures/contracts/v1/compiled-prompt.json")
VISUAL_BIBLE_FIXTURE = Path("tests/fixtures/contracts/v1/visual-bible.json")


def _eval_data() -> dict[str, object]:
    return cast(dict[str, object], json.loads(EVAL_FIXTURE.read_text(encoding="utf-8")))


def _route_cases() -> list[dict[str, object]]:
    return cast(list[dict[str, object]], _eval_data()["route_cases"])


def _plan(
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
                "reason": "Agent evaluation action.",
            },
        }
    )


def _route_context(
    task_id: str,
    plan: CodexOrchestrationPlanContract,
    *,
    required_capabilities: tuple[str, ...] = (),
) -> CodexAgentRoutingContextContract:
    return CodexAgentRoutingContextContract(
        task_id=task_id,
        plan=plan,
        required_capabilities=required_capabilities,
    )


def _visual_bible():
    payload = json.loads(VISUAL_BIBLE_FIXTURE.read_text(encoding="utf-8"))
    return VisualBibleContract.model_validate(payload).to_domain()


def _compiled_prompt():
    payload = json.loads(PROMPT_FIXTURE.read_text(encoding="utf-8"))
    return CompiledPromptContract.model_validate(payload).to_domain()


def _target(asset_id: str = "hero") -> ReferenceTarget:
    return ReferenceTarget(asset_id=AssetId(asset_id))


def _external_reference(
    reference_id: str,
    target: ReferenceTarget,
    *,
    status: ReferenceStatus = ReferenceStatus.CANDIDATE,
) -> VisualReference:
    reference = VisualReference(
        id=ReferenceId(reference_id),
        name=DisplayName(f"Reference {reference_id}"),
        target=target,
        role=ReferenceRole.IDENTITY,
        provenance=ReferenceProvenance(
            origin=ReferenceOrigin.EXTERNAL,
            content_revision=SubjectRevision(f"sha256:{reference_id}"),
            source_uri=SourceUri("https://example.test/reference"),
        ),
    )
    if status is ReferenceStatus.APPROVED:
        return reference.approve(ApprovalId(f"approval-{reference_id}"))
    return replace(reference, status=status)


def _job(
    *,
    job_id: str = "job-hero-front-v1",
    request_revision: str = "sha256:job-request",
    roles: tuple[ReferenceRole, ...] = (ReferenceRole.IDENTITY,),
    supersedes: JobId | None = None,
) -> VisualJob:
    return VisualJob(
        id=JobId(job_id),
        name=DisplayName("Hero visual job"),
        target=_target(),
        profile_version=ProfileVersion(1),
        request_revision=SubjectRevision(request_revision),
        input_reference_ids=(),
        output_roles=roles,
        expected_output_count=len(roles),
        supersedes=supersedes,
    )


def _filesystem(root: Path) -> ProjectFilesystem:
    root.mkdir()
    marker = root / ".ludowright"
    marker.mkdir()
    (marker / "project.json").write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(root)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _png_payload() -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    chunks = (
        _png_chunk(b"IHDR", header),
        _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00")),
        _png_chunk(b"IEND", b""),
    )
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


class _EvaluationProvider:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self._lock = threading.Lock()

    def generate(self, request: ImageGenRequest) -> bytes:
        with self._lock:
            self.calls.append(request.output.index)
        return _png_payload()


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def test_eval_fixture_covers_the_published_catalog() -> None:
    data = _eval_data()
    catalog = load_codex_agent_catalog()
    cases = _route_cases()
    rules = {rule.task_id: rule for rule in catalog.contract.routes}

    assert data["schema_version"] == 1
    assert data["kind"] == "codex-agent-eval-cases"
    assert data["catalog_id"] == catalog.id
    assert data["catalog_version"] == catalog.version
    assert {case["task_id"] for case in cases} == set(rules)
    assert len(cases) == len(rules) == len(catalog.contract.agents)
    for case in cases:
        rule = rules[cast(str, case["task_id"])]
        assert case["agent_id"] == rule.agent_id
        assert cast(str, case["action"]) in rule.allowed_actions


@pytest.mark.parametrize("case", _route_cases(), ids=lambda case: str(case["task_id"]))
def test_route_eval_selects_only_the_declared_specialist(case: dict[str, object]) -> None:
    plan = _plan(cast(str, case["action"]))
    result = CodexAgentRouter(load_codex_agent_catalog()).route(
        _route_context(
            cast(str, case["task_id"]),
            plan,
            required_capabilities=tuple(cast(list[str], case["required_capabilities"])),
        )
    )

    assert result.state == "routed"
    assert result.agent_id == case["agent_id"]
    assert result.can_approve is False
    assert result.requires_human is True


def test_state_inspection_eval_blocks_routing_before_status() -> None:
    policy = load_codex_orchestration_policy()
    router = CodexAgentRouter(load_codex_agent_catalog())
    plan = policy.plan({})

    assert plan.action.action == "inspect-status"
    result = router.route(_route_context("interview", plan))

    assert result.state == "blocked"
    assert result.agent_id is None
    assert result.action == "inspect-status"


def test_decision_safety_eval_forbids_reinvention_and_agent_approval() -> None:
    data = _eval_data()
    boundaries = set(cast(list[str], data["forbidden_boundaries"]))
    catalog = load_codex_agent_catalog()

    assert boundaries == {
        "approve-reference",
        "invent-decision",
        "overwrite-approved-artifact",
    }
    for agent in catalog.contract.agents:
        assert agent.can_approve is False
        assert boundaries.issubset(agent.forbidden_actions)
        assert not boundaries.intersection(agent.allowed_actions)

    result = CodexAgentRouter(catalog).route(
        _route_context("game-design", _plan("record-decision"))
    )
    assert result.state == "routed"
    assert result.agent_id == "game-design-architect"


def test_approved_reference_eval_rejects_unapproved_and_wrong_target() -> None:
    compiler = PromptCompiler()
    target = _target()

    with pytest.raises(InvalidPromptCompilationError, match="not approved"):
        compiler.compile(
            _visual_bible(),
            target,
            references=(_external_reference("candidate", target),),
            reference_ids=(ReferenceId("candidate"),),
        )

    with pytest.raises(InvalidPromptCompilationError, match="does not match"):
        compiler.compile(
            _visual_bible(),
            target,
            references=(
                _external_reference(
                    "other",
                    _target("other"),
                    status=ReferenceStatus.APPROVED,
                ),
            ),
            reference_ids=(ReferenceId("other"),),
        )

    approved = _external_reference("approved", target, status=ReferenceStatus.APPROVED)
    compiled = compiler.compile(
        _visual_bible(),
        target,
        references=(approved,),
        reference_ids=(approved.id,),
    )
    assert tuple(reference.id for reference in compiled.references) == (approved.id,)


def test_prompt_receipt_eval_binds_generation_to_the_compiled_prompt(tmp_path: Path) -> None:
    catalog = load_codex_agent_catalog()
    route = CodexAgentRouter(catalog).route(
        _route_context(
            "generation",
            _plan("execute-phase"),
            required_capabilities=("generation-execution",),
        )
    )
    assert route.agent_id == "generation-operator"

    filesystem = _filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        _job(),
        _compiled_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    provider = _EvaluationProvider()
    result = ImageGenExecutor().execute(
        filesystem,
        operation,
        provider,
        clock=_fixed_clock,
    )

    assert provider.calls == [1]
    assert result.receipt is not None
    assert result.receipt.status.value == "succeeded"
    assert result.receipt.prompt_hash == operation.contract.prompt_hash
    assert len(result.receipt.output_reference_ids) == 1
    reference_path = (
        filesystem.root
        / ".ludowright"
        / "visual-references"
        / f"{result.receipt.output_reference_ids[0]}.json"
    )
    reference = VisualReferenceContract.model_validate(
        json.loads(reference_path.read_text(encoding="utf-8"))
    )
    assert reference.status is ReferenceStatus.CANDIDATE
    assert reference.provenance.source_receipt_id == result.receipt.id
    assert GenerationReceiptRepository().list_for_job(filesystem, operation.contract.job_id) == (
        result.receipt,
    )


def test_selective_regeneration_eval_uses_a_new_job_without_overwriting_prior_output(
    tmp_path: Path,
) -> None:
    filesystem = _filesystem(tmp_path / "project")
    executor = ImageGenExecutor()
    provider = _EvaluationProvider()
    first_operation = executor.prepare(
        _job(),
        _compiled_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    first = executor.execute(filesystem, first_operation, provider, clock=_fixed_clock)
    old_output = filesystem.read_bytes(first_operation.output_paths[0])

    replacement_job = _job(
        job_id="job-hero-front-v2",
        request_revision="sha256:job-request-correction",
        roles=(ReferenceRole.CONSTRUCTION,),
        supersedes=_job().id,
    )
    replacement_operation = executor.prepare(
        replacement_job,
        _compiled_prompt(),
        RepositoryPath("references/hero/job-hero-front-v2"),
    )
    second = executor.execute(filesystem, replacement_operation, provider, clock=_fixed_clock)

    assert replacement_job.supersedes.value == first_operation.contract.job_id
    assert first is not second
    assert second.receipt is not None
    assert second.receipt.job_id == replacement_operation.contract.job_id
    assert provider.calls == [1, 1]
    assert filesystem.read_bytes(first_operation.output_paths[0]) == old_output
    assert filesystem.resolve(replacement_operation.output_paths[0], must_exist=True).is_file()
    assert (
        len(GenerationReceiptRepository().list_for_job(filesystem, first_operation.contract.job_id))
        == 1
    )
    assert (
        len(
            GenerationReceiptRepository().list_for_job(
                filesystem, replacement_operation.contract.job_id
            )
        )
        == 1
    )


def test_approval_and_safety_eval_requires_a_human_and_projects_approval(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    operation = ImageGenExecutor().prepare(
        _job(),
        _compiled_prompt(),
        RepositoryPath("references/hero/job-hero-front-v1"),
    )
    generated = ImageGenExecutor().execute(
        filesystem,
        operation,
        _EvaluationProvider(),
        clock=_fixed_clock,
    )
    assert generated.receipt is not None
    reference_id = generated.receipt.output_reference_ids[0]

    review_path = filesystem.root / "accept.json"
    review_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "visual-review",
                "id": "review-agent-eval-accepted",
                "receipt_id": generated.receipt.id,
                "outcome": "accepted",
                "reviewed_reference_ids": [reference_id],
                "approval_id": "approval-agent-eval",
                "reviewer": {"id": "human-reviewer", "kind": "human"},
                "producer": {"id": "generation-operator", "kind": "agent"},
            }
        ),
        encoding="utf-8",
    )
    result = VisualReviewService(filesystem).apply(RepositoryPath("accept.json"))
    assert result.state == "applied"

    reference = VisualReferenceContract.model_validate(
        json.loads(
            (
                filesystem.root / ".ludowright" / "visual-references" / f"{reference_id}.json"
            ).read_text(encoding="utf-8")
        )
    )
    assert reference.status is ReferenceStatus.APPROVED
    approved_prompt = PromptCompiler().compile(
        _visual_bible(),
        _target(),
        references=(reference.to_domain(),),
        reference_ids=(ReferenceId(reference_id),),
    )
    assert approved_prompt.references[0].id == ReferenceId(reference_id)

    unsafe_path = filesystem.root / "unsafe-agent-review.json"
    unsafe_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "visual-review",
                "id": "review-agent-eval-unsafe",
                "receipt_id": generated.receipt.id,
                "outcome": "accepted",
                "reviewed_reference_ids": [reference_id],
                "approval_id": "approval-agent-eval-unsafe",
                "reviewer": {"id": "generation-operator", "kind": "agent"},
                "producer": {"id": "generation-operator", "kind": "agent"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(VisualReviewValidationError):
        VisualReviewService(filesystem).apply(RepositoryPath("unsafe-agent-review.json"))


def test_agent_eval_fixture_lists_all_required_roadmap_scenarios() -> None:
    assert set(cast(list[str], _eval_data()["scenario_ids"])) == {
        "status-before-routing",
        "no-decision-reinvention",
        "approved-reference-enforcement",
        "prompt-receipt-creation",
        "selective-regeneration",
        "approval-and-safety",
    }
