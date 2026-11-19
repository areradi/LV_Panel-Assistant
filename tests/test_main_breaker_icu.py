import json
import openpyxl
import sqlite3
import pytest
from pathlib import Path

from lv_assist.catalog import CatalogRepository, catalog_repo
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.iec_sld_svg import IECSldSvgGenerator
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.i18n import tr
from lv_assist.models import FeederInput, LoadType, MainBreakerSpec, ProjectSpec
from lv_assist.outputs import TccGenerator
from lv_assist.summary_workflow import format_summary_cards


def _project(ik=30.0, voltage=400.0):
    return ProjectSpec(
        project_name="Main Icu test",
        prospective_ik_ka=ik,
        transformer_kva=None,
        nominal_voltage_v=voltage,
    )


def _feeders():
    return [FeederInput(
        feeder_id="F01",
        description="Test load",
        load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
        cos_phi=0.9,
        efficiency=1.0,
    )]


def _run_with_icu(monkeypatch, icu_ka, exact=True, ik=30.0, voltage=400.0):
    def get_match(device_id, nominal_voltage_v, tolerance_v=20.0):
        return (icu_ka, exact) if icu_ka is not None else (None, False)

    monkeypatch.setattr(catalog_repo, "get_device_icu_match_at_voltage", get_match)
    project = _project(ik=ik, voltage=voltage)
    feeders = _feeders()
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    return project, feeders, outputs, summary, validations


def test_main_breaker_icu_unknown_when_no_capacity_data(monkeypatch):
    _, _, _, summary, _ = _run_with_icu(monkeypatch, None)

    assert summary.main_breaker is not None
    assert summary.main_breaker_icu_status == "UNKNOWN"
    assert summary.main_breaker_icu_source == "unknown"
    assert summary.main_breaker_icu_reason == "no_icu"
    assert summary.main_breaker_icu_value is None
    assert summary.main_breaker_ik == 30.0


def test_catalog_icu_match_reports_exact_and_near_voltage_without_changing_tolerance():
    device = next(
        item for item in CatalogRepository.get_default_catalog()
        if item.device_type == "MCCB"
    )
    with sqlite3.connect(catalog_repo.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO device_breaking_capacities "
            "(device_id, voltage_v, icu_ka, ics_ka, source) VALUES (?, 620.0, 42.0, NULL, 'TEST')",
            (device.part_number,),
        )

    assert catalog_repo.get_device_icu_match_at_voltage(device.part_number, 620.0) == (42.0, True)
    assert catalog_repo.get_device_icu_match_at_voltage(device.part_number, 625.0) == (42.0, False)
    assert catalog_repo.get_device_icu_match_at_voltage(device.part_number, 641.0) == (None, False)
    assert catalog_repo.get_device_icu_at_voltage(device.part_number, 625.0) == 42.0


def test_main_breaker_icu_fails_when_all_current_candidates_are_below_ik(monkeypatch):
    _, _, _, summary, _ = _run_with_icu(monkeypatch, 25.0)

    assert summary.main_breaker is None
    assert summary.main_breaker_icu_status == "FAIL"
    assert summary.main_breaker_icu_source == "unknown"
    assert summary.main_breaker_icu_reason == "icu_below_ik"


def test_main_breaker_icu_passes_on_exact_voltage_match(monkeypatch):
    _, _, _, summary, _ = _run_with_icu(monkeypatch, 50.0, exact=True)

    assert summary.main_breaker is not None
    assert summary.main_breaker_icu_status == "OK"
    assert summary.main_breaker_icu_source == "exact"
    assert summary.main_breaker_icu_value == 50.0


def test_main_breaker_icu_marks_near_voltage_match_estimated(monkeypatch):
    _, _, _, summary, _ = _run_with_icu(
        monkeypatch, 50.0, exact=False, ik=30.0, voltage=415.0
    )

    assert summary.main_breaker is not None
    assert summary.main_breaker_icu_status == "OK"
    assert summary.main_breaker_icu_source == "estimated"
    assert summary.main_breaker_icu_value == 50.0


