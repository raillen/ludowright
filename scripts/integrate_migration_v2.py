"""Temporarily integrate StateStore schema v2 before the migration PR merge."""

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
    raise SystemExit(f"integration marker not found: {label}")


def integrate_state_store() -> None:
    path = "src/ludowright/infrastructure/state_store.py"
    text = read(path)
    text = replace_once(
        text,
        "_STATE_SCHEMA_VERSION = 1",
        "STATE_SCHEMA_VERSION = 2",
        "state schema version",
    )
    text = text.replace("_STATE_SCHEMA_VERSION", "STATE_SCHEMA_VERSION")
    text = replace_once(
        text,
        '        expected = {"event_checkpoint", "indexed_entity", "workflow_progress"}\n',
        "        expected = {\n"
        '            "event_checkpoint",\n'
        '            "indexed_entity",\n'
        '            "migration_history",\n'
        '            "workflow_progress",\n'
        "        }\n",
        "state schema expected tables",
    )

    if "CREATE TABLE migration_history" not in text:
        marker = "\n)\n\n\ndef _workflow_from_row"
        table = (
            "\n"
            '    """\n'
            "    CREATE TABLE migration_history (\n"
            "        migration_id TEXT PRIMARY KEY,\n"
            "        run_id TEXT NOT NULL,\n"
            "        source_version INTEGER NOT NULL CHECK(source_version >= 1),\n"
            "        target_version INTEGER NOT NULL CHECK(target_version = source_version + 1),\n"
            "        applied_at TEXT NOT NULL,\n"
            "        tool_version TEXT NOT NULL\n"
            "    ) STRICT, WITHOUT ROWID\n"
            '    """,'
        )
        if marker not in text:
            raise SystemExit("integration marker not found: state schema tuple")
        text = text.replace(marker, f"{table}{marker}", 1)
    write(path, text)


def integrate_public_exports() -> None:
    path = "src/ludowright/infrastructure/__init__.py"
    text = read(path)
    text = replace_once(
        text,
        "from ludowright.infrastructure.state_store import (\n"
        "    DEFAULT_STATE_STORE_PATH,\n",
        "from ludowright.infrastructure.state_store import (\n"
        "    DEFAULT_STATE_STORE_PATH,\n"
        "    STATE_SCHEMA_VERSION,\n",
        "state schema import",
    )
    text = replace_once(
        text,
        '    "STATE_MIGRATIONS",\n',
        '    "STATE_MIGRATIONS",\n    "STATE_SCHEMA_VERSION",\n',
        "state schema export",
    )
    write(path, text)


def integrate_migration_connections() -> None:
    path = "src/ludowright/infrastructure/migrations.py"
    text = read(path)
    text = replace_once(
        text,
        "from collections.abc import Callable\n",
        "from collections.abc import Callable, Iterator\n",
        "migration iterator import",
    )
    text = replace_once(
        text,
        "from dataclasses import dataclass\n",
        "from contextlib import contextmanager\nfrom dataclasses import dataclass\n",
        "migration contextmanager import",
    )
    text = text.replace("import tempfile\n", "")
    text = replace_once(
        text,
        "from ludowright.infrastructure.state_store import DEFAULT_STATE_STORE_PATH\n",
        "from ludowright.infrastructure.state_store import (\n"
        "    DEFAULT_STATE_STORE_PATH,\n"
        "    STATE_SCHEMA_VERSION,\n"
        ")\n",
        "migration state-store imports",
    )
    text = replace_once(
        text,
        "TARGET_STATE_SCHEMA_VERSION = 2",
        "TARGET_STATE_SCHEMA_VERSION = STATE_SCHEMA_VERSION",
        "migration target schema version",
    )

    old_start = "    def _connect(self, database: Path, *, readonly: bool) -> sqlite3.Connection:\n"
    new_start = "    @contextmanager\n    def _connect(\n"
    if old_start in text:
        start = text.index(old_start)
        end_marker = "\n    def _assert_safe_database_files"
        end = text.index(end_marker, start)
        new_method = (
            "    @contextmanager\n"
            "    def _connect(\n"
            "        self,\n"
            "        database: Path,\n"
            "        *,\n"
            "        readonly: bool,\n"
            "    ) -> Iterator[sqlite3.Connection]:\n"
            "        if readonly:\n"
            "            uri = f\"{database.resolve().as_uri()}?mode=ro\"\n"
            "            connection = sqlite3.connect(\n"
            "                uri,\n"
            "                uri=True,\n"
            "                timeout=self._busy_timeout_ms / 1000,\n"
            "                isolation_level=None,\n"
            "            )\n"
            "        else:\n"
            "            connection = sqlite3.connect(\n"
            "                database,\n"
            "                timeout=self._busy_timeout_ms / 1000,\n"
            "                isolation_level=None,\n"
            "            )\n"
            "        try:\n"
            "            connection.execute(f\"PRAGMA busy_timeout = {self._busy_timeout_ms}\")\n"
            "            connection.execute(\"PRAGMA foreign_keys = ON\")\n"
            "            connection.execute(\"PRAGMA trusted_schema = OFF\")\n"
            "            if not readonly:\n"
            "                connection.execute(\"PRAGMA synchronous = FULL\")\n"
            "            yield connection\n"
            "        finally:\n"
            "            connection.close()\n"
        )
        text = text[:start] + new_method + text[end:]
    elif new_start not in text:
        raise SystemExit("integration marker not found: migration connection method")
    write(path, text)


