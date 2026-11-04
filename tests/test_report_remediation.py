import math

import pytest
from pydantic import ValidationError

from lv_assist.engine import EngineeringEngine
from lv_assist.excel_clipboard import ExcelClipboardParser
from lv_assist.models import FeederInput, LoadType, ProjectSpec
from lv_assist.catalog import CatalogRepository
from lv_assist.calculation_state import StaleCalculationStateError, require_current_calculation
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.outputs import SldGenerator
from lv_assist.bom import build_bom
from lv_assist.engine import CableSizingEngine
from lv_assist.core_verification import calculate_network_ik_profile
from lv_assist.pe_spd_engine import calculate_pe_adiabatic_section, select_pe_k_factor
from lv_assist.busbar import BusbarEngine
from lv_assist.models import CatalogDevice


@pytest.fixture
def calculation():
    project = ProjectSpec(project_name="Audit", prospective_ik_ka=10)
    inputs = [feeder(cable_length_m=20)]
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, checks = engine.process_project(project, inputs)
    return project, inputs, outputs, summary, checks, engine


def feeder(**changes):
    return FeederInput(feeder_id="F01", description="Audit load",
                       load_type=LoadType.HEATER_RESISTIVE, power_kw=10, **changes)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_power_rejected_on_creation_and_edit(value):
    with pytest.raises(ValidationError):
        FeederInput(feeder_id="F", description="Invalid", load_type="SUB_FEEDER", power_kw=value)
    item = feeder()
    with pytest.raises(ValidationError):
        item.power_kw = value
    assert item.power_kw == 10


def test_two_phase_input_is_rejected():
    with pytest.raises(ValidationError):
        feeder(phases=2)


@pytest.mark.parametrize("load_type", [LoadType.HEATER_RESISTIVE, LoadType.SUB_FEEDER, LoadType.LIGHTING_SOCKET])
def test_electrical_load_does_not_apply_motor_efficiency(load_type):
    pf, efficiency = EngineeringEngine._resolve_cos_phi_eff(load_type, 0.8, 0.5)
    assert pf == 0.8
    assert efficiency == 1


def test_motor_efficiency_still_converts_shaft_power():
    _, efficiency = EngineeringEngine._resolve_cos_phi_eff(LoadType.MOTOR_DOL, 0.8, 0.9)
    assert 10 / efficiency == pytest.approx(11.111111)


