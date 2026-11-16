from types import SimpleNamespace

import pytest

from lv_assist import gui
from lv_assist.calculation_state import StaleCalculationStateError
from lv_assist.control_circuits import ControlCircuitGenerator
from lv_assist.exporters import PrintableReportExporter
from lv_assist.i18n import tr
from lv_assist.layout import PanelLayoutGenerator
from lv_assist.outputs import SldGenerator
from lv_assist.outputs import TccGenerator


def _fake_app():
    return SimpleNamespace(
        _get_results=lambda: ([object()], object(), object()),
        current_project=object(),
        _mark_stale=lambda: None,
        _prompt_export_guardrail_dialog=lambda callback: callback(),
    )


def test_svg_and_pdf_exports_show_specific_stale_message(monkeypatch):
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "out.svg")
    errors = []
    monkeypatch.setattr(
        gui.messagebox, "showerror",
        lambda title, msg, **kwargs: errors.append((title, msg)),
    )
    monkeypatch.setattr(
        gui.messagebox, "showinfo",
        lambda *args, **kwargs: pytest.fail("Success shown on stale error"),
    )

    def fail_stale(*args, **kwargs):
        raise StaleCalculationStateError("stale")

    for generator in (SldGenerator, TccGenerator, ControlCircuitGenerator, PanelLayoutGenerator):
        monkeypatch.setattr(generator, "generate_svg_file", fail_stale)
    monkeypatch.setattr(
        PrintableReportExporter, "generate_html_report", fail_stale
    )
    for action in (
        gui.LVAssistApp.action_export_sld,
        gui.LVAssistApp.action_export_tcc,
        gui.LVAssistApp.action_export_ctrl_svg,
        gui.LVAssistApp.action_export_layout,
        gui.LVAssistApp.action_export_pdf,
    ):
        action(_fake_app())

    assert errors == [(tr("msg_stale_title"), tr("msg_stale_export"))] * 5


def test_sld_export_stale_marks_stale(monkeypatch):
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "out.svg")
    monkeypatch.setattr(
        SldGenerator,
        "generate_svg_file",
        lambda *args: (_ for _ in ()).throw(StaleCalculationStateError("stale")),
    )
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *args, **kwargs: None)

    marked = []
    app = _fake_app()
    app._mark_stale = lambda: marked.append(True)
    gui.LVAssistApp.action_export_sld(app)

    assert marked == [True]


def test_sld_export_generic_error_keeps_generic_message(monkeypatch):
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "out.svg")
    monkeypatch.setattr(
        SldGenerator,
        "generate_svg_file",
        lambda *args: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    errors = []
    monkeypatch.setattr(
        gui.messagebox, "showerror",
        lambda title, msg, **kwargs: errors.append((title, msg)),
    )

    gui.LVAssistApp.action_export_sld(_fake_app())

    assert errors[0][0] == tr("msg_error")
    assert "write failed" in errors[0][1]
