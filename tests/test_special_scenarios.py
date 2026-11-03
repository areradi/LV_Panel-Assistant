import math
import shutil
from pathlib import Path

import openpyxl
import pytest

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine, build_design_verification
from lv_assist.gui import ExcelInputManager, build_demo_project
from lv_assist.models import (CatalogDevice, EnclosureMounting, ScenarioInputs, SpecialScenario,
                              ValidationStatus, VerificationStatus)
from lv_assist.paths import get_data_dir
from lv_assist.scenario_rules import PROFILES, evaluate_scenario


def evaluate(scenario, **values):
    project, feeders = build_demo_project()
    project.special_scenario = scenario
    project.scenario_inputs = ScenarioInputs(**values)
    return {row.rule_id: row for row in evaluate_scenario(project, feeders, 100, 25)}


@pytest.mark.parametrize('scenario', [item for item in SpecialScenario if item != SpecialScenario.NONE])
def test_every_selected_scenario_has_a_profile_and_missing_data_is_not_approved(scenario):
    assert scenario.value in PROFILES
    results = evaluate(scenario)
    assert results
    assert results['SCEN-REVIEW'].status == ValidationStatus.INSUFFICIENT_DATA
    assert all(row.status != ValidationStatus.COMPLETED for row in results.values())


def test_ups_capacity_and_battery_energy_are_independent_checks():
    values = dict(load_kw=10, load_pf=0.8, ups_kw=10, ups_kva=12.5,
                  dc_voltage_v=48, autonomy_min=60, efficiency=0.9, usable_fraction=0.8, battery_ah=290)
    rows = evaluate(SpecialScenario.UPS_CRITICAL, **values)
    assert rows['SCEN-APPARENT-POWER'].status == ValidationStatus.COMPLETED
    assert rows['SCEN-BATTERY-ENERGY'].status == ValidationStatus.COMPLETED
    assert str(10000 / (48 * 0.9 * 0.8)) in rows['SCEN-BATTERY-ENERGY'].supporting_evidence
    rows = evaluate(SpecialScenario.UPS_CRITICAL, **{**values, 'ups_kva': 12.4, 'battery_ah': 289})
    assert rows['SCEN-APPARENT-POWER'].status == ValidationStatus.ERROR
    assert rows['SCEN-BATTERY-ENERGY'].status == ValidationStatus.ERROR


def test_pv_cold_voc_and_parallel_current_boundaries():
    values = dict(pv_voc_module_v=50, pv_voc_temp_pct_c=-0.3, pv_min_temp_c=-10,
                  pv_series_modules=20, pv_parallel_strings=3, pv_isc_module_a=12,
                  pv_current_factor=1.25, dc_equipment_voltage_v=1100, equipment_rating_a=44)
    rows = evaluate(SpecialScenario.PV_DC, **values)
    assert rows['SCEN-PV-VOC'].status == ValidationStatus.ERROR
    assert '1105' in rows['SCEN-PV-VOC'].supporting_evidence
    assert rows['SCEN-PV-CURRENT'].status == ValidationStatus.ERROR
    assert '45.0' in rows['SCEN-PV-CURRENT'].supporting_evidence
    rows = evaluate(SpecialScenario.PV_DC, **{**values, 'dc_equipment_voltage_v': 1200, 'equipment_rating_a': 45})
    assert rows['SCEN-PV-VOC'].status == ValidationStatus.COMPLETED
    assert rows['SCEN-PV-CURRENT'].status == ValidationStatus.COMPLETED
    assert rows['SCEN-REVIEW'].status != ValidationStatus.COMPLETED


def test_medical_imd_alarm_is_not_a_general_insulation_acceptance_test():
    rows = evaluate(SpecialScenario.MEDICAL_IT, imd_alarm_kohm=50, insulation_kohm=50)
    assert rows['SCEN-IMD-SETTING'].status == ValidationStatus.COMPLETED
    assert rows['SCEN-IMD-MEASURED'].status == ValidationStatus.ERROR
    rows = evaluate(SpecialScenario.MEDICAL_IT, imd_alarm_kohm=49, insulation_kohm=100)
    assert rows['SCEN-IMD-SETTING'].status == ValidationStatus.ERROR
    assert rows['SCEN-REVIEW'].status == ValidationStatus.INSUFFICIENT_DATA


def test_closed_transition_requires_interlocking_synchronism_and_permission():
    rows = evaluate(SpecialScenario.ATS_CLOSED_TRANSITION, equipment_rating_a=100, equipment_fault_ka=25,
                    interlock_proven=True, synchronism_proven=False, utility_parallel_approved=None)
    assert rows['SCEN-ATS-CURRENT'].status == ValidationStatus.COMPLETED
    assert rows['SCEN-ATS-FAULT'].status == ValidationStatus.WARNING
    assert rows['SCEN-SYNCHRONISM_PROVEN'].status == ValidationStatus.ERROR
    assert rows['SCEN-UTILITY_PARALLEL_APPROVED'].status == ValidationStatus.INSUFFICIENT_DATA


