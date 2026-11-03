from pathlib import Path
from unittest.mock import Mock
import json

import customtkinter as ctk
import openpyxl
import pytest

from lv_assist import gui
from lv_assist.gui import ExcelInputManager, LVAssistApp, build_demo_project
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.iec_ladder_svg import IECLadderSvgGenerator
from lv_assist.i18n import i18n
from lv_assist.models import EarthingSystem, PanelType, ProjectSpec, SpecialScenario


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    config_path = i18n._config_path
    language = i18n.get_language()
    theme = ctk.get_appearance_mode()
    original_path_function = gui.config_file_path
    gui.config_file_path = lambda: str(tmp_path_factory.mktemp("gui_config") / "config.json")
    app = LVAssistApp()
    app.withdraw()
    yield app
    app.destroy()
    gui.config_file_path = original_path_function
    i18n._config_path = config_path
    i18n._language = language
    ctk.set_appearance_mode(theme)


@pytest.fixture
def app(window, monkeypatch):
    for name in ("showerror", "showwarning", "showinfo"):
        monkeypatch.setattr(gui.messagebox, name, Mock())
    window.current_project, window.current_feeders = build_demo_project()
    window._track_demo_text()
    window._last_calculation_project = None
    window._last_calculation_feeders = []
    window.instruments_list = []
    window._fill_project_form(window.current_project)
    window._stale = False
    window._apply_status()
    return window


def edit(app, key, value):
    widget = app.wiz_entries[key]
    widget.delete(0, "end")
    widget.insert(0, value)


def test_imported_project_survives_form_and_recalculation(app, tmp_path):
    path = tmp_path / "inputs.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Project_Spec"
    ws.append(["key", "value"])
    for item in {
        "project_name": " Imported panel ", "standard_ref": "Custom imported standard",
        "earthing_system": "TT", "panel_type": "CONTROL", "special_scenario": "FIRE_PUMP",
        "transformer_uk_pct": 8.125, "altitude_m": 2200,
        "internal_separation_form": "Form 4b", "simultaneous_motor_starts": 4,
        "spd_connection_length_m": 0.25, "nominal_voltage_v": 400.123456789,
        "plc_hmi_24vdc_power_w": 55.123456789, "target_ip": "IP65",
        "preferred_manufacturer": "IMPORTED_VENDOR",
    }.items():
        ws.append(list(item))
    ws = wb.create_sheet("Feeders_List")
    ws.append([f"column_{i}" for i in range(19)])
    ws.append(["F01", "=PWR", "+MCC1", "Test load", "MOTOR_DOL", 11, 3])
    wb.save(path)
    project, _, errors = ExcelInputManager.load_from_excel(str(path))
    assert not errors
    app.current_project = project
    app._fill_project_form(project)
    restored = app._project_from_form()
    assert restored.model_dump() == project.model_dump()
    edit(app, "wiz_voltage", "415")
    restored = app._project_from_form()
    assert restored.model_dump() == {**project.model_dump(), "nominal_voltage_v": 415}
    assert restored.earthing_system == EarthingSystem.TT
    assert restored.panel_type == PanelType.CONTROL
    assert restored.special_scenario == SpecialScenario.FIRE_PUMP


@pytest.mark.parametrize("value", ["oops", "", "NaN", "inf", "-inf", "1e999", "0", "-1"])
def test_invalid_voltage_blocks_calculation_and_old_result_exports(app, value):
    old_project = app.current_project.model_dump()
    old_results = app.last_results
    edit(app, "wiz_voltage", value)
    assert app._stale
    with pytest.raises(ValueError):
        app._project_from_form()
    app.action_recalculate()
    assert gui.messagebox.showerror.called
    assert not gui.messagebox.showinfo.called
    assert app.last_results is old_results
    assert app.current_project.model_dump() == old_project
    assert app._get_results() is None
    assert all(button.cget("state") == "disabled" for button in app._export_buttons)


def test_optional_blanks_stay_none_and_zero_is_rejected(app):
    edit(app, "wiz_ik", "")
    edit(app, "wiz_trafo", "")
    project = app._project_from_form()
    assert project.prospective_ik_ka is None
    assert project.transformer_kva is None
    edit(app, "wiz_ik", "0")
    with pytest.raises(ValueError):
        app._project_from_form()


