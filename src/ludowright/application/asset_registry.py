"""Asset registry use cases over the canonical structured repository."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace

from ludowright.application.asset_taxonomy import (
    AssetTaxonomy,
    AssetTaxonomyError,
    load_asset_taxonomy,
)
from ludowright.contracts import AssetContract, AssetRegistryContract
from ludowright.domain import (
    AssetId,
    AssetStatus,
    CorrelationId,
    EventDraft,
    EventType,
    FrozenJsonValue,
)
from ludowright.infrastructure import (
    DEFAULT_EVENT_LOG_PATH,
    STATE_SCHEMA_VERSION,
    EventLog,
    IndexedEntity,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StateStore,
    StructuredDocumentConflictError,
    StructuredDocumentRepository,
    StructuredDocumentSnapshot,
    YamlDocumentRepository,
)

DEFAULT_ASSET_REGISTRY_PATH = RepositoryPath("assets/registry.yaml")
ASSET_REGISTRY_ENTITY_TYPE = "asset-registry"
ASSET_REGISTRY_ENTITY_ID = "registry"
_ASSET_REGISTRY_LOCK = "asset-registry"
_CORRELATION_ID = CorrelationId("asset-registry")


class AssetRegistryError(RuntimeError):
    """Base class for asset registry application failures."""


class AssetRegistryNotFoundError(AssetRegistryError):
    """Raised when a requested asset is not in the canonical registry."""


class AssetRegistryConflictError(StructuredDocumentConflictError):
    """Raised when an operation would silently replace an existing asset."""


class AssetRegistryRollbackError(AssetRegistryError):
    """Raised when a failed multi-resource operation cannot be restored."""


@dataclass(frozen=True, slots=True)
class AssetRegistryResult:
    """Stable result shared by application callers and CLI renderers."""

    operation: str
    state: str
    dry_run: bool
    registry_path: str
    registry_version: int
    assets: tuple[AssetContract, ...] = ()
    asset: AssetContract | None = None
    output_path: str | None = None
    warnings: tuple[str, ...] = ()
    valid: bool = True
    state_store_schema_version: int = STATE_SCHEMA_VERSION

    def as_data(self) -> dict[str, object]:
        """Return the published JSON-compatible command data."""
        data: dict[str, object] = {
            "assets": [asset.model_dump(mode="json", exclude_none=True) for asset in self.assets],
            "dry_run": self.dry_run,
            "kind": "asset-registry-report",
            "operation": self.operation,
            "registry_path": self.registry_path,
            "registry_version": self.registry_version,
            "schema_version": 1,
            "state": self.state,
            "state_store_schema_version": self.state_store_schema_version,
            "valid": self.valid,
            "warnings": list(self.warnings),
        }
        if self.asset is not None:
            data["asset"] = self.asset.model_dump(mode="json", exclude_none=True)
        if self.output_path is not None:
            data["output_path"] = self.output_path
        return data


class AssetRegistryService:
    """Create, inspect, validate, and exchange assets safely."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        registry_path: RepositoryPath = DEFAULT_ASSET_REGISTRY_PATH,
        taxonomy: AssetTaxonomy | None = None,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("asset registry requires ProjectFilesystem")
        if not isinstance(registry_path, RepositoryPath):
            raise TypeError("asset registry requires RepositoryPath")
        if not registry_path.name.endswith(".yaml"):
            raise AssetRegistryError("asset registry path must use the .yaml extension")
        self._filesystem = filesystem
        self._registry_path = registry_path
        self._taxonomy = taxonomy or load_asset_taxonomy()

    @property
    def registry_path(self) -> RepositoryPath:
        """Return the canonical asset registry path."""
        return self._registry_path

    def create(
        self,
        input_path: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> AssetRegistryResult:
        """Add one asset, refusing duplicate IDs and silent replacement."""
        asset = self._load_asset(input_path)
        return replace(self.create_many((asset,), dry_run=dry_run), asset=asset)

    def create_many(
        self,
        assets: tuple[AssetContract, ...],
        *,
        dry_run: bool = False,
        event_type: str = "asset.created",
        event_payload: Mapping[str, FrozenJsonValue] | None = None,
        operation: str = "create",
    ) -> AssetRegistryResult:
        """Add several validated assets as one registry operation."""
        if not assets:
            raise AssetRegistryError("asset creation requires at least one asset")
        if any(not isinstance(asset, AssetContract) for asset in assets):
            raise TypeError("asset creation requires AssetContract values")
        for asset in assets:
            self._validate_asset(asset)
        asset_ids = tuple(asset.id for asset in assets)
        if len(asset_ids) != len(set(asset_ids)):
            raise AssetRegistryConflictError("asset creation contains duplicate IDs")
        with self._operation_lock(dry_run):
            snapshot, current = self._load_current()
            existing_ids = {asset.id for asset in current.assets}
            duplicates = tuple(sorted(existing_ids.intersection(asset_ids)))
            if duplicates:
                raise AssetRegistryConflictError(
                    "assets already exist in the registry: " + ", ".join(duplicates)
                )
            updated = _with_assets(current, assets, add=True)
            if dry_run:
                return self._result(
                    operation,
                    "planned",
                    True,
                    updated,
                    assets=assets,
                )
            self._persist_registry(
                snapshot,
                updated,
                event_type=event_type,
                asset_ids=asset_ids,
                event_payload=event_payload,
            )
            return self._result(operation, "created", False, updated, assets=assets)

    def update(
        self,
        asset_id: str,
        input_path: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> AssetRegistryResult:
        """Replace one asset while preserving its ID and valid status transitions."""
        asset = self._load_asset(input_path)
        asset_id = _canonical_asset_id(asset_id)
        if asset.id != asset_id:
            raise AssetRegistryError(
                f"update input ID {asset.id!r} does not match requested asset {asset_id!r}"
            )
        return self.replace_contract(asset, dry_run=dry_run)

    def replace_contract(
        self,
        asset: AssetContract,
        *,
        dry_run: bool = False,
        expected_asset: AssetContract | None = None,
        event_type: str = "asset.updated",
        event_payload: Mapping[str, FrozenJsonValue] | None = None,
        operation: str = "update",
    ) -> AssetRegistryResult:
        """Replace one validated asset contract through the canonical mutation boundary."""
        if not isinstance(asset, AssetContract):
            raise TypeError("asset replacement requires an AssetContract")
        self._validate_asset(asset)
        asset_id = _canonical_asset_id(asset.id)
        with self._operation_lock(dry_run):
            snapshot, current = self._load_current(required=True)
            existing = _asset_by_id(current, asset_id)
            if existing is None:
                raise AssetRegistryNotFoundError(f"asset does not exist: {asset_id}")
            if expected_asset is not None and existing != expected_asset:
                raise AssetRegistryConflictError(
                    f"asset changed while the replacement was being planned: {asset_id}"
                )
            existing.to_domain().transition_status(asset.to_domain().status)
            updated = _with_assets(current, (asset,), replace_id=asset_id)
            if dry_run:
                return self._result(
                    operation,
                    "planned",
                    True,
                    updated,
                    asset=asset,
                    assets=(asset,),
                )
            self._persist_registry(
                snapshot,
                updated,
                event_type=event_type,
                asset_ids=(asset.id,),
                event_payload=event_payload,
            )
            return self._result(
                operation,
                "updated",
                False,
                updated,
                asset=asset,
                assets=(asset,),
            )

    def list_assets(self) -> AssetRegistryResult:
        """Return all valid assets in stable ID order without creating state."""
        _snapshot, registry = self._load_current()
        return self._result(
            "list",
            "valid" if registry.assets else "empty",
            False,
            registry,
            assets=registry.assets,
        )

    def inspect(self, asset_id: str) -> AssetRegistryResult:
        """Return one validated asset without changing project files."""
        asset_id = _canonical_asset_id(asset_id)
        _snapshot, registry = self._load_current(required=True)
        asset = _asset_by_id(registry, asset_id)
        if asset is None:
            raise AssetRegistryNotFoundError(f"asset does not exist: {asset_id}")
        return self._result("inspect", "valid", False, registry, asset=asset, assets=(asset,))

    def archive(self, asset_id: str, *, dry_run: bool = False) -> AssetRegistryResult:
        """Move one completed or cancelled asset to the terminal archive state."""
        asset_id = _canonical_asset_id(asset_id)
        with self._operation_lock(dry_run):
            snapshot, current = self._load_current(required=True)
            existing = _asset_by_id(current, asset_id)
            if existing is None:
                raise AssetRegistryNotFoundError(f"asset does not exist: {asset_id}")
            if existing.status is AssetStatus.ARCHIVED:
                return self._result(
                    "archive",
                    "unchanged",
                    dry_run,
                    current,
                    asset=existing,
                    assets=(existing,),
                )
            archived = AssetContract.model_validate(
                {**existing.model_dump(mode="json"), "status": AssetStatus.ARCHIVED.value}
            )
            existing.to_domain().transition_status(archived.to_domain().status)
            updated = _with_assets(current, (archived,), replace_id=asset_id)
            if dry_run:
                return self._result(
                    "archive",
                    "planned",
                    True,
                    updated,
                    asset=archived,
                    assets=(archived,),
                )
            self._persist_registry(
                snapshot,
                updated,
                event_type="asset.archived",
                asset_ids=(asset_id,),
            )
            return self._result(
                "archive",
                "archived",
                False,
                updated,
                asset=archived,
                assets=(archived,),
            )

    def validate(self, asset_id: str | None = None) -> AssetRegistryResult:
        """Validate the registry and optionally one selected asset."""
        if asset_id is not None:
            asset_id = _canonical_asset_id(asset_id)
        _snapshot, registry = self._load_current()
        selected = None
        assets = registry.assets
        if asset_id is not None:
            selected = _asset_by_id(registry, asset_id)
            if selected is None:
                raise AssetRegistryNotFoundError(f"asset does not exist: {asset_id}")
            assets = (selected,)
        return self._result("validate", "valid", False, registry, asset=selected, assets=assets)

    def import_registry(
        self,
        input_path: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> AssetRegistryResult:
        """Merge a versioned registry file without replacing existing IDs."""
        with self._operation_lock(dry_run):
            _source_snapshot, incoming = self._load_registry(input_path)
            snapshot, current = self._load_current()
            incoming_ids = tuple(asset.id for asset in incoming.assets)
            existing_ids = {asset.id for asset in current.assets}
            duplicates = tuple(sorted(existing_ids.intersection(incoming_ids)))
            if duplicates:
                raise AssetRegistryConflictError(
                    "asset import contains IDs already present: " + ", ".join(duplicates)
                )
            updated = _with_assets(current, incoming.assets, add=True)
            if dry_run:
                return self._result(
                    "import",
                    "planned",
                    True,
                    updated,
                    assets=incoming.assets,
                )
            self._persist_registry(
                snapshot,
                updated,
                event_type="asset.imported",
                asset_ids=incoming_ids,
            )
            return self._result("import", "imported", False, updated, assets=incoming.assets)

    def export_registry(
        self,
        output_path: RepositoryPath,
        *,
        dry_run: bool = False,
    ) -> AssetRegistryResult:
        """Write one deterministic batch export without overwriting a file."""
        _snapshot, registry = self._load_current()
        self._validate_registry(registry)
        repository = self._structured_repository(output_path, AssetRegistryContract)
        if dry_run:
            return self._result(
                "export",
                "planned",
                True,
                registry,
                assets=registry.assets,
                output_path=output_path.value,
            )

        with self._filesystem.lock(_ASSET_REGISTRY_LOCK, timeout=5.0):
            prior_output = _read_optional_bytes(self._filesystem, output_path)
            if prior_output is not None:
                raise AssetRegistryConflictError(
                    f"export target already exists and will not be overwritten: {output_path}"
                )
            event_log = EventLog(self._filesystem)
            prior_event_bytes = _read_optional_bytes(self._filesystem, DEFAULT_EVENT_LOG_PATH)
            output_written = False
            event_written = False
            output_after_bytes: bytes | None = None
            event_after_bytes: bytes | None = None
            try:
                repository.create(registry)
                output_written = True
                output_after_bytes = _read_optional_bytes(self._filesystem, output_path)
                event_log.append(
                    _event_draft(
                        "asset.exported",
                        operation="export",
                        registry_version=registry.version,
                        asset_ids=tuple(asset.id for asset in registry.assets),
                        output_path=output_path.value,
                    ),
                    timeout=5.0,
                )
                event_written = True
                event_after_bytes = _read_optional_bytes(self._filesystem, DEFAULT_EVENT_LOG_PATH)
            except BaseException as error:
                try:
                    if output_written:
                        _restore_file_if_unchanged(
                            self._filesystem,
                            output_path,
                            output_after_bytes,
                            prior_output,
                        )
                    if event_written:
                        _restore_file_if_unchanged(
                            self._filesystem,
                            DEFAULT_EVENT_LOG_PATH,
                            event_after_bytes,
                            prior_event_bytes,
                        )
                except BaseException as rollback_error:
                    raise AssetRegistryRollbackError(
                        f"asset export rollback failed: {rollback_error}"
                    ) from error
                raise
        return self._result(
            "export",
            "exported",
            False,
            registry,
            assets=registry.assets,
            output_path=output_path.value,
        )

    def _load_current(
        self,
        *,
        required: bool = False,
    ) -> tuple[StructuredDocumentSnapshot[AssetRegistryContract] | None, AssetRegistryContract]:
        snapshot = self._registry_repository().load_optional()
        if snapshot is None:
            if required:
                raise AssetRegistryNotFoundError(
                    f"asset registry does not exist: {self._registry_path}"
                )
            return None, AssetRegistryContract()
        registry = _sorted_registry(snapshot.value)
        self._validate_registry(registry)
        return snapshot, registry

    def _load_registry(
        self,
        path: RepositoryPath,
    ) -> tuple[StructuredDocumentSnapshot[AssetRegistryContract], AssetRegistryContract]:
        snapshot = self._structured_repository(path, AssetRegistryContract).load()
        registry = _sorted_registry(snapshot.value)
        self._validate_registry(registry)
        return snapshot, registry

    def _load_asset(self, path: RepositoryPath) -> AssetContract:
        return self._structured_repository(path, AssetContract).load().value

    def _validate_registry(self, registry: AssetRegistryContract) -> None:
        for asset in registry.assets:
            self._validate_asset(asset)

    def _validate_asset(self, asset: AssetContract) -> None:
        try:
            self._taxonomy.validate_classification(asset.family, asset.subtype)
            self._taxonomy.validate_asset_id(asset.family, asset.id)
        except AssetTaxonomyError as error:
            raise AssetRegistryError(str(error)) from error
        asset.to_domain()

    def _persist_registry(
        self,
        snapshot: StructuredDocumentSnapshot[AssetRegistryContract] | None,
        registry: AssetRegistryContract,
        *,
        event_type: str,
        asset_ids: tuple[str, ...],
        event_payload: Mapping[str, FrozenJsonValue] | None = None,
    ) -> None:
        repository = self._registry_repository()
        event_log = EventLog(self._filesystem)
        prior_registry_bytes = _read_optional_bytes(self._filesystem, self._registry_path)
        prior_event_bytes = _read_optional_bytes(self._filesystem, DEFAULT_EVENT_LOG_PATH)
        prior_event_snapshot = event_log.replay()
        state_store = StateStore(self._filesystem)
        prior_entity = state_store.get_entity(ASSET_REGISTRY_ENTITY_TYPE, ASSET_REGISTRY_ENTITY_ID)
        state_touched = False
        registry_written = False
        event_written = False
        registry_after_bytes: bytes | None = None
        event_after_bytes: bytes | None = None
        try:
            if snapshot is None:
                saved = repository.create(registry)
            else:
                saved = repository.replace(snapshot, registry)
            registry_written = True
            registry_after_bytes = _read_optional_bytes(self._filesystem, self._registry_path)
            event_log.append(
                _event_draft(
                    event_type,
                    operation=event_type.removeprefix("asset."),
                    registry_version=registry.version,
                    asset_ids=asset_ids,
                    extra_payload=event_payload,
                ),
                timeout=5.0,
            )
            event_written = True
            event_after_bytes = _read_optional_bytes(self._filesystem, DEFAULT_EVENT_LOG_PATH)
            event_snapshot = event_log.replay()
            timestamp = event_snapshot.events[-1].occurred_at
            state_store.index_entity(
                IndexedEntity(
                    entity_type=ASSET_REGISTRY_ENTITY_TYPE,
                    entity_id=ASSET_REGISTRY_ENTITY_ID,
                    source_path=self._registry_path,
                    source_digest=saved.digest,
                    revision=registry.version,
                    status="active",
                    updated_at=timestamp,
                )
            )
            state_touched = True
            state_store.record_event_checkpoint(event_snapshot, updated_at=timestamp)
            state_touched = True
        except BaseException as error:
            try:
                if registry_written:
                    _restore_file_if_unchanged(
                        self._filesystem,
                        self._registry_path,
                        registry_after_bytes,
                        prior_registry_bytes,
                    )
                if event_written:
                    _restore_file_if_unchanged(
                        self._filesystem,
                        DEFAULT_EVENT_LOG_PATH,
                        event_after_bytes,
                        prior_event_bytes,
                    )
                if state_touched:
                    if prior_entity is None:
                        state_store.delete_entity(
                            ASSET_REGISTRY_ENTITY_TYPE,
                            ASSET_REGISTRY_ENTITY_ID,
                        )
                    else:
                        state_store.index_entity(prior_entity)
                    state_store.record_event_checkpoint(prior_event_snapshot)
            except BaseException as rollback_error:
                raise AssetRegistryRollbackError(
                    f"asset registry rollback failed: {rollback_error}"
                ) from error
            raise

    def _registry_repository(self) -> YamlDocumentRepository[AssetRegistryContract]:
        return YamlDocumentRepository(
            self._filesystem,
            self._registry_path,
            AssetRegistryContract,
        )

    def _structured_repository[TContract: AssetContract | AssetRegistryContract](
        self,
        path: RepositoryPath,
        model: type[TContract],
    ) -> StructuredDocumentRepository[TContract]:
        if path.name.endswith(".json"):
            return JsonDocumentRepository(self._filesystem, path, model)
        if path.name.endswith(".yaml"):
            return YamlDocumentRepository(self._filesystem, path, model)
        raise AssetRegistryError("asset registry documents must use .json or .yaml")

    def _operation_lock(self, dry_run: bool) -> AbstractContextManager[object]:
        return (
            _NullContext() if dry_run else self._filesystem.lock(_ASSET_REGISTRY_LOCK, timeout=5.0)
        )

    def _result(
        self,
        operation: str,
        state: str,
        dry_run: bool,
        registry: AssetRegistryContract,
        *,
        asset: AssetContract | None = None,
        assets: tuple[AssetContract, ...] = (),
        output_path: str | None = None,
    ) -> AssetRegistryResult:
        return AssetRegistryResult(
            operation=operation,
            state=state,
            dry_run=dry_run,
            registry_path=self._registry_path.value,
            registry_version=registry.version,
            assets=tuple(sorted(assets, key=lambda value: value.id)),
            asset=asset,
            output_path=output_path,
        )


class _NullContext:
    def __enter__(self) -> _NullContext:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _sorted_registry(registry: AssetRegistryContract) -> AssetRegistryContract:
    return registry.model_copy(
        update={"assets": tuple(sorted(registry.assets, key=lambda asset: asset.id))}
    )


def _with_assets(
    registry: AssetRegistryContract,
    assets: tuple[AssetContract, ...],
    *,
    add: bool = False,
    replace_id: str | None = None,
) -> AssetRegistryContract:
    if add:
        combined = (*registry.assets, *assets)
    elif replace_id is not None:
        combined = tuple(
            asset if asset.id != replace_id else assets[0] for asset in registry.assets
        )
    else:
        combined = assets
    return AssetRegistryContract(
        version=1 if not registry.assets and add else registry.version + 1,
        assets=tuple(sorted(combined, key=lambda asset: asset.id)),
    )


def _asset_by_id(registry: AssetRegistryContract, asset_id: str) -> AssetContract | None:
    return next((asset for asset in registry.assets if asset.id == asset_id), None)


def _canonical_asset_id(asset_id: str) -> str:
    return AssetId(asset_id).value


def _event_draft(
    event_type: str,
    *,
    operation: str,
    registry_version: int,
    asset_ids: tuple[str, ...],
    output_path: str | None = None,
    extra_payload: Mapping[str, FrozenJsonValue] | None = None,
) -> EventDraft:
    payload: dict[str, FrozenJsonValue] = {
        "asset_ids": asset_ids,
        "operation": operation,
        "registry_version": registry_version,
    }
    if output_path is not None:
        payload["output_path"] = output_path
    if extra_payload is not None:
        for key, value in extra_payload.items():
            if key in payload:
                raise AssetRegistryError(f"asset event payload key is reserved: {key}")
            payload[key] = value
    return EventDraft(
        event_type=EventType(event_type),
        correlation_id=_CORRELATION_ID,
        payload=payload,
    )


def _read_optional_bytes(filesystem: ProjectFilesystem, path: RepositoryPath) -> bytes | None:
    try:
        return filesystem.read_bytes(path)
    except FileNotFoundError:
        return None


def _restore_file(
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
    payload: bytes | None,
) -> None:
    if payload is None:
        filesystem.remove_file(path)
    else:
        filesystem.write_bytes(path, payload)


def _restore_file_if_unchanged(
    filesystem: ProjectFilesystem,
    path: RepositoryPath,
    expected_current: bytes | None,
    prior_payload: bytes | None,
) -> None:
    """Restore only when no other writer changed the file after our write."""
    current = _read_optional_bytes(filesystem, path)
    if current != expected_current:
        raise AssetRegistryRollbackError(
            f"cannot safely roll back {path}; another writer changed it"
        )
    _restore_file(filesystem, path, prior_payload)
