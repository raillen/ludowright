"""Deterministic JSON Schema publication and drift checking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ludowright.contracts.registry import (
    CONTRACTS,
    JSON_SCHEMA_DRAFT,
    SCHEMA_VERSION,
    ContractDefinition,
)

DEFAULT_SCHEMA_ROOT = Path("schemas") / f"v{SCHEMA_VERSION}"
MANIFEST_FILENAME = "manifest.json"


def build_schema(definition: ContractDefinition) -> dict[str, Any]:
    """Build one public Draft 2020-12 schema from its canonical model."""
    schema = definition.model.model_json_schema(
        mode="validation",
        ref_template="#/$defs/{model}",
    )
    schema["$schema"] = JSON_SCHEMA_DRAFT
    schema["$id"] = definition.schema_id
    schema["title"] = definition.title
    return schema


def canonical_json(value: object) -> str:
    """Serialize JSON deterministically for publication and hashing."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def publication_files() -> dict[str, str]:
    """Render every schema and the checksum manifest without writing files."""
    rendered: dict[str, str] = {}
    manifest_entries: list[dict[str, object]] = []

    for definition in CONTRACTS:
        content = canonical_json(build_schema(definition))
        rendered[definition.filename] = content
        manifest_entries.append(
            {
                "name": definition.name,
                "file": definition.filename,
                "schema_id": definition.schema_id,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "json_schema_draft": JSON_SCHEMA_DRAFT,
        "schemas": manifest_entries,
    }
    rendered[MANIFEST_FILENAME] = canonical_json(manifest)
    return rendered


def write_publication(root: Path = DEFAULT_SCHEMA_ROOT) -> tuple[Path, ...]:
    """Write the complete generated publication and remove stale JSON files."""
    root.mkdir(parents=True, exist_ok=True)
    rendered = publication_files()
    expected_paths = {root / filename for filename in rendered}

    for stale_path in root.glob("*.json"):
        if stale_path not in expected_paths:
            stale_path.unlink()

    written: list[Path] = []
    for filename, content in rendered.items():
        path = root / filename
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return tuple(written)


def publication_drift(root: Path = DEFAULT_SCHEMA_ROOT) -> tuple[str, ...]:
    """Return missing, stale, or modified generated publication paths."""
    rendered = publication_files()
    expected_names = set(rendered)
    actual_names = {path.name for path in root.glob("*.json")} if root.exists() else set()
    drift: list[str] = []

    for missing in sorted(expected_names - actual_names):
        drift.append(f"missing:{missing}")
    for stale in sorted(actual_names - expected_names):
        drift.append(f"stale:{stale}")
    for filename in sorted(expected_names & actual_names):
        actual = (root / filename).read_text(encoding="utf-8")
        if actual != rendered[filename]:
            drift.append(f"modified:{filename}")
    return tuple(drift)
