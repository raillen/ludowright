"""Apply reviewed migration safety fixes before final validation."""

from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f"safety patch marker not found: {label}")


def replace_between(text: str, start: str, end: str, new: str, label: str) -> str:
    if new in text:
        return text
    try:
        start_index = text.index(start)
        end_index = text.index(end, start_index)
    except ValueError as error:
        raise SystemExit(f"safety patch marker not found: {label}") from error
    return text[:start_index] + new + text[end_index:]


def patch_state_store() -> None:
    path = "src/ludowright/infrastructure/state_store.py"
    text = read(path)
    text = replace_once(
        text,
        '_STATE_STORE_LOCK = "sqlite-state-store-init"\n',
        '_STATE_STORE_LOCK = "sqlite-state-store-init"\n'
        'STATE_STORE_WRITE_LOCK = "sqlite-state-store-write"\n',
        "state write lock constant",
    )
    transaction = '''    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        if write:
            with self._filesystem.lock(
                STATE_STORE_WRITE_LOCK,
                timeout=self._busy_timeout_ms / 1000,
            ):
                with self._database_transaction(write=True) as connection:
                    yield connection
            return
        with self._database_transaction(write=False) as connection:
            yield connection

    @contextmanager
    def _database_transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        self._assert_safe_database_files()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if not write:
                    connection.execute("PRAGMA query_only = ON")
                try:
                    yield connection
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except sqlite3.DatabaseError as error:
            raise StateStoreCorruptionError("SQLite state operation failed") from error
        finally:
            self._assert_safe_database_files()

'''
    text = replace_between(
        text,
        "    @contextmanager\n    def _transaction(",
        "    @contextmanager\n    def _connect(",
        transaction,
        "state transaction boundary",
    )
    write(path, text)