@pytest.mark.parametrize("action", [
    "action_export_all", "action_export_report", "action_open_printable_report",
    "action_open_commercial_quote", "action_export_dv", "action_export_sld",
    "action_export_tcc", "action_export_pdf", "action_export_ctrl_svg",
    "action_export_connections", "action_export_layout", "action_save_single_svg",
    "action_save_all_svgs_folder", "action_preview_selected_svg_in_browser",
])
def test_stale_export_actions_stop_before_any_file_or_browser_action(app, monkeypatch, action):
    def unexpected(*args, **kwargs):
        pytest.fail("A stale export opened a file dialog or browser")
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", unexpected)
    monkeypatch.setattr(gui.filedialog, "askdirectory", unexpected)
    monkeypatch.setattr(gui.webbrowser, "open", unexpected)
    edit(app, "wiz_voltage", "415")
    getattr(app, action)()
    assert gui.messagebox.showwarning.called


def test_dropdown_change_marks_results_stale(app):
    widget = app.wiz_entries["wiz_earthing"]
    widget.set("TT")
    widget.cget("command")("TT")
    assert app._stale


def test_recalculation_reenables_exports_and_supports_reverting_an_edit(app):
    edit(app, "wiz_voltage", "415")
    assert app._run_calculations_and_refresh()
    assert app.current_project.nominal_voltage_v == 415
    assert not app._stale
    assert all(button.cget("state") == "normal" for button in app._export_buttons)
    edit(app, "wiz_voltage", "400")
    assert app._run_calculations_and_refresh()
    assert app.current_project.nominal_voltage_v == 400


def test_theme_and_language_preserve_uncommitted_inputs(app):
    edit(app, "wiz_project_name", "Custom project name")
    edit(app, "wiz_voltage", "invalid draft")
    edit(app, "wiz_higher_func", "==CUSTOM")
    edit(app, "wiz_install_site", "++CUSTOM")
    snapshot = {key: widget.get() for key, widget in app.wiz_entries.items()}
    for language in ("EN", "DE", "FA"):
        app._on_language_change(language)
        app._on_theme_change()
        assert {key: widget.get() for key, widget in app.wiz_entries.items()} == snapshot
        assert app._stale


def test_schematic_preview_and_all_svg_exports_render_demo_feeders(app, tmp_path):
    assert app._run_calculations_and_refresh()
    app._switch_view(4)
    assert app.tree_wires_preview.get_children()
    assert "<svg" in app.txt_svg_inspector.get("1.0", "end")
    outs, summary, _ = app.last_results
    svgs = GuiOutputBridge.generate_all_ladder_svgs(app.current_project, outs, summary)
    assert set(svgs) == {feeder.feeder_id for feeder in outs}
    assert all("<svg" in svg for svg in svgs.values())
    files = GuiOutputBridge.export_all_svgs_to_folder(str(tmp_path), app.current_project, outs, summary)
    assert len(files) == len(outs) + 1
    assert all(Path(path).stat().st_size > 0 for path in files)


def test_numeric_validation_has_all_three_translations():
    for language in ("en", "de", "fa"):
        data = json.loads((Path(gui.__file__).parent / "translations" / f"{language}.json").read_text(encoding="utf-8"))
        assert "{field}" in data["err_project_number"]


def test_manufacturer_and_spd_selection_are_not_replaced_by_import_snapshot(app):
    app.spd_menu.set(app.spd_display[app.spd_values.index("NONE")])
    manufacturer = next(value for value in app.mfg_values if value != "ANY")
    app.mfg_menu.set(app.mfg_display[app.mfg_values.index(manufacturer)])
    restored = app._project_from_form()
    assert restored.spd_class.value == "NONE"
    assert restored.preferred_manufacturer == manufacturer


