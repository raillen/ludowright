"""Tests for the project-local Codex skill lifecycle."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from integrations.codex import (
    CodexSkillCompatibilityError,
    CodexSkillConflictError,
    CodexSkillDefinition,
    CodexSkillOperationError,
    CodexSkillService,
    CodexSkillSourceFile,
    load_codex_skill_definition,
)
from typer.testing import CliRunner

from ludowright.cli.app import app
from ludowright.cli.runtime import CliExitCode
from ludowright.contracts import CodexSkillFileContract, CodexSkillManifestContract
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath, UnsafeProjectPathError

runner = CliRunner()


def create_project(root: Path) -> ProjectFilesystem:
    root.mkdir()
    marker = root / ".ludowright" / "project.json"
    marker.parent.mkdir()
    marker.write_text("{}\n", encoding="utf-8")
    return ProjectFilesystem(root)


def make_definition(version: int, content: str) -> CodexSkillDefinition:
    payload = content.encode("utf-8")
    manifest = CodexSkillManifestContract(
        id="ludowright",
        invocation="$ludowright",
        version=version,
        description="Test LudoWright Codex skill.",
        install_path=".agents/skills/ludowright",
        entrypoint="SKILL.md",
        minimum_ludowright_version="0.1.0.dev0",
        files=(
            CodexSkillFileContract(
                path="SKILL.md",
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        ),
    )
    return CodexSkillDefinition(
        manifest=manifest,
        files=(CodexSkillSourceFile(path="SKILL.md", payload=payload),),
    )


def test_packaged_skill_definition_is_versioned_and_checksumed() -> None:
    definition = load_codex_skill_definition()

    assert definition.manifest.id == "ludowright"
    assert definition.manifest.version == 3
    assert definition.manifest.entrypoint == "SKILL.md"
    assert definition.files[0].path == "SKILL.md"
    assert definition.files[1].path == "orchestration.json"
    assert definition.files[2].path == "agents.json"
    assert (
        hashlib.sha256(definition.files[0].payload).hexdigest()
        == definition.manifest.files[0].sha256
    )


def test_install_and_verify_create_canonical_skill_files(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    service = CodexSkillService(filesystem)

    installed = service.install()
    verified = service.verify()

    assert installed.report.state == "installed"
    assert verified.report.state == "verified"
    assert verified.report.valid is True
    assert (filesystem.root / ".agents/skills/ludowright/SKILL.md").is_file()
    assert (filesystem.root / ".agents/skills/ludowright/orchestration.json").is_file()
    assert (filesystem.root / ".agents/skills/ludowright/manifest.json").is_file()
    assert service.install().report.state == "already-installed"


def test_install_dry_run_does_not_create_project_files(tmp_path: Path) -> None:
    root = tmp_path / "project"
    filesystem = create_project(root)

    result = CodexSkillService(filesystem).install(dry_run=True)

    assert result.report.state == "planned"
    assert result.report.dry_run is True
    assert not (root / ".agents/skills/ludowright").exists()
    assert not (root / ".ludowright/locks/codex-skill.lock").exists()


def test_install_rejects_unrelated_existing_files(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    target = filesystem.root / ".agents/skills/ludowright"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(CodexSkillConflictError, match=r"not empty|modified"):
        CodexSkillService(filesystem).install()

    assert (target / "notes.txt").read_text(encoding="utf-8") == "keep me\n"


def test_modified_skill_is_not_overwritten_or_removed(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    service = CodexSkillService(filesystem)
    service.install()
    skill_file = filesystem.root / ".agents/skills/ludowright/SKILL.md"
    skill_file.write_text("user modification\n", encoding="utf-8")

    verified = service.verify()

    assert verified.report.state == "modified"
    assert verified.report.valid is False
    with pytest.raises(CodexSkillConflictError, match="modified"):
        service.update()
    with pytest.raises(CodexSkillConflictError, match="modified"):
        service.remove()
    assert skill_file.read_text(encoding="utf-8") == "user modification\n"


def test_update_replaces_only_an_intact_older_version(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    old = CodexSkillService(filesystem, definition=make_definition(1, "old skill\n"))
    new = CodexSkillService(filesystem, definition=make_definition(2, "new skill\n"))

    old.install()
    planned = new.update(dry_run=True)

    assert planned.report.state == "planned"
    assert (filesystem.root / ".agents/skills/ludowright/SKILL.md").read_text() == "old skill\n"
    updated = new.update()

    assert updated.report.state == "updated"
    assert new.verify().report.state == "verified"
    assert (filesystem.root / ".agents/skills/ludowright/SKILL.md").read_text() == "new skill\n"


def test_packaged_revision_updates_a_v1_skill_with_the_policy_payload(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    old = CodexSkillService(filesystem, definition=make_definition(1, "old skill\n"))
    current = CodexSkillService(filesystem)

    old.install()
    result = current.update()

    assert result.report.state == "updated"
    assert current.verify().report.state == "verified"
    assert (filesystem.root / ".agents/skills/ludowright/orchestration.json").is_file()


def test_update_failure_restores_the_previous_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = create_project(tmp_path / "project")
    old = CodexSkillService(filesystem, definition=make_definition(1, "old skill\n"))
    new = CodexSkillService(filesystem, definition=make_definition(2, "new skill\n"))
    old.install()
    original_write = filesystem.write_child_bytes
    failed_once = False

    def fail_manifest_once(
        directory: RepositoryPath,
        filename: str,
        payload: bytes,
        *,
        mode: int | None = None,
    ) -> Path:
        nonlocal failed_once
        if filename == "manifest.json" and not failed_once:
            failed_once = True
            raise OSError("simulated skill write failure")
        return original_write(directory, filename, payload, mode=mode)

    monkeypatch.setattr(filesystem, "write_child_bytes", fail_manifest_once)

    with pytest.raises(CodexSkillOperationError, match="previous files were restored"):
        new.update()

    assert new.verify().report.state == "outdated"
    assert (filesystem.root / ".agents/skills/ludowright/SKILL.md").read_text() == "old skill\n"


def test_install_failure_cleans_a_new_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = create_project(tmp_path / "project")
    original_write = filesystem.write_child_bytes

    def fail_manifest(
        directory: RepositoryPath,
        filename: str,
        payload: bytes,
        *,
        mode: int | None = None,
    ) -> Path:
        if filename == "manifest.json":
            raise OSError("simulated manifest failure")
        return original_write(directory, filename, payload, mode=mode)

    monkeypatch.setattr(filesystem, "write_child_bytes", fail_manifest)

    with pytest.raises(CodexSkillOperationError, match="previous files were restored"):
        CodexSkillService(filesystem).install()

    assert not (filesystem.root / ".agents/skills/ludowright/SKILL.md").exists()
    assert not (filesystem.root / ".agents/skills/ludowright/manifest.json").exists()
    assert not (filesystem.root / ".agents/skills/ludowright").exists()


def test_remove_is_idempotent_and_dry_run_is_read_only(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    service = CodexSkillService(filesystem)

    planned = service.remove(dry_run=True)
    assert planned.report.state == "not-installed"
    service.install()
    dry_run = service.remove(dry_run=True)
    assert dry_run.report.state == "planned"
    assert (filesystem.root / ".agents/skills/ludowright/SKILL.md").exists()
    removed = service.remove()
    assert removed.report.state == "removed"
    assert not (filesystem.root / ".agents/skills/ludowright").exists()
    assert service.remove().report.state == "not-installed"


def test_concurrent_install_is_serialized_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "project"
    create_project(root)

    def install() -> str:
        filesystem = ProjectFilesystem(root)
        return str(CodexSkillService(filesystem).install().report.state)

    with ThreadPoolExecutor(max_workers=2) as executor:
        states = tuple(executor.map(lambda _item: install(), range(2)))

    assert sorted(states) == ["already-installed", "installed"]
    assert CodexSkillService(ProjectFilesystem(root)).verify().report.state == "verified"


def test_symlink_target_is_rejected_without_writing_outside_project(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    target = filesystem.root / ".agents/skills/ludowright"
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(UnsafeProjectPathError):
        CodexSkillService(filesystem).install()

    assert not list(outside.iterdir())


def test_framework_version_check_blocks_an_older_runtime(tmp_path: Path) -> None:
    filesystem = create_project(tmp_path / "project")

    with pytest.raises(CodexSkillCompatibilityError, match="requires LudoWright"):
        CodexSkillService(filesystem, framework_version="0.0.1")


def test_cli_human_and_json_surfaces_use_the_shared_envelope(tmp_path: Path) -> None:
    create_project(tmp_path / "project")
    human = runner.invoke(app, ["codex", "skill", "install", str(tmp_path / "project")])
    payload_result = runner.invoke(
        app,
        ["--json", "codex", "skill", "verify", str(tmp_path / "project")],
    )

    assert human.exit_code == int(CliExitCode.SUCCESS)
    assert "Codex skill install: installed." in human.stdout
    assert payload_result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(payload_result.stdout)
    assert payload["command"] == "codex skill verify"
    assert payload["ok"] is True
    assert payload["data"]["state"] == "verified"
    assert payload["error"] is None


def test_cli_verify_missing_skill_returns_error_envelope(tmp_path: Path) -> None:
    create_project(tmp_path / "project")

    result = runner.invoke(
        app,
        ["--json", "codex", "skill", "verify", str(tmp_path / "project")],
    )

    assert result.exit_code == int(CliExitCode.CHECKS_FAILED)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "checks-failed"
    assert payload["data"]["state"] == "not-installed"
