from types import SimpleNamespace

import pytest

from lv_assist.catalog import CatalogRepository
from lv_assist.control_circuits import ControlCircuitGenerator
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import PrintableReportExporter
from lv_assist.i18n import tr
from lv_assist.layout import PanelLayoutGenerator
from lv_assist.models import FeederInput, LoadType, ProjectSpec
from lv_assist.outputs import SldGenerator, TccGenerator


def _calculation():
    project = ProjectSpec(project_name="SVG error test", prospective_ik_ka=22.0)
    feeders = [FeederInput(
        feeder_id="F01", description="Test feeder", load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
    )]
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    return project, feeders, outputs, summary, validations


def test_tcc_intersection_failure_is_logged_and_visible(monkeypatch, caplog):
    from lv_assist.tcc_analyzer import TccAnalyzer

    project, _, outputs, summary, _ = _calculation()
    monkeypatch.setattr(
        TccAnalyzer, "find_intersection",
        lambda *args: (_ for _ in ()).throw(RuntimeError("curve failure")),
    )

    svg = TccGenerator.generate_svg(project, outputs, summary)

    assert "intersection calculation failed" in svg
    assert "curve failure" in caplog.text
    assert "WARNING" in caplog.text


def test_html_report_shows_tcc_error_instead_of_empty_chart(monkeypatch, tmp_path, caplog):
    project, _, outputs, summary, validations = _calculation()
    monkeypatch.setattr(
        TccGenerator, "generate_svg",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("chart failure")),
    )
    path = tmp_path / "report.html"

    PrintableReportExporter.generate_html_report(
        str(path), project, outputs, summary, validations
    )

    html = path.read_text(encoding="utf-8")
    assert "TCC chart could not be generated" in html
    assert "chart failure" in caplog.text


def _check_gui_actions_show_errors(monkeypatch, actions, generators):
    import lv_assist.gui as gui

    class Dialogs:
        errors = []

        @classmethod
        def showerror(cls, *args, **kwargs):
            cls.errors.append(args)

        @staticmethod
        def showinfo(*args, **kwargs):
            pytest.fail("Success dialog shown after failed SVG export")

    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "output.svg")
    monkeypatch.setattr(gui.messagebox, "showerror", Dialogs.showerror)
    monkeypatch.setattr(gui.messagebox, "showinfo", Dialogs.showinfo)

    def fail_export(*args, **kwargs):
        raise OSError("write failed")

    for generator in generators:
        monkeypatch.setattr(generator, "generate_svg_file", fail_export)

    for action in actions:
        app = SimpleNamespace(
            _get_results=lambda: ([], object(), object()),
            current_project=object(),
        )
        action(app)

    assert len(Dialogs.errors) == len(actions)
    assert all("write failed" in str(args) for args in Dialogs.errors)
    assert Dialogs.errors[0][1] == tr("err_calc_generic", detail="write failed")


def test_gui_sld_and_tcc_exports_show_errors(monkeypatch):
    import lv_assist.gui as gui

    _check_gui_actions_show_errors(
        monkeypatch,
        (gui.LVAssistApp.action_export_sld, gui.LVAssistApp.action_export_tcc),
        (SldGenerator, TccGenerator),
    )


def test_gui_control_and_layout_exports_show_errors(monkeypatch):
    import lv_assist.gui as gui

    _check_gui_actions_show_errors(
        monkeypatch,
        (gui.LVAssistApp.action_export_ctrl_svg, gui.LVAssistApp.action_export_layout),
        (ControlCircuitGenerator, PanelLayoutGenerator),
    )
