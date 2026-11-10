import shutil
from pathlib import Path

import pytest

import lv_assist.catalog as catalog_module
from lv_assist.catalog import CatalogRepository
from lv_assist.catalog_smart_search import open_smart_search
from lv_assist.engine import EngineeringEngine
from lv_assist.models import CatalogDevice, DataQuality


@pytest.fixture
def repositories(tmp_path, monkeypatch):
    seed = Path(__file__).resolve().parents[1] / "lv_assist" / "data" / "lv_assist.db"
    db_path = tmp_path / "catalog.db"
    shutil.copy2(seed, db_path)
    singleton = CatalogRepository(db_path=db_path)
    monkeypatch.setattr(catalog_module, "catalog_repo", singleton)
    writer = CatalogRepository(db_path=db_path)
    return singleton, writer, db_path


def _device(part_number="CACHE-TEST", rated_current_in_a=100.0):
    return CatalogDevice(
        part_number=part_number,
        manufacturer="TESTCO",
        series="CACHE-TEST",
        device_type="MCCB",
        rated_current_in_a=rated_current_in_a,
        icu_ka_400v=36.0,
        data_quality=DataQuality.ESTIMATED,
    )


def test_add_device_invalidates_module_singleton(repositories):
    singleton, writer, _ = repositories
    assert all(d.part_number != "CACHE-ADD" for d in singleton.devices)

    writer.add_device(_device("CACHE-ADD"))

    assert any(d.part_number == "CACHE-ADD" for d in singleton.devices)


def test_update_device_invalidates_module_singleton(repositories):
    singleton, writer, _ = repositories
    singleton.add_device(_device("CACHE-UPDATE"))
    assert next(d for d in singleton.devices if d.part_number == "CACHE-UPDATE").rated_current_in_a == 100.0

    payload = writer.get_device_payload("CACHE-UPDATE")
    payload.rated_current_in_a = 125.0
    writer.update_device("CACHE-UPDATE", payload)

    assert next(d for d in singleton.devices if d.part_number == "CACHE-UPDATE").rated_current_in_a == 125.0


def test_delete_device_invalidates_module_singleton(repositories):
    singleton, writer, _ = repositories
    singleton.add_device(_device("CACHE-DELETE"))
    assert any(d.part_number == "CACHE-DELETE" for d in singleton.devices)

    writer.delete_device("CACHE-DELETE")

    assert all(d.part_number != "CACHE-DELETE" for d in singleton.devices)


def test_engine_sees_added_device_after_singleton_reload(repositories):
    singleton, writer, _ = repositories
    _ = singleton.devices

    writer.add_device(_device("CACHE-ENGINE"))
    engine = EngineeringEngine(list(singleton.devices))

    assert any(d.part_number == "CACHE-ENGINE" for d in engine.catalog)


def test_catalog_search_sees_added_device(repositories):
    _, writer, db_path = repositories
    search = open_smart_search(str(db_path))

    writer.add_device(_device("CACHE-SEARCH"))

    results = search.search("CACHE-SEARCH")
    assert any(row["device_id"] == "CACHE-SEARCH" for rows in results.values() for row in rows)