def test_wire_schedule_preserves_parallel_start_and_hold_paths_without_shorting_contacts(app):
    assert app._run_calculations_and_refresh()
    feeders, summary, _ = app.last_results
    for index, feeder in enumerate(feeders, start=1):
        dto = GuiOutputBridge.to_feeder_ladder_dto(app.current_project, feeder, summary, index)
        schedule = IECLadderSvgGenerator.build_feeder_wires_and_terminals(dto)
        edges = {(row["from_pin"], row["to_pin"]) for row in schedule["wires"]}
        if dto.load_type == "MOTOR_DOL":
            assert (f"-S{index}0:12", f"-S{index}1:13") in edges
            assert (f"-S{index}0:12", f"-K{index}M:13") in edges
            terminal = f"-X2:{(index - 1) * 4 + 2}"
            assert (f"-S{index}1:14", terminal) in edges
            assert (f"-K{index}M:14", terminal) in edges
            assert (f"-S{index}1:13", f"-S{index}1:14") not in edges
        assert all(row["wire_spec"] == "" for row in schedule["wires"])
        assert all(not row["cable_tag"] for row in schedule["terminals"])


@pytest.mark.parametrize("language", ["FA", "EN", "DE"])
def test_project_fields_share_input_columns_in_every_language(app, language):
    app._on_language_change(language)
    app._toggle_advanced_fields(True)
    left = ["wiz_project_name", "wiz_higher_func", "wiz_panel_tag", "wiz_trafo",
            "wiz_ambient", "wiz_earthing", "wiz_scenario", "wiz_spare", "wiz_plc_base"]
    right = ["wiz_std_regime", "wiz_install_site", "wiz_voltage", "wiz_ik",
             "wiz_internal", "wiz_panel_type", "wiz_ip", "wiz_ks"]
    for keys in (left, right):
        columns = {app.wiz_entries[key].grid_info()["column"] for key in keys}
        assert len(columns) == 1
        assert all(app.wiz_entries[key].master is app.wiz_entries[keys[0]].master for key in keys)
    assert app.wiz_entries[left[0]].grid_info()["column"] == app.wiz_entries[right[0]].grid_info()["column"]


def test_precision_context_uses_engine_values_and_marks_stale(app):
    assert app._run_calculations_and_refresh()
    summary = app.last_results[1]
    assert app._hero_current.cget('text') == f'{summary.main_breaker.rated_current_in_a:,.1f} A'
    assert '√3' in app._formula_text.cget('text')
    edit(app, 'wiz_voltage', '415')
    assert app._formula_note.cget('text') == app._shell_copy[11]


def test_advanced_fields_keep_their_values(app):
    app._toggle_advanced_fields(True)
    edit(app, 'wiz_trafo', '1250')
    app._toggle_advanced_fields(False)
    assert app.wiz_entries['wiz_trafo'].get() == '1250'
    assert app._project_from_form().transformer_kva == 1250


def test_stepper_navigates_to_existing_views(app):
    for button, expected in zip(app._step_buttons, (1, 3, 3, 4)):
        button.invoke()
        assert app._active_view == expected


def test_equipment_and_busbar_steps_show_distinct_results(app):
    app._step_buttons[1].invoke()
    assert app._results_tabs.get() == gui.tr('tab_equipment')
    app._step_buttons[2].invoke()
    assert app._results_tabs.get() == gui.tr('tab_busbars')
    assert app._run_calculations_and_refresh()
    values = [app.tree_busbars.item(row, 'values')[1] for row in app.tree_busbars.get_children()]
    assert f'{app.last_results[1].busbar_rating_a:g} A' in values


def test_mounting_and_special_inputs_survive_language_changes(app):
    from lv_assist.models import EnclosureMounting, ScenarioInputs
    project = app.current_project.model_copy(deep=True)
    project.enclosure_mounting = EnclosureMounting.CONSOLE
    project.special_scenario = SpecialScenario.MEDICAL_IT
    project.scenario_inputs = ScenarioInputs(imd_alarm_kohm=50, insulation_kohm=120)
    app._fill_project_form(project)
    for language in ('FA', 'EN', 'DE'):
        app._on_language_change(language)
        restored = app._project_from_form()
        assert app.wiz_entries['wiz_mounting'].get() == 'CONSOLE'
        assert restored.scenario_inputs.imd_alarm_kohm == 50
        assert restored.special_scenario == SpecialScenario.MEDICAL_IT


