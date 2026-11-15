import pytest
from openpyxl import Workbook

from lv_assist.gui import ExcelImportError, ExcelInputManager


def _write_project_sheet(workbook):
    sheet = workbook.active
    sheet.title = "Project_Spec"
    sheet.append(["key", "value"])
    sheet.append(["project_name", "Header Mapping Test"])
    return sheet


def _write_custom_feeders_workbook(path, headers, values):
    workbook = Workbook()
    _write_project_sheet(workbook)
    sheet = workbook.create_sheet("Feeders_List")
    sheet.append(headers)
    sheet.append(values)
    workbook.save(path)


def test_import_maps_reordered_multilingual_feeder_headers(tmp_path):
    path = tmp_path / "reordered.xlsx"
    _write_custom_feeders_workbook(
        path,
        [
            "Beschreibung", "Power (kW)", "Abgangs-ID", "Lastart", "Länge (m)",
            "فاز", "cos φ", "Querschnitt (mm²)", "Leiterwerkstoff", "THDi%",
            "Steckdosen?", "Brandschutz",
        ],
        ["Pump", 12.5, "F99", "MOTOR_VFD", 60, 1, 0.92, 10, "AL", 30, "TRUE", "yes"],
    )

    project, feeders, errors = ExcelInputManager.load_from_excel(str(path))

    assert project.project_name == "Header Mapping Test"
    assert errors == []
    assert len(feeders) == 1
    feeder = feeders[0]
    assert feeder.feeder_id == "F99"
    assert feeder.description == "Pump"
    assert feeder.load_type.value == "MOTOR_VFD"
    assert feeder.power_kw == 12.5
    assert feeder.cable_length_m == 60
    assert feeder.phases == 1
    assert feeder.cos_phi == 0.92
    assert feeder.cable_section_mm2 == 10
    assert feeder.conductor_material.value == "AL"
    assert feeder.thdi_pct == 30
    assert feeder.has_socket_outlets is True
    assert feeder.fire_resistant is True


def test_import_requires_power_column_by_header(tmp_path):
    path = tmp_path / "missing_power.xlsx"
    _write_custom_feeders_workbook(
        path,
        ["Feeder ID", "Description", "Load Type", "Length (m)"],
        ["F01", "Pump", "MOTOR_DOL", 25],
    )

    with pytest.raises(ExcelImportError, match="power_kw"):
        ExcelInputManager.load_from_excel(str(path))


def test_template_roundtrip_loads_feeder_columns(tmp_path):
    path = tmp_path / "template.xlsx"
    ExcelInputManager.create_input_template(str(path))

    project, feeders, errors = ExcelInputManager.load_from_excel(str(path))

    assert errors == []
    assert len(feeders) == 4
    assert [feeder.feeder_id for feeder in feeders] == ["F01", "F02", "F03", "F04"]
    assert feeders[0].power_kw == 15.0
    assert feeders[0].phases == 3
    assert feeders[2].thdi_pct == 40.0
    assert project.project_name
