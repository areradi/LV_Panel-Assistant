import re
from copy import deepcopy

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
    assert re.search(r"th, td\s*\{[^}]*overflow-wrap:\s*break-word", print_css)
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
    validation_table = content.split('<table class="validation-table">', 1)[1].split("</table>", 1)[0]
    assert '<td dir="auto"><bdi dir="ltr"><b>RULE-' in validation_table
    assert '<td dir="ltr">' not in validation_table


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
