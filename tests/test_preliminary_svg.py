import xml.etree.ElementTree as ET

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.iec_sld_svg import IECSldSvgGenerator, SLDFeederDTO, SLDPanelDTO
from lv_assist.i18n import tr
from lv_assist.models import DataQuality, FeederInput, LoadType, ProjectSpec
from lv_assist.outputs import SldGenerator, TccGenerator


_SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


def _make_project(**overrides):
    values = {
        "project_name": "SVG prelim test",
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


def _run(project, feeders=None):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders or [_make_feeder()])
    return outputs, summary


def test_prelim_out_helper():
    from lv_assist.outputs import _prelim_out

    assert _prelim_out("25", True) == "25 (prelim.)"
    assert _prelim_out("25", False) == "25"


def test_sld_ik_marked_when_estimated():
    project = _make_project(prospective_ik_ka=None, transformer_kva=630.0)
    outputs, summary = _run(project)
    svg = SldGenerator.generate_svg(project, outputs, summary)
    assert f"Ik″={summary.ik_used_ka:g} kA (prelim.)" in svg


def test_sld_ik_not_marked_when_explicit():
    project = _make_project(prospective_ik_ka=25.0)
    outputs, summary = _run(project)
    svg = SldGenerator.generate_svg(project, outputs, summary)
    ik_label = f"Ik″={summary.ik_used_ka:g} kA"
    assert ik_label in svg
    assert f"{ik_label} (prelim.)" not in svg


def test_tcc_ik_estimated_marked():
    project = _make_project(prospective_ik_ka=None, transformer_kva=630.0)
    outputs, summary = _run(project)
    svg = TccGenerator.generate_svg(project, outputs, summary)
    assert f"{tr('tcc_ik')} {summary.ik_used_ka} kA (prelim.)" in svg


def test_tcc_ik_explicit_not_marked():
    project = _make_project(prospective_ik_ka=22.0)
    outputs, summary = _run(project)
    svg = TccGenerator.generate_svg(project, outputs, summary)
    ik_label = f"{tr('tcc_ik')} {summary.ik_used_ka} kA"
    assert ik_label in svg
    assert f"{ik_label} (prelim.)" not in svg


def _make_sld_dto(**overrides):
    values = {
        "project_name": "SVG prelim test",
        "panel_tag": "+MCC1",
        "standard_ref": "IEC 61439-2",
        "nominal_voltage_v": 400.0,
        "frequency_hz": 50.0,
        "earthing_system": "TN-S",
        "prospective_ik_ka": 25.0,
        "main_breaker_part": "MAIN",
        "main_breaker_in_a": 100.0,
        "main_breaker_icu_ka": None,
        "design_main_current_a": 80.0,
        "busbar_spec": "Cu 20x10",
        "pe_busbar_spec": "Cu 10x5",
        "incoming_cable_spec": "4C 35 mm²",
        "feeders": [],
    }
    values.update(overrides)
    return SLDPanelDTO(**values)


def test_iec_sld_dto_preliminary_flags_default_false():
    dto = _make_sld_dto()
    assert dto.ik_is_preliminary is False
    assert dto.main_icu_is_preliminary is False
    assert dto.feeder_icu_preliminary == {}


def test_iec_sld_marks_preliminary_ik_and_icu_values():
    feeder = SLDFeederDTO(
        feeder_id="F01",
        func_tag="=PWR",
        loc_tag="+MCC1",
        description="Feeder",
        load_type="SUB_FEEDER",
        power_kw=5.0,
        design_current_ib_a=8.0,
        protection_tag="-Q1",
        protection_part="FEEDER",
        protection_in_a=16.0,
        protection_icu_ka=25.0,
        cable_designation="Cu 4C 4 mm²",
        cable_length_m=25.0,
        voltage_drop_pct=1.0,
        selectivity_status="PRELIMINARY",
    )
    dto = _make_sld_dto(
        ik_is_preliminary=True,
        main_breaker_icu_ka=36.0,
        main_icu_is_preliminary=True,
        feeder_icu_preliminary={"F01": True},
        feeders=[feeder],
    )
    svg = IECSldSvgGenerator.render_sld_svg(dto)
    assert "Ik'' = 25 kA (prelim.)" in svg
    assert "Icu = 36 kA (prelim.)" in svg
    assert "25kA (prelim.)" in svg


def test_bridge_populates_ik_and_icu_quality_flags():
    project = _make_project(prospective_ik_ka=None, transformer_kva=630.0)
    outputs, summary = _run(project)
    assert summary.main_breaker is not None
    assert outputs[0].selected_protection is not None
    summary.main_breaker.data_quality = DataQuality.ESTIMATED
    outputs[0].selected_protection.data_quality = DataQuality.ESTIMATED

    dto = GuiOutputBridge.to_sld_dto(project, outputs, summary)
    assert dto.ik_is_preliminary is True
    assert dto.main_icu_is_preliminary is True
    assert dto.feeder_icu_preliminary["F01"] is True

    summary.main_breaker.data_quality = DataQuality.REAL_VERIFIED
    outputs[0].selected_protection.data_quality = DataQuality.REAL_VERIFIED
    verified_dto = GuiOutputBridge.to_sld_dto(project, outputs, summary)
    assert verified_dto.main_icu_is_preliminary is False
    assert verified_dto.feeder_icu_preliminary["F01"] is False


def test_sld_contains_metadata_provenance():
    project = _make_project()
    outputs, summary = _run(project)
    root = ET.fromstring(SldGenerator.generate_svg(project, outputs, summary))
    metadata = root.find("svg:metadata", _SVG_NS)
    assert metadata is not None, "SLD must contain <metadata>"
    assert metadata.text is not None
    assert "Input Hash" in metadata.text
    if summary.verified_input_hash:
        assert summary.verified_input_hash in metadata.text


def test_tcc_contains_metadata_provenance():
    project = _make_project()
    outputs, summary = _run(project)
    root = ET.fromstring(TccGenerator.generate_svg(project, outputs, summary))
    metadata = root.find("svg:metadata", _SVG_NS)
    assert metadata is not None
    assert metadata.text is not None
    assert "Input Hash" in metadata.text


def test_iec_sld_contains_metadata_provenance():
    dto = _make_sld_dto(
        verified_input_hash="abc123",
        engine_version="1.2.3",
        calculated_at="2026-11-12T08:00:00+00:00",
    )
    root = ET.fromstring(IECSldSvgGenerator.render_sld_svg(dto))
    metadata = root.find("svg:metadata", _SVG_NS)
    assert metadata is not None
    assert metadata.text is not None
    assert "abc123" in metadata.text
    assert "1.2.3" in metadata.text


def test_bridge_populates_provenance_in_dto():
    project = _make_project()
    outputs, summary = _run(project)
    dto = GuiOutputBridge.to_sld_dto(project, outputs, summary)
    assert dto.verified_input_hash == summary.verified_input_hash
    assert dto.engine_version == summary.engine_version
    assert dto.catalog_revision == summary.catalog_revision
    assert dto.rules_revision == summary.rules_revision
    assert dto.calculated_at == summary.calculated_at
