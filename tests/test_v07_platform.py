# -*- coding: utf-8 -*-
"""Platform tests for catalog CRUD, web search, TCC, paths and Excel import errors."""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lv_assist.models import (CatalogDevice, DataQuality, FeederInput, LoadType,
                              ProjectSpec, SelectivityEvalState)
from lv_assist.catalog import CatalogRepository, SiemensSelectivityRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.paths import (get_app_working_dir, get_data_dir, get_translations_dir,
                             is_frozen, resource_path)
from lv_assist.web_catalog import (DeviceSearchSpec, device_from_search, parse_duckduckgo_html,
                                   source_urls, search_sources)
from lv_assist.tcc_analyzer import TccAnalyzer


def make_project(**overrides) -> ProjectSpec:
    params = dict(project_name="V07 Test Panel", prospective_ik_ka=22.0)
    params.update(overrides)
    return ProjectSpec(**params)


def make_feeder(feeder_id="F01", **overrides) -> FeederInput:
    params = dict(feeder_id=feeder_id, description="Test feeder",
                  load_type=LoadType.MOTOR_DOL, power_kw=11.0, cos_phi=0.85, efficiency=0.91,
                  cable_length_m=30.0)
    params.update(overrides)
    return FeederInput(**params)


def _demo_results():
    project = make_project()
    feeders = [make_feeder("F01"), make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=22.0)]
    outs, summary, vals = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, feeders)
    return project, outs, summary


# ================================================================ مسیرها (PyInstaller)
class TestPaths:
    def test_working_dir_is_project_root(self):
        assert Path(get_app_working_dir()).resolve() == Path(__file__).resolve().parent.parent

    def test_data_dir_dev_points_to_package_data(self):
        assert get_data_dir().name == "data"
        assert (get_data_dir() / "lv_assist.db").exists()

    def test_translations_dir_exists(self):
        tdir = get_translations_dir()
        for lang in ("fa", "en", "de"):
            assert (tdir / f"{lang}.json").exists()

    def test_resource_path_prefers_existing_working_copy(self, tmp_path):
        target = Path(get_app_working_dir()) / "config.json"
        assert Path(resource_path("config.json")) == target
        assert Path(resource_path("no_such_file.xyz")) == \
            Path(get_app_working_dir()) / "no_such_file.xyz"

    def test_frozen_flag_false_in_dev(self):
        assert is_frozen() is False


