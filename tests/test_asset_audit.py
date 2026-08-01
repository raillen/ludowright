"""Tests for deterministic, read-only asset completeness auditing."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ludowright.application import AssetAuditService, AssetRegistryService
from ludowright.cli.app import app
from ludowright.contracts import AssetContract
from ludowright.domain import (
    DependencyEdge,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    InvalidationMode,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DependencyGraphRepository,
    ProjectFilesystem,
)

runner = CliRunner()


def _project(tmp_path: Path) -> ProjectFilesystem:
    marker = tmp_path / ".ludowright" / "project.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(tmp_path)


def _asset(
    *,
    asset_id: str = "prop-cabinet",
    name: str = "Arcade Cabinet",
    owner: bool = False,
    decomposed: bool = False,
    status: str = "planned",
) -> AssetContract:
    owner_payload = {"id": "team-art", "label": "Art", "kind": "team"} if owner else None
    component_owner = owner_payload if owner else None
    return AssetContract.model_validate(
        {
            "schema_version": 1,
            "kind": "asset",
            "id": asset_id,
            "name": name,
            "family": "prop",
            "subtype": "container",
            "priority": "normal",
            "status": status,
            "owner": owner_payload,
            "components": (
                [
                    {
                        "id": "body",
                        "name": "Body",
                        "status": "planned",
                        "required": True,
                        "owner": component_owner,
                    }
                ]
                if decomposed
                else []
            ),
            "variants": [],
            "states": [],
        }
    )


def _graph(*keys: DependencyKey, edge: DependencyEdge | None = None) -> DependencyGraph:
    graph = DependencyGraph.empty()
    for key in keys:
        graph = graph.add_node(DependencyNode(key, RevisionVersion(1)))
    if edge is not None:
        graph = graph.connect(
            edge.source,
            edge.target,
            edge.relation,
            edge.invalidation_mode,
        )
    return graph


def test_empty_audit_is_valid_and_read_only(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    first = AssetAuditService(filesystem).audit()
    second = AssetAuditService(filesystem).audit()

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert first.report.state == "empty"
    assert first.report.valid is True
    assert first.as_data() == second.as_data()
    assert first.report.state_store_schema_version == 2
    assert before == after


def test_audit_reports_missing_spec_profile_and_metadata_as_warnings(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    AssetRegistryService(filesystem).create_many((_asset(),))

    result = AssetAuditService(filesystem).audit()
    codes = [finding.code for finding in result.report.findings]

    assert codes == [
        "incomplete-production-metadata",
        "missing-capture-profile",
        "missing-specification",
    ]
    assert result.report.warning_count == 3
    assert result.report.error_count == 0
    assert result.report.valid is True


def test_audit_accepts_a_complete_asset_but_keeps_profile_warning(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    AssetRegistryService(filesystem).create_many((_asset(owner=True, decomposed=True),))

    result = AssetAuditService(filesystem).audit()

    assert [finding.code for finding in result.report.findings] == ["missing-capture-profile"]
    assert result.report.valid is True


def test_audit_excludes_cancelled_and_archived_assets_from_warnings(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    AssetRegistryService(filesystem).create_many(
        (
            _asset(asset_id="prop-cancelled", status="cancelled"),
            _asset(asset_id="prop-archived", status="archived"),
        )
    )

    result = AssetAuditService(filesystem).audit()

    assert result.report.findings == ()
    assert result.report.valid is True


def test_audit_reports_orphan_graph_nodes_and_invalid_dependencies(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    AssetRegistryService(filesystem).create_many(
        (
            _asset(asset_id="prop-cabinet", owner=True, decomposed=True),
            _asset(asset_id="prop-counter", name="Counter", owner=True, decomposed=True),
        )
    )
    cabinet = DependencyKey(DependencyNodeKind.ASSET, "prop-cabinet")
    counter = DependencyKey(DependencyNodeKind.ASSET, "prop-counter")
    orphan = DependencyKey(DependencyNodeKind.ASSET, "prop-orphan")
    edge = DependencyEdge(
        source=cabinet,
        target=orphan,
        relation=DependencyRelation.REQUIRES,
        invalidation_mode=InvalidationMode.STALE,
        observed_source_revision=RevisionVersion(1),
    )
    graph = _graph(cabinet, counter, orphan, edge=edge)
    graph = graph.connect(
        cabinet,
        counter,
        DependencyRelation.REFERENCES,
        InvalidationMode.NONE,
    )
    DependencyGraphRepository(filesystem).create(graph)

    result = AssetAuditService(filesystem).audit()
    findings = {(finding.code, finding.subject) for finding in result.report.findings}

    assert ("orphan-asset-node", "asset:prop-orphan") in findings
    assert ("invalid-dependency", "asset:prop-cabinet->asset:prop-orphan") in findings
    assert ("invalid-dependency", "asset:prop-cabinet->asset:prop-counter") in findings
    assert result.report.valid is False
    assert result.report.dependency_graph_revision > 0


def test_cli_human_and_json_surfaces_use_the_published_report(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    AssetRegistryService(filesystem).create_many((_asset(),))

    human = runner.invoke(app, ["assets", "audit", str(tmp_path)])
    assert human.exit_code == 0
    assert "Asset audit" in human.stdout
    assert "missing-capture-profile" in human.stdout

    machine = runner.invoke(app, ["--json", "assets", "audit", str(tmp_path), "--dry-run"])
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload["kind"] == "cli-response"
    assert payload["command"] == "assets audit"
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["kind"] == "asset-audit"


def test_cli_check_returns_error_envelope_for_blocking_findings(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    asset = _asset(owner=True, decomposed=True)
    AssetRegistryService(filesystem).create_many((asset,))
    known = DependencyKey(DependencyNodeKind.ASSET, asset.id)
    orphan = DependencyKey(DependencyNodeKind.ASSET, "prop-orphan")
    graph = _graph(
        known,
        orphan,
        edge=DependencyEdge(
            source=known,
            target=orphan,
            relation=DependencyRelation.REQUIRES,
            invalidation_mode=InvalidationMode.STALE,
            observed_source_revision=RevisionVersion(1),
        ),
    )
    DependencyGraphRepository(filesystem).create(graph)

    result = runner.invoke(
        app,
        ["--json", "assets", "audit", str(tmp_path), "--check"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["kind"] == "asset-audit"
    assert payload["error"]["details"]["errors"] == 2


def test_cli_returns_corrupt_state_for_invalid_graph(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    filesystem.write_text(DEFAULT_DEPENDENCY_GRAPH_PATH, '{"kind":"wrong"}\n')

    result = runner.invoke(app, ["--json", "assets", "audit", str(tmp_path)])

    assert result.exit_code == 6
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "corrupt-state"


def test_audit_does_not_create_state_store_or_event_log(tmp_path: Path) -> None:
    filesystem = _project(tmp_path)
    result = AssetAuditService(filesystem).audit(dry_run=True)

    assert result.report.dry_run is True
    assert not (tmp_path / ".ludowright/state.sqlite3").exists()
    assert not (tmp_path / ".ludowright/events.jsonl").exists()
    assert not (tmp_path / "assets/registry.yaml").exists()
