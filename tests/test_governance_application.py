"""Integration tests for governance persistence, application workflows, and CLI surfaces."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ludowright.application import GovernanceService
from ludowright.cli.app import app
from ludowright.contracts import ProjectContract
from ludowright.domain import (
    ApprovalStatus,
    DecisionId,
    DecisionStatus,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    PlatformFamily,
    ProjectDimension,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DECISIONS_DIRECTORY,
    DEFAULT_EVENT_LOG_PATH,
    LOCK_DIRECTORY,
    DecisionRepository,
    DependencyGraphRepository,
    EventLog,
    GovernanceRecordNotFoundError,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    StructuredDocumentConflictError,
    UnsafeProjectPathError,
)

runner = CliRunner()


def project_root(tmp_path: Path) -> Path:
    filesystem = ProjectFilesystem(tmp_path)
    filesystem.ensure_directory(LOCK_DIRECTORY, mode=0o700)
    filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, b"")
    graph = DependencyGraph.empty().add_node(
        DependencyNode(
            key=DependencyKey(DependencyNodeKind.PROJECT, "test-game"),
            revision=RevisionVersion(1),
        )
    )
    DependencyGraphRepository(filesystem).create(graph)
    StateStore(filesystem).record_event_checkpoint(EventLog(filesystem).replay())
    JsonDocumentRepository(
        filesystem,
        RepositoryPath(".ludowright/project.json"),
        ProjectContract,
    ).create(
        ProjectContract(
            id="test-game",
            name="Test Game",
            dimensions=ProjectDimension.TWO_D,
            targets=({"platform": PlatformFamily.WINDOWS},),
        )
    )
    return tmp_path


def test_decision_repository_round_trip_and_conflict(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    filesystem = ProjectFilesystem(root)
    service = GovernanceService()

    service.record_decision(root, decision_id="z-last", title="Last")
    service.record_decision(root, decision_id="a-first", title="First")

    repository = DecisionRepository(filesystem)
    listed = repository.list()
    assert [item.decision.id.value for item in listed] == ["a-first", "z-last"]
    with pytest.raises(GovernanceRecordNotFoundError):
        repository.load(DecisionId("missing"))
    assert DECISIONS_DIRECTORY.value == "decisions"


def test_record_refuses_to_overwrite_existing_decision(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()
    service.record_decision(root, decision_id="protected", title="Original")

    with pytest.raises(StructuredDocumentConflictError):
        service.record_decision(root, decision_id="protected", title="Replacement")

    inspected = service.inspect_decision(root, decision_id="protected")["decision"]
    assert isinstance(inspected, dict)
    assert inspected["title"] == "Original"


def test_decision_lifecycle_updates_graph_and_event_log(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()

    created = service.record_decision(
        root,
        decision_id="camera-choice",
        title="Use an isometric camera",
        note="Initial direction.",
    )
    assert created["status"] == "proposed"
    assert created["event_sequence"] == 1

    accepted = service.transition_decision(
        root,
        decision_id="camera-choice",
        status=DecisionStatus.ACCEPTED,
        note="Approved after review.",
    )
    assert accepted["status"] == "accepted"
    assert accepted["history_length"] == 2
    assert accepted["event_sequence"] == 2

    repeated = service.transition_decision(
        root,
        decision_id="camera-choice",
        status=DecisionStatus.ACCEPTED,
    )
    assert repeated["event_sequence"] is None
    assert EventLog(ProjectFilesystem(root)).replay().last_sequence == 2
    assert StateStore(ProjectFilesystem(root)).get_event_checkpoint().last_sequence == 2

    inspected = service.inspect_decision(root, decision_id="camera-choice")
    decision = inspected["decision"]
    assert isinstance(decision, dict)
    assert [entry["status"] for entry in decision["history"]] == ["proposed", "accepted"]

    graph = DependencyGraphRepository(ProjectFilesystem(root)).load().graph
    node = graph.get_node(DependencyKey(DependencyNodeKind.DECISION, "camera-choice"))
    assert node.revision.value == 2


def test_decision_supersede_requires_existing_replacement(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()
    service.record_decision(root, decision_id="old-choice", title="Old choice")
    service.transition_decision(
        root,
        decision_id="old-choice",
        status=DecisionStatus.ACCEPTED,
    )
    service.record_decision(root, decision_id="new-choice", title="New choice")

    result = service.supersede_decision(
        root,
        decision_id="old-choice",
        replacement_id="new-choice",
    )
    assert result["status"] == "superseded"
    history = service.inspect_decision(root, decision_id="old-choice")["decision"]
    assert isinstance(history, dict)
    assert history["history"][-1]["superseded_by"] == "new-choice"

    with pytest.raises(GovernanceRecordNotFoundError):
        service.supersede_decision(root, decision_id="old-choice", replacement_id="missing")


def test_invalid_decision_transition_does_not_change_file(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()
    service.record_decision(root, decision_id="stable-choice", title="Stable")

    with pytest.raises(ValueError):
        service.transition_decision(
            root,
            decision_id="stable-choice",
            status=DecisionStatus.SUPERSEDED,
        )

    result = service.inspect_decision(root, decision_id="stable-choice")
    decision = result["decision"]
    assert isinstance(decision, dict)
    assert len(decision["history"]) == 1
    assert EventLog(ProjectFilesystem(root)).replay().last_sequence == 1


def test_approval_lifecycle_binds_subject_revision_and_audits(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()

    requested = service.request_approval(
        root,
        approval_id="front-review",
        subject_kind="reference",
        subject_id="maya-front",
        revision="sha256:abc123",
        label="Maya front",
    )
    assert requested["status"] == "pending"
    approved = service.transition_approval(
        root,
        approval_id="front-review",
        status=ApprovalStatus.APPROVED,
        note="Approved.",
    )
    assert approved["status"] == "approved"
    revoked = service.transition_approval(
        root,
        approval_id="front-review",
        status=ApprovalStatus.REVOKED,
    )
    assert revoked["status"] == "revoked"

    inspected = service.inspect_approval(root, approval_id="front-review")["approval"]
    assert isinstance(inspected, dict)
    assert inspected["subject"]["revision"] == "sha256:abc123"
    events = EventLog(ProjectFilesystem(root)).replay().events
    assert events[-1].payload["subject_revision"] == "sha256:abc123"
    assert len(events) == 3
    listed = service.list_approvals(root)["approvals"]
    assert isinstance(listed, list)
    assert listed[0]["subject"]["kind"] == "reference"


def test_approval_supersede_and_invalid_subject_are_rejected(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()
    service.request_approval(
        root,
        approval_id="old-review",
        subject_kind="reference",
        subject_id="maya-front",
        revision="v1",
    )
    service.transition_approval(
        root,
        approval_id="old-review",
        status=ApprovalStatus.APPROVED,
    )
    service.request_approval(
        root,
        approval_id="new-review",
        subject_kind="reference",
        subject_id="maya-front",
        revision="v2",
    )

    result = service.supersede_approval(
        root,
        approval_id="old-review",
        replacement_id="new-review",
    )
    assert result["status"] == "superseded"

    with pytest.raises(ValueError):
        service.request_approval(
            root,
            approval_id="invalid-review",
            subject_kind="reference",
            subject_id="maya-front",
            revision="bad revision",
        )


def test_failed_event_append_rolls_back_document_and_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()

    import ludowright.application.governance as governance_module

    def fail_event(*args: object, **kwargs: object) -> int:
        raise RuntimeError("simulated event-log failure")

    monkeypatch.setattr(governance_module, "_append_event", fail_event)
    with pytest.raises(RuntimeError, match="rolled back"):
        service.record_decision(root, decision_id="rolled-back", title="Rollback")

    assert not (root / "decisions/rolled-back.json").exists()
    graph = DependencyGraphRepository(ProjectFilesystem(root)).load().graph
    with pytest.raises(KeyError):
        graph.get_node(DependencyKey(DependencyNodeKind.DECISION, "rolled-back"))
    assert EventLog(ProjectFilesystem(root)).replay().last_sequence == 0


def test_concurrent_records_are_serialized_by_governance_lock(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    service = GovernanceService()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda index: service.record_decision(
                    root,
                    decision_id=f"concurrent-{index}",
                    title=f"Decision {index}",
                ),
                range(4),
            )
        )

    assert sorted(item["id"] for item in results) == [
        "concurrent-0",
        "concurrent-1",
        "concurrent-2",
        "concurrent-3",
    ]
    assert EventLog(ProjectFilesystem(root)).replay().last_sequence == 4


def test_governance_directory_symlink_is_rejected(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    (root / "decisions").mkdir()
    (root / "decisions/evil.json").symlink_to(root / ".ludowright/project.json")

    with pytest.raises(UnsafeProjectPathError):
        DecisionRepository(ProjectFilesystem(root)).list()


def test_cli_human_and_json_surfaces_use_shared_envelope(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    human = runner.invoke(
        app,
        [
            "decision",
            "record",
            str(root),
            "--id",
            "cli-choice",
            "--title",
            "CLI choice",
        ],
    )
    assert human.exit_code == 0
    assert "Decision updated" in human.stdout

    machine = runner.invoke(app, ["--json", "decision", "list", str(root)])
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload["kind"] == "cli-response"
    assert payload["command"] == "decision list"
    assert payload["ok"] is True
    assert payload["data"]["decisions"][0]["id"] == "cli-choice"


def test_cli_missing_record_uses_json_error_envelope(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    result = runner.invoke(app, ["--json", "decision", "inspect", str(root), "missing"])

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid-input"


def test_cli_rejects_symlinked_governance_directory(tmp_path: Path) -> None:
    root = project_root(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (root / "decisions").symlink_to(external, target_is_directory=True)

    result = runner.invoke(
        app,
        [
            "--json",
            "decision",
            "record",
            str(root),
            "--id",
            "unsafe",
            "--title",
            "Unsafe",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid-input"
