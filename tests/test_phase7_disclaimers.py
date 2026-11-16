import json
import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.models import FeederInput, LoadType, ProjectSpec


def _calculation():
    project = ProjectSpec(
        project_name="Disclaimer Test",
        prospective_ik_ka=25.0,
        transformer_kva=630.0,
    )
    feeders = [FeederInput(
        feeder_id="F01", description="Test feeder", load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
    )]
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    return project, feeders, outputs, summary, validations


def test_excel_sets_general_disclaimer_on_every_sheet(tmp_path):
    from lv_assist.i18n import tr

    project, feeders, outputs, summary, validations = _calculation()
    path = tmp_path / "report.xlsx"
    ExcelExporter.export_to_excel(str(path), project, outputs, summary, validations)
    wb = load_workbook(path)

    for ws in wb.worksheets:
        assert tr("disclaimer_general") in (ws.oddFooter.center.text or "")


def test_html_page_footer_contains_short_disclaimer(tmp_path):
    from lv_assist.i18n import tr

    project, feeders, outputs, summary, validations = _calculation()
    path = tmp_path / "report.html"
    PrintableReportExporter.generate_html_report(
        str(path), project, outputs, summary, validations
    )
    assert tr("disclaimer_short") in path.read_text(encoding="utf-8")


def test_design_verification_footer_contains_short_disclaimer(tmp_path):
    from lv_assist.engine import build_design_verification
    from lv_assist.exporters import DesignVerificationExporter
    from lv_assist.i18n import tr

    project, feeders, outputs, summary, validations = _calculation()
    report = build_design_verification(project, outputs, summary, validations)
    path = tmp_path / "design-verification.html"
    DesignVerificationExporter.generate_html(str(path), project, summary, report)
    assert tr("disclaimer_short") in path.read_text(encoding="utf-8")


def test_commercial_quote_contains_general_disclaimer(tmp_path):
    from lv_assist.commercial import CommercialEngine
    from lv_assist.i18n import tr

    project, feeders, outputs, summary, _ = _calculation()
    path = tmp_path / "quote.html"
    CommercialEngine.export_quote_html(str(path), project, outputs, summary)
    assert tr("disclaimer_general") in path.read_text(encoding="utf-8")


def test_bom_csv_appends_general_disclaimer(tmp_path):
    from lv_assist.bom import build_bom, export_bom_csv
    from lv_assist.i18n import i18n

    project, feeders, outputs, summary, _ = _calculation()
    path = tmp_path / "bom.csv"
    export_bom_csv(str(path), build_bom(project, outputs, summary))
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    expected = [
        [f"# DISCLAIMER ({language.upper()})", i18n._table(language)["disclaimer_general"]]
        for language in ("en", "fa", "de")
    ]
    assert rows[-3:] == expected


def test_gui_bom_csv_export_uses_csv_extension_and_utf8_sig(tmp_path, monkeypatch):
    import lv_assist.gui as gui

    project, _, outputs, summary, _ = _calculation()
    messages = []
    monkeypatch.setattr(
        gui.filedialog, "asksaveasfilename", lambda **kwargs: str(tmp_path / "bom.xlsx")
    )
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *args, **kwargs: messages.append(args))
    app = SimpleNamespace(
        _get_results=lambda: (outputs, summary, []),
        current_project=project,
    )

    gui.LVAssistApp.action_export_bom_csv(app)

    csv_path = tmp_path / "bom.csv"
    assert csv_path.exists()
    assert not (tmp_path / "bom.xlsx").exists()
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert messages


def test_gui_bom_csv_suggests_ascii_timestamped_filename(tmp_path, monkeypatch):
    import re
    import lv_assist.gui as gui

    project, _, outputs, summary, _ = _calculation()
    dialog_options = {}
    monkeypatch.setattr(
        gui.filedialog,
        "asksaveasfilename",
        lambda **kwargs: dialog_options.update(kwargs) or str(tmp_path / "bom.csv"),
    )
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *args, **kwargs: None)
    app = SimpleNamespace(
        _get_results=lambda: (outputs, summary, []),
        current_project=project,
    )

    gui.LVAssistApp.action_export_bom_csv(app)

    suggested = dialog_options["initialfile"]
    assert suggested.endswith(".csv")
    assert suggested.isascii()
    assert re.fullmatch(r"BOM_Export_[A-Za-z0-9_-]+_\d{8}_\d{4}\.csv", suggested)


