"""Tests for the canonical generated-output review workflow."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import (
    VisualReviewConflictError,
    VisualReviewService,
    VisualReviewValidationError,
)
from ludowright.cli.app import app
from ludowright.contracts import (
    GenerationReceiptContract,
    VisualReferenceContract,
)
from ludowright.contracts.visual import ReferenceProvenanceContract, ReferenceTargetContract
from ludowright.domain import ReferenceOrigin, ReferenceRole
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DEFAULT_EVENT_LOG_PATH,
    GENERATED_REFERENCE_DIRECTORY,
    GENERATION_RECEIPT_DIRECTORY,
    EventLog,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    StructuredDocumentConflictError,
)

runner = CliRunner()
RECEIPT_ID = "receipt-maya-front-1"
REFERENCE_ID = "ref-maya-front-output"
JOB_ID = "job-maya-front-v1"


def _filesystem(root: Path) -> ProjectFilesystem:
    root.mkdir()
    (root / ".ludowright").mkdir()
    (root / ".ludowright/project.json").write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(root)


def _seed_generation(filesystem: ProjectFilesystem) -> None:
    receipt = GenerationReceiptContract.model_validate(
        json.loads(Path("tests/fixtures/contracts/v1/generation-receipt.json").read_text())
    )
    reference = VisualReferenceContract(
        id=REFERENCE_ID,
        name="Maya Front Output",
        target=ReferenceTargetContract(asset_id="chr-maya"),
        role=ReferenceRole.OUTPUT,
        provenance=ReferenceProvenanceContract(
            origin=ReferenceOrigin.GENERATED,
            content_revision="sha256:output-revision",
            source_job_id=JOB_ID,
            source_receipt_id=RECEIPT_ID,
        ),
    )
    receipt_path = GENERATION_RECEIPT_DIRECTORY.child(JOB_ID).child(f"{RECEIPT_ID}.json")
    JsonDocumentRepository(
        filesystem,
        receipt_path,
        GenerationReceiptContract,
    ).create(receipt)
    JsonDocumentRepository(
        filesystem,
        GENERATED_REFERENCE_DIRECTORY.child(f"{REFERENCE_ID}.json"),
        VisualReferenceContract,
    ).create(reference)


def _seed_replacement_generation(filesystem: ProjectFilesystem) -> None:
    payload = json.loads(Path("tests/fixtures/contracts/v1/generation-receipt.json").read_text())
    payload["id"] = "receipt-maya-front-2"
    payload["job_id"] = "job-maya-front-v2"
    payload["operation_id"] = "imagegen-maya-front-v2"
    payload["output_reference_ids"] = ["ref-maya-front-output-2"]
    payload["outputs"][0]["reference_id"] = "ref-maya-front-output-2"
    receipt = GenerationReceiptContract.model_validate(payload)
    reference = VisualReferenceContract(
        id="ref-maya-front-output-2",
        name="Maya Front Output Replacement",
        target=ReferenceTargetContract(asset_id="chr-maya"),
        role=ReferenceRole.OUTPUT,
        provenance=ReferenceProvenanceContract(
            origin=ReferenceOrigin.GENERATED,
            content_revision="sha256:replacement-revision",
            source_job_id="job-maya-front-v2",
            source_receipt_id="receipt-maya-front-2",
        ),
    )
    JsonDocumentRepository(
        filesystem,
        GENERATION_RECEIPT_DIRECTORY.child("job-maya-front-v2").child("receipt-maya-front-2.json"),
        GenerationReceiptContract,
    ).create(receipt)
    JsonDocumentRepository(
        filesystem,
        GENERATED_REFERENCE_DIRECTORY.child("ref-maya-front-output-2.json"),
        VisualReferenceContract,
    ).create(reference)


def _review(path: Path, *, outcome: str = "accepted", note: str | None = None) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "visual-review",
        "id": "review-maya-front-1",
        "receipt_id": RECEIPT_ID,
        "outcome": outcome,
        "reviewed_reference_ids": [REFERENCE_ID],
        "reviewer": {"id": "human-reviewer", "kind": "human"},
        "producer": {"id": "imagegen-agent", "kind": "agent"},
    }
    if outcome == "accepted":
        payload["approval_id"] = "approval-maya-front-output"
    if note is not None:
        payload["note"] = note
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_accepted_review_projects_approval_and_event(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    input_path = filesystem.root / "review.json"
    _review(input_path, note="Approved for the front view.")

    result = VisualReviewService(
        filesystem,
        clock=lambda: datetime(2026, 8, 1, 12, 0, 0, 123456, tzinfo=UTC),
    ).apply(RepositoryPath("review.json"))

    assert result.state == "applied"
    assert result.event_sequence == 1
    persisted_reference = json.loads(
        (filesystem.root / ".ludowright/visual-references/ref-maya-front-output.json").read_text()
    )
    assert persisted_reference["status"] == "approved"
    assert persisted_reference["approval_id"] == "approval-maya-front-output"
    assert (filesystem.root / ".ludowright/approvals/approval-maya-front-output.json").is_file()
    assert (filesystem.root / ".ludowright/visual-reviews/review-maya-front-1.json").is_file()
    assert (filesystem.root / DEFAULT_DEPENDENCY_GRAPH_PATH.value).is_file()
    assert (filesystem.root / DEFAULT_EVENT_LOG_PATH.value).is_file()


def test_review_keeps_an_existing_state_checkpoint_consistent(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    StateStore(filesystem)
    _seed_generation(filesystem)
    _review(filesystem.root / "review.json")

    VisualReviewService(filesystem).apply(RepositoryPath("review.json"))

    assert (
        StateStore(filesystem, read_only=True)
        .check_consistency(EventLog(filesystem).replay())
        .is_consistent
    )


def test_review_dry_run_does_not_change_project(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    _review(filesystem.root / "review.json")
    before = sorted(
        path.relative_to(filesystem.root).as_posix()
        for path in filesystem.root.rglob("*")
        if path.is_file()
    )

    result = VisualReviewService(filesystem).apply(RepositoryPath("review.json"), dry_run=True)

    after = sorted(
        path.relative_to(filesystem.root).as_posix()
        for path in filesystem.root.rglob("*")
        if path.is_file()
    )
    assert result.state == "planned"
    assert result.dry_run is True
    assert before == after
    assert not (filesystem.root / DEFAULT_EVENT_LOG_PATH.value).exists()


def test_changes_requested_invalidates_graph_for_review(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    _review(filesystem.root / "review.json", outcome="changes-requested", note="Correct the hand.")

    result = VisualReviewService(filesystem).apply(RepositoryPath("review.json"))

    assert result.state == "applied"
    assert any(item["state"] == "review-required" for item in result.impacts)
    reference = json.loads(
        (filesystem.root / ".ludowright/visual-references/ref-maya-front-output.json").read_text()
    )
    assert reference["status"] == "candidate"


def test_rejected_review_rejects_reference_and_propagates_stale(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    _review(filesystem.root / "review.json", outcome="rejected", note="Wrong silhouette.")

    result = VisualReviewService(filesystem).apply(RepositoryPath("review.json"))

    assert any(item["state"] == "stale" for item in result.impacts)
    reference = json.loads(
        (filesystem.root / ".ludowright/visual-references/ref-maya-front-output.json").read_text()
    )
    assert reference["status"] == "rejected"


def test_accepted_review_supersedes_prior_approval_and_reference(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    _seed_replacement_generation(filesystem)
    first_path = filesystem.root / "review.json"
    _review(first_path)
    service = VisualReviewService(filesystem)
    service.apply(RepositoryPath("review.json"))

    replacement = json.loads(first_path.read_text())
    replacement.update(
        {
            "id": "review-maya-front-2",
            "receipt_id": "receipt-maya-front-2",
            "reviewed_reference_ids": ["ref-maya-front-output-2"],
            "approval_id": "approval-maya-front-output-2",
            "supersedes": "review-maya-front-1",
        }
    )
    first_path.write_text(json.dumps(replacement), encoding="utf-8")

    service.apply(RepositoryPath("review.json"))

    old_reference = json.loads(
        (filesystem.root / ".ludowright/visual-references/ref-maya-front-output.json").read_text()
    )
    new_reference = json.loads(
        (filesystem.root / ".ludowright/visual-references/ref-maya-front-output-2.json").read_text()
    )
    old_approval = json.loads(
        (filesystem.root / ".ludowright/approvals/approval-maya-front-output.json").read_text()
    )
    assert old_reference["status"] == "superseded"
    assert old_reference["superseded_by"] == "ref-maya-front-output-2"
    assert new_reference["status"] == "approved"
    assert old_approval["history"][-1]["status"] == "superseded"


def test_review_is_idempotent_but_different_content_is_a_conflict(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    input_path = filesystem.root / "review.json"
    _review(input_path)
    service = VisualReviewService(filesystem)
    service.apply(RepositoryPath("review.json"))

    unchanged = service.apply(RepositoryPath("review.json"))
    assert unchanged.state == "unchanged"

    payload = json.loads(input_path.read_text())
    payload["note"] = "A different immutable review record."
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VisualReviewConflictError, match="different content"):
        service.apply(RepositoryPath("review.json"))


def test_failure_after_canonical_writes_rolls_back_all_review_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    _review(filesystem.root / "review.json")

    def fail_append(*args: object, **kwargs: object) -> object:
        raise RuntimeError("event sink failed")

    monkeypatch.setattr("ludowright.application.visual_review.EventLog.append", fail_append)
    with pytest.raises(RuntimeError, match="event sink failed"):
        VisualReviewService(filesystem).apply(RepositoryPath("review.json"))

    assert not (filesystem.root / ".ludowright/visual-reviews").exists()
    assert not (filesystem.root / ".ludowright/approvals").exists()
    assert not (filesystem.root / DEFAULT_DEPENDENCY_GRAPH_PATH.value).exists()
    reference = json.loads(
        (filesystem.root / ".ludowright/visual-references/ref-maya-front-output.json").read_text()
    )
    assert reference["status"] == "candidate"


def test_concurrent_review_execution_has_one_canonical_writer(tmp_path: Path) -> None:
    root = tmp_path / "project"
    filesystem = _filesystem(root)
    _seed_generation(filesystem)
    _review(root / "review.json")

    def apply() -> str:
        try:
            return (
                VisualReviewService(ProjectFilesystem(root))
                .apply(RepositoryPath("review.json"))
                .state
            )
        except (StructuredDocumentConflictError, VisualReviewConflictError) as error:
            return type(error).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(pool.map(lambda _item: apply(), range(2)))

    assert sum(state == "applied" for state in states) == 1
    assert (
        sum(
            state in {"unchanged", "VisualReviewConflictError", "StructuredDocumentConflictError"}
            for state in states
        )
        == 1
    )


def test_agent_cannot_approve_and_self_review_is_rejected(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    input_path = filesystem.root / "review.json"
    _review(input_path)
    payload = json.loads(input_path.read_text())
    payload["reviewer"]["kind"] = "agent"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VisualReviewValidationError):
        VisualReviewService(filesystem).apply(RepositoryPath("review.json"))

    payload["reviewer"] = {"id": "imagegen-agent", "kind": "human"}
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VisualReviewValidationError):
        VisualReviewService(filesystem).apply(RepositoryPath("review.json"))


def test_cli_human_and_json_outputs_use_review_command(tmp_path: Path) -> None:
    filesystem = _filesystem(tmp_path / "project")
    _seed_generation(filesystem)
    _review(filesystem.root / "review.json")

    human = runner.invoke(app, ["review", "review.json", str(filesystem.root)])
    assert human.exit_code == 0
    assert "Visual review" in human.stdout

    second = runner.invoke(app, ["--json", "review", "review.json", str(filesystem.root)])
    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    assert payload["kind"] == "cli-response"
    assert payload["data"]["state"] == "unchanged"
