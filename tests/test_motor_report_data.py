import json
import math

from openpyxl import load_workbook

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.i18n import tr
from lv_assist.models import FeederInput, LoadType, ProjectSpec


def _project():
    return ProjectSpec(
        project_name="Motor report values",
        prospective_ik_ka=25.0,
        transformer_kva=630.0,
    )


def _motor(feeder_id="M01", **overrides):
    values = {
        "feeder_id": feeder_id,
        "description": "Motor",
        "load_type": LoadType.MOTOR_DOL,
        "power_kw": 15.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _calculate(feeder):
    return EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(
        _project(), [feeder]
    )


def test_engine_keeps_motor_nameplate_values_and_normal_kva():
    feeder = _motor(cos_phi=0.82, efficiency=0.93)

    outputs, _, _ = _calculate(feeder)

    motor = outputs[0]
    assert motor.cos_phi_resolved == 0.82
    assert motor.cos_phi_source == "plate"
    assert motor.efficiency_resolved == 0.93
    assert motor.efficiency_source == "plate"
    assert math.isclose(motor.kva_normal, 15.0 / (0.82 * 0.93), abs_tol=0.005)


def test_engine_marks_default_motor_values_separately():
    outputs, _, _ = _calculate(_motor())

    motor = outputs[0]
    assert motor.cos_phi_resolved == 0.86
    assert motor.cos_phi_source == "default"
    assert motor.efficiency_resolved == 0.91
    assert motor.efficiency_source == "default"
    assert math.isclose(motor.kva_normal, 15.0 / (0.86 * 0.91), abs_tol=0.005)


def test_excel_schedule_has_motor_values_and_assumed_markers(tmp_path):
    outputs, summary, validations = _calculate(_motor())
    path = tmp_path / "motor-report.xlsx"

    ExcelExporter.export_to_excel(str(path), _project(), outputs, summary, validations)

    sheet = load_workbook(path, data_only=True)["02_Feeder_Cable_Schedule"]
    headers = [cell.value for cell in sheet[1]]
    assert tr("col_cos_phi_assumed") in headers
    assert tr("col_efficiency_assumed") in headers
    assert tr("col_kva_normal") in headers
    assert tr("col_kva_starting") in headers
    values = {header: sheet.cell(row=2, column=index + 1).value for index, header in enumerate(headers)}
    assert "(prelim.)" in str(values[tr("col_cos_phi_assumed")])
    assert "(prelim.)" in str(values[tr("col_efficiency_assumed")])
    assert float(str(values[tr("col_kva_normal")]).split()[0]) == outputs[0].kva_normal
    assert float(str(values[tr("col_kva_starting")]).split()[0]) == outputs[0].starting_kva


def test_html_schedule_shows_assumed_badges_and_motor_kva(tmp_path):
    outputs, summary, validations = _calculate(_motor())
    path = tmp_path / "motor-report.html"

    PrintableReportExporter.generate_html_report(
        str(path), _project(), outputs, summary, validations
    )
    html = path.read_text(encoding="utf-8")

    assert f"<th>{tr('col_cos_phi_assumed')}</th>" in html
    assert f"<th>{tr('col_efficiency_assumed')}</th>" in html
    assert f"<th>{tr('col_kva_normal')}</th>" in html
    assert f"<th>{tr('col_kva_starting')}</th>" in html
    assert f'class="badge badge-assumed">{tr("badge_assumed")}</span>' in html
    assert str(outputs[0].kva_normal) in html
    assert str(outputs[0].starting_kva) in html


def test_motor_report_translation_keys_exist_in_all_languages():
    from pathlib import Path

    translations = Path(__file__).resolve().parents[1] / "lv_assist" / "translations"
    keys = {
        "col_cos_phi",
        "col_cos_phi_assumed",
        "col_efficiency",
        "col_efficiency_assumed",
        "col_kva_normal",
        "col_kva_starting",
        "badge_assumed",
    }
    for language in ("fa", "en", "de"):
        with (translations / f"{language}.json").open(encoding="utf-8") as file:
            table = json.load(file)
        assert keys <= table.keys(), f"Missing keys in {language}: {keys - table.keys()}"