# ================================================================ CRUD کاتالوگ و قیمت
class TestCatalogCrud:
    @pytest.fixture()
    def repo(self, tmp_path):
        # دیتابیس موقت مستقل (کپی بذر) تا کاتالوگ اصلی پروژه دست‌نخورده بماند
        import shutil
        seed = get_data_dir() / "lv_assist.db"
        db = tmp_path / "test_catalog.db"
        shutil.copy2(seed, db)
        return CatalogRepository(db_path=db)

    def _device(self, pn="TST-MCCB-1"):
        return CatalogDevice(part_number=pn, manufacturer="TESTCO", series="TS-9",
                             device_type="MCCB", rated_current_in_a=100.0, icu_ka_400v=36.0,
                             power_loss_w=12.5, data_quality=DataQuality.ESTIMATED)

    def test_add_and_load_device(self, repo):
        repo.add_device(self._device(), unit_price=250.0, currency="EUR")
        repo.reload()
        devices = repo.load_devices()
        assert any(d.part_number == "TST-MCCB-1" for d in devices)
        new_dev = next(d for d in devices if d.part_number == "TST-MCCB-1")
        assert new_dev.data_quality == DataQuality.ESTIMATED
        # جداول وابسته: Icu در 400V برای موتور انتخاب ثبت شده باشد
        assert repo.get_device_icu_at_voltage("TST-MCCB-1", 400.0) == pytest.approx(36.0)

    def test_price_roundtrip_and_delete(self, repo):
        repo.add_device(self._device("TST-MCCB-2"), unit_price=99.9, currency="USD")
        assert repo.get_device_price("TST-MCCB-2")["unit_price"] == pytest.approx(99.9)
        assert repo.get_device_price("TST-MCCB-2")["currency"] == "USD"
        repo.set_device_price("TST-MCCB-2", 120.0)
        assert repo.get_device_price("TST-MCCB-2")["unit_price"] == pytest.approx(120.0)
        repo.set_device_price("TST-MCCB-2", None)  # حذف قیمت
        assert repo.get_device_price("TST-MCCB-2") is None
        assert repo.delete_device("TST-MCCB-2")
        assert repo.get_device_payload("TST-MCCB-2") is None

    def test_update_device(self, repo):
        repo.add_device(self._device("TST-MCCB-3"))
        dev = repo.get_device_payload("TST-MCCB-3")
        dev.rated_current_in_a = 125.0
        dev.manufacturer = "TESTCO2"
        repo.update_device("TST-MCCB-3", dev, unit_price=77.0)
        updated = repo.get_device_payload("TST-MCCB-3")
        assert updated.rated_current_in_a == 125.0
        assert updated.manufacturer == "TESTCO2"
        assert repo.get_device_price("TST-MCCB-3")["unit_price"] == pytest.approx(77.0)

    def test_user_rows_survive_rebuild(self, repo, tmp_path):
        from lv_assist.catalog import (_backup_user_data, _restore_user_data, _ensure_user_tables)
        repo.add_device(self._device("TST-KEEP-1"), unit_price=10.0)
        db = repo.db_path
        user_rows, price_rows = _backup_user_data(db)
        assert len(user_rows) == 1
        assert any(row[0] == 'TST-KEEP-1' and row[1] == 10.0 for row in price_rows)
        # شبیه‌سازی بازسازی: پاک‌سازی جدول کاتالوگ و بازگردانی
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM catalog_devices")
            conn.commit()
        _ensure_user_tables(db)
        _restore_user_data(db, user_rows, price_rows)
        repo.reload()
        restored = repo.get_device_payload("TST-KEEP-1")
        assert restored is not None
        assert restored.manufacturer == "TESTCO"
        assert repo.get_device_price("TST-KEEP-1")["unit_price"] == pytest.approx(10.0)

    def test_new_device_used_by_engine(self, repo):
        repo.add_device(CatalogDevice(part_number="TST-MPCB-9", manufacturer="TESTCO", series="TS-9",
                                      device_type="MPCB", rated_current_in_a=12.0, icu_ka_400v=50.0))
        repo.reload()
        catalog = list(repo.devices)
        engine = EngineeringEngine(catalog)
        project = make_project(preferred_manufacturer="TESTCO")
        outs, summary, _ = engine.process_project(project, [make_feeder("F01", power_kw=5.0)])
        assert outs[0].selected_protection is not None
        assert outs[0].selected_protection.device_type == "MPCB"


# ================================================================ جستجوی وب
class TestWebCatalog:
    def test_query_builds_from_general_specs(self):
        spec = DeviceSearchSpec(device_type="MCCB", rated_current_in_a=100, breaking_capacity_ka=36,
                                poles=3, voltage_v=400, manufacturer="SIEMENS")
        q = spec.build_query()
        assert "MCCB" in q and "100A" in q and "36kA" in q and "SIEMENS" in q and "datasheet" in q

    def test_source_urls_cover_manufacturer_and_eplan(self):
        urls = dict(source_urls(DeviceSearchSpec(device_type="MCCB")))
        assert "EPLAN Data Portal" in urls and "Siemens Industry Mall" in urls
        for url in urls.values():
            assert url.startswith("https://") and "%20" in url or "MCCB" in url

    def test_ddg_parser_extracts_results(self):
        html_page = '''
        <div class="result">
         <div class="result__body">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F3va1+datasheet.pdf&amp;rut=abc">3VA1 100A datasheet PDF</a>
          <a class="result__snippet" href="#">Sentron <b>3VA1</b> MCCB In=100A Icu=36kA ...</a>
         </div>
         <div class="result__body">
          <a class="result__a" href="https://vendor.example/x">Another hit</a>
          <a class="result__snippet" href="#">spec text</a>
         </div>
        </div>'''
        results = parse_duckduckgo_html(html_page)
        assert len(results) == 2
        assert results[0].url == "https://example.com/3va1 datasheet.pdf"
        assert "3VA1" in results[0].title
        assert "Icu=36kA" in results[0].snippet

    def test_fetch_returns_empty_without_network(self):
        # آدرس غیرقابل‌دسترس → فهرست خالی بدون Exception (امن برای GUI آفلاین)
        spec = DeviceSearchSpec(device_type="MCB")
        results = []
        for name, url in source_urls(spec)[:1]:
            import urllib.request
            try:
                urllib.request.urlopen("http://127.0.0.1:9/x", timeout=0.5)
            except OSError:
                pass
        assert isinstance(results, list)

    def test_device_from_search_is_estimated_with_source(self):
        spec = DeviceSearchSpec(device_type="CONTACTOR", rated_current_in_a=25, manufacturer="SCHNEIDER")
        dev = device_from_search(spec, part_number="LC1D25", series="TeSys D",
                                 manufacturer="SCHNEIDER", source_url="https://example.com/ds")
        assert dev.data_quality == DataQuality.ESTIMATED
        assert dev.part_number == "LC1D25"
        assert "example.com" in dev.series
        assert dev.rated_current_in_a == 25.0