def test_gui_bom_csv_shows_clear_message_when_file_is_locked(tmp_path, monkeypatch):
    import lv_assist.gui as gui
    import lv_assist.bom as bom
    from lv_assist.i18n import tr

    project, _, outputs, summary, _ = _calculation()
    monkeypatch.setattr(
        gui.filedialog, "asksaveasfilename", lambda **kwargs: str(tmp_path / "bom.csv")
    )
    errors = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    monkeypatch.setattr(
        bom, "export_bom_csv", lambda *args, **kwargs: (_ for _ in ()).throw(
            PermissionError("CSV file is open in another application")
        )
    )
    app = SimpleNamespace(
        _get_results=lambda: (outputs, summary, []),
        current_project=project,
    )

    gui.LVAssistApp.action_export_bom_csv(app)

    assert errors
    assert tr("err_csv_file_locked") in str(errors[0])


def test_bom_csv_preflights_locked_destination(tmp_path, monkeypatch):
    from pathlib import Path

    import lv_assist.bom as bom

    project, feeders, outputs, summary, _ = _calculation()
    path = tmp_path / "bom.csv"
    original_open = Path.open

    def deny_append(self, mode="r", *args, **kwargs):
        if self == path and mode == "a":
            raise PermissionError("sharing violation")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_append)
    with pytest.raises(PermissionError, match="open in another application"):
        bom.export_bom_csv(str(path), bom.build_bom(project, outputs, summary))
    assert not path.exists()


def test_all_svg_generators_include_general_disclaimer(monkeypatch):
    import xml.etree.ElementTree as ET

    from lv_assist.control_circuits import ControlCircuitGenerator
    from lv_assist.gui_output_bridge import GuiOutputBridge
    from lv_assist.iec_sld_svg import IECSldSvgGenerator
    from lv_assist.i18n import i18n, tr
    from lv_assist.layout import PanelLayoutGenerator
    from lv_assist.outputs import SldGenerator, TccGenerator

    monkeypatch.setattr(i18n, "_language", "fa")
    project, feeders, outputs, summary, _ = _calculation()
    svgs = [
        SldGenerator.generate_svg(project, outputs, summary),
        TccGenerator.generate_svg(project, outputs, summary),
        PanelLayoutGenerator.generate_svg(project, outputs, summary),
        ControlCircuitGenerator.generate_svg(project, outputs, summary),
        IECSldSvgGenerator.render_sld_svg(
            GuiOutputBridge.to_sld_dto(project, outputs, summary)
        ),
    ]
    disclaimer = tr("disclaimer_general")
    ns = {"svg": "http://www.w3.org/2000/svg"}
    parsed = [ET.fromstring(svg) for svg in svgs]
    disclaimer_nodes = []
    for root in parsed:
        nodes = [node for node in root.findall(".//svg:text", ns)
                 if "".join(node.itertext()) == disclaimer]
        assert len(nodes) == 1
        node = nodes[0]
        disclaimer_nodes.append(node)
        assert node.attrib["font-family"] == "sans-serif"
        assert node.attrib["fill"] == "#666"
        assert node.attrib["direction"] == "rtl"
        assert node.attrib["unicode-bidi"] == "embed"
        first_line = node.find("svg:tspan", ns)
        assert first_line is not None
        ltr_runs = [span for span in node.findall(".//svg:tspan", ns)
                    if span.attrib.get("direction") == "ltr"]
        assert any("IEC 61439" in "".join(span.itertext()) for span in ltr_runs)
        bounds = root.attrib.get("viewBox")
        bottom = float(bounds.split()[3]) if bounds else float(root.attrib["height"].removesuffix("px"))
        lines = node.findall("svg:tspan", ns)
        last_line_y = float(lines[-1].attrib["y"])
        assert last_line_y + float(node.attrib["font-size"]) <= bottom
        stamp = next(
            text for text in root.findall(".//svg:text", ns)
            if text.text == "PRELIMINARY: engineering review required"
        )
        assert float(first_line.attrib["y"]) - float(stamp.attrib["y"]) >= 15.0

    # Footer sits below Layout's final note.
    layout_texts = list(parsed[2].findall(".//svg:text", ns))
    layout_note = next(node for node in layout_texts if node.text == tr("lay_note"))
    layout_footer_line = disclaimer_nodes[2].find("svg:tspan", ns)
    assert float(layout_footer_line.attrib["y"]) - float(layout_note.attrib["y"]) > 17.0

    # It is below each SLD title-block rectangle, rather than inside it.
    for root, footer in ((parsed[0], disclaimer_nodes[0]), (parsed[4], disclaimer_nodes[4])):
        title_fill = "#F4F6F7" if root is parsed[0] else "#F8FAFC"
        rects = [rect for rect in root.findall(".//svg:rect", ns) if rect.attrib.get("fill") == title_fill]
        title_block = max(rects, key=lambda rect: float(rect.attrib["y"]))
        title_bottom = float(title_block.attrib["y"]) + float(title_block.attrib["height"])
        stamp = next(
            node for node in root.findall(".//svg:text", ns)
            if node.text == "PRELIMINARY: engineering review required"
        )
        assert float(stamp.attrib["y"]) - float(stamp.attrib["font-size"]) >= title_bottom
        footer_line = footer.find("svg:tspan", ns)
        assert float(footer_line.attrib["y"]) - float(footer.attrib["font-size"]) >= title_bottom


