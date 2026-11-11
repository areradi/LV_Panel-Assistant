from lv_assist.bom import CATEGORIES, build_bom
from lv_assist.catalog import CatalogRepository
from lv_assist.commercial import CommercialEngine
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec


def _make_motor_project():
    project = ProjectSpec(
        project_name="Terminal test",
        prospective_ik_ka=25.0,
        transformer_kva=630.0,
    )
    feeder = FeederInput(
        feeder_id="F01",
        description="Motor feeder",
        load_type=LoadType.MOTOR_DOL,
        power_kw=5.0,
    )
    return project, [feeder]


def _build(project, feeders):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders)
    return build_bom(project, outputs, summary), outputs, summary


def test_terminal_row_exists_for_motor_feeder():
    project, feeders = _make_motor_project()
    bom, _, _ = _build(project, feeders)
    terminal_rows = [item for item in bom if item.category == CATEGORIES["TERMINALS"]]
    assert terminal_rows


def test_terminal_row_has_pin_count():
    project, feeders = _make_motor_project()
    bom, _, _ = _build(project, feeders)
    terminal_rows = [item for item in bom if item.category == CATEGORIES["TERMINALS"]]
    assert terminal_rows
    for row in terminal_rows:
        assert row.qty is not None and row.qty >= 1
        assert row.unit == "pcs"


def test_terminal_row_is_informational_and_excluded_from_quote():
    project, feeders = _make_motor_project()
    bom, outputs, summary = _build(project, feeders)
    terminal_rows = [item for item in bom if item.category == CATEGORIES["TERMINALS"]]
    assert terminal_rows
    assert all(item.quote_exclude for item in terminal_rows)
    quote = CommercialEngine.build_quote(project, outputs, summary)
    terminal_tags = {item.tag for item in terminal_rows}
    for line in quote.lines:
        if line.category != "Wiring & Terminals":
            assert not any(tag in line.tag for tag in terminal_tags)


def test_terminal_spec_marks_missing_selection():
    project, feeders = _make_motor_project()
    bom, _, _ = _build(project, feeders)
    terminal_rows = [item for item in bom if item.category == CATEGORIES["TERMINALS"]]
    assert terminal_rows
    assert all("PENDING_DATA" in item.tech_spec for item in terminal_rows)
    assert all(item.missing_part_number for item in terminal_rows)


def test_aggregate_wiring_and_terminals_quote_line_remains():
    project, feeders = _make_motor_project()
    bom, outputs, summary = _build(project, feeders)
    quote = CommercialEngine.build_quote(project, outputs, summary)
    assert any(line.category == "Wiring & Terminals" for line in quote.lines)