def test_main_breaker_icu_is_unknown_when_ik_is_missing(monkeypatch):
    _, _, _, summary, _ = _run_with_icu(monkeypatch, 50.0, ik=None)

    assert summary.main_breaker is not None
    assert summary.main_breaker_icu_status == "UNKNOWN"
    assert summary.main_breaker_icu_reason == "no_ik"
    assert summary.main_breaker_icu_source == "unknown"


@pytest.mark.parametrize("invalid_icu", [
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param("not-a-number", id="non-numeric-string"),
])
def test_main_breaker_icu_invalid_capacity_is_unknown(monkeypatch, invalid_icu):
    def get_match(device_id, nominal_voltage_v, tolerance_v=20.0):
        return (invalid_icu, True)

    monkeypatch.setattr(catalog_repo, "get_device_icu_match_at_voltage", get_match)
    _, summary, _ = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(_project(), [])

    assert summary.main_breaker_icu_status == "UNKNOWN"
    assert summary.main_breaker_icu_source == "unknown"
    assert summary.main_breaker_icu_value is None


@pytest.mark.parametrize("invalid_icu", [
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param("not-a-number", id="non-numeric-string"),
])
def test_feeder_breaking_capacity_invalid_icu_is_insufficient_data(monkeypatch, invalid_icu):
    def get_match(device_id, nominal_voltage_v, tolerance_v=20.0):
        return (invalid_icu, True)

    monkeypatch.setattr(catalog_repo, "get_device_icu_match_at_voltage", get_match)
    project = _project()
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, _feeders())

    feeder_check = next(
        item for item in validations
        if item.rule_id == "RULE-PROT-SC-001" and item.feeder_id == "F01"
    )
    assert feeder_check.status.value == "INSUFFICIENT_DATA"
    assert outputs[0].protection_icu_ka is None
    assert summary.main_breaker_icu_status == "UNKNOWN"
    assert summary.main_breaker_icu_value is None


def test_main_breaker_card_uses_resolved_icu_status_and_source():
    cards = format_summary_cards(
        MainBreakerSpec(part_number="TEST", in_a=100.0),
        None,
        icu_status="OK",
        icu_source="estimated",
        icu_value=36.0,
        icu_voltage_v=415.0,
    )

    assert "36" in cards["main_protection"]["breaking_capacity"]
    assert "415" in cards["main_protection"]["breaking_capacity"]
    assert tr("status_ok") in cards["main_protection"]["icu_status"]
    assert tr("badge_icu_estimated") in cards["main_protection"]["icu_status"]


@pytest.mark.parametrize(
    ("status", "source", "badge_key", "color", "tooltip_key"),
    [
        ("OK", "exact", "badge_icu_exact", "#DCFCE7", None),
        ("OK", "estimated", "badge_icu_estimated", "#FEF9C3", "tooltip_icu_estimated"),
        ("UNKNOWN", "unknown", "badge_icu_unknown", "#E5E7EB", "tooltip_icu_unknown"),
        ("FAIL", "unknown", "status_fail", "#FEE2E2", "tooltip_icu_fail"),
    ],
)
def test_main_icu_gui_badge_presentation(status, source, badge_key, color, tooltip_key):
    from lv_assist.precision_ui import _main_icu_badge_style

    key, foreground, _text_color, actual_tooltip_key = _main_icu_badge_style(status, source)

    assert key == badge_key
    assert color in foreground
    assert actual_tooltip_key == tooltip_key


def test_main_icu_summary_card_shows_exact_and_unknown_source():
    exact = format_summary_cards(
        MainBreakerSpec(part_number="TEST", in_a=100.0), None,
        icu_status="OK", icu_source="exact", icu_value=36.0, icu_voltage_v=400.0,
    )
    unknown = format_summary_cards(
        MainBreakerSpec(part_number="TEST", in_a=100.0), None,
        icu_status="UNKNOWN", icu_source="unknown",
    )

    assert tr("badge_icu_exact") in exact["main_protection"]["icu_status"]
    assert tr("badge_icu_unknown") in unknown["main_protection"]["icu_status"]