@pytest.mark.parametrize(
    ("language", "direction"), [("fa", "rtl"), ("en", "ltr"), ("de", "ltr")]
)
def test_svg_disclaimer_uses_language_direction_and_isolates_latin(monkeypatch, language, direction):
    import xml.etree.ElementTree as ET

    from lv_assist.drawing_status import preliminary_drawing
    from lv_assist.i18n import i18n

    monkeypatch.setattr(i18n, "_language", language)

    @preliminary_drawing
    def render():
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 100" height="100">'
            '<rect x="0" y="0" width="10" height="10"/></svg>'
        )

    root = ET.fromstring(render())
    disclaimer_node = next(
        node for node in root.findall(
            ".//svg:text", {"svg": "http://www.w3.org/2000/svg"}
        )
        if node.text != "PRELIMINARY: engineering review required"
    )
    assert disclaimer_node.attrib["direction"] == direction
    assert disclaimer_node.attrib["unicode-bidi"] == "embed"
    assert disclaimer_node.attrib["text-anchor"] == ("end" if language == "fa" else "start")
    if language == "fa":
        ltr_runs = [
            span for span in disclaimer_node.findall(
                ".//svg:tspan", {"svg": "http://www.w3.org/2000/svg"}
            )
            if span.attrib.get("direction") == "ltr"
        ]
        assert any("IEC 61439" in "".join(span.itertext()) for span in ltr_runs)
    assert "".join(disclaimer_node.itertext()) == i18n._table(language)["disclaimer_general"]
    assert "\u2068" not in "".join(disclaimer_node.itertext())
    assert "\u2069" not in "".join(disclaimer_node.itertext())


def test_render_bidi_text_wraps_and_preserves_ltr_runs():
    import xml.etree.ElementTree as ET

    from lv_assist.drawing_status import render_bidi_text

    text = "گواهی انطباق IEC 61439 نیست و روی ریل DIN طبق استاندارد است"
    svg_text = render_bidi_text(
        text, x=190, y=10, lang="fa", font_size=6, max_width=100, max_lines=3,
        **{"text-anchor": "end", "fill": "#666"},
    )
    root = ET.fromstring(
        f'<svg xmlns="http://www.w3.org/2000/svg">{svg_text}</svg>'
    )
    text_node = root.find("svg:text", {"svg": "http://www.w3.org/2000/svg"})
    lines = text_node.findall("svg:tspan", {"svg": "http://www.w3.org/2000/svg"})
    assert 1 < len(lines) <= 3
    assert "".join(text_node.itertext()) == text
    ltr_runs = [span for span in text_node.findall(
        ".//svg:tspan", {"svg": "http://www.w3.org/2000/svg"}
    ) if span.attrib.get("direction") == "ltr"]
    assert any("IEC 61439" in "".join(span.itertext()) for span in ltr_runs)
    assert any("DIN" in "".join(span.itertext()) for span in ltr_runs)


