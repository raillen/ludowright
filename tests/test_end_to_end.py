"""End-to-end validation of the local-first project production path."""

from __future__ import annotations

import base64
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from integrations.codex import (
    ImageGenExecutor,
    ImageGenProviderMetadata,
    ImageGenRequest,
)
from typer.testing import CliRunner

from ludowright.application import PromptCompiler
from ludowright.cli.app import app
from ludowright.contracts import (
    CompiledPromptContract,
    TechnicalSheetRequestContract,
    VisualBibleContract,
    VisualJobContract,
    VisualReviewContract,
)
from ludowright.contracts.governance import ReviewActorContract
from ludowright.domain import VisualReviewOutcome
from ludowright.infrastructure import (
    EventLog,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
)

EXAMPLE_ROOT = Path("examples/minimal/project")
FIXTURE_PATH = EXAMPLE_ROOT / "fixtures/lantern-front.png.b64"
runner = CliRunner()


class FixtureImageProvider:
    """Return the versioned one-pixel fixture at the provider boundary."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def generate(self, request: ImageGenRequest) -> bytes:
        del request
        self.calls += 1
        return self.payload


def _json_command(*arguments: str) -> dict[str, object]:
    result = runner.invoke(app, ["--json", *arguments])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["kind"] == "cli-response"
    assert payload["ok"] is True
    data = payload["data"]
    assert isinstance(data, dict)
    return data


def _copy_example_inputs(project: Path) -> None:
    for relative in (
        "docs/game-brief.md",
        "imports/lantern.json",
        "imports/lantern-job.json",
        "requests/lantern-sheet.json",
    ):
        source = EXAMPLE_ROOT / relative
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _prepare_generation_and_review(project: Path, payload: bytes) -> str:
    filesystem = ProjectFilesystem(project)
    job = VisualJobContract.model_validate(
        json.loads((project / "imports/lantern-job.json").read_text(encoding="utf-8"))
    ).to_domain()
    visual_bible = VisualBibleContract.model_validate(
        json.loads(Path("tests/fixtures/contracts/v1/visual-bible.json").read_text())
    ).to_domain()
    prompt = PromptCompiler().compile(visual_bible, job.target)
    assert CompiledPromptContract.from_domain(prompt).prompt_hash == prompt.prompt_hash

    operation = ImageGenExecutor().prepare(
        job,
        prompt,
        RepositoryPath("references/prop-lantern/job-lantern-front-v1"),
    )
    timestamps = iter(
        (
            datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 8, 1, 12, 0, 1, tzinfo=UTC),
        )
    )
    provider = FixtureImageProvider(payload)
    execution = ImageGenExecutor().execute(
        filesystem,
        operation,
        provider,
        metadata=ImageGenProviderMetadata(
            provider="fixture",
            model="lantern-png",
            tool="e2e-test",
        ),
        clock=lambda: next(timestamps),
    )
    assert execution.receipt is not None
    assert execution.receipt.status.value == "succeeded"
    assert provider.calls == 1
    reference_id = execution.receipt.output_reference_ids[0]

    review = VisualReviewContract(
        id="review-lantern-front-v1",
        receipt_id=execution.receipt.id,
        outcome=VisualReviewOutcome.ACCEPTED,
        reviewed_reference_ids=(reference_id,),
        approval_id="approval-lantern-front-v1",
        reviewer=ReviewActorContract(id="human-reviewer", kind="human"),
        producer=ReviewActorContract(id="fixture-provider", kind="agent"),
    )
    JsonDocumentRepository(
        filesystem,
        RepositoryPath("reviews/lantern-front.json"),
        VisualReviewContract,
    ).create(review)
    return reference_id


def _point_request_at_reference(project: Path, reference_id: str) -> None:
    filesystem = ProjectFilesystem(project)
    path = RepositoryPath("requests/lantern-sheet.json")
    repository = JsonDocumentRepository(filesystem, path, TechnicalSheetRequestContract)
    snapshot = repository.load()
    input_item = snapshot.value.inputs[0].model_copy(update={"reference_id": reference_id})
    repository.replace(snapshot, snapshot.value.model_copy(update={"inputs": (input_item,)}))


@pytest.mark.end_to_end
def test_minimal_project_completes_the_local_first_production_path(tmp_path: Path) -> None:
    project = tmp_path / "lantern-path"
    payload = base64.b64decode(
        FIXTURE_PATH.read_text(encoding="ascii").strip(),
        validate=True,
    )

    initialized = _json_command(
        "init",
        str(project),
        "--name",
        "Lantern Path",
        "--template",
        "minimal",
        "--non-interactive",
    )
    assert initialized["state"] == "created"
    assert initialized["project_id"] == "lantern-path"
    _copy_example_inputs(project)
    (project / "normalized").mkdir()
    (project / "normalized/lantern-front.png").write_bytes(payload)

    asset = _json_command("assets", "create", str(project), "--input", "imports/lantern.json")
    assert asset["state"] == "created"
    workbook = _json_command("assets", "export-ods", str(project), "exports/assets.ods")
    assert workbook["state"] == "exported"
    asset_audit = _json_command("assets", "audit", str(project), "--check")
    assert asset_audit["valid"] is True

    reference_id = _prepare_generation_and_review(project, payload)
    _point_request_at_reference(project, reference_id)
    review = _json_command("review", "reviews/lantern-front.json", str(project))
    assert review["state"] == "applied"
    assert review["approval_id"] == "approval-lantern-front-v1"

    sheet = _json_command(
        "sheets",
        "assemble",
        "requests/lantern-sheet.json",
        "sheets/lantern",
        str(project),
    )
    assert sheet["state"] == "applied"
    manifest = _json_command(
        "package",
        "manifest",
        str(project),
        "release/package-manifest.json",
        "--package-id",
        "lantern-path",
    )
    assert manifest["state"] == "created"
    package = _json_command(
        "package",
        "build",
        str(project),
        "release/package-manifest.json",
        "release",
    )
    assert package["state"] == "created"

    audit = _json_command("audit", str(project))
    assert audit["state"] != "blocked"
    findings = audit["findings"]
    assert isinstance(findings, list)
    assert not any(finding["severity"] == "error" for finding in findings)
    release = _json_command(
        "release",
        "verify",
        str(project),
        "release",
        "--package-id",
        "lantern-path",
        "--allow-warnings",
        "--check",
    )
    assert release["state"] == "ready-with-warnings"
    assert release["valid"] is True

    filesystem = ProjectFilesystem(project)
    event_log = EventLog(filesystem).replay()
    assert event_log.last_sequence >= 2
    assert StateStore(filesystem, read_only=True).check_consistency(event_log).is_consistent
    assert (project / "exports/assets.ods").is_file()
    assert (project / "sheets/lantern/sheet.png").is_file()
    assert (project / "release/lantern-path.zip").is_file()
    assert (project / "release/lantern-path.release.json").is_file()
