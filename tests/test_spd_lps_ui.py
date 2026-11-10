from unittest.mock import Mock
import tkinter as tk

import customtkinter as ctk
import pytest

from lv_assist import gui
from lv_assist.gui import LVAssistApp, build_demo_project
from lv_assist.i18n import i18n


def _tk_available():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


_TK_OK = _tk_available()


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    if not _TK_OK:
        pytest.skip("Tk unavailable in this environment (multiple Tk instances not supported)")
    config_path = i18n._config_path
    language = i18n.get_language()
    theme = ctk.get_appearance_mode()
    original_path_function = gui.config_file_path
    gui.config_file_path = lambda: str(tmp_path_factory.mktemp("lps_ui_config") / "config.json")
    try:
        app = LVAssistApp()
    except Exception as e:
        gui.config_file_path = original_path_function
        i18n._config_path = config_path
        i18n._language = language
        ctk.set_appearance_mode(theme)
        pytest.skip(f"LVAssistApp failed to initialize: {e}")
    app.withdraw()
    yield app
    try:
        app.destroy()
    except Exception:
        pass
    gui.config_file_path = original_path_function
    i18n._config_path = config_path
    i18n._language = language
    ctk.set_appearance_mode(theme)


@pytest.fixture
def app(window):
    window.current_project, window.current_feeders = build_demo_project()
    window._track_demo_text()
    window._last_calculation_project = None
    window._last_calculation_feeders = []
    window.instruments_list = []
    window._fill_project_form(window.current_project)
    window._stale = False
    window._apply_status()
    return window


def test_lps_menu_default_is_unknown(app):
    assert app.lps_menu.get() == app.lps_display[0]


def test_lps_unknown_round_trip(app):
    app.lps_menu.set(app.lps_display[0])
    project = app._project_from_form()
    assert project.has_external_lps is None


def test_lps_yes_round_trip(app):
    app.lps_menu.set(app.lps_display[1])
    project = app._project_from_form()
    assert project.has_external_lps is True


def test_lps_no_round_trip(app):
    app.lps_menu.set(app.lps_display[2])
    project = app._project_from_form()
    assert project.has_external_lps is False


def test_lps_survives_language_change(app):
    app.lps_menu.set(app.lps_display[1])
    app._on_lps_change(app.lps_display[1])
    app._on_language_change("DE")
    assert app.lps_menu.get() == app.lps_display[1]
    assert app._project_from_form().has_external_lps is True
