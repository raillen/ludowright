"""Tests for bounded canonical JSON and YAML document repositories."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ludowright.contracts.project import ProjectContract
from ludowright.infrastructure import (
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StructuredDocumentConflictError,
    StructuredDocumentFormat,
    StructuredDocumentFormatError,
    StructuredDocumentParseError,
    YamlDocumentRepository,
)


def project_contract(*, name: str = "Locadora 2000") -> ProjectContract:
    return ProjectContract.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "project",
                "id": "locadora-2000",
                "name": name,
                "dimensions": "3d",
                "targets": [{"platform": "windows"}],
                "stage": "concept",
                "lifecycle": "active",
            }
        )
    )


def json_repository(tmp_path: Path, *, max_bytes: int = 2_000_000) -> JsonDocumentRepository[ProjectContract]:
    return JsonDocumentRepository(
        ProjectFilesystem(tmp_path),
        RepositoryPath("data/project.json"),
        ProjectContract,
        max_bytes=max_bytes,
    )


def yaml_repository(tmp_path: Path, *, max_bytes: int = 2_000_000) -> YamlDocumentRepository[ProjectContract]:
    return YamlDocumentRepository(
        ProjectFilesystem(tmp_path),
        RepositoryPath("data/project.yaml"),
        ProjectContract,
        max_bytes=max_bytes,
    )


def test_json_create_and_load_canonical_document(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)

    created = repository.create(project_contract())
    loaded = repository.load()

    assert created == loaded
    assert loaded.format is StructuredDocumentFormat.JSON
    assert loaded.canonical is True
    assert loaded.size_bytes == len(repository.canonical_bytes(loaded.value))
    assert (tmp_path / "data/project.json").read_text(encoding="utf-8").endswith("\n")


def test_yaml_create_and_load_canonical_document(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)

    created = repository.create(project_contract())
    loaded = repository.load()

    assert created == loaded
    assert loaded.format is StructuredDocumentFormat.YAML
    assert loaded.canonical is True
    text = (tmp_path / "data/project.yaml").read_text(encoding="utf-8")
    assert "name: Locadora 2000" in text
    assert text.endswith("\n")


def test_json_noncanonical_input_is_detected_and_rewritten(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    filesystem = ProjectFilesystem(tmp_path)
    filesystem.write_text(
        RepositoryPath("data/project.json"),
        '{"name":"Locadora 2000","kind":"project","id":"locadora-2000",'
        '"schema_version":1,"dimensions":"3d","targets":[{"platform":"windows"}],'
        '"stage":"concept","lifecycle":"active"}',
    )

    loaded = repository.load()
    rewritten = repository.replace(loaded, loaded.value)

    assert loaded.canonical is False
    assert rewritten.canonical is True
    assert repository.load().canonical is True


def test_yaml_comments_and_manual_order_are_noncanonical(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "# human note\nname: Locadora 2000\nkind: project\nid: locadora-2000\n"
        "schema_version: 1\ndimensions: 3d\ntargets:\n  - platform: windows\n"
        "stage: concept\nlifecycle: active\n",
    )

    loaded = repository.load()

    assert loaded.canonical is False
    assert loaded.value == project_contract()


def test_load_optional_returns_none_for_missing_document(tmp_path: Path) -> None:
    assert json_repository(tmp_path).load_optional() is None


def test_create_rejects_existing_document(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    repository.create(project_contract())

    with pytest.raises(StructuredDocumentConflictError, match="already exists"):
        repository.create(project_contract(name="Changed"))


def test_expected_digest_prevents_lost_update(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    original = repository.create(project_contract())
    current = repository.save(project_contract(name="Current"), expected_digest=original.digest)

    with pytest.raises(StructuredDocumentConflictError, match="changed before save"):
        repository.save(project_contract(name="Stale"), expected_digest=original.digest)

    assert repository.load() == current


def test_replace_rejects_snapshot_from_another_repository(tmp_path: Path) -> None:
    json_repo = json_repository(tmp_path)
    yaml_repo = yaml_repository(tmp_path)
    snapshot = json_repo.create(project_contract())

    with pytest.raises(StructuredDocumentConflictError, match="different"):
        yaml_repo.replace(snapshot, project_contract())


def test_invalid_expected_digest_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        json_repository(tmp_path).save(project_contract(), expected_digest="bad")


def test_repository_rejects_wrong_contract_instance(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)

    with pytest.raises(TypeError, match="ProjectContract"):
        repository.save(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    (path, repository_type),
    [
        ("data/project.yaml", JsonDocumentRepository),
        ("data/project.yml", YamlDocumentRepository),
        ("data/project.json", YamlDocumentRepository),
    ],
)
def test_repository_requires_canonical_extension(
    tmp_path: Path,
    path: str,
    repository_type: type[JsonDocumentRepository[ProjectContract]]
    | type[YamlDocumentRepository[ProjectContract]],
) -> None:
    with pytest.raises(StructuredDocumentFormatError, match="extension"):
        repository_type(
            ProjectFilesystem(tmp_path),
            RepositoryPath(path),
            ProjectContract,
        )


def test_repository_requires_positive_byte_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        json_repository(tmp_path, max_bytes=0)


def test_read_limit_is_enforced_before_parsing(tmp_path: Path) -> None:
    repository = json_repository(tmp_path, max_bytes=32)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.json"),
        "{" + '"padding":"' + ("x" * 100) + '"}',
    )

    with pytest.raises(RuntimeError, match="read limit"):
        repository.load()


def test_json_rejects_duplicate_keys(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.json"),
        '{"schema_version":1,"schema_version":1}',
    )

    with pytest.raises(StructuredDocumentParseError, match="duplicate JSON"):
        repository.load()


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_json_rejects_non_finite_numbers(tmp_path: Path, constant: str) -> None:
    repository = json_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.json"),
        f'{{"value":{constant}}}',
    )

    with pytest.raises(StructuredDocumentParseError, match="non-finite"):
        repository.load()


def test_json_rejects_unknown_contract_fields(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    payload = json.loads(repository.canonical_bytes(project_contract()))
    payload["unexpected"] = True
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.json"),
        json.dumps(payload),
    )

    with pytest.raises(ValidationError):
        repository.load()


def test_structured_documents_reject_utf8_bom(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_bytes(
        RepositoryPath("data/project.json"),
        b"\xef\xbb\xbf{}",
    )

    with pytest.raises(StructuredDocumentFormatError, match="BOM"):
        repository.load()


def test_structured_documents_reject_non_utf8(tmp_path: Path) -> None:
    repository = json_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_bytes(
        RepositoryPath("data/project.json"),
        b"\xff\xfe",
    )

    with pytest.raises(StructuredDocumentFormatError, match="UTF-8"):
        repository.load()


def test_yaml_rejects_duplicate_keys(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "schema_version: 1\nschema_version: 1\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="unsafe YAML"):
        repository.load()


def test_yaml_rejects_aliases(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "base: &base\n  platform: windows\ntargets:\n  - *base\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="unsafe YAML"):
        repository.load()


def test_yaml_rejects_merge_keys(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "base: &base\n  platform: windows\ntarget:\n  <<: *base\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="unsafe YAML"):
        repository.load()


def test_yaml_rejects_multiple_documents(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "schema_version: 1\n---\nschema_version: 1\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="exactly one"):
        repository.load()


def test_yaml_rejects_non_string_mapping_keys(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "1: value\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="unsafe YAML"):
        repository.load()


def test_yaml_rejects_python_object_tags(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "value: !!python/object/apply:os.system ['echo unsafe']\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="unsafe YAML"):
        repository.load()


def test_yaml_rejects_implicit_timestamp_objects(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(
        RepositoryPath("data/project.yaml"),
        "value: 2026-07-29\n",
    )

    with pytest.raises(StructuredDocumentParseError, match="date"):
        repository.load()


def test_yaml_rejects_empty_document(tmp_path: Path) -> None:
    repository = yaml_repository(tmp_path)
    ProjectFilesystem(tmp_path).write_text(RepositoryPath("data/project.yaml"), "\n")

    with pytest.raises(StructuredDocumentParseError, match="empty"):
        repository.load()


def test_json_and_yaml_round_trip_to_equal_contracts(tmp_path: Path) -> None:
    json_repo = json_repository(tmp_path)
    yaml_repo = yaml_repository(tmp_path)
    value = project_contract(name="Locadora São João")

    json_snapshot = json_repo.create(value)
    yaml_snapshot = yaml_repo.create(value)

    assert json_snapshot.value == yaml_snapshot.value
    assert json_snapshot.digest != yaml_snapshot.digest
    assert "São João" in (tmp_path / "data/project.yaml").read_text(encoding="utf-8")


def test_canonical_serialization_is_deterministic(tmp_path: Path) -> None:
    value = project_contract()
    json_repo = json_repository(tmp_path)
    yaml_repo = yaml_repository(tmp_path)

    assert json_repo.canonical_bytes(value) == json_repo.canonical_bytes(value)
    assert yaml_repo.canonical_bytes(value) == yaml_repo.canonical_bytes(value)
