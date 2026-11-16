from lv_assist.bom import build_bom
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec, SpdClass


def _make_project(n=3, spd=False):
    project = ProjectSpec(
        project_name=f"BOM test {n}",
        prospective_ik_ka=25.0,
        transformer_kva=630.0,
        spd_class=SpdClass.T2 if spd else SpdClass.NONE,
    )
    feeders = [
        FeederInput(
            feeder_id=f"F{i + 1:02d}",
            description=f"Feeder {i + 1}",
            load_type=LoadType.SUB_FEEDER,
            power_kw=10.0,
        )
        for i in range(n)
    ]
    return project, feeders


def _build(project, feeders):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders)
    return build_bom(project, outputs, summary), summary


def test_bom_contains_phase_busbar():
    project, feeders = _make_project()
    bom, summary = _build(project, feeders)
    items = [item for item in bom if item.tag == "-BUS-PH"]
    assert len(items) == 1
    assert items[0].category == "Busbar"
    assert summary.recommended_busbar_spec in items[0].tech_spec
    assert f"Icw={summary.busbar_icw_1s_ka:g}kA/1s" in items[0].tech_spec
    assert f"Ipk={summary.busbar_ipk_ka:g}kA" in items[0].tech_spec


def test_bom_contains_pe_busbar():
    project, feeders = _make_project()
    bom, summary = _build(project, feeders)
    items = [item for item in bom if item.tag == "-BUS-PE"]
    assert len(items) == 1
    assert summary.recommended_pe_busbar_spec in items[0].tech_spec


def test_bom_contains_incoming_cable():
    project, feeders = _make_project()
    bom, summary = _build(project, feeders)
    items = [item for item in bom if item.tag == "-W-IN"]
    assert len(items) == 1
    assert items[0].category == "Cable"
    assert summary.recommended_incoming_cable_str in items[0].tech_spec


def test_unknown_busbar_length_is_none():
    project, feeders = _make_project()
    bom, summary = _build(project, feeders)
    phase = next(item for item in bom if item.tag == "-BUS-PH")
    assert phase.qty == summary.busbar_length_m
    if summary.busbar_length_m is None:
        assert phase.notes == "length TBD"


def test_unknown_pe_busbar_length_is_none():
    project, feeders = _make_project()
    bom, summary = _build(project, feeders)
    pe = next(item for item in bom if item.tag == "-BUS-PE")
    assert pe.qty == (summary.pe_busbar_length_m or summary.busbar_length_m)
    if summary.pe_busbar_length_m is None and summary.busbar_length_m is None:
        assert pe.notes == "length TBD"


def test_unknown_incoming_cable_length_is_none():
    project, feeders = _make_project()
    bom, _ = _build(project, feeders)
    incomer = next(item for item in bom if item.tag == "-W-IN")
    assert incomer.qty is None
    assert incomer.notes == "length TBD"


def test_new_bom_tags_are_unique():
    project, feeders = _make_project(spd=True)
    bom, _ = _build(project, feeders)
    tags = [item.tag for item in bom if item.tag]
    assert len(tags) == len(set(tags))


def test_bom_excel_contains_busbars_and_incoming_cable(tmp_path):
    from openpyxl import load_workbook
    from lv_assist.bom import export_bom_excel

    project, feeders = _make_project()
    bom, _ = _build(project, feeders)
    out = tmp_path / "bom.xlsx"
    export_bom_excel(str(out), bom)
    rows = list(load_workbook(out)["04_BOM"].iter_rows(min_row=2, values_only=True))
    tags = {row[1] for row in rows}
    assert {"'-BUS-PH", "'-BUS-PE", "'-W-IN"} <= tags


def test_build_quote_skips_none_qty_items():
    from lv_assist.commercial import CommercialEngine

    project, feeders = _make_project()
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders)
    quote = CommercialEngine.build_quote(project, outputs, summary)
    assert quote is not None


def test_build_quote_excludes_none_qty_lines():
    from lv_assist.commercial import CommercialEngine

    project, feeders = _make_project()
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders)
    quote = CommercialEngine.build_quote(project, outputs, summary)
    for line in quote.lines:
        assert line.tag not in {"-BUS-PH", "-BUS-PE", "-W-IN"}
