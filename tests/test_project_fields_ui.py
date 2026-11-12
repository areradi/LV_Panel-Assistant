import customtkinter as ctk
import pytest
from openpyxl import load_workbook

from lv_assist import gui
from lv_assist.gui import ExcelInputManager, LVAssistApp
from lv_assist.i18n import i18n


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    config_path = i18n._config_path
    language = i18n.get_language()
    theme = ctk.get_appearance_mode()
    original_config_path = gui.config_file_path
    gui.config_file_path = lambda: str(tmp_path_factory.mktemp("project_fields") / "config.json")
    app = LVAssistApp()
    app.withdraw()
    yield app
    try:
        app.destroy()
    except Exception:
        pass
    gui.config_file_path = original_config_path
    i18n._config_path = config_path
    i18n._language = language
    ctk.set_appearance_mode(theme)


@pytest.fixture
def app(window):
    window.current_project, window.current_feeders = gui.build_demo_project()
    window._track_demo_text()
    window._last_calculation_project = None
    window._last_calculation_feeders = []
    window.instruments_list = []
    window._fill_project_form(window.current_project)
    window._stale = False
    window._apply_status()
    return window


def _set_entry(app, key, value):
    widget = app.wiz_entries[key]
    if isinstance(widget, ctk.CTkEntry):
        widget.delete(0, "end")
        widget.insert(0, value)
    else:
        widget.set(value)


def test_new_fields_present_in_wiz_entries(app):
    for key in (
        "transformer_uk_pct", "cable_grouping_factor_k2", "spd_connection_length_m",
        "altitude_m", "internal_separation_form", "designer_name",
    ):
        assert key in app.wiz_entries, f"{key} missing from wiz_entries"


def test_project_fields_roundtrip(app):
    values = {
        "transformer_uk_pct": "6.5",
        "cable_grouping_factor_k2": "0.85",
        "spd_connection_length_m": "0.7",
        "altitude_m": "1200",
        "internal_separation_form": "Form 3b",
        "designer_name": "Test Designer",
    }
    for key, value in values.items():
        _set_entry(app, key, value)

    project = app._project_from_form()
    assert project.transformer_uk_pct == 6.5
    assert project.cable_grouping_factor_k2 == 0.85
    assert project.spd_connection_length_m == 0.7
    assert project.altitude_m == 1200.0
    assert project.internal_separation_form == "Form 3b"
    assert project.designer_name == "Test Designer"


def test_set_project_form_populates_new_fields(app):
    project = gui.build_demo_project()[0].model_copy(update={
        "transformer_uk_pct": 7.1,
        "cable_grouping_factor_k2": 0.9,
        "spd_connection_length_m": 0.8,
        "altitude_m": 1500.0,
        "internal_separation_form": "Form 4b",
        "designer_name": "Panel Designer",
    })
    app._fill_project_form(project)
    assert app.wiz_entries["transformer_uk_pct"].get() == "7.1"
    assert app.wiz_entries["cable_grouping_factor_k2"].get() == "0.9"
    assert app.wiz_entries["spd_connection_length_m"].get() == "0.8"
    assert app.wiz_entries["altitude_m"].get() == "1500"
    assert app.wiz_entries["internal_separation_form"].get() == "Form 4b"
    assert app.wiz_entries["designer_name"].get() == "Panel Designer"


def test_project_fields_survive_rebuild(app):
    _set_entry(app, "transformer_uk_pct", "7.2")
    _set_entry(app, "designer_name", "Rebuild Test")
    app._rebuild_preserving_project_form()
    assert app.wiz_entries["transformer_uk_pct"].get() == "7.2"
    assert app.wiz_entries["designer_name"].get() == "Rebuild Test"


def test_blank_designer_name_maps_to_none(app):
    app.current_project, app.current_feeders = gui.build_demo_project()
    app._fill_project_form(app.current_project)
    _set_entry(app, "designer_name", "   ")
    assert app._project_from_form().designer_name is None


def test_excel_template_import_roundtrip_for_k2_and_designer(tmp_path):
    path = tmp_path / "project_fields.xlsx"
    ExcelInputManager.create_input_template(str(path))
    workbook = load_workbook(path)
    project_sheet = workbook["Project_Spec"]
    rows = {row[0].value: row[0].row for row in project_sheet.iter_rows(min_row=2)}
    assert "cable_grouping_factor_k2" in rows
    assert "designer_name" in rows
    project_sheet.cell(rows["cable_grouping_factor_k2"], 2).value = 0.91
    project_sheet.cell(rows["designer_name"], 2).value = "Excel Designer"
    workbook.save(path)

    project, feeders, errors = ExcelInputManager.load_from_excel(str(path))
    assert not errors
    assert feeders
    assert project.cable_grouping_factor_k2 == 0.91
    assert project.designer_name == "Excel Designer"
