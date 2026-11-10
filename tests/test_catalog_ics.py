import shutil
import sqlite3
from pathlib import Path

import pytest

from lv_assist.catalog import CatalogRepository
from lv_assist.models import CatalogDevice, DataQuality


@pytest.fixture
def repo(tmp_path):
    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db_path = tmp_path / "catalog.db"
    shutil.copy2(seed, db_path)
    return CatalogRepository(db_path=db_path)


def _device(part_number):
    return CatalogDevice(
        part_number=part_number,
        manufacturer="TESTCO",
        series="TEST",
        device_type="MCCB",
        rated_current_in_a=100.0,
        icu_ka_400v=36.0,
        data_quality=DataQuality.ESTIMATED,
    )


def _ics_rows(repo, part_number):
    with sqlite3.connect(repo.db_path) as conn:
        return conn.execute(
            "SELECT voltage_v, ics_ka FROM device_breaking_capacities "
            "WHERE device_id=? ORDER BY voltage_v",
            (part_number,),
        ).fetchall()


def test_add_device_without_ics_stores_null(repo):
    repo.add_device(_device("TEST-ADD-ICS"))
    assert _ics_rows(repo, "TEST-ADD-ICS") == [(400.0, None)]

def test_update_device_without_ics_stores_null(repo):
    part_number = "TEST-UPDATE-ICS"
    repo.add_device(_device(part_number))
    device = repo.get_device_payload(part_number)
    device.rated_current_in_a = 125.0
    repo.update_device(part_number, device)
    assert _ics_rows(repo, part_number) == [(400.0, None)]


def test_update_device_without_icu_preserves_existing_capacity(tmp_path):
    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db_path = tmp_path / "catalog.db"
    shutil.copy2(seed, db_path)
    repo = CatalogRepository(db_path=db_path)
    device = CatalogDevice(
        part_number="TEST-UPD-PRESERVE",
        manufacturer="TEST", series="TEST", device_type="MCCB",
        rated_current_in_a=100.0, icu_ka_400v=36.0, ics_ka_400v=25.0,
        data_quality=DataQuality.ESTIMATED,
    )
    repo.add_device(device)
    payload = repo.get_device_payload("TEST-UPD-PRESERVE")
    payload.rated_current_in_a = 125.0
    payload.icu_ka_400v = None
    payload.ics_ka_400v = None
    repo.update_device("TEST-UPD-PRESERVE", payload)
    with sqlite3.connect(repo.db_path) as conn:
        rows = conn.execute(
            "SELECT voltage_v, icu_ka, ics_ka FROM device_breaking_capacities "
            "WHERE device_id=? ORDER BY voltage_v",
            ("TEST-UPD-PRESERVE",),
        ).fetchall()
    assert rows == [(400.0, 36.0, 25.0)]


def test_update_device_with_icu_removes_stale_415(tmp_path):
    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db_path = tmp_path / "catalog.db"
    shutil.copy2(seed, db_path)
    repo = CatalogRepository(db_path=db_path)
    device = CatalogDevice(
        part_number="TEST-UPD-CLEAN-415",
        manufacturer="TEST", series="TEST", device_type="MCCB",
        rated_current_in_a=100.0, icu_ka_400v=36.0,
        data_quality=DataQuality.ESTIMATED,
    )
    repo.add_device(device)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO device_breaking_capacities (device_id, voltage_v, icu_ka, ics_ka) "
            "VALUES (?, 415.0, ?, NULL)",
            ("TEST-UPD-CLEAN-415", 36.0),
        )
    payload = repo.get_device_payload("TEST-UPD-CLEAN-415")
    payload.icu_ka_400v = 36.0
    repo.update_device("TEST-UPD-CLEAN-415", payload)
    with sqlite3.connect(repo.db_path) as conn:
        rows = conn.execute(
            "SELECT voltage_v FROM device_breaking_capacities "
            "WHERE device_id=? ORDER BY voltage_v",
            ("TEST-UPD-CLEAN-415",),
        ).fetchall()
    assert rows == [(400.0,)]