def patch_migration_manager() -> None:
    path = "src/ludowright/infrastructure/migrations.py"
    text = read(path)
    text = replace_once(
        text,
        "from ludowright.infrastructure.state_store import (\n"
        "    DEFAULT_STATE_STORE_PATH,\n"
        "    STATE_SCHEMA_VERSION,\n"
        ")\n",
        "from ludowright.infrastructure.state_store import (\n"
        "    DEFAULT_STATE_STORE_PATH,\n"
        "    STATE_SCHEMA_VERSION,\n"
        "    STATE_STORE_WRITE_LOCK,\n"
        ")\n",
        "migration shared lock import",
    )

    methods = '''    def apply(
        self,
        *,
        target_version: int = TARGET_STATE_SCHEMA_VERSION,
        timeout: float = 0.0,
    ) -> MigrationApplyResult:
        """Back up, apply, validate, and persist rollback metadata."""
        with self._filesystem.lock(_MIGRATION_LOCK, timeout=timeout):
            with self._filesystem.lock(STATE_STORE_WRITE_LOCK, timeout=timeout):
                return self._apply_locked(target_version=target_version)

    def _apply_locked(self, *, target_version: int) -> MigrationApplyResult:
        plan = self.plan(target_version=target_version)
        if not plan.requires_migration:
            return MigrationApplyResult(plan=plan, receipt=None)

        run_id = _new_run_id()
        run_directory = _BACKUP_ROOT.child(run_id)
        self._filesystem.ensure_directory(run_directory)
        backup_path = run_directory.child("state-before.sqlite3")
        receipt_path = run_directory.child("rollback.json")
        backup_absolute = self._filesystem.resolve(backup_path)

        self._create_consistent_copy(self._database_path, backup_absolute)
        before_digest = _sha256_file(backup_absolute)
        receipt_repository = JsonDocumentRepository(
            self._filesystem,
            receipt_path,
            MigrationReceiptContract,
            max_bytes=128_000,
        )
        prepared = MigrationReceiptContract(
            run_id=run_id,
            status=MigrationRunStatus.PREPARED,
            database_path=self._path.value,
            backup_path=backup_path.value,
            source_version=plan.source_version,
            target_version=plan.target_version,
            migration_ids=plan.migration_ids,
            started_at=_format_timestamp(datetime.now(UTC)),
            before_digest=before_digest,
            backup_digest=before_digest,
        )
        receipt_snapshot = receipt_repository.create(prepared)

        try:
            self._apply_plan(self._database_path, plan, run_id=run_id)
            after_digest = self._logical_digest(self._database_path)
        except BaseException as error:
            restore_error: BaseException | None = None
            try:
                self._restore_failed_apply(
                    backup_absolute,
                    source_version=plan.source_version,
                    before_digest=before_digest,
                )
            except BaseException as recovery_error:
                restore_error = recovery_error

            if restore_error is None:
                detail = f"{_safe_failure_text(error)}; database restored from backup"
            else:
                detail = (
                    f"{_safe_failure_text(error)}; automatic restore failed: "
                    f"{_safe_failure_text(restore_error)}"
                )
            failed = prepared.model_copy(
                update={
                    "status": MigrationRunStatus.FAILED,
                    "completed_at": _format_timestamp(datetime.now(UTC)),
                    "failure": _safe_failure_text(RuntimeError(detail)),
                }
            )
            receipt_repository.replace(receipt_snapshot, failed)

            if restore_error is not None:
                raise MigrationExecutionError(
                    f"state migration {run_id} failed and automatic restore failed; "
                    "backup retained"
                ) from error
            if isinstance(error, MigrationError):
                raise
            raise MigrationExecutionError(
                f"state migration {run_id} failed; database restored from backup"
            ) from error

        completed = prepared.model_copy(
            update={
                "status": MigrationRunStatus.COMPLETED,
                "completed_at": _format_timestamp(datetime.now(UTC)),
                "after_digest": after_digest,
            }
        )
        receipt_repository.replace(receipt_snapshot, completed)
        return MigrationApplyResult(plan=plan, receipt=completed)

    def rollback(self, run_id: str, *, timeout: float = 0.0) -> MigrationReceiptContract:
        """Restore one completed migration backup when the database is unchanged."""
        try:
            validate_slug(run_id)
        except (TypeError, ValueError) as error:
            raise MigrationRollbackError("migration run ID must be canonical") from error

        with self._filesystem.lock(_MIGRATION_LOCK, timeout=timeout):
            with self._filesystem.lock(STATE_STORE_WRITE_LOCK, timeout=timeout):
                return self._rollback_locked(run_id)

    def _rollback_locked(self, run_id: str) -> MigrationReceiptContract:
        run_directory = _BACKUP_ROOT.child(run_id)
        receipt_path = run_directory.child("rollback.json")
        receipt_repository = JsonDocumentRepository(
            self._filesystem,
            receipt_path,
            MigrationReceiptContract,
            max_bytes=128_000,
        )
        snapshot = receipt_repository.load()
        receipt = snapshot.value
        if receipt.status is not MigrationRunStatus.COMPLETED:
            raise MigrationRollbackError(f"migration {run_id} is not in completed state")
        if receipt.after_digest is None:
            raise MigrationRollbackError("completed receipt lacks post-migration digest")
        current_digest = self._logical_digest(self._database_path)
        if current_digest != receipt.after_digest:
            raise MigrationRollbackError(
                "state database changed after migration; rollback would destroy newer work"
            )

        backup_path = RepositoryPath(receipt.backup_path)
        backup_absolute = self._filesystem.resolve(backup_path)
        if _sha256_file(backup_absolute) != receipt.backup_digest:
            raise MigrationRollbackError("migration backup digest is invalid")

        pre_rollback = run_directory.child("state-before-rollback.sqlite3")
        pre_rollback_absolute = self._filesystem.resolve(pre_rollback)
        self._create_consistent_copy(self._database_path, pre_rollback_absolute)
        pre_rollback_digest = _sha256_file(pre_rollback_absolute)

        try:
            self._replace_database_from_backup(backup_absolute)
            restored_version = self.inspect_version()
            if restored_version != receipt.source_version:
                raise MigrationRollbackError(
                    "restored database version does not match migration source"
                )
            restored_digest = self._logical_digest(self._database_path)
            if restored_digest != receipt.before_digest:
                raise MigrationRollbackError(
                    "restored database content does not match migration backup"
                )
        except BaseException as error:
            self._replace_database_from_backup(pre_rollback_absolute)
            if isinstance(error, MigrationRollbackError):
                raise
            raise MigrationRollbackError(
                f"rollback of migration {run_id} failed; current database restored"
            ) from error

        rolled_back = receipt.model_copy(
            update={
                "status": MigrationRunStatus.ROLLED_BACK,
                "rolled_back_at": _format_timestamp(datetime.now(UTC)),
                "pre_rollback_digest": pre_rollback_digest,
            }
        )
        receipt_repository.replace(snapshot, rolled_back)
        return rolled_back

    def _restore_failed_apply(
        self,
        backup: Path,
        *,
        source_version: int,
        before_digest: str,
    ) -> None:
        self._replace_database_from_backup(backup)
        restored_version = self.inspect_version()
        if restored_version != source_version:
            raise MigrationExecutionError(
                "automatic restore produced an unexpected schema version"
            )
        restored_digest = self._logical_digest(self._database_path)
        if restored_digest != before_digest:
            raise MigrationExecutionError(
                "automatic restore does not match the pre-migration backup"
            )

'''
    text = replace_between(
        text,
        "    def apply(",
        "    def _apply_plan(",
        methods,
        "migration apply and rollback methods",
    )
    write(path, text)


