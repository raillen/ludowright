"""Contract and planning smoke tests for the 2D sprite example."""

from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ludowright.application import VisualJobPlanner
from ludowright.contracts import (
    ApprovalContract,
    AssetContract,
    CaptureProfileContract,
    TechnicalSheetRequestContract,
    VisualJobContract,
    VisualReferenceContract,
)
from ludowright.domain import ReferenceId, VisualPlanBlockerCode, VisualPlanTarget

EXAMPLE_ROOT = Path("examples/2d/project")
EXPECTED_FIXTURE_SHA256 = "30f680984b7af812f8ded0cf5f8feafebe6458d889c35d7163f5fb023c414ece"


def _contract(path: str, model: type[Any]) -> Any:
    payload = json.loads((EXAMPLE_ROOT / path).read_text(encoding="utf-8"))
    return model.model_validate(payload)


def test_2d_example_inputs_are_valid_and_cross_referenced() -> None:
    asset = _contract("imports/courier.json", AssetContract)
    profile = _contract("profiles/courier-sprite.json", CaptureProfileContract)
    reference = _contract("imports/courier-reference.json", VisualReferenceContract)
    job = _contract("imports/courier-job.json", VisualJobContract)
    approval = _contract("imports/courier-approval.json", ApprovalContract)
    request = _contract("requests/courier-sheet.json", TechnicalSheetRequestContract)
    brief = (EXAMPLE_ROOT / "docs/game-brief.md").read_text(encoding="utf-8")

    assert asset.id == "chr-courier"
    assert asset.family == "character"
    assert profile.family == "character"
    assert profile.background is not None
    assert profile.background.mode == "transparent"
    assert profile.validation is not None
    assert (profile.validation.width, profile.validation.height) == (256, 256)
    assert reference.target.asset_id == asset.id
    assert job.target.asset_id == asset.id
    assert job.input_reference_ids == (reference.id,)
    assert approval.subject.id == reference.id
    assert approval.subject.revision == reference.provenance.content_revision
    assert request.inputs[0].reference_id == reference.id
    assert "ludowright:asset-candidate" in brief


def test_2d_profile_plans_sprite_jobs_but_requires_approval() -> None:
    asset = _contract("imports/courier.json", AssetContract)
    profile = _contract("profiles/courier-sprite.json", CaptureProfileContract)
    reference = _contract("imports/courier-reference.json", VisualReferenceContract)

    plan = VisualJobPlanner().plan(
        "courier-sprite-plan",
        "Courier Sprite Plan",
        (
            VisualPlanTarget(
                asset.to_domain(),
                profile.to_domain(),
                (ReferenceId(reference.id),),
            ),
        ),
        references=(reference.to_domain(),),
    )

    assert plan.jobs
    assert plan.state.value == "blocked"
    assert VisualPlanBlockerCode.REFERENCE_NOT_APPROVED in {
        blocker.code for blocker in plan.blockers
    }
    assert {job.target.asset_id.value for job in plan.jobs} == {asset.id}


def test_2d_fixture_matches_request_and_is_a_small_png() -> None:
    encoded = (EXAMPLE_ROOT / "fixtures/courier-front.png.b64").read_text(encoding="ascii").strip()
    payload = base64.b64decode(encoded, validate=True)
    request = _contract("requests/courier-sheet.json", TechnicalSheetRequestContract)

    assert hashlib.sha256(payload).hexdigest() == EXPECTED_FIXTURE_SHA256
    assert request.inputs[0].sha256 == EXPECTED_FIXTURE_SHA256
    with Image.open(BytesIO(payload)) as image:
        image.verify()
    with Image.open(BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == (16, 16)


def test_2d_example_file_inventory_is_deterministic() -> None:
    first = tuple(
        (
            path.relative_to(EXAMPLE_ROOT).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(EXAMPLE_ROOT.rglob("*"))
        if path.is_file()
    )
    second = tuple(
        (
            path.relative_to(EXAMPLE_ROOT).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(EXAMPLE_ROOT.rglob("*"))
        if path.is_file()
    )

    assert first == second
    assert tuple(path for path, _digest in first) == (
        "docs/game-brief.md",
        "fixtures/courier-front.png.b64",
        "imports/courier-approval.json",
        "imports/courier-job.json",
        "imports/courier-reference.json",
        "imports/courier.json",
        "profiles/courier-sprite.json",
        "requests/courier-sheet.json",
    )


__all__ = []