def test_main_breaker_icu_is_attached_to_excel_and_html_reports(monkeypatch, tmp_path):
    project, feeders, outputs, summary, validations = _run_with_icu(
        monkeypatch, 50.0, exact=True
    )
    xlsx_path = tmp_path / "main-icu.xlsx"
    ExcelExporter.export_to_excel(str(xlsx_path), project, outputs, summary, validations)
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
    values = [value for row in workbook["01_Project_Summary"].iter_rows(values_only=True)
              for value in row if value is not None]
    assert tr("col_icu_main_breaker") in values
    assert any("50" in str(value) and "kA @ 400V" in str(value) for value in values)
    assert any(tr("status_ok") in str(value) for value in values)

    html_path = tmp_path / "main-icu.html"
    PrintableReportExporter.generate_html_report(
        str(html_path), project, outputs, summary, validations
    )
    html = html_path.read_text(encoding="utf-8")
    assert "50" in html
    assert tr("status_ok") in html


def test_estimated_main_icu_source_is_visible_in_excel_and_html(monkeypatch, tmp_path):
    project, feeders, outputs, summary, validations = _run_with_icu(
        monkeypatch, 50.0, exact=False, voltage=415.0
    )
    assert summary.main_breaker_icu_status == "OK"
    assert summary.main_breaker_icu_source == "estimated"

    xlsx_path = tmp_path / "main-icu-estimated.xlsx"
    ExcelExporter.export_to_excel(str(xlsx_path), project, outputs, summary, validations)
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
    rows = list(workbook["01_Project_Summary"].iter_rows(values_only=True))
    header_row = next(row for row in rows if tr("main_breaker_icu_status_source") in row)
    status_col = header_row.index(tr("main_breaker_icu_status_source"))
    data_row = rows[rows.index(header_row) + 1]
    assert data_row[status_col] == f"{tr('status_ok')} ({tr('badge_icu_estimated')})"
    assert tr("badge_icu_estimated") in data_row[status_col]

    html_path = tmp_path / "main-icu-estimated.html"
    PrintableReportExporter.generate_html_report(
        str(html_path), project, outputs, summary, validations
    )
    html = html_path.read_text(encoding="utf-8")
    assert 'class="badge badge-preliminary"' in html
    assert tr("badge_icu_estimated") in html
    assert tr("tooltip_icu_estimated") in html


def test_exact_voltage_source_is_not_labeled_estimated_in_excel(monkeypatch, tmp_path):
    project, _feeders, outputs, summary, validations = _run_with_icu(
        monkeypatch, 55.0, exact=True, voltage=415.0
    )
    assert summary.main_breaker_icu_status == "OK"
    assert summary.main_breaker_icu_source == "exact"

    xlsx_path = tmp_path / "main-icu-exact-preliminary-data.xlsx"
    ExcelExporter.export_to_excel(str(xlsx_path), project, outputs, summary, validations)
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
    rows = list(workbook["01_Project_Summary"].iter_rows(values_only=True))
    header_row = next(row for row in rows if tr("main_breaker_icu_status_source") in row)
    status_col = header_row.index(tr("main_breaker_icu_status_source"))
    data_row = rows[rows.index(header_row) + 1]
    icu_col = header_row.index(tr("col_icu_main_breaker"))

    assert data_row[status_col] == f"{tr('status_ok')} ({tr('badge_icu_exact')})"
    assert tr("badge_icu_estimated") not in data_row[status_col]
    assert "prelim." in data_row[icu_col]


def test_icu_display_translation_keys_have_parity():
    root = Path(__file__).resolve().parents[1] / "lv_assist" / "translations"
    required = {
        "badge_icu_exact", "badge_icu_estimated", "badge_icu_unknown",
        "tooltip_icu_estimated", "main_breaker_icu_status_source",
    }
    for language in ("fa", "en", "de"):
        data = json.loads((root / f"{language}.json").read_text(encoding="utf-8"))
        assert required <= data.keys(), f"Missing keys in {language}: {required - data.keys()}"


def test_iec_sld_and_tcc_mark_estimated_main_icu(monkeypatch):
    project, feeders, outputs, summary, _ = _run_with_icu(
        monkeypatch, 50.0, exact=False, voltage=415.0
    )
    dto = GuiOutputBridge.to_sld_dto(project, outputs, summary)
    svg = IECSldSvgGenerator.render_sld_svg(dto)
    assert tr("status_estimated") in svg

    tcc = TccGenerator.generate_svg(project, outputs, summary)
    assert tr("tcc_icu_estimated") in tcc