def patch_tests() -> None:
    path = "tests/test_migrations.py"
    text = read(path)
    text = replace_once(
        text,
        "from pathlib import Path\n",
        "from pathlib import Path\nfrom threading import Event\n",
        "migration Event import",
    )
    text = replace_once(
        text,
        "def failing_migration(_connection: sqlite3.Connection) -> None:\n"
        "    _connection.execute(\"CREATE TABLE should_rollback (value TEXT) STRICT\")\n"
        "    raise RuntimeError(\"deliberate migration failure\")\n",
        "def failing_migration(_connection: sqlite3.Connection) -> None:\n"
        "    _connection.execute(\"CREATE TABLE should_rollback (value TEXT) STRICT\")\n"
        "    raise RuntimeError(\"deliberate migration failure\")\n\n\n"
        "def create_v3_marker(connection: sqlite3.Connection) -> None:\n"
        "    connection.execute(\"CREATE TABLE state_v3_marker (value TEXT) STRICT\")\n",
        "migration v3 test helper",
    )

    marker = "\ndef test_migration_receipt_contract_rejects_invalid_states() -> None:\n"
    tests = '''
def test_post_commit_validation_failure_restores_v1_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = create_v1_database(tmp_path)
    manager = StateMigrationManager(ProjectFilesystem(tmp_path))

    def fail_validation(_database: Path, _expected_version: int) -> None:
        raise MigrationExecutionError("post-commit validation failed")

    monkeypatch.setattr(manager, "_validate_target", fail_validation)

    with pytest.raises(MigrationExecutionError, match="post-commit validation failed"):
        manager.apply()

    assert database_version(database) == 1
    assert "migration_history" not in table_names(database)
    receipt = load_receipt(receipt_paths(tmp_path)[0])
    assert receipt.status is MigrationRunStatus.FAILED
    assert receipt.failure is not None
    assert "database restored from backup" in receipt.failure


def test_state_write_waits_until_migration_backup_window_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    state = StateStore(filesystem)
    catalog = MigrationCatalog(
        (
            MigrationStep(
                "state-v2-to-v3-test-marker",
                2,
                3,
                "add a test-only v3 marker",
                create_v3_marker,
            ),
        )
    )
    manager = StateMigrationManager(filesystem, catalog=catalog)
    backup_complete = Event()
    writer_started = Event()
    writer_finished = Event()
    original_copy = manager._create_consistent_copy

    def controlled_copy(source: Path, target: Path) -> None:
        original_copy(source, target)
        if target.name == "state-before.sqlite3":
            backup_complete.set()
            assert writer_started.wait(5.0)
            assert not writer_finished.wait(0.2)

    monkeypatch.setattr(manager, "_create_consistent_copy", controlled_copy)

    pending = WorkflowProgress(
        workflow_id="concurrent-write",
        workflow_type="migration-test",
        status="complete",
        current_step=None,
        context={"preserved": True},
        source_event_sequence=None,
        updated_at=datetime_from_text("2026-07-29T16:30:00.123456Z"),
    )

    def write_state() -> None:
        writer_started.set()
        state.save_workflow(pending)
        writer_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        migration_future = executor.submit(
            manager.apply,
            target_version=3,
            timeout=10.0,
        )
        assert backup_complete.wait(5.0)
        writer_future = executor.submit(write_state)
        migrated = migration_future.result(timeout=10.0)
        writer_future.result(timeout=10.0)

    assert migrated.applied is True
    assert writer_finished.is_set()
    assert state.get_workflow("concurrent-write") == pending
    assert database_version(tmp_path / ".ludowright/state.sqlite3") == 3
    assert migrated.receipt is not None
    with pytest.raises(MigrationRollbackError, match="changed after migration"):
        manager.rollback(migrated.receipt.run_id)

'''
    if "test_post_commit_validation_failure_restores_v1_backup" not in text:
        if marker not in text:
            raise SystemExit("safety patch marker not found: migration regression tests")
        text = text.replace(marker, tests + marker, 1)
    write(path, text)


