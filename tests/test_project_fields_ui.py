import json
from pathlib import Path

import customtkinter as ctk
import pytest
from openpyxl import load_workbook

from lv_assist import gui
from lv_assist.gui import ExcelInputManager, LVAssistApp
from lv_assist.i18n import i18n


def test_sidebar_section_labels_are_translated_in_all_locales():
    expected = {
        "fa": {
            "sidebar_active_project": "پروژه فعال",
            "sidebar_validation_center": "مرکز اعتبارسنجی اسناد",
        },
        "en": {
            "sidebar_active_project": "Active Project",
            "sidebar_validation_center": "Document Validation Center",
        },
        "de": {
            "sidebar_active_project": "Aktives Projekt",
            "sidebar_validation_center": "Dokumentenvalidierung",
        },
    }
    translations_dir = Path(__file__).resolve().parents[1] / "lv_assist" / "translations"

    for language, expected_labels in expected.items():
        translations = json.loads(
            (translations_dir / f"{language}.json").read_text(encoding="utf-8")
        )
        for key, value in expected_labels.items():
            assert translations.get(key) == value


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


def test_project_form_idle_callbacks_do_not_mix_geometry_managers(window):
    callback_errors = []
    window.report_callback_exception = lambda _type, error, _traceback: callback_errors.append(error)
    entry = window.wiz_entries["wiz_project_name"]

    # Run the deferred operation synchronously too: Tk reports exceptions from
    # after_idle callbacks through report_callback_exception instead of raising.
    indicator = window._attach_assumed_field_indicator(
        entry.master, "wiz_project_name", entry, row=0,
    )
    assert indicator.winfo_manager() == "grid"
    form_managers = {
        child.winfo_manager() for child in window._project_form_frame.winfo_children()
        if child.winfo_manager() in {"pack", "grid"}
    }
    assert form_managers <= {"grid"}

    window.update_idletasks()

    assert not callback_errors, [str(error) for error in callback_errors]


def test_feeder_edit_dialog_builds_with_real_widgets(app):
    dialog = gui.FeederEditDialog(app, app.current_feeders[0], lambda _feeder: None)
    try:
        app.update_idletasks()
        assert isinstance(dialog._form_frame, ctk.CTkScrollableFrame)
        child_managers = {child.winfo_manager() for child in dialog.winfo_children()}
        assert child_managers <= {"pack"}
    finally:
        dialog.destroy()


def test_main_window_minsize_fits_compact_work_area(app):
    assert 1100 <= app._min_width <= max(1100, app.winfo_screenwidth() - 40)
    assert 650 <= app._min_height <= max(650, app.winfo_screenheight() - 80)


def test_initial_window_dimensions_fit_1366_by_768_screen():
    assert gui._initial_window_dimensions(1366, 768) == (1326, 688)


def test_main_window_minsize_uses_content_request_with_screen_caps(app):
    assert gui._window_minsize_dimensions(1180, 700, 1366, 768) == (1220, 688)
    assert gui._window_minsize_dimensions(1500, 900, 1366, 768) == (1326, 688)


def test_project_entries_can_shrink_below_old_fixed_width(app):
    form = app._project_form_frame
    assert int(form.grid_columnconfigure(1)["weight"]) > 0
    assert app.wiz_entries["wiz_project_name"].cget("width") < 210


def test_project_action_buttons_remain_mapped_at_minsize(app):
    app.deiconify()
    try:
        app.geometry(f"{app._min_width}x{app._min_height}")
        app.update()
        assert app._project_action_buttons
        assert all(button.winfo_ismapped() for button in app._project_action_buttons)
    finally:
        app.withdraw()


def test_catalog_preview_copy_uses_english_without_persian_literals(app):
    import re

    original_language = i18n.get_language()

    def texts(root):
        values = []
        for widget in (root, *root.winfo_children()):
            try:
                value = widget.cget("text")
            except Exception:
                value = ""
            if isinstance(value, str) and value:
                values.append(value)
            if widget is not root and widget.winfo_children():
                values.extend(texts(widget))
        return values

    try:
        i18n.set_language("en")
        app._rebuild_preserving_project_form()
        app_copy = texts(app)
        guardrail = texts(app._guardrail_bar)
        catalog = texts(app.views[5])
        assert "Active Project" in app_copy
        assert "Document Validation Center" in app_copy
        assert any("active on baseline assumptions" in value for value in guardrail)
        assert any("unique documents" in value for value in guardrail)
        assert {"All", "Preview", "Awaiting", "Insufficient data"}.issubset(set(catalog))
        assert any("isolated preview" in value for value in catalog)
        assert any("inquiry tracker" in value.lower() for value in catalog)
        assert len({value for value in catalog if value.startswith("Step ")}) == 4
        target_copy = guardrail + catalog
        assert not any(re.search(r"[\u0600-\u06ff]", value) for value in target_copy)
        assert not any("PR #13" in value for value in catalog)
    finally:
        i18n.set_language(original_language)
        app._rebuild_preserving_project_form()


def test_feeder_save_cancel_buttons_stay_outside_scrollable_form(app):
    dialog = gui.FeederEditDialog(app, app.current_feeders[0], lambda _feeder: None)
    try:
        buttons = [
            child for parent in dialog.winfo_children()
            for child in parent.winfo_children()
            if isinstance(child, ctk.CTkButton)
        ]
        button_labels = {button.cget("text") for button in buttons}
        assert gui.tr("dlg_save") in button_labels
        assert gui.tr("dlg_cancel") in button_labels
        assert all(button.master is not dialog._form_frame for button in buttons)
    finally:
        dialog.destroy()


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
