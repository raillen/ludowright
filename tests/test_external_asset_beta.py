"""Opt-in beta validation against a user-authorized external project."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

from ludowright.application import (
    PromptCompiler,
    VisualJobPlanner,
    load_humanoid_profile,
    load_visual_profile,
)
from ludowright.contracts import AssetContract, VisualBibleContract
from ludowright.domain import (
    CaptureProfile,
    DisplayName,
    InvalidPromptCompilationError,
    ReferenceId,
    ReferenceOrigin,
    ReferenceProvenance,
    ReferenceRole,
    ReferenceStatus,
    ReferenceTarget,
    SubjectRevision,
    VisualPlanState,
    VisualPlanTarget,
    VisualReference,
)
from ludowright.infrastructure import ImageNormalizer, RepositoryPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SLICE_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/beta/echos_of_mythology_slice.json"
VISUAL_BIBLE_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/contracts/v1/visual-bible.json"


def _load_slice() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(SLICE_FIXTURE.read_text(encoding="utf-8")))


def _selected_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requested = os.environ.get("LUDOWRIGHT_EXTERNAL_ASSET_IDS", "").strip()
    if not requested:
        return samples
    selected_ids = {value.strip() for value in requested.split(",") if value.strip()}
    selected = [sample for sample in samples if sample["external_id"] in selected_ids]
    unknown = selected_ids - {sample["external_id"] for sample in samples}
    if unknown:
        pytest.fail(f"unknown beta slice asset IDs: {sorted(unknown)}")
    if not selected:
        pytest.fail("LUDOWRIGHT_EXTERNAL_ASSET_IDS selected no beta slice assets")
    return selected


def _load_profile(profile_id: str) -> CaptureProfile:
    if profile_id.startswith("humanoid:"):
        return load_humanoid_profile(profile_id.split(":", maxsplit=1)[1]).to_capture_profile()
    return load_visual_profile(profile_id).to_capture_profile()


def _candidate_reference(
    sample: dict[str, Any],
    target: ReferenceTarget,
    image: bytes,
) -> VisualReference:
    digest = hashlib.sha256(image).hexdigest()
    reference_id = ReferenceId(f"ref-beta-{sample['external_id'].lower()}")
    return VisualReference(
        id=reference_id,
        name=DisplayName(f"{sample['external_id']} beta candidate"),
        target=target,
        role=ReferenceRole.IDENTITY,
        provenance=ReferenceProvenance(
            origin=ReferenceOrigin.CAPTURED,
            content_revision=SubjectRevision(f"sha256:{digest}"),
            creator=DisplayName("Echos of Mythology art pipeline"),
        ),
        status=ReferenceStatus.CANDIDATE,
    )


def _visual_bible():
    payload = json.loads(VISUAL_BIBLE_FIXTURE.read_text(encoding="utf-8"))
    return VisualBibleContract.model_validate(payload).to_domain()


@pytest.mark.external_beta
def test_external_project_slice_blocks_unapproved_generation_and_is_deterministic() -> None:
    external_project = os.environ.get("LUDOWRIGHT_EXTERNAL_PROJECT", "").strip()
    if not external_project:
        pytest.skip("set LUDOWRIGHT_EXTERNAL_PROJECT to run the external beta slice")

    root = Path(external_project).expanduser().resolve(strict=True)
    if not root.is_dir():
        pytest.fail("LUDOWRIGHT_EXTERNAL_PROJECT must point to a directory")

    data = _load_slice()
    manifest_path = root / data["manifest"]
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    manifest_by_id = {item["id"]: item for item in manifest["assets"]}
    samples = _selected_samples(cast(list[dict[str, Any]], data["samples"]))

    for sample in samples:
        external_asset = manifest_by_id.get(sample["external_id"])
        assert external_asset is not None
        assert external_asset["slug"] == sample["expected_slug"]
        assert external_asset["category"] == sample["expected_category"]

        image_path = root / sample["image"]
        image = image_path.read_bytes()
        prepared = ImageNormalizer().prepare(
            image,
            source_path=RepositoryPath(sample["image"]),
            output_directory=RepositoryPath(f"beta/normalized/{sample['asset']['id']}"),
        )
        repeated = ImageNormalizer().prepare(
            image,
            source_path=RepositoryPath(sample["image"]),
            output_directory=RepositoryPath(f"beta/normalized/{sample['asset']['id']}"),
        )
        assert prepared.report == repeated.report
        assert tuple(item.payload for item in prepared.artifacts) == tuple(
            item.payload for item in repeated.artifacts
        )
        assert len(prepared.artifacts) == 4
        assert all(item.width > 0 and item.height > 0 for item in prepared.artifacts)

        asset = AssetContract.model_validate(sample["asset"]).to_domain()
        profile = _load_profile(sample["profile"])
        target = ReferenceTarget(asset_id=asset.id)
        candidate = _candidate_reference(sample, target, image)
        plan = VisualJobPlanner().plan(
            f"beta-{asset.id.value}-plan",
            DisplayName(f"Beta {asset.name.value}"),
            (VisualPlanTarget(asset, profile, (candidate.id,)),),
            references=(candidate,),
        )
        assert plan.state is VisualPlanState.BLOCKED
        assert any(blocker.code.value == "reference-not-approved" for blocker in plan.blockers)
        assert plan.workload.output_count > 0

        with pytest.raises(InvalidPromptCompilationError, match="not approved"):
            PromptCompiler().compile(
                _visual_bible(),
                target,
                references=(candidate,),
                reference_ids=(candidate.id,),
            )


__all__ = []
