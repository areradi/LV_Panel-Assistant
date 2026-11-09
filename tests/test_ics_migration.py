import json
import sqlite3

from migrate_to_sqlite import SCHEMA_SQL, migrate_catalog_devices


def _migrate(tmp_path, device):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "catalog_devices.json").write_text(
        json.dumps({"devices": [device]}), encoding="utf-8"
    )
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    migrate_catalog_devices(conn, data_dir)
    rows = conn.execute(
        "SELECT voltage_v, ics_ka FROM device_breaking_capacities ORDER BY voltage_v"
    ).fetchall()
    conn.close()
    return rows


def _device(**extra):
    device = {
        "part_number": "TEST-ICS",
        "manufacturer": "TEST",
        "series": "TEST",
        "device_type": "MCCB",
        "rated_current_in_a": 100.0,
        "icu_ka_400v": 36.0,
    }
    device.update(extra)
    return device


def test_migration_without_ics_preserves_unknown_as_null(tmp_path):
    rows = _migrate(tmp_path, _device())
    assert rows == [(400.0, None), (415.0, None)]

def test_migration_icu_by_voltage_without_ics_preserves_unknown_as_null(tmp_path):
    device = _device()
    device.pop("icu_ka_400v")
    device["icu_by_voltage"] = {"400": 36.0, "415": 25.0}
    rows = _migrate(tmp_path, device)
    assert rows == [(400.0, None), (415.0, None)]

def test_migration_preserves_explicit_zero_ics(tmp_path):
    rows = _migrate(tmp_path, _device(ics_ka_400v=0))
    assert rows == [(400.0, 0.0), (415.0, 0.0)]

def test_migration_preserves_explicit_ics_value(tmp_path):
    rows = _migrate(tmp_path, _device(ics_ka_400v=25.5))
    assert rows == [(400.0, 25.5), (415.0, 25.5)]

def test_migration_treats_empty_string_ics_as_unknown(tmp_path):
    rows = _migrate(tmp_path, _device(ics_ka_400v=""))
    assert rows == [(400.0, None), (415.0, None)]