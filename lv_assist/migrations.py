"""Schema versioning for the LV Panel Assistant SQLite database.

PRAGMA user_version is the single source of schema version truth. Each
migration runs in its own transaction, and a pending migration is backed up
before it starts.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable

MigrationFn = Callable[[sqlite3.Connection], None]


def _migration_1_baseline(conn: sqlite3.Connection) -> None:
    """Verify the baseline schema without changing tables or data."""
    required_tables = {
        "catalog_devices",
        "device_breaking_capacities",
        "device_prices",
        "device_thermal_derating",
        "selectivity_rules",
        "trip_curves",
        "standards_registry",
        "cable_ampacity_reference",
        "pe_standard_sections",
        "metadata_info",
        "datasheet_sources",
    }
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    missing = required_tables - existing
    if missing:
        raise RuntimeError(
            f"Baseline incompatible: missing tables {sorted(missing)}. "
            "Run: python migrate_to_sqlite.py --rebuild-from-json"
        )


def _migration_2_source_column(conn: sqlite3.Connection) -> None:
    """Add provenance tracking to breaking-capacity rows."""
    columns = [
        row[1]
        for row in conn.execute("PRAGMA table_info(device_breaking_capacities)")
    ]
    if "source" not in columns:
        conn.execute(
            "ALTER TABLE device_breaking_capacities "
            "ADD COLUMN source TEXT NOT NULL DEFAULT 'UNKNOWN_LEGACY'"
        )
    conn.execute(
        "UPDATE device_breaking_capacities "
        "SET source = 'UNKNOWN_LEGACY' WHERE source IS NULL"
    )


MIGRATIONS: list[tuple[int, str, MigrationFn]] = [
    (1, "baseline", _migration_1_baseline),
    (2, "source_column", _migration_2_source_column),
]
CURRENT_VERSION = MIGRATIONS[-1][0] if MIGRATIONS else 0


def get_user_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise ValueError(f"Invalid version: {version}")
    conn.execute(f"PRAGMA user_version = {version}")


def _cleanup_old_backups(db_path: Path, keep: int = 3) -> None:
    pattern = f"{db_path.name}.backup-v*"
    backups = sorted(
        db_path.parent.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[keep:]:
        try:
            old_backup.unlink()
        except OSError:
            pass


def backup_database(db_path: Path, version: int) -> Path:
    """Copy the database before a pending migration and retain three copies."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    backup_path = db_path.with_name(
        f"{db_path.name}.backup-v{version}-{timestamp}"
    )
    shutil.copy2(db_path, backup_path)
    _cleanup_old_backups(db_path, keep=3)
    return backup_path


def run_migrations(db_path: Path) -> None:
    """Apply pending migrations transactionally, creating a backup first."""
    db_path = Path(db_path)
    database_existed = db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        current = get_user_version(conn)
        if current > CURRENT_VERSION:
            raise RuntimeError(
                f"Database schema version {current} is newer than code version "
                f"{CURRENT_VERSION}. Please upgrade the application."
            )
        pending = [
            (version, name, migration)
            for version, name, migration in MIGRATIONS
            if version > current
        ]
        if not pending:
            return

        if database_existed:
            try:
                backup_database(db_path, current)
            except Exception as exc:
                raise RuntimeError(
                    f"Backup failed, migration aborted: {exc}"
                ) from exc

        for version, _name, migration in pending:
            conn.execute("BEGIN")
            try:
                migration(conn)
                set_user_version(conn, version)
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