def patch_documentation() -> None:
    path = "docs/contracts/STATE_STORE.md"
    text = read(path)
    text = replace_once(
        text,
        "Writes use:\n\n```text\nBEGIN IMMEDIATE\n```\n",
        "Writes acquire the shared `sqlite-state-store-write` project lock and then use:\n\n"
        "```text\nBEGIN IMMEDIATE\n```\n\n"
        "Migration apply and rollback operations acquire the same lock across backup, schema "
        "mutation, digest calculation, and database replacement. This prevents a StateStore "
        "write from falling between the rollback snapshot and the migrated state.\n",
        "state-store shared write lock documentation",
    )
    write(path, text)

    path = "docs/contracts/MIGRATIONS.md"
    text = read(path)
    marker = "## Failure behavior\n"
    paragraph = (
        "Migration apply shares the StateStore write lock from the pre-migration backup through "
        "post-commit validation and digest calculation. If any apply or validation step fails, "
        "LudoWright restores the verified backup before persisting the failed receipt. The receipt "
        "records whether automatic restoration succeeded; a restoration failure retains the durable "
        "backup and raises a distinct execution error.\n\n"
    )
    if paragraph not in text:
        if marker not in text:
            raise SystemExit("safety patch marker not found: migration failure documentation")
        text = text.replace(marker, marker + "\n" + paragraph, 1)
    write(path, text)

    path = "docs/decisions/0012-explicit-backed-up-schema-migrations.md"
    text = read(path)
    marker = "## Consequences\n"
    paragraph = (
        "- StateStore writes and migration apply/rollback share one project write lock, so the "
        "rollback snapshot and migrated state cannot straddle a normal indexed-state write.\n"
        "- A failure after SQLite commit triggers verified automatic restoration from the durable "
        "backup before the receipt becomes `failed`.\n"
    )
    if paragraph not in text:
        if marker not in text:
            raise SystemExit("safety patch marker not found: migration ADR consequences")
        text = text.replace(marker, marker + "\n" + paragraph, 1)
    write(path, text)


if __name__ == "__main__":
    patch_state_store()
    patch_migration_manager()
    patch_tests()
    patch_documentation()
