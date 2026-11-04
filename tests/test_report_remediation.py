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
from lv_assist.core_verification import calculate_network_ik_profile, verify_breaking_capacity_icu
from lv_assist.pe_spd_engine import calculate_pe_adiabatic_section, select_pe_k_factor
from lv_assist.busbar import BusbarEngine
from lv_assist.models import CatalogDevice, StepEngStatus
from lv_assist.commercial import CommercialEngine
from lv_assist.pe_spd_engine import evaluate_spd_requirements
from lv_assist.tcc_analyzer import TccAnalyzer
from lv_assist.catalog import TripCurveRepository
from lv_assist.engine import build_design_verification
from lv_assist.layout import PanelLayoutGenerator
import openpyxl


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
    z = 1.1 * (400 / math.sqrt(3)) / 10_000
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


@pytest.mark.parametrize('kind', ['MOTOR_DOL', 'MOTOR_STAR_DELTA', 'MOTOR_SOFT_STARTER', 'MOTOR_VFD'])
def test_selected_feeder_tags_agree_across_bom_and_drawings(kind):
    project = ProjectSpec(project_name='Tag test', prospective_ik_ka=10)
    source = FeederInput(feeder_id='F01', description='Tag test', load_type=kind, power_kw=7.5)
    outputs, summary, _ = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, [source])
    items = build_bom(project, outputs, summary)
    tags = {item.tag for item in items}
    assert '-Q0' in tags and '-Q1' in tags and '-G1' in tags and '-W1' in tags
    dto = GuiOutputBridge.to_feeder_ladder_dto(project, outputs[0], summary)
    for tag in [dto.prot_tag, dto.km_tag, dto.kd_tag, dto.ky_tag, dto.vfd_tag, dto.timer_tag]:
        if tag:
            assert tag in tags
    sld = GuiOutputBridge.generate_sld_svg(project, outputs, summary)
    ladder = GuiOutputBridge.generate_feeder_ladder_svg(project, outputs[0], summary)
    layout = PanelLayoutGenerator.generate_svg(project, outputs, summary)
    assert 'PRELIMINARY' in sld and 'PRELIMINARY' in ladder and 'PRELIMINARY' in layout
    for tag in [dto.km_tag, dto.vfd_tag]:
        if tag:
            assert tag in sld and tag in ladder and tag in layout
    assert all(not item.part_number for item in items if item.missing_part_number)
    with pytest.raises(ValueError, match='Final BOM'):
        build_bom(project, outputs, summary, final=True)
    quote = CommercialEngine.build_quote(project, outputs, summary)
    assert any('-Q1' in line.tag for line in quote.lines)


def test_unknown_short_circuit_stays_unknown_in_sld():
    project = ProjectSpec(project_name='Unknown supply')
    outputs, summary, _ = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, [feeder()])
    dto = GuiOutputBridge.to_sld_dto(project, outputs, summary)
    assert dto.prospective_ik_ka is None
    assert 'Ik' in GuiOutputBridge.generate_sld_svg(project, outputs, summary)


def test_schedule_and_qc_workbook_exports_actual_records(calculation, tmp_path):
    project, _, outputs, summary, checks, _ = calculation
    path = tmp_path / 'schedules.xlsx'
    ExcelExporter.export_to_excel(str(path), project, outputs, summary, checks)
    wb = openpyxl.load_workbook(path)
    assert {'Terminal_Schedule', 'Wire_Schedule', 'Routine_Verification'} <= set(wb.sheetnames)
    qc = list(wb['Routine_Verification'].values)
    assert len(qc) == 10
    assert all(row[2] == 'NOT_TESTED' and row[3] is None for row in qc[1:])


def test_assumptions_survive_serialization_and_clear_on_edit():
    project = ProjectSpec(project_name='Defaults')
    restored = ProjectSpec.model_validate_json(project.model_dump_json())
    assert restored.assumed_fields == project.assumed_fields
    restored.ambient_temp_c = 45
    assert 'ambient_temp_c' not in restored.assumed_fields
    assert 'spare_factor' in restored.assumed_fields


def test_duplicate_feeder_ids_cannot_produce_ambiguous_tags():
    with pytest.raises(ValueError):
        EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(
            ProjectSpec(project_name='Duplicate'), [feeder(), feeder()])


