import re
from copy import deepcopy
from types import SimpleNamespace

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import PrintableReportExporter, _prelim
from lv_assist.models import DataQuality, FeederInput, LoadType, ProjectSpec


def _make_project(**overrides):
    values = {
        "project_name": "HTML prelim test",
        "prospective_ik_ka": 25.0,
        "transformer_kva": 630.0,
    }
    values.update(overrides)
    return ProjectSpec(**values)


def _make_feeder(**overrides):
    values = {
        "feeder_id": "F01",
        "description": "Feeder",
        "load_type": LoadType.SUB_FEEDER,
        "power_kw": 5.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _render(tmp_path, project, feeders=None, protection_quality=None):
    feeders = feeders or [_make_feeder()]
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, validations = engine.process_project(project, feeders)
    if protection_quality is not None and outputs[0].selected_protection is not None:
        outputs[0].selected_protection = deepcopy(outputs[0].selected_protection)
        outputs[0].selected_protection.data_quality = protection_quality
    path = tmp_path / "report.html"
    PrintableReportExporter.generate_html_report(
        str(path), project, outputs, summary, validations
    )
    return path.read_text(encoding="utf-8"), outputs, summary


def test_busbar_icw_and_ipk_are_marked_and_ipk_is_visible(tmp_path):
    content, _, summary = _render(tmp_path, _make_project())
    assert f"Icw(1s)={_prelim(f'{summary.busbar_icw_1s_ka:g}', True)} kA" in content
    assert f"Ipk={_prelim(f'{summary.busbar_ipk_ka:g}', True)} kA" in content


def test_transformer_ik_is_marked_but_explicit_ik_is_not(tmp_path):
    estimated, _, _ = _render(
        tmp_path, _make_project(prospective_ik_ka=None, transformer_kva=630.0)
    )
    assert re.search(r"Ik: [\d.]+ kA \(prelim\.\)", estimated)

    explicit, _, _ = _render(tmp_path, _make_project(prospective_ik_ka=25.0))
    assert re.search(r"Ik: 25(?:\.0)? kA(?: \(prelim\.\))?", explicit)
    assert not re.search(r"Ik: 25(?:\.0)? kA \(prelim\.\)", explicit)


def test_icu_marker_follows_catalog_quality_and_keeps_format(tmp_path):
    verified, _, _ = _render(
        tmp_path, _make_project(), protection_quality=DataQuality.REAL_VERIFIED
    )
    assert re.search(r"Icu: [\d.]+ kA @ 400\.0V", verified)
    assert not re.search(r"Icu: [\d.]+ kA @ 400\.0V \(prelim\.\)", verified)

    estimated, _, _ = _render(
        tmp_path, _make_project(), protection_quality=DataQuality.ESTIMATED
    )
    assert re.search(r"Icu: [\d.]+ kA @ 400\.0V \(prelim\.\)", estimated)


def test_cable_derating_and_pe_basis_are_marked(tmp_path):
    content, outputs, _ = _render(tmp_path, _make_project())
    feeder = outputs[0]
    for value in (feeder.cable_temp_factor_k1, feeder.cable_grouping_factor_k2,
                  feeder.cable_total_derating_k):
        assert _prelim(f"{value:g}", True) in content
    assert feeder.clearing_time_s is not None
    assert _prelim(feeder.pe_basis_str, True) in content


def test_estimated_internal_temperature_is_marked(tmp_path):
    content, _, summary = _render(tmp_path, _make_project())
    assert summary.estimated_internal_temp_c is not None
    temperature = f"{summary.estimated_internal_temp_c}°C"
    assert _prelim(temperature, True) in content


def test_html_has_preliminary_disclaimer(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    assert '<div class="disclaimer"' in content
    assert "PRELIMINARY:" in content
    assert "IEC 61439" in content
    assert "qualified engineer" in content


def test_print_wraps_table_text_and_has_no_footer_rule(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]
    assert re.search(r"td, th\s*\{[^}]*overflow-wrap:\s*break-word", print_css)
    assert re.search(r"\.cell-wrap\s*\{[^}]*overflow-wrap:\s*anywhere", print_css)
    assert "max-width: 100%" in print_css
    footer = re.search(r"\.page-footer\s*\{([^}]+)\}", print_css).group(1)
    assert "position: fixed" in footer
    assert "bottom: 0" in footer
    assert "border-top" not in footer


def test_report_isolates_technical_text_in_mixed_direction_cells(tmp_path):
    content, _, _ = _render(
        tmp_path, _make_project(), [_make_feeder(description="شرح Feeder F01")]
    )
    assert '<td class="cell-wrap" dir="auto">شرح Feeder F01</td>' in content
    assert '<td dir="auto"><b><bdi dir="ltr">F01</bdi>' in content
    assert '<td dir="auto"><small><bdi dir="ltr">Iz = ' in content
    assert "<bdi dir=\"ltr\">" in content
    validation_table = content.split('<table class="validation-table">', 1)[1].split("</table>", 1)[0]
    assert '<td dir="auto"><bdi dir="ltr"><b>RULE-' in validation_table
    assert '<td dir="ltr">' not in validation_table


def test_calculation_trace_has_balanced_rows_and_scoped_repeat_header(tmp_path):
    feeders = [_make_feeder(feeder_id="F01"), _make_feeder(feeder_id="F02")]
    content, _, _ = _render(tmp_path, _make_project(), feeders)
    trace = content.split('<table class="trace-table">', 1)[1].split("</table>", 1)[0]
    tbody = trace.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    assert trace.count("<thead>") == trace.count("</thead>") == 1
    assert trace.count("<tbody>") == trace.count("</tbody>") == 1
    assert tbody.count("<tr>") == tbody.count("</tr>") == len(feeders)
    assert tbody.count("<td ") == len(feeders) * 9
    assert re.search(r"\.feeder-table thead, \.trace-table thead[^\{]*\{ display: table-header-group; \}", print_css)
    assert not re.search(r"(?m)^\s*thead\s*\{", print_css)


def test_print_tcc_has_scalable_viewport(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    assert '<div class="tcc-chart" dir="ltr"><svg ' in content
    assert 'viewBox="0 0 1180 720"' in content
    assert 'preserveAspectRatio="xMidYMid meet"' in content


def test_report_escapes_plain_ampersand_once(tmp_path):
    content, _, _ = _render(tmp_path, _make_project(), [
        _make_feeder(description="Cables & Accessories"),
    ])
    assert "Cables &amp; Accessories" in content
    assert "Cables &amp;amp; Accessories" not in content


def test_print_allows_signature_to_flow_after_summary_and_disclaimer(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    signature = re.search(r"\.signature-block\s*\{([^}]*)\}", print_css)
    assert signature
    assert "break-inside: avoid" not in signature.group(1)
    assert "page-break-inside: avoid" not in signature.group(1)

    for selector in (".summary-box", ".disclaimer"):
        rule = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", print_css)
        assert rule, f"missing print rule for {selector}"
        assert "break-inside: avoid" in rule.group(1)
        assert "page-break-inside: avoid" in rule.group(1)
        assert "margin-top: 0" in rule.group(1)


def test_print_table_headers_use_light_ink_friendly_colors(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]
    header = re.search(r"(?m)^\s*th\s*\{([^}]*)\}", print_css)

    assert header
    assert "background-color: #e0e0e0" in header.group(1)
    assert "color: #000" in header.group(1)
    assert "-webkit-print-color-adjust: exact" in header.group(1)
    assert "print-color-adjust: exact" in header.group(1)


def test_print_assumption_json_wraps_inside_its_cell(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    assert 'class="assumption-json"' in content
    json_cell = re.search(r"\.assumption-json\s*\{([^}]*)\}", print_css)
    assert json_cell
    assert "word-break: break-all" in json_cell.group(1)
    assert "font-size: 6pt" in json_cell.group(1)
    assert "max-width:" in json_cell.group(1)
    assert "overflow: hidden" not in json_cell.group(1)


def test_design_verification_print_groups_conclusion_and_signatures(tmp_path):
    from lv_assist.engine import build_design_verification
    from lv_assist.exporters import DesignVerificationExporter

    project = _make_project()
    feeders = [_make_feeder()]
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    report = build_design_verification(project, outputs, summary, validations)
    path = tmp_path / "design-verification.html"
    DesignVerificationExporter.generate_html(str(path), project, summary, report)
    content = path.read_text(encoding="utf-8")
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    assert '<div class="conclusion-box summary-box">' in content
    assert '<div class="signature-block">\n<h2>' in content
    signature_rule = re.search(r"\.signature-block\s*\{([^}]*)\}", print_css)
    assert signature_rule
    assert "break-inside: avoid" not in signature_rule.group(1)
    summary_rule = re.search(r"\.summary-box, \.conclusion-box\s*\{([^}]*)\}", print_css)
    assert summary_rule
    assert "break-inside: avoid" in summary_rule.group(1)
    assert "background-color: #e0e0e0" in print_css
    assert re.search(r"tr\s*\{[^}]*break-inside:\s*auto", print_css)
    assert re.search(r"td,\s*th\s*\{[^}]*break-inside:\s*avoid", print_css)
    assert "orphans: 3; widows: 3" in print_css
    assert '<td dir="auto" style="text-align:center;"><b><bdi dir="ltr">' in content
    assert '<td dir="ltr">' not in content


def test_commercial_quote_keeps_totals_together_and_bom_columns_wrappable(tmp_path):
    from lv_assist.commercial import CommercialEngine

    project = _make_project()
    feeders = [_make_feeder()]
    outputs, summary, _ = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    path = tmp_path / "quote.html"
    CommercialEngine.export_quote_html(str(path), project, outputs, summary)
    content = path.read_text(encoding="utf-8")
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    totals = re.search(r"\.totals\s*\{([^}]*)\}", print_css)
    assert totals
    assert "break-inside: avoid" in totals.group(1)
    assert "page-break-inside: avoid" in totals.group(1)

    bom_cells = re.search(r"\.bom-table\s+th,\s*\.bom-table\s+td\s*\{([^}]*)\}", print_css)
    assert bom_cells
    assert "word-break: normal" in bom_cells.group(1)
    assert "overflow-wrap: break-word" in bom_cells.group(1)
    assert "background-color: #e0e0e0" in print_css
    assert re.search(r"tr\s*\{[^}]*break-inside:\s*auto", print_css)
    assert re.search(r"td,\s*th\s*\{[^}]*break-inside:\s*avoid", print_css)
    assert "orphans: 3; widows: 3" in print_css
    assert 'class="bom-table"' in content
    assert '<table class="totals">' in content


def _prepare_quote_with_unpriced_item(monkeypatch):
    import lv_assist.commercial as commercial

    device = SimpleNamespace(
        part_number="CAT-1", series="Test series", device_type="MCB",
        manufacturer="Test maker",
    )
    rows = [
        SimpleNamespace(
            func_loc="", tag="-Q1", category="Protection", device=device,
            description="Catalog breaker", tech_spec="", qty=2.0, unit="pcs",
            quote_exclude=False,
        ),
        SimpleNamespace(
            func_loc="", tag="-KX", category="Control", device=None,
            description="Unpriced auxiliary", tech_spec="selection TBD", qty=1.0,
            unit="pcs", quote_exclude=False,
        ),
    ]

    class FakeCatalogRepository:
        def __init__(self, *args, **kwargs):
            pass

        def list_prices(self):
            return {"CAT-1": {"unit_price": 12.5, "source": "MANUAL"}}

    monkeypatch.setattr(commercial, "require_current_calculation", lambda *args: None)
    monkeypatch.setattr(commercial, "seed_default_catalog_prices", lambda **kwargs: 0)
    monkeypatch.setattr(commercial, "CatalogRepository", FakeCatalogRepository)
    monkeypatch.setattr(commercial, "build_bom", lambda *args: rows)

    project = SimpleNamespace(
        project_name="Quote test", panel_tag="P-1", standard_ref="IEC test"
    )
    summary = SimpleNamespace(
        recommended_busbar_spec="20 x 5 mm", estimated_panel_width_mm=800.0,
        busbar_required_supports=2,
    )
    quote = commercial.CommercialEngine.build_quote(project, [], summary)
    return commercial, project, summary, quote


def test_tbd_prices_are_none_and_excluded_from_quote_subtotal(monkeypatch):
    _, _, _, quote = _prepare_quote_with_unpriced_item(monkeypatch)

    unpriced = [line for line in quote.lines if line.price_source == "TBD"]
    assert len(unpriced) == 1
    assert unpriced[0].unit_price is None
    assert unpriced[0].total_price is None
    assert quote.equipment_subtotal == 25.0
    assert quote.subtotal_net == (
        quote.equipment_subtotal + quote.busbar_copper_cost
        + quote.wiring_and_accessories_cost + quote.engineering_and_fat_cost
    )


def test_quote_html_marks_tbd_shows_separate_qty_unit_and_print_header(monkeypatch, tmp_path):
    commercial, project, summary, quote = _prepare_quote_with_unpriced_item(monkeypatch)
    path = tmp_path / "quote.html"
    commercial.CommercialEngine.export_quote_html(str(path), project, [], summary)
    content = path.read_text(encoding="utf-8")
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    assert (
        'توجه: <bdi dir="ltr">1</bdi> قلم قیمت‌گذاری نشده‌اند و در جمع کل لحاظ نشده‌اند.'
        in content
    )
    assert "—" in content
    assert 'colspan="2">مبالغ (EUR)</th>' in content
    assert '<th rowspan="2">تعداد</th><th rowspan="2">واحد</th>' in content
    assert ".bom-table thead { display: table-header-group; }" in print_css
    table_body = content.split('<tbody>', 1)[1].split('</tbody>', 1)[0]
    assert '<bdi dir="ltr">2</bdi></td>' in table_body
    assert '<bdi dir="auto">pcs</bdi>' in table_body
    assert "12.50 EUR" not in table_body
    assert '<td dir="ltr">' not in table_body
    assert quote.lines[0].unit_price == 12.5


def test_quote_bom_uses_content_sized_columns_and_scopes_header_repeat(monkeypatch, tmp_path):
    commercial, project, summary, _ = _prepare_quote_with_unpriced_item(monkeypatch)
    path = tmp_path / "quote-print-layout.html"
    commercial.CommercialEngine.export_quote_html(str(path), project, [], summary)
    content = path.read_text(encoding="utf-8")
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    table_rule = re.search(r"\.bom-table\s*\{([^}]*)\}", print_css)
    assert table_rule
    assert "table-layout: auto" in table_rule.group(1)
    assert "table-layout: fixed" not in table_rule.group(1)
    assert ".bom-table thead { display: table-header-group; }" in print_css
    assert not re.search(r"(?m)^\s*thead\s*\{", print_css)
    assert "width: 100%" in table_rule.group(1)
    assert "padding: 3px 4px" in print_css
    assert "<colgroup>" not in content


def test_printable_reports_use_bdi_for_ltr_values_and_auto_for_text(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    assert '<bdi dir="ltr">F01</bdi>' in content
    assert '<td dir="auto"><bdi dir="ltr">' in content
    assert '<td dir="ltr">' not in content


def test_design_verification_exporter_is_declared_once():
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "lv_assist" / "exporters.py"
    text = source.read_text(encoding="utf-8")
    assert text.count("class DesignVerificationExporter:") == 1


def test_print_css_allows_long_rows_to_break_and_keeps_cells_intact(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]

    assert re.search(r"tr\s*\{[^}]*break-inside:\s*auto", print_css)
    assert re.search(r"td,\s*th\s*\{[^}]*break-inside:\s*avoid", print_css)
    assert re.search(r"table\s*\{[^}]*orphans:\s*3;[^}]*widows:\s*3", print_css)
    assert re.search(r"p,\s*blockquote\s*\{[^}]*orphans:\s*2;[^}]*widows:\s*2", print_css)


def test_assumption_table_cells_wrap_without_changing_table_display(tmp_path):
    content, _, _ = _render(tmp_path, _make_project())
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]
    cells = re.search(r"\.assumptions-table td\s*\{([^}]*)\}", print_css)

    assert cells
    assert "white-space: normal" in cells.group(1)
    assert "overflow-wrap: break-word" in cells.group(1)
    assert not re.search(r"(?:tr|table)\s*\{[^}]*display:\s*(?:flex|grid)", print_css)


def test_design_verification_signature_has_no_forced_break_or_large_top_margin(tmp_path):
    from lv_assist.engine import build_design_verification
    from lv_assist.exporters import DesignVerificationExporter

    project = _make_project()
    feeders = [_make_feeder()]
    outputs, summary, validations = EngineeringEngine(
        CatalogRepository.get_default_catalog()
    ).process_project(project, feeders)
    report = build_design_verification(project, outputs, summary, validations)
    path = tmp_path / "signature-flow.html"
    DesignVerificationExporter.generate_html(str(path), project, summary, report)
    content = path.read_text(encoding="utf-8")
    print_css = content.split("@media print {", 1)[1].split("</style>", 1)[0]
    signature = re.search(r"\.signature-block\s*\{([^}]*)\}", print_css)

    assert signature
    assert "break-before: auto" in signature.group(1)
    assert "page-break-before: auto" in signature.group(1)
    assert "break-inside: auto" in signature.group(1)
    assert "margin-top: 0" in signature.group(1)


def test_report_tables_and_trace_cells_are_balanced(tmp_path):
    feeders = [_make_feeder(feeder_id="F01"), _make_feeder(feeder_id="F02")]
    content, _, _ = _render(tmp_path, _make_project(), feeders)

    assert content.count("<table") == content.count("</table>")
    footer_index = content.index('<div class="page-footer">')
    assert footer_index > content.rfind("</table>", 0, footer_index)

    for _, table in re.findall(r"<table([^>]*)>(.*?)</table>", content, flags=re.DOTALL):
        head = re.search(r"<thead>(.*?)</thead>", table, flags=re.DOTALL)
        body = re.search(r"<tbody>(.*?)</tbody>", table, flags=re.DOTALL)
        if not head or not body:
            continue
        header_row = re.search(r"<tr\b[^>]*>(.*?)</tr>", head.group(1), flags=re.DOTALL)
        assert header_row
        header_cells = len(re.findall(r"<th\b", header_row.group(1)))
        for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", body.group(1), flags=re.DOTALL):
            assert len(re.findall(r"<td\b", row)) == header_cells


def test_pdf_export_disables_chrome_native_header_and_footer(monkeypatch, tmp_path):
    from pathlib import Path
    from lv_assist.outputs import PdfExporter

    monkeypatch.setattr(PdfExporter, "_find_browser", staticmethod(lambda: "fake-chrome"))
    seen_args = []

    def fake_run(args, **kwargs):
        seen_args.extend(args)
        pdf_arg = next(arg for arg in args if arg.startswith("--print-to-pdf="))
        Path(pdf_arg.split("=", 1)[1]).write_bytes(b"%PDF-test")

    monkeypatch.setattr("lv_assist.outputs.subprocess.run", fake_run)
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body>test</body></html>", encoding="utf-8")

    assert PdfExporter.export_html_to_pdf(str(html_path), str(pdf_path))
    assert "--no-pdf-header-footer" in seen_args