def test_scenario_dialog_stages_validated_data_and_marks_results_stale(app):
    from lv_assist.scenario_dialog import ScenarioDialog
    project = app._project_from_form()
    project.special_scenario = SpecialScenario.UPS_CRITICAL
    app._fill_project_form(project)
    app.action_scenario_settings()
    dialog = next(widget for widget in app.winfo_children() if isinstance(widget, ScenarioDialog))
    dialog._entries['load_kw'].insert(0, '15')
    dialog._save()
    assert app._project_from_form().scenario_inputs.load_kw == 15
    assert app._stale


@pytest.mark.parametrize("language", ["EN", "DE"])
def test_language_switch_translates_demo_and_generated_results(app, language):
    app._on_language_change("FA")
    app.action_load_demo()
    old_current = app.last_results[1].design_main_current_a
    app._on_language_change(language)
    assert app.current_project.project_name == gui.tr("demo_name")
    assert app.wiz_entries["wiz_project_name"].get() == gui.tr("demo_name")
    assert app._project_input_data["project_name"] == gui.tr("demo_name")
    assert not app._stale
    assert app.last_results[1].design_main_current_a == old_current
    for index, feeder in enumerate(app.current_feeders, start=1):
        assert feeder.description == gui.tr(f"xl_d_f{index:02d}")
    for item in app.last_results[2]:
        for field in ("description", "supporting_evidence", "recommended_action"):
            assert not any("\u0600" <= c <= "\u06ff" for c in getattr(item, field))


def test_localized_options_keep_engineering_values_and_selection(app):
    app._on_language_change("EN")
    panel = app.wiz_entries["wiz_panel_type"]
    panel.set("DISTRIBUTION")
    scenario = app.wiz_entries["wiz_scenario"]
    scenario.set("FIRE_PUMP")
    app._on_project_input_change()
    for language in ("DE", "FA", "EN"):
        app._on_language_change(language)
        panel = app.wiz_entries["wiz_panel_type"]
        scenario = app.wiz_entries["wiz_scenario"]
        assert panel.get() == "DISTRIBUTION"
        assert ctk.CTkOptionMenu.get(panel) == gui.tr("panel_DISTRIBUTION")
        assert scenario.get() == "FIRE_PUMP"
        assert ctk.CTkOptionMenu.get(scenario) == gui.tr("scenario_FIRE_PUMP")
        project = app._project_from_form()
        assert project.panel_type == PanelType.DISTRIBUTION
        assert project.special_scenario == SpecialScenario.FIRE_PUMP
        assert app._stale


def test_custom_names_and_drafts_survive_language_switches(app):
    app.current_project.project_name = "نام پروژه واردشده"
    app.current_feeders[0].description = "توضیح کاربر"
    app._demo_text = {}
    app._fill_project_form(app.current_project)
    edit(app, "wiz_voltage", "415")
    for language in ("EN", "DE", "FA"):
        app._on_language_change(language)
        assert app.wiz_entries["wiz_project_name"].get() == "نام پروژه واردشده"
        assert app.current_feeders[0].description == "توضیح کاربر"
        assert app.wiz_entries["wiz_voltage"].get() == "415"
        assert app._stale


@pytest.mark.parametrize('language', ['FA', 'EN', 'DE'])
def test_localized_alignment_keeps_formulas_and_engineering_entries_readable(app, language):
    app._on_language_change(language)
    rtl = language == 'FA'
    assert app.f_entries['wiz_f_desc'].cget('justify') == ('right' if rtl else 'left')
    assert app.i_entries['wiz_i_desc'].cget('justify') == ('right' if rtl else 'left')
    assert app.wiz_entries['wiz_project_name'].cget('justify') == ('right' if rtl else 'left')
    assert app.wiz_entries['wiz_voltage'].cget('justify') == 'left'
    assert app.f_entries['wiz_f_id'].cget('justify') == 'left'
    assert app._formula_text.cget('justify') == 'left'
    if rtl:
        assert app._formula_note.cget('justify') == 'right'
        assert app._formula_note.cget('anchor') == 'e'
        assert str(app.tree_feeders.column('desc', 'anchor')) == 'e'
        assert str(app.tree_feeders.column('kw', 'anchor')) == 'center'
        assert str(app.tree_feeders.heading('desc', 'anchor')) == 'e'
        assert tuple(app.tree_feeders['displaycolumns'])[-1] == 'id'
    else:
        assert str(app.tree_feeders.column('desc', 'anchor')) == 'center'
        assert str(app.tree_feeders['displaycolumns'][0]) == '#all'


