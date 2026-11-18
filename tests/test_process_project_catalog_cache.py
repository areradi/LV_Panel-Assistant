from contextlib import contextmanager

from lv_assist.catalog import CatalogRepository, catalog_repo
from lv_assist.engine import EngineeringEngine
from lv_assist.models import ProjectSpec


def test_project_cache_memoizes_catalog_lookups_and_clears(monkeypatch):
    device = next(
        item for item in CatalogRepository.get_default_catalog()
        if item.device_type == "MCCB"
    )
    real_connect = catalog_repo._connect
    connection_count = 0

    def counted_connect():
        nonlocal connection_count
        connection_count += 1
        return real_connect()

    monkeypatch.setattr(catalog_repo, "_connect", counted_connect)

    with catalog_repo._project_cache_scope() as cache:
        for _ in range(2):
            catalog_repo.get_device_icu_match_at_voltage(device.part_number, 400.0)
            catalog_repo.get_device_derating_factor(device.part_number, 50.0)
            catalog_repo.get_standard_pe_section(16.0)
            catalog_repo.get_cable_iz0_table_cu_pvc_c(3)

        assert connection_count == 4
        assert len(cache._icu_cache) == 1
        assert len(cache._derating_cache) == 1
        assert len(cache._pe_section_cache) == 1
        assert len(cache._iz0_cache) == 1

    assert not cache._icu_cache
    assert not cache._derating_cache
    assert not cache._pe_section_cache
    assert not cache._iz0_cache

    catalog_repo.get_device_icu_match_at_voltage(device.part_number, 400.0)
    catalog_repo.get_device_derating_factor(device.part_number, 50.0)
    catalog_repo.get_standard_pe_section(16.0)
    catalog_repo.get_cable_iz0_table_cu_pvc_c(3)
    assert connection_count == 8


def test_process_project_uses_and_clears_catalog_cache(monkeypatch):
    original_scope = catalog_repo._project_cache_scope
    caches = []

    @contextmanager
    def tracked_scope():
        with original_scope() as cache:
            caches.append(cache)
            yield cache

    monkeypatch.setattr(catalog_repo, "_project_cache_scope", tracked_scope)
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    engine.process_project(
        ProjectSpec(project_name="Catalog cache scope", prospective_ik_ka=25.0),
        [],
    )

    assert len(caches) == 1
    assert not caches[0]._icu_cache
    assert not caches[0]._derating_cache
    assert not caches[0]._pe_section_cache
    assert not caches[0]._iz0_cache
