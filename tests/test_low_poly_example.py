"""Contract, profile, planning, and fixture tests for the low-poly example."""

from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ludowright.application import (
    VisualJobPlanner,
    load_hard_surface_profile,
    load_humanoid_profile,
)
from ludowright.contracts import (
    ApprovalContract,
    AssetContract,
    TechnicalSheetRequestContract,
    VisualJobContract,
    VisualReferenceContract,
)
from ludowright.domain import ReferenceId, VisualPlanBlockerCode, VisualPlanTarget

EXAMPLE_ROOT = Path("examples/low-poly-3d/project")
FIXTURE_HASHES = {
    "copper-front.png.b64": "2dfce186478b8e10407a0cd1897840a5e86bf4c40f89695466fdb168821b2cae",
    "forge-front.png.b64": "5e4747b1d8664bd550cf8d491e69abb48ad3bf61b465d5ea8f6035b6b7f9ae6f",
}


def _contract(path: str, model: type[Any]) -> Any:
    payload = json.loads((EXAMPLE_ROOT / path).read_text(encoding="utf-8"))
    return model.model_validate(payload)


def test_low_poly_inputs_and_profile_lineage_are_valid() -> None:
    copper = _contract("imports/copper.json", AssetContract)
    forge = _contract("imports/forge-building.json", AssetContract)
    copper_reference = _contract("imports/copper-reference.json", VisualReferenceContract)
    forge_reference = _contract("imports/forge-reference.json", VisualReferenceContract)
    copper_job = _contract("imports/copper-job.json", VisualJobContract)
    forge_job = _contract("imports/forge-job.json", VisualJobContract)
    copper_approval = _contract("imports/copper-approval.json", ApprovalContract)
    forge_approval = _contract("imports/forge-approval.json", ApprovalContract)
    copper_request = _contract("requests/copper-sheet.json", TechnicalSheetRequestContract)
    forge_request = _contract("requests/forge-sheet.json", TechnicalSheetRequestContract)
    brief = (EXAMPLE_ROOT / "docs/game-brief.md").read_text(encoding="utf-8")

    humanoid = load_humanoid_profile("minimal")
    building = load_hard_surface_profile("building")
    humanoid_capture = humanoid.to_capture_profile()
    building_capture = building.to_capture_profile()

    assert copper.family == "character"
    assert forge.id == "arch-forge"
    assert tuple(component.id for component in copper.components) == (
        "base-body",
        "jacket",
        "trousers",
        "footwear",
        "backpack",
    )
    assert forge.family == "architecture"
    assert tuple(state.id for state in forge.states) == ("closed", "construction")
    assert humanoid_capture.family.value == copper.family
    assert building_capture.family.value == forge.family
    assert humanoid_capture.sheets
    assert building_capture.sheets
    assert copper_reference.target.asset_id == copper.id
    assert forge_reference.target.asset_id == forge.id
    assert copper_job.input_reference_ids == (copper_reference.id,)
    assert forge_job.input_reference_ids == (forge_reference.id,)
    assert copper_approval.subject.id == copper_reference.id
    assert forge_approval.subject.id == forge_reference.id
    assert copper_request.inputs[0].reference_id == copper_reference.id
    assert forge_request.inputs[0].reference_id == forge_reference.id
    assert 'family="character"' in brief
    assert 'family="architecture"' in brief


def test_low_poly_plans_segmented_jobs_and_blocks_candidate_references() -> None:
    copper = _contract("imports/copper.json", AssetContract)
    forge = _contract("imports/forge-building.json", AssetContract)
    copper_reference = _contract("imports/copper-reference.json", VisualReferenceContract)
    forge_reference = _contract("imports/forge-reference.json", VisualReferenceContract)
    planner = VisualJobPlanner()

    copper_plan = planner.plan(
        "copper-plan",
        "Copper Plan",
        (
            VisualPlanTarget(
                copper.to_domain(),
                load_humanoid_profile("minimal").to_capture_profile(),
                (ReferenceId(copper_reference.id),),
            ),
        ),
        references=(copper_reference.to_domain(),),
    )
    forge_plan = planner.plan(
        "forge-plan",
        "Forge Plan",
        (
            VisualPlanTarget(
                forge.to_domain(),
                load_hard_surface_profile("building").to_capture_profile(),
                (ReferenceId(forge_reference.id),),
            ),
        ),
        references=(forge_reference.to_domain(),),
    )

    assert copper_plan == planner.plan(
        "copper-plan",
        "Copper Plan",
        (
            VisualPlanTarget(
                copper.to_domain(),
                load_humanoid_profile("minimal").to_capture_profile(),
                (ReferenceId(copper_reference.id),),
            ),
        ),
        references=(copper_reference.to_domain(),),
    )
    assert len(copper_plan.jobs) == 9
    assert len(forge_plan.jobs) == 11
    assert copper_plan.state.value == "blocked"
    assert forge_plan.state.value == "blocked"
    assert VisualPlanBlockerCode.REFERENCE_NOT_APPROVED in {
        blocker.code for blocker in copper_plan.blockers
    }
    assert VisualPlanBlockerCode.REFERENCE_NOT_APPROVED in {
        blocker.code for blocker in forge_plan.blockers
    }
    assert {job.target.asset_id.value for job in copper_plan.jobs} == {copper.id}
    assert {job.target.asset_id.value for job in forge_plan.jobs} == {forge.id}


def test_low_poly_fixtures_match_requests_and_are_deterministic_pngs() -> None:
    for filename, expected_hash in FIXTURE_HASHES.items():
        payload = base64.b64decode(
            (EXAMPLE_ROOT / "fixtures" / filename).read_text(encoding="ascii").strip(),
            validate=True,
        )
        request_name = filename.removesuffix(".png.b64").replace("-", "-")
        request = _contract(
            f"requests/{'copper' if request_name.startswith('copper') else 'forge'}-sheet.json",
            TechnicalSheetRequestContract,
        )
        assert hashlib.sha256(payload).hexdigest() == expected_hash
        assert request.inputs[0].sha256 == expected_hash
        with Image.open(BytesIO(payload)) as image:
            image.verify()
        with Image.open(BytesIO(payload)) as image:
            assert image.format == "PNG"
            assert image.size == (16, 16)


def test_low_poly_file_inventory_is_deterministic() -> None:
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
        "fixtures/copper-front.png.b64",
        "fixtures/forge-front.png.b64",
        "imports/copper-approval.json",
        "imports/copper-job.json",
        "imports/copper-reference.json",
        "imports/copper.json",
        "imports/forge-approval.json",
        "imports/forge-building.json",
        "imports/forge-job.json",
        "imports/forge-reference.json",
        "requests/copper-sheet.json",
        "requests/forge-sheet.json",
    )


__all__ = []