def test_persian_editor_rows_and_dynamic_device_fields_are_aligned(app):
    app._on_language_change('FA')
    editor = gui.FeederEditDialog(app, app.current_feeders[0], lambda feeder: None)
    try:
        entry = editor._entries['description'][0]
        assert entry.cget('justify') == 'right'
        assert entry.pack_info()['side'] == 'left'
        labels = [child for child in entry.master.winfo_children() if isinstance(child, ctk.CTkLabel)]
        assert labels[0].cget('anchor') == 'e'
        assert labels[0].pack_info()['side'] == 'right'
    finally:
        editor.destroy()
    device_editor = gui.DeviceEditDialog(app, None, lambda device: None)
    try:
        device_editor._on_type_changed('ENCLOSURE')
        entry = device_editor._entries['width_mm']
        assert entry.cget('justify') == 'left'
        assert entry.pack_info()['side'] == 'left'
        labels = [child for child in entry.master.winfo_children() if isinstance(child, ctk.CTkLabel)]
        assert labels[0].cget('justify') == 'right'
        assert labels[0].pack_info()['side'] == 'right'
    finally:
        device_editor.destroy()


@pytest.mark.parametrize('language', ['FA', 'EN', 'DE'])
def test_ui_titles_have_no_step_numbers_and_results_use_latin_digits(app, language):
    app._on_language_change(language)
    assert app._run_calculations_and_refresh()
    for widget in (*app._nav_buttons, *app._step_buttons, *app._export_buttons):
        assert not widget.cget('text').strip()[0].isdigit()
    for key in ('btn_template', 'btn_import', 'grp_docs', 'grp_drawings', 'html_s1'):
        assert not gui.tr(key).strip()[0].isdigit()
    texts = [label.cget('text') for label in app.kpi_labels.values()]
    texts += [app._hero_current.cget('text'), app._formula_text.cget('text')]
    texts += [str(app.tree_results_tbl.item(row, 'values')) for row in app.tree_results_tbl.get_children()]
    texts += [str(app.tree_rules.item(row, 'values')) for row in app.tree_rules.get_children()]
    assert not any(char in '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩' for text in texts for char in text)


def test_translated_numbers_are_latin_without_rewriting_user_text(app):
    app._on_language_change('FA')
    assert '15' in gui.tr('xl_d_f01')
    assert '24' in gui.tr('kpi_psu_24v')
    user_name = 'پروژه ۱۲'
    assert user_name in gui.tr('lbl_project', name=user_name, tag='+MCC1')


def test_persian_dropdown_selection_preserves_raw_code_and_cancel_is_inert(app):
    app._on_language_change('FA')
    app.deiconify()
    app._switch_view(1)
    app.update()
    menu = app.cmb_f_type
    menu.set('MOTOR_DOL')
    try:
        menu._open_dropdown_menu()
        popup = menu._persian_popup
        app.update()
        assert popup.winfo_ismapped()
        assert popup.listbox.cget('justify') == 'right'
        popup.listbox.selection_clear(0, 'end')
        popup.listbox.selection_set(1)
        popup.choose()
        assert menu.get() == menu.cget('values')[1]
        selected = menu.get()
        menu._open_dropdown_menu()
        app.update()
        menu._persian_popup.listbox.event_generate('<Escape>')
        app.update()
        assert not menu._persian_popup.winfo_exists()
        assert menu.get() == selected
        assert app.grab_current() is None
    finally:
        popup = getattr(menu, '_persian_popup', None)
        if popup is not None and popup.winfo_exists():
            popup.close()
        app.withdraw()
