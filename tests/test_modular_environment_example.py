"""Contract, profile, planning, and connection tests for the modular example."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ludowright.application import (
    VisualJobPlanner,
    load_hard_surface_profile,
    load_visual_profile,
)
from ludowright.contracts import (
    ApprovalContract,
    AssetContract,
    CaptureProfileContract,
    TechnicalSheetRequestContract,
    VisualJobContract,
    VisualReferenceContract,
)
from ludowright.domain import ReferenceId, VisualPlanBlockerCode, VisualPlanTarget

EXAMPLE_ROOT = Path("examples/modular-environment/project")
FIXTURE_SHA256 = "2dfce186478b8e10407a0cd1897840a5e86bf4c40f89695466fdb168821b2cae"

ASSET_FILES = {
    "building": "imports/commons-building.json",
    "kit": "imports/courtyard-kit.json",
    "road": "imports/old-road.json",
    "tree": "imports/oak-tree.json",
    "plant": "imports/field-plant.json",
}
REFERENCE_FILES = {
    "building": "imports/commons-reference.json",
    "kit": "imports/courtyard-reference.json",
    "road": "imports/road-reference.json",
    "tree": "imports/oak-reference.json",
    "plant": "imports/plant-reference.json",
}
JOB_FILES = {
    "building": "imports/commons-job.json",
    "kit": "imports/courtyard-job.json",
    "road": "imports/road-job.json",
    "tree": "imports/oak-job.json",
    "plant": "imports/plant-job.json",
}
APPROVAL_FILES = {
    "building": "imports/commons-approval.json",
    "kit": "imports/courtyard-approval.json",
    "road": "imports/road-approval.json",
    "tree": "imports/oak-approval.json",
    "plant": "imports/plant-approval.json",
}
REQUEST_FILES = {
    "building": "requests/commons-sheet.json",
    "kit": "requests/courtyard-sheet.json",
    "road": "requests/road-sheet.json",
    "tree": "requests/oak-sheet.json",
    "plant": "requests/plant-sheet.json",
}


def _contract(path: str, model: type[Any]) -> Any:
    payload = json.loads((EXAMPLE_ROOT / path).read_text(encoding="utf-8"))
    return model.model_validate(payload)


def test_modular_inputs_profiles_and_connections_are_valid() -> None:
    assets = {key: _contract(path, AssetContract) for key, path in ASSET_FILES.items()}
    references = {
        key: _contract(path, VisualReferenceContract) for key, path in REFERENCE_FILES.items()
    }
    jobs = {key: _contract(path, VisualJobContract) for key, path in JOB_FILES.items()}
    approvals = {key: _contract(path, ApprovalContract) for key, path in APPROVAL_FILES.items()}
    requests = {
        key: _contract(path, TechnicalSheetRequestContract) for key, path in REQUEST_FILES.items()
    }
    road_profile = _contract("profiles/road-surface.json", CaptureProfileContract)
    brief = (EXAMPLE_ROOT / "docs/game-brief.md").read_text(encoding="utf-8")

    assert assets["building"].family == "architecture"
    assert assets["building"].subtype == "building"
    assert assets["kit"].family == "environment"
    assert assets["kit"].subtype == "modular-environment"
    assert assets["road"].family == "terrain"
    assert assets["road"].subtype == "road"
    assert tuple(item.id for item in assets["kit"].components) == (
        "root",
        "floor-module",
        "wall-module",
        "connector",
    )
    assert tuple(item.id for item in assets["kit"].states) == (
        "assembled",
        "construction",
    )
    assert road_profile.family == "terrain"
    assert road_profile.subtype == "road"

    modular_profile = load_hard_surface_profile("modular-kit")
    connection_keys = {
        (
            row.source_component_id.value,
            row.target_component_id.value,
            row.kind.value,
        )
        for row in modular_profile.connection_matrix
    }
    assert ("root", "floor-module", "edge") in connection_keys
    assert ("root", "wall-module", "edge") in connection_keys
    assert ("root", "connector", "socket") in connection_keys
    assert load_hard_surface_profile("building").to_capture_profile().family.value == "architecture"
    assert load_visual_profile("tree").to_capture_profile().subtype.value == "large-tree"
    assert load_visual_profile("plant").to_capture_profile().subtype.value == "plant"

    for key, asset in assets.items():
        reference = references[key]
        job = jobs[key]
        approval = approvals[key]
        request = requests[key]
        assert reference.target.asset_id == asset.id
        assert job.target.asset_id == asset.id
        assert job.input_reference_ids == (reference.id,)
        assert approval.subject.id == reference.id
        assert approval.subject.revision == reference.provenance.content_revision
        assert request.inputs[0].reference_id == reference.id

    assert all(
        f'subtype="{subtype}"' in brief
        for subtype in (
            "building",
            "modular-environment",
            "road",
            "large-tree",
            "plant",
        )
    )


def test_modular_profiles_plan_deterministic_segmented_workload_and_blockers() -> None:
    assets = {key: _contract(path, AssetContract) for key, path in ASSET_FILES.items()}
    references = {
        key: _contract(path, VisualReferenceContract) for key, path in REFERENCE_FILES.items()
    }
    profiles = {
        "building": load_hard_surface_profile("building").to_capture_profile(),
        "kit": load_hard_surface_profile("modular-kit").to_capture_profile(),
        "road": _contract("profiles/road-surface.json", CaptureProfileContract).to_domain(),
        "tree": load_visual_profile("tree").to_capture_profile(),
        "plant": load_visual_profile("plant").to_capture_profile(),
    }
    targets = tuple(
        VisualPlanTarget(
            assets[key].to_domain(),
            profiles[key],
            (ReferenceId(references[key].id),),
        )
        for key in ASSET_FILES
    )
    selected_references = tuple(reference.to_domain() for reference in references.values())
    planner = VisualJobPlanner()

    first = planner.plan(
        "mossbridge-plan",
        "Mossbridge Commons Plan",
        targets,
        references=selected_references,
    )
    second = planner.plan(
        "mossbridge-plan",
        "Mossbridge Commons Plan",
        targets,
        references=selected_references,
    )

    assert first == second
    assert first.state.value == "blocked"
    assert len(first.jobs) == 50
    assert Counter(job.target.asset_id.value for job in first.jobs) == Counter(
        {
            "arch-commons": 11,
            "env-courtyard": 13,
            "ter-old-road": 10,
            "veg-oak": 8,
            "veg-field-plant": 8,
        }
    )
    assert {blocker.code for blocker in first.blockers} == {
        VisualPlanBlockerCode.REFERENCE_NOT_APPROVED
    }


def test_modular_fixture_matches_every_sheet_request() -> None:
    encoded = (EXAMPLE_ROOT / "fixtures/commons-front.png.b64").read_text(encoding="ascii").strip()
    payload = base64.b64decode(encoded, validate=True)

    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    with Image.open(BytesIO(payload)) as image:
        image.verify()
    with Image.open(BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == (16, 16)

    for path in REQUEST_FILES.values():
        request = _contract(path, TechnicalSheetRequestContract)
        assert request.inputs[0].sha256 == FIXTURE_SHA256


def test_modular_example_file_inventory_is_deterministic() -> None:
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
        "fixtures/commons-front.png.b64",
        "imports/commons-approval.json",
        "imports/commons-building.json",
        "imports/commons-job.json",
        "imports/commons-reference.json",
        "imports/courtyard-approval.json",
        "imports/courtyard-job.json",
        "imports/courtyard-kit.json",
        "imports/courtyard-reference.json",
        "imports/field-plant.json",
        "imports/oak-approval.json",
        "imports/oak-job.json",
        "imports/oak-reference.json",
        "imports/oak-tree.json",
        "imports/old-road.json",
        "imports/plant-approval.json",
        "imports/plant-job.json",
        "imports/plant-reference.json",
        "imports/road-approval.json",
        "imports/road-job.json",
        "imports/road-reference.json",
        "profiles/road-surface.json",
        "requests/commons-sheet.json",
        "requests/courtyard-sheet.json",
        "requests/oak-sheet.json",
        "requests/plant-sheet.json",
        "requests/road-sheet.json",
    )


__all__ = []