def test_report_reference_unbalanced_single_phase_loads():
    project = ProjectSpec(project_name='32/10/12 A reference', prospective_ik_ka=10,
                          simultaneity_factor_ks=1, spare_factor=0)
    u_ln = 400 / math.sqrt(3)
    sources = [FeederInput(feeder_id=phase, description=phase, load_type='HEATER_RESISTIVE',
                          power_kw=current*u_ln/1000, cos_phi=1, phases=1, supply_phase=phase)
               for phase, current in zip(('L1', 'L2', 'L3'), (32, 10, 12))]
    outputs, summary, checks = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, sources)
    assert summary.design_main_current_a == pytest.approx(32, abs=.02)
    assert summary.phase_design_currents_a['L1'] == pytest.approx(32, abs=.02)
    assert summary.neutral_current_a == pytest.approx(math.sqrt(444), abs=.03)
    assert summary.phase_imbalance_pct == pytest.approx(77.78, abs=.2)
    assert all('L+N+PE' in f.cable_designation_str for f in outputs)
    assert any(v.rule_id == 'RULE-PHASE-BALANCE' for v in checks)


def test_unassigned_single_phase_loads_are_not_silently_balanced():
    project = ProjectSpec(project_name='Unknown phases', prospective_ik_ka=10, simultaneity_factor_ks=1, spare_factor=0)
    sources = [FeederInput(feeder_id=f'F{i}', description='Unassigned', load_type='HEATER_RESISTIVE',
                          power_kw=2.3, cos_phi=1, phases=1) for i in range(3)]
    _, summary, checks = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, sources)
    assert summary.design_main_current_a > 29
    assert any(v.rule_id == 'RULE-PHASE-BALANCE' and v.status.value == 'INSUFFICIENT_DATA' for v in checks)


def test_report_distribution_reference_and_motor_efficiencies():
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    project = ProjectSpec(project_name='45 kW reference', prospective_ik_ka=10,
                          simultaneity_factor_ks=.8, spare_factor=0)
    item = FeederInput(feeder_id='F1', description='Distribution', load_type='SUB_FEEDER', power_kw=45, cos_phi=.85)
    _, summary, _ = engine.process_project(project, [item])
    assert summary.design_main_current_a == pytest.approx(36_000 / (math.sqrt(3)*400*.85), abs=.02)
    sources = [FeederInput(feeder_id=f'M{i}', description='Motor', load_type='MOTOR_DOL',
                          power_kw=power, efficiency=efficiency, cos_phi=pf)
               for i, (power, efficiency, pf) in enumerate([(7.5, .88, .84), (15, .90, .85), (22, .92, .86)])]
    outputs, _, _ = engine.process_project(project, sources)
    for result, source in zip(outputs, sources):
        expected = source.power_kw*1000/(math.sqrt(3)*400*source.efficiency*source.cos_phi)
        assert result.design_current_ib_a == pytest.approx(expected, abs=.01)


def test_report_50ka_adiabatic_reference_without_energy_limiting():
    section = calculate_pe_adiabatic_section(50_000, .1, 'Cu', 'PVC', 'in_cable')
    assert section['s_adiabatic_mm2'] == pytest.approx(137.49, abs=.01)
    rx = .25 / math.sqrt(1 - .25**2)
    peak = BusbarEngine._kappa_iec60909(50, rx)*math.sqrt(2)*50
    assert peak == pytest.approx(104.119, abs=.1)


def test_design_checklist_cannot_pass_without_recorded_assembly_evidence(calculation):
    project, _, outputs, summary, checks, _ = calculation
    report = build_design_verification(project, outputs, summary, checks)
    assert all(item.status.value != 'PASS' for item in report.items)
    assert report.conclusion_status.value != 'PASS'


@pytest.mark.parametrize('earth,voltage,fault', [('invalid',230,10), ('TN-S',float('nan'),10), ('TT',230,-1)])
def test_spd_rejects_missing_or_invalid_physical_inputs(earth, voltage, fault):
    result = evaluate_spd_requirements(earth, voltage, False, prospective_ik_ka=fault)
    assert result.engineering_status == StepEngStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize('earth,lps,candidate_type,uc', [('IT',False,'Type 2',385), ('TN-S',True,'Type 1',275), ('TT',False,'Type 2',275)])
def test_spd_preselection_keeps_actual_type_and_requires_review(earth, lps, candidate_type, uc):
    result = evaluate_spd_requirements(earth, 230, lps, is_sensitive_terminal_load=True,
        prospective_ik_ka=10, candidates=[{'spd_type':candidate_type, 'uc_v':uc, 'model_name':'Test SPD'}])
    assert result.spd_type.value == candidate_type
    assert result.model_name == 'Test SPD'
    assert result.engineering_status == StepEngStatus.WARNING