def integrate_tests() -> None:
    path = "tests/test_state_store.py"
    text = read(path)
    text = replace_once(
        text,
        "assert state.schema_version == 1",
        "assert state.schema_version == 2",
        "state-store schema assertion",
    )
    text = replace_once(
        text,
        'assert connection.execute("PRAGMA user_version").fetchone()[0] == 1',
        'assert connection.execute("PRAGMA user_version").fetchone()[0] == 2',
        "state-store pragma assertion",
    )
    text = replace_once(
        text,
        '            "indexed_entity",\n            "workflow_progress",\n',
        '            "indexed_entity",\n'
        '            "migration_history",\n'
        '            "workflow_progress",\n',
        "state-store expected tables assertion",
    )
    write(path, text)

    path = "tests/test_migrations.py"
    text = read(path)
    text = replace_once(
        text,
        "from concurrent.futures import ThreadPoolExecutor\nfrom pathlib import Path\n",
        "from concurrent.futures import ThreadPoolExecutor\n"
        "from datetime import UTC, datetime\n"
        "from pathlib import Path\n",
        "migration datetime imports",
    )
    text = replace_once(
        text,
        "    UnsupportedStateSchemaError,\n",
        "    UnsupportedStateSchemaError,\n    UnsafeProjectPathError,\n",
        "migration unsafe-path import",
    )
    text = replace_once(
        text,
        '    with pytest.raises(Exception, match="symlink"):\n',
        '    with pytest.raises(UnsafeProjectPathError, match="symlink"):\n',
        "migration symlink exception",
    )
    helper_start = "def datetime_from_text(value: str):\n"
    new_helper = (
        "def datetime_from_text(value: str) -> datetime:\n"
        "    return datetime.strptime(value, \"%Y-%m-%dT%H:%M:%S.%fZ\").replace(\n"
        "        tzinfo=UTC\n"
        "    )\n"
    )
    if helper_start in text:
        start = text.index(helper_start)
        text = text[:start] + new_helper
    elif "def datetime_from_text(value: str) -> datetime:" not in text:
        raise SystemExit("integration marker not found: migration datetime helper")
    write(path, text)