def test_ev_single_phase_input_and_low_voltage_dc_scope():
    project, feeders = build_demo_project()
    project.special_scenario = SpecialScenario.EV_CHARGING
    project.nominal_voltage_v = 230
    project.scenario_inputs = ScenarioInputs(ev_supply_type='AC', ac_phases=1, load_kw=7.4,
                                             ac_voltage_v=230, load_pf=1, efficiency=1, equipment_rating_a=32)
    rows = {row.rule_id: row for row in evaluate_scenario(project, feeders, 100, 25)}
    assert rows['SCEN-EV-AC-INPUT'].status == ValidationStatus.ERROR
    rows = evaluate(SpecialScenario.EV_CHARGING, ev_supply_type='DC_LOW_VOLTAGE', dc_voltage_v=121)
    assert rows['SCEN-EV-LOW-VOLTAGE'].status == ValidationStatus.ERROR


def test_fire_pump_has_no_fixed_six_times_compliance_claim():
    project, feeders = build_demo_project()
    project.special_scenario = SpecialScenario.FIRE_PUMP
    feeders = feeders[:1]
    feeders[0].fire_pump_service = True
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outs, summary, rows = engine.process_project(project, feeders)
    assert 'RULE-SCEN-FP-021' not in {row.rule_id for row in rows}
    assert next(row for row in rows if row.rule_id == 'SCEN-FIRE-START').status == ValidationStatus.INSUFFICIENT_DATA
    baseline = summary.design_main_current_a
    feeders[0].locked_rotor_current_a = 180
    outs, summary, rows = engine.process_project(project, feeders)
    assert summary.design_main_current_a == baseline
    assert outs[0].starting_kva == pytest.approx(round(math.sqrt(3) * 400 * 180 / 1000, 1))
    report = build_design_verification(project, outs, summary, rows)
    assert next(item for item in report.items if item.clause_ref == 'SCENARIO').status == VerificationStatus.NOT_VERIFIED
    assert report.conclusion_status != VerificationStatus.PASS
    feeders[0].phases = 1
    outs, _, _ = engine.process_project(project, feeders)
    assert outs[0].starting_kva == pytest.approx(41.6)


@pytest.mark.parametrize('mounting', list(EnclosureMounting)[1:])
def test_mounting_and_custom_dimensions_reach_engine_and_verification(mounting):
    project, feeders = build_demo_project()
    project.enclosure_mounting = mounting
    project.enclosure_width_mm = 650
    project.enclosure_height_mm = 900
    project.enclosure_depth_mm = 350
    outs, summary, rows = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, feeders)
    assert (summary.estimated_panel_width_mm, summary.estimated_panel_height_mm, summary.estimated_panel_depth_mm) == (650, 900, 350)
    assert summary.selected_enclosure.data_quality.value == 'ESTIMATED'
    assert next(row for row in rows if row.rule_id == 'SCEN-MOUNTING').status == ValidationStatus.INSUFFICIENT_DATA
    report = build_design_verification(project, outs, summary, rows)
    assert any(item.clause_ref == 'MOUNTING' for item in report.items)


def test_mounting_catalog_metadata_survives_database_roundtrip(tmp_path):
    db = tmp_path / 'catalog.db'
    shutil.copy2(get_data_dir() / 'lv_assist.db', db)
    repo = CatalogRepository(db_path=db)
    repo.add_device(CatalogDevice(part_number='TEST-WALL', manufacturer='TEST', series='TEST', device_type='ENCLOSURE',
                                  enclosure_mounting=EnclosureMounting.WALL_MOUNTED, width_mm=500, height_mm=700, depth_mm=250, ip_rating='IP55'))
    restored = next(device for device in repo.devices if device.part_number == 'TEST-WALL')
    assert restored.enclosure_mounting == EnclosureMounting.WALL_MOUNTED


def test_new_workbook_inputs_roundtrip_without_long_inline_validation_lists(tmp_path):
    path = tmp_path / 'input.xlsx'
    ExcelInputManager.create_input_template(str(path))
    workbook = openpyxl.load_workbook(path)
    for row in workbook['Project_Spec'].iter_rows(min_row=2):
        if row[0].value == 'enclosure_mounting':
            row[1].value = 'RACK'
        if row[0].value == 'special_scenario':
            row[1].value = 'UPS_CRITICAL'
    for row in workbook['Scenario_Inputs'].iter_rows(min_row=2):
        if row[0].value == 'load_kw':
            row[1].value = 12.5
    workbook['Feeders_List'].cell(2, 20, 123)
    assert all(len(validation.formula1) <= 255 for validation in workbook['Project_Spec'].data_validations.dataValidation)
    workbook.save(path)
    project, feeders, errors = ExcelInputManager.load_from_excel(str(path))
    assert not errors
    assert project.enclosure_mounting == EnclosureMounting.RACK
    assert project.scenario_inputs.load_kw == 12.5
    assert feeders[0].locked_rotor_current_a == 123


def test_ip_selection_checks_both_digits_and_does_not_assume_jet_protection_from_immersion():
    from types import SimpleNamespace
    devices = [CatalogDevice(part_number=rating, manufacturer='TEST', series='TEST', device_type='ENCLOSURE', ip_rating=rating)
               for rating in ('IP60', 'IP55', 'IP65', 'IP68', 'IP66/IP68')]
    repo = SimpleNamespace(devices=devices)
    selected = CatalogRepository.get_compatible_enclosures(repo, 'IP54')
    assert {device.part_number for device in selected} == {'IP55', 'IP65', 'IP66/IP68'}
    assert CatalogRepository.get_compatible_enclosures(repo, 'UNKNOWN') == []