def test_spd_cannot_select_a_device_below_required_continuous_voltage():
    result = evaluate_spd_requirements('IT',230,False,prospective_ik_ka=10,
        candidates=[{'spd_type':'Type 2','uc_v':275}])
    assert result.model_name is None


def test_tcc_intersection_matches_independent_analytic_curves(monkeypatch):
    up = CatalogDevice(part_number='UP', manufacturer='Test', series='UP', device_type='MCCB', rated_current_in_a=100)
    down = CatalogDevice(part_number='DN', manufacturer='Test', series='DN', device_type='MCB', rated_current_in_a=50)
    monkeypatch.setattr(TripCurveRepository, 'thermal_time_s', lambda series, mult: 1000 / mult**3 if series == 'UP' else 10 / mult)
    monkeypatch.setattr(TripCurveRepository, 'instantaneous_band_a', lambda series, rating: (5000,6000))
    result = TccAnalyzer.find_intersection(up, down)
    assert result.intersection_a == pytest.approx(math.sqrt(2_000_000), rel=.005)
    assert TccAnalyzer.trip_time_s('UP',100,float('nan')) is None
    up.rated_current_in_a = 0
    assert TccAnalyzer.evaluate_pair(up, down, 10)[0] == 'UNKNOWN'


@pytest.mark.parametrize('voltage', [109, 1001])
def test_panel_voltage_outside_declared_lv_scope_is_rejected(voltage):
    with pytest.raises(ValidationError):
        ProjectSpec(project_name='Outside LV scope', nominal_voltage_v=voltage)


def test_transformer_fault_uses_declared_maximum_voltage_factor():
    project = ProjectSpec(project_name='Fault reference', transformer_kva=1600, voltage_factor_c_max=1.1)
    assert EngineeringEngine._ik_from_transformer(project) == pytest.approx(1.1*1600/(math.sqrt(3)*.4*.06)/1000, abs=.005)


def test_motor_contribution_cannot_be_relied_on_for_minimum_fault():
    arguments = dict(source_r_x=.3, feeder_cable_length_m=25, feeder_phase_mm2=16, feeder_pe_mm2=16)
    base = calculate_network_ik_profile(None, None, source_ik_ka=10, **arguments)
    maximum = calculate_network_ik_profile(None, None, source_ik_ka=20, source_min_ik_ka=10, **arguments)
    assert maximum.ik_feeder_end_max_3p_ka > base.ik_feeder_end_max_3p_ka
    assert maximum.ik_feeder_end_min_1p_ka == base.ik_feeder_end_min_1p_ka


@pytest.mark.parametrize('icu,fault', [(float('nan'),10), (25,float('inf'))])
def test_nonfinite_breaking_capacity_cannot_pass(icu, fault):
    assert verify_breaking_capacity_icu(icu, fault).status.value == 'INSUFFICIENT_DATA'


def test_automatic_cable_selection_rechecks_end_fault_and_pe_energy():
    project = ProjectSpec(project_name='Long automatic feeder', prospective_ik_ka=10)
    item = feeder(cable_length_m=400)
    protection = CatalogDevice(part_number='TEST-32', manufacturer='Test', series='SENTRON 3VA1',
                               device_type='MCCB', rated_current_in_a=32)
    outputs, _, checks = EngineeringEngine([protection]).process_project(project, [item])
    assert outputs[0].selected_phase_mm2 > 16
    assert not any(v.rule_id in {'RULE-ADS-TN', 'RULE-PHASE-I2T', 'RULE-PE-I2T'} and v.status.value == 'ERROR' for v in checks)


@pytest.mark.parametrize('kind', ['MOTOR_DOL', 'MOTOR_STAR_DELTA'])
def test_motor_selection_does_not_mix_manufacturers_or_overload_ranges(kind):
    catalog = [
        CatalogDevice(part_number='PROTECT-A', manufacturer='A', series='SENTRON 3VA1', device_type='MPCB', rated_current_in_a=63),
        CatalogDevice(part_number='CONTACT-B', manufacturer='B', series='Test', device_type='CONTACTOR', rated_current_in_a=100),
        CatalogDevice(part_number='OVERLOAD-A', manufacturer='A', series='Test', device_type='BIMETAL', setting_min_a=20, setting_max_a=40),
    ]
    project = ProjectSpec(project_name='Pair selection', prospective_ik_ka=10)
    item = FeederInput(feeder_id='F1', description='Motor', load_type=kind, power_kw=7.5)
    result, _ = EngineeringEngine(catalog)._process_single_feeder(project, item, 10, 10)
    assert result.selected_protection.manufacturer == 'A'
    assert result.selected_contactor_main is None
    assert result.selected_bimetal is None
