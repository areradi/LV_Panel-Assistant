from lv_assist.bom import build_bom
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec


def _make_feeder(**overrides):
    values = {
        "feeder_id": "F01",
        "description": "Test feeder",
        "load_type": LoadType.SUB_FEEDER,
        "power_kw": 10.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _build_single(feeder, **project_kwargs):
    project = ProjectSpec(
        project_name="Cable test",
        prospective_ik_ka=25.0,
        transformer_kva=630.0,
        **project_kwargs,
    )
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, [feeder])
    bom = build_bom(project, outputs, summary)
    return bom, outputs[0], summary


def test_feeder_cable_row_present():
    bom, _, _ = _build_single(_make_feeder())
    assert len([item for item in bom if item.tag == "-W1"]) == 1


def test_cable_row_has_phase_section():
    bom, out, _ = _build_single(_make_feeder())
    cable = next(item for item in bom if item.tag == "-W1")
    assert out.selected_phase_mm2 is not None
    assert f"{out.selected_phase_mm2:g}" in cable.tech_spec
    assert "Phase" in cable.tech_spec


def test_cable_row_has_pe_section_when_available():
    bom, out, _ = _build_single(_make_feeder())
    cable = next(item for item in bom if item.tag == "-W1")
    if out.selected_pe_mm2 is not None:
        assert "PE" in cable.tech_spec
        assert f"{out.selected_pe_mm2:g}" in cable.tech_spec


def test_cable_row_has_conductor_and_insulation():
    bom, out, _ = _build_single(_make_feeder())
    cable = next(item for item in bom if item.tag == "-W1")
    assert out.conductor_material is not None
    assert out.conductor_material in cable.tech_spec
    assert out.insulation_type is not None
    assert out.insulation_type in cable.tech_spec


def test_cable_row_keeps_length_and_unit():
    bom, out, _ = _build_single(_make_feeder())
    cable = next(item for item in bom if item.tag == "-W1")
    assert cable.qty == out.cable_length_m
    assert cable.unit == "m"


def test_cable_material_has_no_catalog_part_number():
    bom, _, _ = _build_single(_make_feeder())
    cable = next(item for item in bom if item.tag == "-W1")
    assert cable.missing_part_number is True
    assert cable.part_number in ("", None)
