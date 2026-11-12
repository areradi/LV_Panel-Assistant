import xml.etree.ElementTree as ET

from lv_assist.catalog import CatalogRepository
from lv_assist.control_circuits import ControlCircuitGenerator
from lv_assist.engine import EngineeringEngine
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.iec_sld_svg import IECSldSvgGenerator
from lv_assist.layout import PanelLayoutGenerator
from lv_assist.models import FeederInput, LoadType, ProjectSpec
from lv_assist.outputs import SldGenerator, TccGenerator


_XSS_PAYLOADS = (
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "Feeder with & < > chars",
    'Feeder with "quotes"',
)


def _make_project(name="XSS test", **overrides):
    values = {"project_name": name, "prospective_ik_ka": 22.0}
    values.update(overrides)
    return ProjectSpec(**values)


def _make_feeder(description="Feeder", **overrides):
    values = {
        "feeder_id": "F01",
        "description": description,
        "load_type": LoadType.SUB_FEEDER,
        "power_kw": 5.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _run(project, feeder):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    return engine.process_project(project, [feeder])


def _assert_payload_is_safe_svg_text(svg, payload):
    root = ET.fromstring(svg)
    assert payload in "".join(root.itertext())
    if "<" in payload or "&" in payload:
        assert payload not in svg


def test_sld_escapes_project_name_and_feeder_description():
    for payload in _XSS_PAYLOADS:
        project = _make_project(name=payload)
        outputs, summary, _ = _run(project, _make_feeder(description=payload))
        _assert_payload_is_safe_svg_text(
            SldGenerator.generate_svg(project, outputs, summary), payload
        )


def test_tcc_escapes_project_name():
    for payload in _XSS_PAYLOADS:
        project = _make_project(name=payload)
        outputs, summary, _ = _run(project, _make_feeder())
        _assert_payload_is_safe_svg_text(
            TccGenerator.generate_svg(project, outputs, summary), payload
        )


def test_iec_sld_escapes_project_name():
    for payload in _XSS_PAYLOADS:
        project = _make_project(name=payload)
        outputs, summary, _ = _run(project, _make_feeder())
        dto = GuiOutputBridge.to_sld_dto(project, outputs, summary)
        _assert_payload_is_safe_svg_text(
            IECSldSvgGenerator.render_sld_svg(dto), payload
        )


def test_control_circuits_escapes_user_text():
    for payload in _XSS_PAYLOADS:
        project = _make_project(name=payload)
        feeder = _make_feeder(
            description=payload,
            load_type=LoadType.MOTOR_DOL,
            power_kw=15.0,
            cos_phi=0.85,
            efficiency=0.91,
        )
        outputs, summary, _ = _run(project, feeder)
        _assert_payload_is_safe_svg_text(
            ControlCircuitGenerator.generate_svg(project, outputs, summary), payload
        )


def test_layout_escapes_project_name():
    for payload in _XSS_PAYLOADS:
        project = _make_project(name=payload)
        outputs, summary, _ = _run(project, _make_feeder())
        _assert_payload_is_safe_svg_text(
            PanelLayoutGenerator.generate_svg(project, outputs, summary), payload
        )


def test_intersection_label_is_marked_approximate(monkeypatch):
    from types import SimpleNamespace

    from lv_assist.i18n import tr
    from lv_assist.tcc_analyzer import TccAnalyzer

    project = _make_project()
    outputs, summary, _ = _run(project, _make_feeder())
    assert summary.main_breaker is not None
    assert outputs[0].selected_protection is not None
    outputs[0].selectivity_limit_is_ka = 5.5
    monkeypatch.setattr(
        TccAnalyzer,
        "find_intersection",
        lambda *args: SimpleNamespace(intersection_a=4200.0),
    )

    svg = TccGenerator.generate_svg(project, outputs, summary)

    assert "Is ≈ 4.2 kA" in svg
    assert f"{tr('tcc_sel')} F01 = 5.5 kA" in svg