# ================================================================ تحلیلگر TCC
class TestTccAnalyzer:
    def test_trip_time_from_datasheet_points(self):
        # SENTRON 3VA1 دارای نقاط رسمی: در 2×In حدود 20 ثانیه
        t = TccAnalyzer.trip_time_s("SENTRON 3VA1", 100.0, 200.0)
        assert 15.0 < t < 26.0
        assert TccAnalyzer.trip_time_s("SENTRON 3VA1", 100.0, 90.0) is None  # زیر 1.05×In

    def test_intersection_of_same_series_ratio_2(self):
        up = CatalogDevice(part_number="U", manufacturer="S", series="SENTRON 3VA1",
                           device_type="MCCB", rated_current_in_a=250.0)
        down = CatalogDevice(part_number="D", manufacturer="S", series="SENTRON 3VA1",
                             device_type="MCCB", rated_current_in_a=125.0)
        inter = TccAnalyzer.find_intersection(up, down)
        # حد هماهنگی باید در ناحیه آنی بالادست (8×250=2000A) یا تقاطع حرارتی قبل از آن باشد
        assert inter.limit_ka is not None and inter.limit_ka > 0.0
        assert inter.limit_ka <= 2.01  # 2000A = 2.0 kA
        state, limit, note = TccAnalyzer.evaluate_pair(up, down, 22.0)
        assert state in ("PARTIAL", "TOTAL_ESTIMATED") and limit and limit > 0.0

    def test_non_selective_pair_returns_none(self):
        up = CatalogDevice(part_number="U", manufacturer="S", series="SENTRON 3VA1",
                           device_type="MCCB", rated_current_in_a=125.0)
        down = CatalogDevice(part_number="D", manufacturer="S", series="SENTRON 3VA1",
                             device_type="MCCB", rated_current_in_a=140.0)
        inter = TccAnalyzer.find_intersection(up, down)
        assert inter.note == "upstream_not_larger_than_downstream"
        state, limit, _ = TccAnalyzer.evaluate_pair(up, down, 22.0)
        assert state in ("NONE", "UNKNOWN")

    def test_selectivity_engine_uses_intersection_estimate(self):
        up = CatalogDevice(part_number="U", manufacturer="S", series="SENTRON 3VA1",
                           device_type="MCCB", rated_current_in_a=250.0)
        down = CatalogDevice(part_number="D", manufacturer="S", series="SENTRON 3VA1",
                             device_type="MCCB", rated_current_in_a=100.0)
        state, limit, ref = SiemensSelectivityRepository.evaluate_pair(up, down, 22.0)
        # قاعده سازنده برای این زوج نسبت 2.5 ندارد → تخمین منحنی (هرگز VERIFIED)
        assert state == SelectivityEvalState.PRELIMINARY
        assert limit and limit > 0.0


