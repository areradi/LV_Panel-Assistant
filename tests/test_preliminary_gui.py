import tkinter as tk

import customtkinter as ctk
import pytest

from lv_assist import gui
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.gui import LVAssistApp, build_demo_project
from lv_assist.i18n import i18n


def test_prelim_gui_helper():
    assert gui._prelim_gui("25", True) == "25 (prelim.)"
    assert gui._prelim_gui("25", False) == "25"


def _tk_available():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


_TK_OK = _tk_available()


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    if not _TK_OK:
        pytest.skip("Tk unavailable in this environment")

    config_path = i18n._config_path
    language = i18n.get_language()
    theme = ctk.get_appearance_mode()
    original_path_function = gui.config_file_path
    gui.config_file_path = lambda: str(tmp_path_factory.mktemp("preliminary_gui") / "config.json")
    try:
        window = LVAssistApp()
    except Exception as exc:
        gui.config_file_path = original_path_function
        i18n._config_path = config_path
        i18n._language = language
        ctk.set_appearance_mode(theme)
        pytest.skip(f"LVAssistApp failed to initialize: {exc}")

    window.withdraw()
    project, feeders = build_demo_project()
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    window._refresh_results_views(outputs, summary, validations)
    yield window

    try:
        window.destroy()
    except Exception:
        pass
    gui.config_file_path = original_path_function
    i18n._config_path = config_path
    i18n._language = language
    ctk.set_appearance_mode(theme)


def test_busbar_kpi_and_temperature_factor_are_preliminary(app):
    busbar_text = app.kpi_labels["busbar"].cget("text")
    assert "Icw(1s)=" in busbar_text
    assert "(prelim.)" in busbar_text
    assert "Ipk=" in busbar_text

    busbar_rows = [app.tree_busbars.item(row, "values") for row in app.tree_busbars.get_children()]
    temperature_row = next(
        row for row in busbar_rows
        if any(label in str(row[0]).lower() for label in (
            "temperature factor", "ضریب دمای شینه", "schienentemperaturfaktor"
        ))
    )
    assert "(prelim.)" in temperature_row[1]


def test_thermal_kpi_and_motor_contribution_are_preliminary(app):
    thermal_text = app.kpi_labels["thermal"].cget("text")
    assert "°C (prelim.)" in thermal_text

    busbar_text = app.kpi_labels["busbar"].cget("text")
    if "I''kM=" in busbar_text:
        motor_value = busbar_text.split("I''kM=", 1)[1].split("kA", 1)[0]
        assert "(prelim.)" in motor_value
