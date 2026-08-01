"""Contract and determinism smoke tests for the minimal example."""

from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ludowright.contracts import (
    ApprovalContract,
    AssetContract,
    TechnicalSheetRequestContract,
    VisualJobContract,
)

EXAMPLE_ROOT = Path("examples/minimal/project")
EXPECTED_FIXTURE_SHA256 = "431ced6916a2a21a156e38701afe55bbd7f88969fbbfc56d7fe099d47f265460"


def _contract(path: str, model: type[Any]) -> Any:
    payload = json.loads((EXAMPLE_ROOT / path).read_text(encoding="utf-8"))
    return model.model_validate(payload)


def test_minimal_example_inputs_are_valid_and_cross_referenced() -> None:
    asset = _contract("imports/lantern.json", AssetContract)
    job = _contract("imports/lantern-job.json", VisualJobContract)
    approval = _contract("imports/lantern-approval.json", ApprovalContract)
    request = _contract("requests/lantern-sheet.json", TechnicalSheetRequestContract)
    brief = (EXAMPLE_ROOT / "docs/game-brief.md").read_text(encoding="utf-8")

    assert asset.id == "prop-lantern"
    assert asset.subtype == "handheld-tool"
    assert job.target.asset_id == asset.id
    assert approval.subject.id == "ref-lantern-front"
    assert request.inputs[0].reference_id == approval.subject.id
    assert "ludowright:asset-candidate" in brief
    assert 'family="prop"' in brief


def test_minimal_example_fixture_matches_sheet_request() -> None:
    encoded = (EXAMPLE_ROOT / "fixtures/lantern-front.png.b64").read_text(encoding="ascii").strip()
    payload = base64.b64decode(encoded, validate=True)
    request = _contract("requests/lantern-sheet.json", TechnicalSheetRequestContract)

    assert hashlib.sha256(payload).hexdigest() == EXPECTED_FIXTURE_SHA256
    assert request.inputs[0].sha256 == EXPECTED_FIXTURE_SHA256
    with Image.open(BytesIO(payload)) as image:
        image.verify()
    with Image.open(BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == (1, 1)


def test_minimal_example_file_inventory_is_deterministic() -> None:
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
        "fixtures/lantern-front.png.b64",
        "imports/lantern-approval.json",
        "imports/lantern-job.json",
        "imports/lantern.json",
        "requests/lantern-sheet.json",
    )


__all__ = []