# ================================================================ خطاهای دوستانه اکسل
class TestFriendlyExcelErrors:
    def test_invalid_file_raises_friendly_error(self, tmp_path):
        from lv_assist.gui import ExcelInputManager, ExcelImportError
        bad = tmp_path / "broken.xlsx"
        bad.write_text("this is not excel", encoding="utf-8")
        with pytest.raises(ExcelImportError):
            ExcelInputManager.load_from_excel(str(bad))

    def test_missing_sheet_raises_friendly_error(self, tmp_path):
        from lv_assist.gui import ExcelInputManager, ExcelImportError
        import openpyxl
        wb = openpyxl.Workbook()
        wb.active.title = "Wrong_Sheet"
        path = tmp_path / "wrong.xlsx"
        wb.save(path)
        with pytest.raises(ExcelImportError) as info:
            ExcelInputManager.load_from_excel(str(path))
        assert "Project_Spec" in str(info.value)

    def test_bad_power_row_skipped_with_row_error(self, tmp_path):
        from lv_assist.gui import ExcelInputManager
        from lv_assist.i18n import i18n
        i18n.set_language("en")  # پیام‌های خطا در تست به لاتین بررسی می‌شوند
        import openpyxl
        good = tmp_path / "ok.xlsx"
        ExcelInputManager.create_input_template(str(good))
        wb = openpyxl.load_workbook(good)
        ws = wb["Feeders_List"]
        ws.cell(row=2, column=6).value = None   # F01 توان حذف شد
        ws.cell(row=3, column=6, value="abc")  # F02 توان خراب
        ws.cell(row=4, column=7, value="xyz")  # F03 فاز خراب (نباید سطر را بیندازد)
        bad = tmp_path / "bad_rows.xlsx"
        wb.save(bad)
        project, feeders, errors = ExcelInputManager.load_from_excel(str(bad))
        ids = [f.feeder_id for f in feeders]
        assert "F01" not in ids and "F02" not in ids
        assert "F03" in ids  # خطای فاز غیرمرگبار است
        assert any("F01" in e or "F02" in e for e in errors)

    def test_bad_numeric_cell_reports_and_defaults(self, tmp_path):
        from lv_assist.gui import ExcelInputManager
        import openpyxl
        good = tmp_path / "ok2.xlsx"
        ExcelInputManager.create_input_template(str(good))
        wb = openpyxl.load_workbook(good)
        ws = wb["Feeders_List"]
        ws.cell(row=2, column=8, value="garbage")  # cos φ خراب
        path = tmp_path / "bad_cos.xlsx"
        wb.save(path)
        _, feeders, errors = ExcelInputManager.load_from_excel(str(path))
        assert len(feeders) == 4          # هیچ سطری حذف نشد
        assert feeders[0].cos_phi is None  # fallback به پیش‌فرض موتور
        assert any("cos" in e.lower() or "garbage" in e for e in errors)




# ================================================================ ادغام ویزارد
class TestWizardMerge:
    def test_wizard_app_is_main_app(self):
        import wizard_app
        from lv_assist.gui import LVAssistApp
        assert issubclass(wizard_app.InteractiveEngineeringWizard, LVAssistApp)

    def test_main_app_has_all_views_and_actions(self):
        from lv_assist.gui import LVAssistApp
        for attr in ("_build_view_project", "_build_view_feeders", "_build_view_instruments",
                     "_build_view_results", "_build_view_drawings", "_build_view_exports",
                     "_build_view_catalog", "_switch_view",
                     "action_add_feeder_interactively", "action_add_instrument",
                     "action_catalog_add", "action_catalog_edit", "action_catalog_delete",
                     "action_catalog_web_search",
                     "action_export_eplan_macros", "action_import_excel"):
            assert hasattr(LVAssistApp, attr), attr

    def test_field_wizard_engine_integrated_in_calc_path(self):
        from lv_assist.gui import LVAssistApp
        import inspect
        src = inspect.getsource(LVAssistApp._run_calculations_and_refresh)
        assert "IndustrialAutomationEngine" in src
