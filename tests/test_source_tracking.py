import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from lv_assist.migrations import CURRENT_VERSION, get_user_version, run_migrations


@pytest.fixture
def baseline_db(tmp_path):
    """Baseline-compatible DB at version 1, before source migration 2."""
    from lv_assist.catalog import _ensure_database

    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db = tmp_path / "baseline.db"
    shutil.copy2(seed, db)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    return db


def test_migration_2_adds_source_column(baseline_db):
    run_migrations(baseline_db)
    conn = sqlite3.connect(str(baseline_db))
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(device_breaking_capacities)")]
        assert "source" in cols
        assert get_user_version(conn) == 2
    finally:
        conn.close()


def test_migration_2_backfills_unknown_legacy(baseline_db):
    run_migrations(baseline_db)
    conn = sqlite3.connect(str(baseline_db))
    try:
        null_count = conn.execute(
            "SELECT COUNT(*) FROM device_breaking_capacities WHERE source IS NULL"
        ).fetchone()[0]
        unknown_count = conn.execute(
            "SELECT COUNT(*) FROM device_breaking_capacities WHERE source = 'UNKNOWN_LEGACY'"
        ).fetchone()[0]
        assert null_count == 0
        assert unknown_count > 0
    finally:
        conn.close()


def test_migration_2_idempotent(baseline_db):
    run_migrations(baseline_db)
    run_migrations(baseline_db)
    conn = sqlite3.connect(str(baseline_db))
    try:
        assert get_user_version(conn) == 2
        cols = [row[1] for row in conn.execute("PRAGMA table_info(device_breaking_capacities)")]
        assert cols.count("source") == 1
    finally:
        conn.close()


def test_seed_json_writes_seed_json_source(tmp_path):
    from migrate_to_sqlite import SCHEMA_SQL, migrate_catalog_devices

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    device = {
        "part_number": "TEST-SEED",
        "manufacturer": "TEST",
        "series": "TEST",
        "device_type": "MCCB",
        "rated_current_in_a": 100.0,
        "icu_ka_400v": 36.0,
    }
    (data_dir / "catalog_devices.json").write_text(
        json.dumps({"devices": [device]}), encoding="utf-8"
    )
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA_SQL)
        migrate_catalog_devices(conn, data_dir)
        rows = conn.execute(
            "SELECT source FROM device_breaking_capacities WHERE device_id = 'TEST-SEED'"
        ).fetchall()
        assert rows == [("SEED_JSON",)]
    finally:
        conn.close()


def test_user_input_writes_user_input_source(tmp_path):
    from lv_assist.catalog import CatalogRepository
    from lv_assist.models import CatalogDevice, DataQuality

    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db = tmp_path / "catalog.db"
    shutil.copy2(seed, db)
    repo = CatalogRepository(db_path=db)
    repo.add_device(CatalogDevice(
        part_number="TEST-USER",
        manufacturer="TEST", series="TEST", device_type="MCCB",
        rated_current_in_a=100.0, icu_ka_400v=36.0,
        data_quality=DataQuality.ESTIMATED,
    ))
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT source FROM device_breaking_capacities WHERE device_id = 'TEST-USER'"
        ).fetchall()
    assert rows == [("USER_INPUT",)]


def test_update_device_writes_user_input_source(tmp_path):
    from lv_assist.catalog import CatalogRepository
    from lv_assist.models import CatalogDevice, DataQuality

    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db = tmp_path / "catalog-update.db"
    shutil.copy2(seed, db)
    repo = CatalogRepository(db_path=db)
    device = CatalogDevice(
        part_number="TEST-USER-UPDATE",
        manufacturer="TEST", series="TEST", device_type="MCCB",
        rated_current_in_a=100.0, icu_ka_400v=36.0,
        data_quality=DataQuality.ESTIMATED,
    )
    repo.add_device(device)
    payload = repo.get_device_payload("TEST-USER-UPDATE")
    payload.rated_current_in_a = 125.0
    repo.update_device("TEST-USER-UPDATE", payload)
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT source FROM device_breaking_capacities "
            "WHERE device_id = 'TEST-USER-UPDATE'"
        ).fetchall()
    assert rows == [("USER_INPUT",)]


def test_fail_closed_on_newer_db_version(tmp_path):
    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db = tmp_path / "future.db"
    shutil.copy2(seed, db)
    conn = sqlite3.connect(str(db))
    conn.execute(f"PRAGMA user_version = {CURRENT_VERSION + 10}")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="newer than code version"):
        run_migrations(db)


def test_schema_sql_includes_source_column():
    from migrate_to_sqlite import SCHEMA_SQL

    assert "source TEXT NOT NULL DEFAULT 'UNKNOWN_LEGACY'" in SCHEMA_SQL
    assert "source" in SCHEMA_SQL