@pytest.mark.parametrize("column", ["power_kw", "length_m"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_clipboard_rejects_nonfinite_values(column, value):
    kw, length = (value, "20") if column == "power_kw" else ("10", value)
    parsed = ExcelClipboardParser.parse_clipboard_text(f"tag\tkw\tlength\nF01\t{kw}\t{length}")
    assert not parsed.valid_rows
    assert parsed.errors[0].column_name == column


def test_assumptions_record_only_omitted_defaults():
    project = ProjectSpec(project_name="Audit", nominal_voltage_v=400)
    assert project.assumed_fields["transformer_uk_pct"] == 6
    assert "nominal_voltage_v" not in project.assumed_fields
    parsed = ExcelClipboardParser.parse_clipboard_text("tag\tkw\nF01\t10")
    assert parsed.valid_rows[0].assumed_fields == {"cos_phi": 0.85, "efficiency": 0.9}


@pytest.mark.parametrize("change", ["temperature", "length", "replacement", "addition"])
def test_direct_exports_reject_changed_inputs_before_writing(calculation, tmp_path, change):
    project, inputs, outputs, summary, checks, engine = calculation
    if change == "temperature":
        project.ambient_temp_c = 45
    elif change == "length":
        inputs[0].cable_length_m = 200
    elif change == "replacement":
        inputs[0] = feeder(cable_length_m=200)
    else:
        inputs.append(FeederInput(
            feeder_id="F02", description="Added", power_kw=1, load_type="SUB_FEEDER"))
    path = tmp_path / "report.xlsx"
    operations = [
        lambda: ExcelExporter.export_to_excel(str(path), project, outputs, summary, checks),
        lambda: PrintableReportExporter.generate_html_report(str(path), project, outputs, summary, checks),
        lambda: GuiOutputBridge.generate_sld_svg(project, outputs, summary),
        lambda: SldGenerator.generate_svg(project, outputs, summary),
        lambda: build_bom(project, outputs, summary),
    ]
    for operation in operations:
        with pytest.raises(StaleCalculationStateError):
            operation()
    assert not path.exists()
    fresh, new_summary, _ = engine.process_project(project, inputs)
    require_current_calculation(project, new_summary, fresh)


def test_mixed_calculation_results_are_rejected(calculation):
    project, inputs, outputs, summary, _, engine = calculation
    inputs[0].cable_length_m = 21
    fresh, new_summary, _ = engine.process_project(project, inputs)
    with pytest.raises(StaleCalculationStateError):
        require_current_calculation(project, new_summary, outputs)
    require_current_calculation(project, new_summary, fresh)


def test_serialized_calculation_remains_verifiable(calculation):
    project, _, outputs, summary, _, _ = calculation
    restored = type(summary).model_validate_json(summary.model_dump_json())
    require_current_calculation(project, restored, outputs)
    restored.calculation_inputs[0].cable_length_m = 200
    with pytest.raises(StaleCalculationStateError):
        require_current_calculation(project, restored, outputs)


def test_pe_uses_full_fault_current_and_correct_material():
    required = 10_000 * math.sqrt(0.02) / 115
    selected = CableSizingEngine.calculate_pe_section(2.5, 10, 0.02, "Cu", "PVC", "in_cable")
    assert required == pytest.approx(12.2975, rel=1e-4)
    assert selected == 16
    assert CableSizingEngine.calculate_pe_section(2.5, 10, 0.02, "Al", "PVC", "in_cable") == 25


@pytest.mark.parametrize("time", [5.01, float("inf"), float("nan"), 0])
def test_pe_does_not_accept_invalid_adiabatic_time(time):
    assert CableSizingEngine.calculate_pe_section(10, 10, time) is None
    with pytest.raises(ValueError):
        calculate_pe_adiabatic_section(10_000, time)


def test_unknown_material_cannot_use_a_copper_fallback():
    with pytest.raises(ValueError):
        select_pe_k_factor("Unknown", "PVC", "in_cable")


def test_cable_autosizing_checks_phase_thermal_withstand():
    result = CableSizingEngine.select_feeder_cable(
        10, 16, False, 10, 1, 400, 3, 30, 1, 5, LoadType.SUB_FEEDER,
        fault_current_ka=25, clear_time_s=0.02)
    assert result[0] >= 25_000 * math.sqrt(0.02) / 115


def test_fuse_second_overload_condition_increases_required_ampacity():
    result = CableSizingEngine.select_feeder_cable(
        50, 63, False, 10, 1, 400, 3, 30, 1, 5, LoadType.SUB_FEEDER,
        overload_i2_factor=1.6)
    assert result[3] >= 1.6 * 63 / 1.45


def test_hot_fault_loop_matches_independent_impedance_calculation():
    result = calculate_network_ik_profile(None, None, source_ik_ka=10, source_r_x=0.3,
        feeder_cable_length_m=100, feeder_phase_mm2=10, feeder_pe_mm2=10)
    z = 1.05 * (400 / math.sqrt(3)) / 10_000
    x = z / math.sqrt(1 + 0.3**2)
    r = x * 0.3
    hot_r = 0.017241 * (1 + 0.00393 * 140) * 100 * (1/10 + 1/10)
    expected = 0.95 * (400 / math.sqrt(3)) / math.hypot(2*r + hot_r, 2*x + 2*0.00008*100) / 1000
    assert result.ik_feeder_end_min_1p_ka == pytest.approx(expected, abs=0.0005)


def test_long_tn_feeder_fails_disconnection_check():
    project = ProjectSpec(project_name="Long TN", prospective_ik_ka=10)
    item = feeder(cable_length_m=2000, cable_section_mm2=2.5)
    _, _, checks = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, [item])
    assert any(v.rule_id == "RULE-ADS-TN" and v.status.value == "ERROR" for v in checks)


def test_tt_requires_rcd_and_vfd_rejects_ac_type():
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    project = ProjectSpec(project_name="TT drive", prospective_ik_ka=10, earthing_system="TT")
    item = FeederInput(feeder_id="F01", description="Drive", power_kw=5, load_type="MOTOR_VFD", rcd_type="AC")
    _, _, checks = engine.process_project(project, [item])
    assert any(v.rule_id == "RULE-ADS-TT" and v.status.value == "INSUFFICIENT_DATA" for v in checks)
    assert any(v.rule_id == "RULE-RCD-VFD" and v.status.value == "ERROR" for v in checks)


def test_peak_factor_uses_rx_and_never_exceeds_physical_limit():
    assert BusbarEngine._kappa_iec60909(100) == 2
    assert BusbarEngine._kappa_iec60909(10, 0.3) == pytest.approx(1.02 + .98 * math.exp(-.9))
    assert BusbarEngine._kappa_iec60909(100, 0) == 2


def test_busbar_stress_and_span_match_beam_equation():
    _, _, section_modulus = BusbarEngine._bar_withstand(50, 10)
    force = .173 * 50**2 / .06
    expected_span = math.sqrt(120 * 8 * section_modulus / (force * 1000)) * 1000
    assert BusbarEngine._max_support_spacing_mm(50, section_modulus) == pytest.approx(expected_span)
    result = BusbarEngine.select(400, 25, 800, ip_total_ka=50, support_span_mm=1000)
    assert result.bending_stress_mpa > 120
    assert any(v.rule_id == 'RULE-BUS-027' and v.status.value == 'ERROR' for v in result.validations)


def test_hot_busbar_has_lower_rating_for_same_geometry():
    bar35, _ = BusbarEngine._choose_bar(1, None, None, 1)
    bar50, _ = BusbarEngine._choose_bar(1, None, None, math.sqrt(20/35))
    assert bar35[:2] == bar50[:2]
    assert bar50[2] < bar35[2]


def test_verified_label_without_datasheet_does_not_prove_provenance():
    device = CatalogDevice(part_number='TEST', manufacturer='Test', series='Test', device_type='MCB')
    assert not device.has_verified_datasheet
    device.datasheet_reference = 'Specific test datasheet'
    device.datasheet_revision = 'Revision 1'
    assert device.has_verified_datasheet


def test_assumptions_and_rule_categories_are_exported(calculation, tmp_path):
    project, _, outputs, summary, checks, _ = calculation
    path = tmp_path / 'audit.html'
    PrintableReportExporter.generate_html_report(str(path), project, outputs, summary, checks)
    document = path.read_text()
    assert 'ASSUMED_DEFAULT' in document
    assert 'transformer_uk_pct' in document
    assert 'IEC_MANDATORY_CLAUSE' in document
    assert 'ENGINEERING_DESIGN_PRACTICE' in document
