from openpyxl import load_workbook
from copy import deepcopy

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import ExcelExporter
from lv_assist.models import DataQuality, FeederInput, LoadType, ProjectSpec
from lv_assist.i18n import tr


def _make_project(**overrides):
    values = {
        "project_name": "Prelim test",
        "prospective_ik_ka": 25.0,
        "transformer_kva": 630.0,
    }
    values.update(overrides)
    return ProjectSpec(**values)


def _make_feeder(**overrides):
    values = {
        "feeder_id": "F01",
        "description": "Feeder",
        "load_type": LoadType.SUB_FEEDER,
        "power_kw": 5.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _export(tmp_path, project, feeders=None, protection_quality=None):
    feeders = feeders or [_make_feeder()]
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, validations = engine.process_project(project, feeders)
    if protection_quality is not None and outputs[0].selected_protection is not None:
        outputs[0].selected_protection = deepcopy(outputs[0].selected_protection)
        outputs[0].selected_protection.data_quality = protection_quality
    out = tmp_path / "out.xlsx"
    ExcelExporter.export_to_excel(str(out), project, outputs, summary, validations)
    return load_workbook(out)


def _row_for_label(ws, label):
    return next(row for row in ws.iter_rows() if row[0].value == label)


def test_busbar_icw_ipk_and_temperature_factor_are_marked(tmp_path):
    wb = _export(tmp_path, _make_project())
    ws = wb["01_Project_Summary"]
    busbar_row = _row_for_label(ws, tr("rpt_bus_icw"))
    assert "Icw(1s)=" in busbar_row[1].value and "(prelim.)" in busbar_row[1].value
    assert "Ipk=" in busbar_row[1].value and "(prelim.)" in busbar_row[1].value

    temp_row = _row_for_label(ws, "Busbar temperature factor")
    assert "(prelim.)" in str(temp_row[1].value)


def test_global_footer_is_present_on_report_sheets(tmp_path):
    _EXPECTED_FOOTER_SHEETS = {
        "01_Project_Summary",
        "02_Feeder_Cable_Schedule",
        "03_Validation_Log",
        "04_BOM",
    }
    wb = _export(tmp_path, _make_project())
    for sheet_name in _EXPECTED_FOOTER_SHEETS:
        if sheet_name not in wb.sheetnames:
            continue
        values = [
            str(value)
            for row in wb[sheet_name].iter_rows(values_only=True)
            for value in row if value is not None
        ]
        assert any("PRELIMINARY:" in value and "IEC 61439" in value for value in values), \
            f"Footer missing in report sheet: {sheet_name}"


def test_no_footer_in_data_sheets(tmp_path):
    wb = _export(tmp_path, _make_project())
    for sheet_name in ("Routine_Verification", "Terminal_Schedule", "Wire_Schedule"):
        if sheet_name not in wb.sheetnames:
            continue
        values = [
            str(value)
            for row in wb[sheet_name].iter_rows(values_only=True)
            for value in row if value is not None
        ]
        assert not any("PRELIMINARY:" in value for value in values), \
            f"Footer must not appear in data sheet: {sheet_name}"


def test_transformer_ik_is_marked_but_explicit_ik_is_not(tmp_path):
    estimated = _export(
        tmp_path, _make_project(prospective_ik_ka=None, transformer_kva=630.0)
    )
    ik_row = _row_for_label(estimated["01_Project_Summary"], tr("rpt_ik"))
    assert "(prelim.)" in str(ik_row[1].value)

    explicit = _export(tmp_path, _make_project(prospective_ik_ka=25.0))
    ik_row = _row_for_label(explicit["01_Project_Summary"], tr("rpt_ik"))
    assert "(prelim.)" not in str(ik_row[1].value)


def test_icu_marker_follows_catalog_data_quality_and_keeps_format(tmp_path):
    verified = _export(tmp_path, _make_project(), protection_quality=DataQuality.REAL_VERIFIED)
    ws = verified["02_Feeder_Cable_Schedule"]
    headers = [cell.value for cell in ws[1]]
    icu_col = headers.index(tr("rpt_c_icu")) + 1
    verified_value = str(ws.cell(row=2, column=icu_col).value)
    assert "kA @" in verified_value and "400V" in verified_value
    assert "(prelim.)" not in verified_value

    estimated = _export(tmp_path, _make_project(), protection_quality=DataQuality.ESTIMATED)
    ws = estimated["02_Feeder_Cable_Schedule"]
    headers = [cell.value for cell in ws[1]]
    estimated_value = str(ws.cell(row=2, column=headers.index(tr("rpt_c_icu")) + 1).value)
    assert "kA @" in estimated_value and "400V" in estimated_value
    assert "(prelim.)" in estimated_value


def test_cable_derating_factors_are_marked_when_thermal_method_is_preliminary(tmp_path):
    wb = _export(tmp_path, _make_project())
    ws = wb["02_Feeder_Cable_Schedule"]
    headers = [cell.value for cell in ws[1]]
    row = next(row for row in ws.iter_rows(min_row=2) if row[0].value == "F01")
    for key in ("rpt_c_k1", "rpt_c_k2", "rpt_c_ktot"):
        value = row[headers.index(tr(key))].value
        assert "(prelim.)" in str(value), key

