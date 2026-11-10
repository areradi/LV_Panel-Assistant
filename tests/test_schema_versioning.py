import shutil
import sqlite3
from pathlib import Path

import pytest

from lv_assist.migrations import (
    CURRENT_VERSION,
    backup_database,
    get_user_version,
    run_migrations,
)


def _create_empty_db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    conn.close()
    return path


def _create_baseline_compatible_db(path: Path) -> Path:
    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    shutil.copy2(seed, path)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    return path


def test_fresh_db_gets_current_version(tmp_path):
    db = _create_baseline_compatible_db(tmp_path / "test.db")
    run_migrations(db)
    conn = sqlite3.connect(str(db))
    try:
        assert get_user_version(conn) == CURRENT_VERSION
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path):
    db = _create_baseline_compatible_db(tmp_path / "test.db")
    run_migrations(db)
    run_migrations(db)
    conn = sqlite3.connect(str(db))
    try:
        assert get_user_version(conn) == CURRENT_VERSION
    finally:
        conn.close()


def test_migration_creates_backup_when_pending(tmp_path):
    db = _create_baseline_compatible_db(tmp_path / "test.db")
    run_migrations(db)
    assert len(list(tmp_path.glob("test.db.backup-v*"))) == 1


def test_no_backup_when_already_current(tmp_path):
    db = _create_baseline_compatible_db(tmp_path / "test.db")
    run_migrations(db)
    before = list(tmp_path.glob("test.db.backup-v*"))
    run_migrations(db)
    after = list(tmp_path.glob("test.db.backup-v*"))
    assert len(before) == len(after)


def test_incompatible_db_raises_clear_error(tmp_path):
    db = _create_empty_db(tmp_path / "incompat.db")
    with pytest.raises(RuntimeError, match="Baseline incompatible"):
        run_migrations(db)
    conn = sqlite3.connect(str(db))
    try:
        assert get_user_version(conn) == 0
    finally:
        conn.close()


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    from lv_assist import migrations

    db = _create_baseline_compatible_db(tmp_path / "test.db")

    def failing_migration(conn):
        conn.execute("CREATE TABLE _test_canary (x INTEGER)")
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(migrations, "MIGRATIONS", [
        (1, "baseline", migrations._migration_1_baseline),
        (2, "failing", failing_migration),
    ])
    monkeypatch.setattr(migrations, "CURRENT_VERSION", 2)

    with pytest.raises(RuntimeError, match="simulated failure"):
        run_migrations(db)

    conn = sqlite3.connect(str(db))
    try:
        assert get_user_version(conn) == 1
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "_test_canary" not in tables
    finally:
        conn.close()


def test_backup_retention_keeps_three(tmp_path):
    db = _create_baseline_compatible_db(tmp_path / "test.db")
    for i in range(5):
        (tmp_path / f"test.db.backup-v0-2026010{i + 1}-0000").write_bytes(b"fake")
    backup_database(db, 0)
    assert len(list(tmp_path.glob("test.db.backup-v*"))) <= 3


def test_catalog_ensure_database_runs_pending_migrations(tmp_path, monkeypatch):
    from lv_assist import paths

    # Keep CatalogRepository's module-level singleton on a temporary database.
    data_dir = tmp_path / "catalog_data"
    data_dir.mkdir()
    _create_baseline_compatible_db(data_dir / "lv_assist.db")
    monkeypatch.setattr(paths, "get_data_dir", lambda: data_dir)
    from lv_assist.catalog import _ensure_database

    db = _create_baseline_compatible_db(tmp_path / "catalog.db")
    _ensure_database(db)
    conn = sqlite3.connect(str(db))
    try:
        assert get_user_version(conn) == CURRENT_VERSION
    finally:
        conn.close()