def integrate_documentation() -> None:
    path = "docs/contracts/STATE_STORE.md"
    text = read(path)
    text = replace_once(
        text,
        "The initial database uses:\n\n```text\nPRAGMA user_version = 1\n```",
        "The current database uses:\n\n```text\nPRAGMA user_version = 2\n```\n\n"
        "Fresh databases are created at v2. Existing v1 databases require the explicit "
        "migration framework documented in [`MIGRATIONS.md`](MIGRATIONS.md).",
        "state-store version documentation",
    )
    text = replace_once(
        text,
        "A new empty database is initialized as version 1. A database with another non-zero "
        "version is rejected with `UnsupportedStateSchemaError`.",
        "A new empty database is initialized as version 2. A v1 database is rejected until "
        "the explicit v1→v2 migration is applied. Other non-zero versions are rejected with "
        "`UnsupportedStateSchemaError`.",
        "state-store migration requirement documentation",
    )
    text = replace_once(
        text,
        "Schema migration is deliberately deferred to the next implementation PR. The state "
        "store must not guess how to upgrade an unknown version.",
        "Schema migration is explicit and backed up. The state store must not guess how to "
        "upgrade an unknown version.",
        "state-store migration policy documentation",
    )
    if "### `migration_history`" not in text:
        marker = "### `event_checkpoint`\n"
        section = (
            "### `migration_history`\n\n"
            "Stores one immutable row per applied state-schema migration:\n\n"
            "- migration ID;\n"
            "- run ID;\n"
            "- source and target versions;\n"
            "- canonical UTC timestamp;\n"
            "- LudoWright tool version.\n\n"
            "The external rollback receipt remains authoritative for backup restoration because "
            "rolling back to v1 removes this v2-only table.\n\n"
        )
        if marker not in text:
            raise SystemExit("integration marker not found: state-store migration table docs")
        text = text.replace(marker, section + marker, 1)
    text = text.replace("- schema migrations;\n", "- canonical-file migrations;\n", 1)
    write(path, text)

    path = "docs/contracts/JSON_SCHEMAS.md"
    text = read(path)
    text = replace_once(
        text,
        "| Capture profile | `capture-profile.schema.json` |\n",
        "| Capture profile | `capture-profile.schema.json` |\n"
        "| Migration receipt | `migration-receipt.schema.json` |\n",
        "migration receipt schema documentation",
    )
    write(path, text)

    path = "mkdocs.yml"
    text = read(path)
    text = replace_once(
        text,
        "      - SQLite State Store: contracts/STATE_STORE.md\n",
        "      - SQLite State Store: contracts/STATE_STORE.md\n"
        "      - Migrations: contracts/MIGRATIONS.md\n",
        "migration contract navigation",
    )
    text = replace_once(
        text,
        "      - ADR 0011 — Rebuildable SQLite State Index: "
        "decisions/0011-rebuildable-sqlite-state-index.md\n",
        "      - ADR 0011 — Rebuildable SQLite State Index: "
        "decisions/0011-rebuildable-sqlite-state-index.md\n"
        "      - ADR 0012 — Explicit Backed-Up Migrations: "
        "decisions/0012-explicit-backed-up-schema-migrations.md\n",
        "migration ADR navigation",
    )
    write(path, text)

    path = "docs/ATLAS.md"
    text = read(path)
    text = replace_once(
        text,
        "- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — rebuildable SQLite workflow "
        "state, entity indexes, event checkpoints, transactions, and canonical-source consistency.\n",
        "- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — rebuildable SQLite workflow "
        "state, entity indexes, event checkpoints, transactions, and canonical-source consistency.\n"
        "- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — contiguous plans, dry runs, "
        "consistent backups, receipts, transactional apply, and guarded rollback.\n",
        "migration contract atlas entry",
    )
    text = replace_once(
        text,
        "- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — WAL, strict tables, rollback, "
        "concurrency, checkpoint, source-digest, corruption, and rebuild tests.\n",
        "- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — WAL, strict tables, rollback, "
        "concurrency, checkpoint, source-digest, corruption, and rebuild tests.\n"
        "- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — catalog, dry-run, backup, "
        "failure rollback, explicit restore, tampering, and concurrency tests.\n",
        "migration quality atlas entry",
    )
    text = replace_once(
        text,
        "- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — SQLite sidecar safety, "
        "parameterized operations, strict schemas, short transactions, and corruption isolation.\n",
        "- [`contracts/STATE_STORE.md`](contracts/STATE_STORE.md) — SQLite sidecar safety, "
        "parameterized operations, strict schemas, short transactions, and corruption isolation.\n"
        "- [`contracts/MIGRATIONS.md`](contracts/MIGRATIONS.md) — trusted migration code, durable "
        "backups, strict receipts, digest-guarded rollback, and fail-closed versions.\n",
        "migration security atlas entry",
    )
    text = replace_once(
        text,
        "## Decisions\n\n",
        "## Decisions\n\n"
        "- [`decisions/0012-explicit-backed-up-schema-migrations.md`]"
        "(decisions/0012-explicit-backed-up-schema-migrations.md) — accepted explicit contiguous "
        "migration plans, dry runs, durable SQLite backups, strict receipts, transactional apply, "
        "and guarded rollback.\n",
        "migration ADR atlas entry",
    )
    write(path, text)


if __name__ == "__main__":
    integrate_state_store()
    integrate_public_exports()
    integrate_migration_connections()
    integrate_tests()
    integrate_documentation()
