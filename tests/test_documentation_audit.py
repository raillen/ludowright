"""Tests for deterministic documentation auditing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from ludowright.application import DocumentationAuditError, DocumentationAuditor
from ludowright.cli.app import app
from ludowright.contracts import (
    AtlasMetadataContract,
    DocumentationAuditPolicyContract,
    DocumentationContradictionRuleContract,
    DocumentationDeprecatedReferenceContract,
    DocumentationPhraseContract,
    DocumentationTopicContract,
)

runner = CliRunner()


def _write_metadata(root: Path, documents: list[dict[str, str]]) -> None:
    path = root / "docs" / "atlas.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = AtlasMetadataContract(version=1, documents=tuple(documents))
    path.write_text(_json(value.model_dump(mode="json")), encoding="utf-8")


def _write_policy(root: Path, policy: DocumentationAuditPolicyContract) -> None:
    path = root / "docs" / "audit-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(policy.model_dump(mode="json")), encoding="utf-8")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _valid_tree(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n\n[Guide](guide.md)\n", encoding="utf-8")
    (docs / "guide.md").write_text("# Guide\n\nA guide.\n", encoding="utf-8")
    _write_metadata(
        root,
        [
            {
                "path": "guide.md",
                "title": "Guide",
                "section": "project",
                "canonical_source": "guide.md",
            },
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            },
        ],
    )
    _write_policy(
        root,
        DocumentationAuditPolicyContract(
            version=1,
            topics=(
                DocumentationTopicContract(
                    id="guide",
                    title="Guide",
                    canonical_source="guide.md",
                ),
            ),
        ),
    )


def test_repository_audit_is_valid_and_deterministic() -> None:
    root = Path(__file__).parents[1]
    first = DocumentationAuditor(root).generate()
    second = DocumentationAuditor(root).generate()

    assert first == second
    assert first.valid
    assert first.report.findings == ()
    assert len(first.report.orphan_documents) == 0
    assert "Documentation Audit Report" in first.markdown


def test_audit_does_not_modify_inputs(tmp_path: Path) -> None:
    _valid_tree(tmp_path)
    tracked = (tmp_path / "docs" / "audit-policy.json", tmp_path / "docs" / "atlas.json")
    before = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked)

    DocumentationAuditor(tmp_path).generate()

    assert before == tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked)


def test_audit_reports_missing_canonical_topic(tmp_path: Path) -> None:
    _valid_tree(tmp_path)
    policy = DocumentationAuditPolicyContract(
        version=1,
        topics=(
            DocumentationTopicContract(
                id="missing-topic",
                title="Missing topic",
                canonical_source="missing.md",
            ),
        ),
    )
    _write_policy(tmp_path, policy)

    result = DocumentationAuditor(tmp_path).generate()

    assert not result.valid
    assert [item.code for item in result.report.findings] == ["missing-canonical-topic"]
    assert result.report.findings[0].subject == "missing-topic"


def test_audit_reports_duplicate_canonical_sources(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n", encoding="utf-8")
    (docs / "alias.md").write_text("# Alias\n", encoding="utf-8")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "alias.md",
                "title": "Alias",
                "section": "project",
                "canonical_source": "index.md",
            },
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            },
        ],
    )
    _write_policy(tmp_path, DocumentationAuditPolicyContract(version=1))

    result = DocumentationAuditor(tmp_path).generate()

    assert [item.code for item in result.report.findings] == ["duplicate-canonical-source"]
    assert result.report.findings[0].related_paths == ("alias.md", "index.md")


def test_audit_reports_stale_alias_link(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n\n[Old](alias.md)\n", encoding="utf-8")
    (docs / "alias.md").write_text("# Alias\n", encoding="utf-8")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "alias.md",
                "title": "Alias",
                "section": "project",
                "canonical_source": "alias.md",
            },
            {
                "path": "index.md",
                "title": "Index",
                "section": "project",
                "canonical_source": "index.md",
            },
        ],
    )
    _write_policy(
        tmp_path,
        DocumentationAuditPolicyContract(
            version=1,
            deprecated_references=(
                DocumentationDeprecatedReferenceContract(
                    path="alias.md",
                    replacement="index.md",
                ),
            ),
        ),
    )

    result = DocumentationAuditor(tmp_path).generate()

    assert [item.code for item in result.report.findings] == ["stale-reference"]
    assert result.report.findings[0].replacement == "index.md"


def test_audit_reports_explicit_contradiction_rule(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "left.md").write_text("# Left\nThe game is local-first.\n", encoding="utf-8")
    (docs / "right.md").write_text("# Right\nThe game is cloud-only.\n", encoding="utf-8")
    _write_metadata(
        tmp_path,
        [
            {
                "path": "left.md",
                "title": "Left",
                "section": "project",
                "canonical_source": "left.md",
            },
            {
                "path": "right.md",
                "title": "Right",
                "section": "project",
                "canonical_source": "right.md",
            },
        ],
    )
    policy = DocumentationAuditPolicyContract(
        version=1,
        contradictions=(
            DocumentationContradictionRuleContract(
                id="deployment-model",
                title="Deployment model",
                left=DocumentationPhraseContract(path="left.md", phrase="local-first"),
                right=DocumentationPhraseContract(path="right.md", phrase="cloud-only"),
            ),
        ),
    )
    _write_policy(tmp_path, policy)

    result = DocumentationAuditor(tmp_path).generate()

    assert [item.code for item in result.report.findings] == ["contradictory-claim"]
    assert result.report.findings[0].subject == "deployment-model"


def test_cli_supports_human_and_json_audit_surfaces(tmp_path: Path) -> None:
    _valid_tree(tmp_path)

    human = runner.invoke(app, ["--no-color", "docs", "audit", str(tmp_path)])
    machine = runner.invoke(app, ["--json", "docs", "audit", str(tmp_path)])

    assert human.exit_code == 0
    assert "Documentation Audit" in human.stdout
    assert "Documentation audit: valid" in human.stdout
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload["command"] == "docs audit"
    assert payload["ok"] is True
    assert payload["data"]["valid"] is True


def test_cli_check_returns_stable_failure_envelope(tmp_path: Path) -> None:
    _valid_tree(tmp_path)
    _write_policy(
        tmp_path,
        DocumentationAuditPolicyContract(
            version=1,
            topics=(
                DocumentationTopicContract(
                    id="missing-topic",
                    title="Missing topic",
                    canonical_source="missing.md",
                ),
            ),
        ),
    )

    result = runner.invoke(app, ["--json", "docs", "audit", str(tmp_path), "--check"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "docs audit"
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["valid"] is False


def test_audit_rejects_unsafe_policy_path(tmp_path: Path) -> None:
    _valid_tree(tmp_path)

    try:
        DocumentationAuditor(tmp_path, policy_path="../audit-policy.json")
    except DocumentationAuditError:
        pass
    else:
        raise AssertionError("unsafe policy path must be rejected")