def test_eplan_placeholder_button_is_disabled_and_has_tooltip(monkeypatch):
    import lv_assist.gui as gui
    from lv_assist.i18n import tr

    class FakeWidget:
        def __init__(self, parent=None, **options):
            self.parent = parent
            self.options = options
            self.state = None

        def pack(self, **kwargs): pass
        def grid(self, **kwargs): pass
        def pack_forget(self): pass
        def grid_columnconfigure(self, *args, **kwargs): pass
        def configure(self, **kwargs): self.options.update(kwargs)

    widgets = []

    def make_widget(parent=None, **kwargs):
        widget = FakeWidget(parent, **kwargs)
        widgets.append(widget)
        return widget

    tips = []
    monkeypatch.setattr(gui.ctk, "CTkFont", lambda **kwargs: object())
    monkeypatch.setattr(gui.ctk, "CTkFrame", make_widget)
    monkeypatch.setattr(gui.ctk, "CTkLabel", make_widget)
    monkeypatch.setattr(gui.ctk, "CTkButton", make_widget)
    monkeypatch.setattr(gui, "ToolTip", lambda widget, text: tips.append(text))
    actions = (
        "action_export_report", "action_open_printable_report", "action_export_pdf",
        "action_export_dv", "action_open_commercial_quote", "action_export_bom_csv",
        "action_export_tcc",
        "action_export_layout", "action_export_eplan", "action_export_all",
    )
    app = SimpleNamespace(**{name: (lambda: None) for name in actions})
    app._build_schematics_preview_tab = lambda parent: None

    gui.LVAssistApp._build_view_exports(app, FakeWidget())

    eplan = next(widget for widget in widgets if widget.options.get("text") == tr("btn_eplan"))
    assert eplan.options["state"] == "disabled"
    assert eplan.options["fg_color"] == "gray"
    assert eplan.options["text_color"] == "darkgray"
    assert eplan.options["hover_color"] == "gray"
    assert tr("tip_eplan_coming_soon") in tips

    app._export_buttons = [eplan]
    app._status_lbl = FakeWidget()
    app.current_project = object()
    app._stale = False
    app.last_results = ([], object(), object())
    app._last_calc_time = "now"
    app._disabled_export_buttons = [eplan]
    app._refresh_precision_context = lambda: None
    gui.LVAssistApp._apply_status(app)
    assert eplan.options["state"] == "disabled"


def test_eplan_actions_report_that_export_is_unavailable(monkeypatch):
    import lv_assist.gui as gui

    messages = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *args, **kwargs: messages.append(args))
    for action in (
        gui.LVAssistApp.action_export_eplan,
        gui.LVAssistApp.action_export_eplan_script,
        gui.LVAssistApp.action_export_eplan_macros,
        gui.LVAssistApp.action_export_eplan_page_macros,
        gui.LVAssistApp.action_export_eplan_test_kit,
        gui.LVAssistApp.action_export_connections,
        gui.LVAssistApp.action_export_parts,
    ):
        app = SimpleNamespace()
        app._get_results = lambda: ([], object(), object())
        app._show_eplan_coming_soon = lambda: gui.LVAssistApp._show_eplan_coming_soon(app)
        action(app)
    assert len(messages) == 7
    from lv_assist.i18n import tr
    assert all(tr("tip_eplan_coming_soon") in str(message) for message in messages)


def test_disclaimer_and_eplan_tooltip_translation_parity():
    root = Path(__file__).resolve().parents[1] / "lv_assist" / "translations"
    translations = {
        language: json.loads((root / f"{language}.json").read_text(encoding="utf-8"))
        for language in ("fa", "en", "de")
    }
    keys = {"disclaimer_general", "disclaimer_short", "tip_eplan_coming_soon", "btn_bom_csv"}
    for language, data in translations.items():
        assert keys <= data.keys(), f"Missing keys in {language}: {keys - data.keys()}"
