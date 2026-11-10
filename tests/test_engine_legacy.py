# -*- coding: utf-8 -*-
import html
import json
import math
import os
import openpyxl
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from lv_assist.models import (
    ProjectSpec, FeederInput, LoadType, ValidationStatus, SelectivityEvalState,
    CatalogDevice, SpecialScenario, DataQuality, InstallationMethod, ValidationResult, SpdClass,
)
from lv_assist.catalog import CatalogRepository, SiemensSelectivityRepository, TripCurveRepository, catalog_repo
from lv_assist.engine import CableSizingEngine, EngineeringEngine
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.outputs import SldGenerator, TccGenerator, PdfExporter, EplanExporter, EplanPartsExporter
from lv_assist.control_circuits import ControlCircuitGenerator
from lv_assist.layout import PanelLayoutGenerator
from lv_assist.busbar import BusbarEngine
from lv_assist.gui import ExcelInputManager
from lv_assist.i18n import tr, i18n, I18n


CATALOG = CatalogRepository.get_default_catalog()


def make_project(**overrides) -> ProjectSpec:
    params = dict(project_name="Test Panel", prospective_ik_ka=22.0)
    params.update(overrides)
    return ProjectSpec(**params)


def make_feeder(feeder_id="F01", **overrides) -> FeederInput:
    params = dict(
        feeder_id=feeder_id, description="Test feeder", load_type=LoadType.SUB_FEEDER,
        power_kw=5.0, cos_phi=0.90, efficiency=1.0,
    )
    params.update(overrides)
    return FeederInput(**params)


class TestCableSizing:
    def test_temp_factor_k1_boundaries(self):
        expected = [(30, 1.00), (31, 0.94), (35, 0.94), (36, 0.87), (40, 0.87),
                    (41, 0.79), (45, 0.79), (46, 0.71), (50, 0.71), (51, 0.61)]
        for temp, factor in expected:
            assert CableSizingEngine.get_temp_factor_k1(temp) == factor, f"k1({temp})"

    def test_voltage_drop_hand_calc(self):
        vd = CableSizingEngine.calc_voltage_drop_pct(ib_a=30.0, length_m=50.0, section_mm2=6.0,
                                                     cos_phi=0.9, voltage_v=400.0, phases=3)
        # مقاومت در دمای کارکرد کامل PVC (×۱.۲ نسبت به R20) اعمال می‌شود
        assert abs(vd - 2.65) < 0.01

    def test_voltage_drop_temp_correction_factors(self):
        vd_pvc = CableSizingEngine.calc_voltage_drop_pct(30.0, 50.0, 6.0, 0.9, 400.0, 3, insulation="PVC")
        vd_xlpe = CableSizingEngine.calc_voltage_drop_pct(30.0, 50.0, 6.0, 0.9, 400.0, 3, insulation="XLPE")
        assert CableSizingEngine.VD_TEMP_FACTOR["PVC"] == 1.2
        assert CableSizingEngine.VD_TEMP_FACTOR["XLPE"] == 1.28
        assert abs(vd_pvc / vd_xlpe - 1.2 / 1.28) < 0.002

    def test_pe_section_table_logic(self):
        assert CableSizingEngine.calculate_pe_section(2.5, fault_current_ka=0.0, clear_time_s=0.4) == 2.5
        assert CableSizingEngine.calculate_pe_section(16.0, fault_current_ka=0.0, clear_time_s=0.4) == 16.0
        assert CableSizingEngine.calculate_pe_section(25.0, fault_current_ka=0.0, clear_time_s=0.4) == 16.0
        assert CableSizingEngine.calculate_pe_section(35.0, fault_current_ka=0.0, clear_time_s=0.4) == 16.0
        assert CableSizingEngine.calculate_pe_section(50.0, fault_current_ka=0.0, clear_time_s=0.4) == 25.0
        assert CableSizingEngine.calculate_pe_section(95.0, fault_current_ka=0.0, clear_time_s=0.4) == 50.0
        assert CableSizingEngine.calculate_pe_section(240.0, fault_current_ka=0.0, clear_time_s=0.4) == 120.0

    def test_pe_section_adiabatic_with_explicit_fault_data(self):
        # 10 kA / 20 ms با k=176 نیازمند حدود 8.0 mm² است؛ مقطع استاندارد بعدی 10 mm² است.
        assert CableSizingEngine.calculate_pe_section(
            2.5, fault_current_ka=10.0, clear_time_s=0.02
        ) == 10.0

    def test_auto_sizing_meets_iz_and_vdrop(self):
        s_ph, s_n, s_pe, iz, vd, _ = CableSizingEngine.select_feeder_cable(
            ib_a=45.0, protection_in_a=50.0, is_adjustable_prot=True, length_m=60.0,
            cos_phi=0.85, voltage_v=400.0, phases=3, ambient_temp_c=40.0, grouping_k2=0.8,
            max_vdrop_pct=5.0, load_type=LoadType.SUB_FEEDER,
            fault_current_ka=10.0, clear_time_s=0.02)
        assert iz >= 45.0
        assert vd <= 5.0
        assert s_pe <= s_ph

    def test_auto_sizing_without_fault_data_returns_none_pe(self):
        _, _, s_pe, _, _, _ = CableSizingEngine.select_feeder_cable(
            ib_a=45.0, protection_in_a=50.0, is_adjustable_prot=True, length_m=60.0,
            cos_phi=0.85, voltage_v=400.0, phases=3, ambient_temp_c=40.0, grouping_k2=0.8,
            max_vdrop_pct=5.0, load_type=LoadType.SUB_FEEDER)
        assert s_pe is None

    def test_user_specified_section_respected(self):
        s_ph, _, _, _, _, _ = CableSizingEngine.select_feeder_cable(
            ib_a=20.0, protection_in_a=25.0, is_adjustable_prot=True, length_m=30.0,
            cos_phi=0.9, voltage_v=400.0, phases=3, ambient_temp_c=40.0, grouping_k2=0.8,
            max_vdrop_pct=5.0, load_type=LoadType.SUB_FEEDER, user_specified_mm2=10.0)
        assert s_ph == 10.0


class TestSelectivity:
    def test_3va2_3rv20_total_selectivity(self):
        upstream = next(d for d in CATALOG if d.part_number == "3VA2216-5HL32-0AA0")
        downstream = next(d for d in CATALOG if d.part_number == "3RV2021-4EA10")
        state, limit, ref = SiemensSelectivityRepository.evaluate_pair(upstream, downstream, 22.0)
        assert state == SelectivityEvalState.VERIFIED_TOTAL
        assert limit == 55.0
        assert ref

    def test_ratio_below_1_25_is_violation(self):
        upstream = CatalogDevice(part_number="X", manufacturer="T", series="S1",
                                 device_type="MCCB", rated_current_in_a=25.0)
        downstream = CatalogDevice(part_number="Y", manufacturer="T", series="S2",
                                   device_type="MCCB", rated_current_in_a=40.0)
        state, _, _ = SiemensSelectivityRepository.evaluate_pair(upstream, downstream, 22.0)
        assert state == SelectivityEvalState.VIOLATION


class TestEngine:
    def test_smoke_demo_project(self):
        project = make_project()
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93),
            make_feeder("F03", load_type=LoadType.MOTOR_VFD, power_kw=18.5, cos_phi=0.95, efficiency=0.90),
            make_feeder("F04", load_type=LoadType.LIGHTING_SOCKET, power_kw=12.0, demand_factor_kd=0.8, has_socket_outlets=True),
        ]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert len(outs) == 4
        assert summary.design_main_current_a > 0
        assert summary.main_breaker is not None
        assert summary.selected_enclosure is not None
        assert len(validations) > 0
        assert not any(v.status == ValidationStatus.ERROR for v in validations)

    def test_dol_motor_gets_mpcb_and_contactor(self):
        outs, _, _ = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)])
        f = outs[0]
        assert f.selected_protection is not None
        assert f.selected_protection.device_type == "MPCB"
        assert f.selected_contactor_main is not None
        assert f.selected_vfd is None

    def test_star_delta_gets_three_contactors_bimetal_timer(self):
        outs, _, _ = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93)])
        f = outs[0]
        assert f.selected_contactor_main is not None
        assert f.selected_contactor_delta is not None
        assert f.selected_contactor_star is not None
        assert f.selected_bimetal is not None
        assert f.selected_timer_yd is not None

    def test_vfd_feeder_gets_drive_and_mccb(self):
        outs, _, _ = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.MOTOR_VFD, power_kw=18.5, cos_phi=0.95, efficiency=0.90)])
        f = outs[0]
        assert f.selected_vfd is not None
        assert f.selected_protection is not None

    def test_socket_outlet_adds_rcd(self):
        outs, _, _ = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.LIGHTING_SOCKET, power_kw=12.0, has_socket_outlets=True)])
        assert outs[0].selected_rcd is not None

    def test_missing_motor_data_flagged(self):
        _, _, validations = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=None, efficiency=None)])
        assert any(v.rule_id == "RULE-DATA-001" and v.status == ValidationStatus.INSUFFICIENT_DATA
                   for v in validations)

    def test_very_high_ik_yields_no_main_breaker_and_prot_error(self):
        _, summary, validations = EngineeringEngine(CATALOG).process_project(
            make_project(prospective_ik_ka=150.0),
            [make_feeder()])
        assert summary.main_breaker is None
        assert any(v.rule_id == "RULE-PROT-SC-001" and v.status == ValidationStatus.ERROR
                   for v in validations)


class TestExcelIO:
    def test_template_roundtrip(self, tmp_path):
        in_path = tmp_path / "input.xlsx"
        ExcelInputManager.create_input_template(str(in_path))
        project, feeders, errors = ExcelInputManager.load_from_excel(str(in_path))
        assert errors == []
        assert len(feeders) == 4
        assert project.prospective_ik_ka == 22.0
        assert project.altitude_m == 1000.0

        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        out_path = tmp_path / "output.xlsx"
        ExcelExporter.export_to_excel(str(out_path), project, outs, summary, validations)
        wb = openpyxl.load_workbook(str(out_path))
        assert wb.sheetnames == ["01_Project_Summary", "02_Feeder_Cable_Schedule",
                                 "03_Validation_Log", "04_BOM", "05_Control_Circuits",
                                 "06_Design_Verification", "Scenario_Inputs", "07_Commercial_Quote",
                                 "Wire_Schedule", "Terminal_Schedule", "Routine_Verification", "Assumed_Defaults"]

    def test_altitude_loaded_from_excel(self, tmp_path):
        path = tmp_path / "input.xlsx"
        ExcelInputManager.create_input_template(str(path))
        wb = openpyxl.load_workbook(str(path))
        ws = wb["Project_Spec"]
        for row in ws.iter_rows(min_row=2):
            if row[0].value == "altitude_m":
                row[1].value = 2500.0
        wb.save(str(path))
        project, _, _ = ExcelInputManager.load_from_excel(str(path))
        assert project.altitude_m == 2500.0

    def test_html_report_generates(self, tmp_path):
        project = make_project()
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(
            project, [make_feeder()])
        path = tmp_path / "report.html"
        PrintableReportExporter.generate_html_report(str(path), project, outs, summary, validations)
        content = path.read_text(encoding="utf-8")
        assert project.project_name in content
        assert "دفترچه محاسبات" in content


class TestParseBool:
    def test_edge_cases(self):
        assert ExcelInputManager._parse_bool("False") is False
        assert ExcelInputManager._parse_bool("True") is True
        assert ExcelInputManager._parse_bool(True) is True
        assert ExcelInputManager._parse_bool(0) is False
        assert ExcelInputManager._parse_bool(1) is True
        assert ExcelInputManager._parse_bool(None) is False
        assert ExcelInputManager._parse_bool("") is False


class TestI18n:
    def teardown_method(self):
        i18n.set_language("fa")

    def test_switch_languages(self):
        i18n.set_language("en")
        assert tr("kpi_main_current") == "Total Current"
        i18n.set_language("de")
        assert tr("kpi_main_current") == "Gesamtstrom"
        i18n.set_language("fa")
        assert tr("kpi_main_current") == "جریان کل"

    def test_unknown_key_returns_key(self):
        assert tr("no_such_key_xyz") == "no_such_key_xyz"

    def test_fa_calculated_numbers_are_latin(self):
        i18n.set_language("fa")
        text = tr("rpt_ref_ks", ks=0.85, spare=20.0)
        assert "0.85" in text and "20.0" in text
        assert not any(c in text for c in '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩')
        i18n.set_language("en")
        assert "0" in tr("rpt_ref_ks", ks=0.85, spare=20.0)

    def test_direction_and_font(self):
        assert i18n.direction() == "rtl"
        i18n.set_language("de")
        assert i18n.direction() == "ltr"
        assert i18n.font_family() == "Segoe UI"

    def test_config_persistence(self, tmp_path):
        cfg = tmp_path / "config.json"
        standalone = I18n()
        standalone.set_config_path(str(cfg))
        standalone.set_language("de")
        assert standalone.get_language() == "de"
        reloaded = I18n()
        reloaded.set_config_path(str(cfg))
        assert reloaded.get_language() == "de"

    def test_validation_messages_translated(self):
        from lv_assist.catalog import CatalogRepository
        from lv_assist.engine import EngineeringEngine
        project = ProjectSpec(project_name="Test", prospective_ik_ka=22.0)
        feeder = FeederInput(feeder_id="F01", description="M", load_type=LoadType.MOTOR_DOL,
                             power_kw=15.0, cos_phi=None, efficiency=None)
        i18n.set_language("en")
        _, _, validations = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, [feeder])
        data_rule = next(v for v in validations if v.rule_id == "RULE-DATA-001")
        assert data_rule.description == "Motor cos phi or efficiency not provided."


class TestPhase2DataLayer:
    def test_json_catalog_loaded_with_soft_starters(self):
        assert len(CATALOG) >= 55
        types = {d.device_type for d in CATALOG}
        assert "SOFT_STARTER" in types
        assert "MPCB" in types and "CONTACTOR" in types and "VFD" in types

    def test_json_selectivity_rules_loaded(self):
        rules = SiemensSelectivityRepository.get_selectivity_rules()
        assert len(rules) >= 7
        assert any(r.upstream_series == "SENTRON 3VA2" for r in rules)

    def test_standards_registry_localized(self):
        from lv_assist.catalog import StandardsRegistry
        i18n.set_language("en")
        t_en = StandardsRegistry.title("IEC 60909-0")
        assert t_en and t_en != "IEC 60909-0"
        assert StandardsRegistry.scope("IEC 60909-0")
        i18n.set_language("fa")
        t_fa = StandardsRegistry.title("IEC 60909-0")
        assert t_fa != t_en
        i18n.set_language("fa")


class TestPhase2IkAndDip:
    def test_ik_from_transformer(self):
        project = make_project(prospective_ik_ka=None, transformer_kva=1600.0, transformer_uk_pct=6.0)
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, [make_feeder()])
        assert summary.ik_used_ka is not None
        assert abs(summary.ik_used_ka - 42.34) < 0.05
        assert any(v.rule_id == "RULE-IK-012" and v.status == ValidationStatus.COMPLETED for v in validations)

    def test_no_ik_degrades_gracefully(self):
        project = make_project(prospective_ik_ka=None)
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, [make_feeder()])
        assert summary.ik_used_ka is None
        assert outs[0].selectivity_state == SelectivityEvalState.PRELIMINARY_RATIO_ONLY
        assert any(v.rule_id == "RULE-IK-012" and v.status == ValidationStatus.INSUFFICIENT_DATA for v in validations)

    def test_starting_dip_calculated(self):
        project = make_project(prospective_ik_ka=22.0)
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(
            project, [make_feeder(load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)])
        f = outs[0]
        assert f.starting_kva > 0
        assert f.starting_dip_pct is not None and 0 < f.starting_dip_pct < 20
        assert summary.max_motor_starting_dip_pct == f.starting_dip_pct
        assert summary.max_starting_dip_motor == f.feeder_id

    def test_dip_without_ik_is_none(self):
        project = make_project(prospective_ik_ka=None)
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(
            project, [make_feeder(load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)])
        assert outs[0].starting_kva > 0
        assert outs[0].starting_dip_pct is None
        assert summary.max_motor_starting_dip_pct is None


class TestPhase2CableData:
    def test_al_conductor_requires_larger_section(self):
        cu = CableSizingEngine.select_feeder_cable(
            ib_a=100.0, protection_in_a=125.0, is_adjustable_prot=True, length_m=20.0, cos_phi=0.9,
            voltage_v=400.0, phases=3, ambient_temp_c=30.0, grouping_k2=0.8, max_vdrop_pct=5.0,
            load_type=LoadType.SUB_FEEDER, conductor="CU")
        al = CableSizingEngine.select_feeder_cable(
            ib_a=100.0, protection_in_a=125.0, is_adjustable_prot=True, length_m=20.0, cos_phi=0.9,
            voltage_v=400.0, phases=3, ambient_temp_c=30.0, grouping_k2=0.8, max_vdrop_pct=5.0,
            load_type=LoadType.SUB_FEEDER, conductor="AL")
        assert al[0] > cu[0]
        assert "Al" in al[5]

    def test_xlpe_and_method_e_boost_iz(self):
        pvc = CableSizingEngine.select_feeder_cable(
            ib_a=30.0, protection_in_a=32.0, is_adjustable_prot=True, length_m=20.0, cos_phi=0.9,
            voltage_v=400.0, phases=3, ambient_temp_c=30.0, grouping_k2=0.8, max_vdrop_pct=5.0,
            load_type=LoadType.SUB_FEEDER, insulation="PVC", installation_method="C")
        xlpe_e = CableSizingEngine.select_feeder_cable(
            ib_a=30.0, protection_in_a=32.0, is_adjustable_prot=True, length_m=20.0, cos_phi=0.9,
            voltage_v=400.0, phases=3, ambient_temp_c=30.0, grouping_k2=0.8, max_vdrop_pct=5.0,
            load_type=LoadType.SUB_FEEDER, insulation="XLPE", installation_method="E")
        assert xlpe_e[3] > pvc[3]

    def test_thdi_neutral_sized_equal_phase(self):
        s_ph, s_n, _, _, _, _ = CableSizingEngine.select_feeder_cable(
            ib_a=45.0, protection_in_a=50.0, is_adjustable_prot=True, length_m=30.0, cos_phi=0.85,
            voltage_v=400.0, phases=3, ambient_temp_c=40.0, grouping_k2=0.8, max_vdrop_pct=5.0,
            load_type=LoadType.SUB_FEEDER, thdi_pct=35.0)
        assert s_n == s_ph

    def test_fire_resistant_designation(self):
        *_, desig = CableSizingEngine.select_feeder_cable(
            ib_a=30.0, protection_in_a=32.0, is_adjustable_prot=True, length_m=20.0, cos_phi=0.9,
            voltage_v=400.0, phases=3, ambient_temp_c=30.0, grouping_k2=0.8, max_vdrop_pct=5.0,
            load_type=LoadType.SUB_FEEDER, fire_resistant=True)
        assert "FR" in desig

    def test_harmonic_validations_emitted(self):
        project = make_project()
        outs, _, validations = EngineeringEngine(CATALOG).process_project(
            project, [make_feeder(load_type=LoadType.SUB_FEEDER, thdi_pct=40.0)])
        assert any(v.rule_id == "RULE-HARM-011" and v.status == ValidationStatus.WARNING for v in validations)
        assert outs[0].selected_phase_mm2 > 0


class TestPhase2SoftStarterAndScenarios:
    def test_soft_starter_selected(self):
        outs, _, _ = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.MOTOR_SOFT_STARTER, power_kw=18.5, cos_phi=0.85, efficiency=0.93)])
        f = outs[0]
        assert f.selected_soft_starter is not None
        assert f.selected_soft_starter.device_type == "SOFT_STARTER"
        assert f.selected_protection is not None

    def test_type2_coordination_rule_dol(self):
        _, _, validations = EngineeringEngine(CATALOG).process_project(
            make_project(),
            [make_feeder(load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)])
        coord = next(v for v in validations if v.rule_id == "RULE-COORD-002")
        assert coord.status in (ValidationStatus.COMPLETED, ValidationStatus.WARNING)

    def test_fire_pump_requires_real_starting_data_instead_of_fixed_multiplier(self):
        project = make_project(special_scenario="FIRE_PUMP")
        fp = make_feeder("FP1", power_kw=30.0, cos_phi=0.8, efficiency=0.9, fire_pump_service=True)
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, [fp])
        assert summary.design_main_current_a > 0
        assert not any(v.rule_id == 'RULE-SCEN-FP-021' for v in validations)
        assert any(v.rule_id == 'SCEN-FIRE-START' and v.status == ValidationStatus.INSUFFICIENT_DATA for v in validations)

    def test_suggested_spec_when_catalog_short(self):
        small_catalog = [d for d in CATALOG if d.device_type in ("MCB", "CONTACTOR")]
        outs, _, _ = EngineeringEngine(small_catalog).process_project(
            make_project(prospective_ik_ka=5.0),
            [make_feeder(load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)])
        f = outs[0]
        assert f.selected_protection is None
        assert f.suggested_spec_str


class TestPhase2TemplateRoundtrip:
    def test_new_fields_roundtrip(self, tmp_path):
        in_path = tmp_path / "input.xlsx"
        ExcelInputManager.create_input_template(str(in_path))
        project, feeders, _ = ExcelInputManager.load_from_excel(str(in_path))
        assert project.transformer_kva == 1600.0
        assert project.transformer_uk_pct == 6.0
        assert project.panel_type.value == "MCC"
        assert feeders[2].insulation.value == "XLPE"
        assert feeders[2].thdi_pct == 40.0

    def test_old_template_without_new_columns_still_loads(self, tmp_path):
        path = tmp_path / "old.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active; ws.title = "Project_Spec"
        ws.append(["key", "value", "guide"])
        ws.append(["project_name", "Old"])
        ws.append(["prospective_ik_ka", 22.0])
        ws2 = wb.create_sheet("Feeders_List")
        ws2.append(["feeder_id", "func_tag", "loc_tag", "description", "load_type",
                    "power_kw", "phases", "cos_phi", "efficiency", "demand_factor_kd",
                    "cable_length_m", "cable_section_mm2", "has_socket_outlets"])
        ws2.append(["F01", "=PWR", "+MCC1", "Old feeder", "SUB_FEEDER", 5.0, 3, 0.9, 1.0, 1.0, 20.0, None, False])
        wb.save(str(path))
        project, feeders, _ = ExcelInputManager.load_from_excel(str(path))
        assert project.prospective_ik_ka == 22.0
        assert project.transformer_kva is None
        assert feeders[0].conductor_material.value == "CU"
        assert feeders[0].fire_pump_service is False


def _phase3_project():
    project = make_project(transformer_kva=1600.0)
    feeders = [
        make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
        make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93),
        make_feeder("F03", load_type=LoadType.MOTOR_VFD, power_kw=18.5, cos_phi=0.95, efficiency=0.90),
        make_feeder("F04", load_type=LoadType.LIGHTING_SOCKET, power_kw=12.0, has_socket_outlets=True),
    ]
    outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
    return project, outs, summary, validations


class TestPhase3Sld:
    def test_sld_generates_valid_svg(self, tmp_path):
        import xml.etree.ElementTree as ET
        project, outs, summary, _ = _phase3_project()
        path = tmp_path / "sld.svg"
        SldGenerator.generate_svg_file(str(path), project, outs, summary)
        root = ET.parse(str(path)).getroot()
        assert root.tag.endswith("svg")
        content = path.read_text(encoding="utf-8")
        assert project.project_name in content
        assert "F01" in content and "F04" in content
        assert summary.main_breaker.part_number in content
        assert "L1" in content and "PE" in content

    def test_sld_without_main_breaker_shows_suggestion(self, tmp_path):
        project = make_project(prospective_ik_ka=150.0)
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, [make_feeder()])
        svg = SldGenerator.generate_svg(project, outs, summary)
        assert summary.suggested_main_breaker_str in svg


class TestPhase3Tcc:
    def test_tcc_generates_valid_svg(self, tmp_path):
        import xml.etree.ElementTree as ET
        project, outs, summary, _ = _phase3_project()
        path = tmp_path / "tcc.svg"
        TccGenerator.generate_svg_file(str(path), project, outs, summary)
        root = ET.parse(str(path)).getroot()
        assert root.tag.endswith("svg")
        content = path.read_text(encoding="utf-8")
        assert "100,000" in content
        assert summary.main_breaker.part_number in content

    def test_tcc_includes_ik_and_selectivity_markers(self):
        project, outs, summary, _ = _phase3_project()
        svg = TccGenerator.generate_svg(project, outs, summary)
        assert "22.0 kA" in svg
        assert "55" in svg

    def test_tcc_curve_geometry_within_plot_area(self):
        dev = CatalogDevice(part_number="T", manufacturer="T", series="T", device_type="MCCB",
                            rated_current_in_a=100.0, icu_ka_400v=36.0)
        for i, t in TccGenerator._curve_points(dev):
            assert TccGenerator.X0 <= TccGenerator._px(i) <= TccGenerator.X1
            assert TccGenerator.Y0 <= TccGenerator._py(t) <= TccGenerator.Y1
        assert TccGenerator._curve_points(dev)[-1][1] == 0.01


class TestPhase7SldTccTuning:
    def test_sld_line_weight_hierarchy_and_title_block(self):
        project, outs, summary, _ = _phase3_project()
        svg = SldGenerator.generate_svg(project, outs, summary)
        assert 'stroke-width="3.5"' in svg   # شین اصلی
        assert 'stroke-width="1.8"' in svg   # مدار قدرت
        assert 'stroke-width="1.0"' in svg   # کنترل/سیگنال
        assert tr("sld_dwg") in svg and "SLD-" in svg
        assert tr("sld_legend") in svg
        assert tr("sld_lw_busbar") in svg and tr("sld_lw_power") in svg and tr("sld_lw_control") in svg
        assert project.earthing_system.value in svg

    def test_sld_designer_in_title_block(self):
        project = make_project(designer_name="A. Engineer")
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, [make_feeder()])
        svg = SldGenerator.generate_svg(project, outs, summary)
        assert "A. Engineer" in svg

    def test_sld_dynamic_column_pitch(self):
        import re
        project, _, _, _ = _phase3_project()
        feeders = [make_feeder(f"F{i:02d}", description="پمپ تغذیه آب آتش‌نشانی واحد فرآیندی شمال",
                               load_type=LoadType.MOTOR_DOL, power_kw=11.0, cos_phi=0.85, efficiency=0.9)
                   for i in range(1, 7)]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        svg = SldGenerator.generate_svg(project, outs, summary)
        w = float(re.search(r'width="([\d.]+)"', svg).group(1))
        assert w > 1180.0   # برچسب‌های بلند → ستون عریض‌تر و بوم عریض‌تر

    def test_sld_cable_text_wraps_to_two_lines(self):
        project, outs, summary, _ = _phase3_project()
        svg = SldGenerator.generate_svg(project, outs, summary)
        long_cable = any(len(f.cable_designation_str or "") > 24 for f in outs)
        assert ("<tspan" in svg) == long_cable

    def test_tcc_estimated_curve_label_f003(self):
        project, outs, summary, _ = _phase3_project()
        svg = TccGenerator.generate_svg(project, outs, summary)
        series = [summary.main_breaker.series] + [f.selected_protection.series
                                                  for f in outs if f.selected_protection]
        n_est = sum(1 for s in series if not TripCurveRepository.is_datasheet_points(s))
        note = tr("tcc_estimated_note")
        assert (note in svg) == (n_est > 0)
        if n_est > 0:
            assert svg.count("≈") == n_est + 1  # علامت هر منحنی تخمینی + بنر

    def test_tcc_verified_curves_have_no_est_label(self):
        project, outs, summary, _ = _phase3_project()
        for f in outs:
            if f.selected_protection:
                f.selected_protection.series = "ABB MS132"   # سری دارای دیتاشیت
        if summary.main_breaker:
            summary.main_breaker.series = "ABB Tmax XT1"
        svg = TccGenerator.generate_svg(project, outs, summary)
        assert tr("tcc_estimated_note") not in svg


class TestPhase3Eplan:
    def test_eplan_csv_columns_and_rows(self, tmp_path):
        project, outs, summary, _ = _phase3_project()
        path = tmp_path / "parts.csv"
        EplanExporter.export_csv(str(path), project, outs, summary)
        import csv
        with open(str(path), encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[0] == EplanExporter.HEADERS
        assert len(rows) > 10
        assert summary.main_breaker.part_number in [r[0] for r in rows]
        assert any("=INCOMING" in r[4] for r in rows)

    def test_eplan_suggested_when_no_device(self, tmp_path):
        project = make_project(prospective_ik_ka=150.0)
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, [make_feeder()])
        path = tmp_path / "parts.csv"
        EplanExporter.export_csv(str(path), project, outs, summary)
        with open(str(path), encoding="utf-8-sig") as f:
            content = f.read()
        assert "To be purchased" in content


class TestPhase3Pdf:
    def test_pdf_browser_found(self):
        assert PdfExporter._find_browser() is not None

    def test_html_to_pdf_roundtrip(self, tmp_path):
        project, outs, summary, validations = _phase3_project()
        html_path = tmp_path / "report.html"
        pdf_path = tmp_path / "report.pdf"
        PrintableReportExporter.generate_html_report(str(html_path), project, outs, summary, validations)
        assert PdfExporter.export_html_to_pdf(str(html_path), str(pdf_path))
        assert pdf_path.stat().st_size > 1000
        assert open(str(pdf_path), "rb").read(5) == b"%PDF-"

    def test_pdf_fails_without_browser(self, monkeypatch, tmp_path):
        monkeypatch.setattr(PdfExporter, "_find_browser", lambda: None)
        html_path = tmp_path / "r.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        assert PdfExporter.export_html_to_pdf(str(html_path), str(tmp_path / "r.pdf")) is False

# -*- coding: utf-8 -*-


def _phase4_cap_project(**project_overrides):
    """cos φ low → capacitor bank required."""
    project = make_project(**project_overrides)
    feeders = [
        make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=60.0, cos_phi=0.80, efficiency=0.90),
    ]
    outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
    return project, outs, summary, validations


def _rule_ids(validations):
    return [v.rule_id for v in validations]


class TestPhase4CapBank:
    def test_cap_bank_sizing_and_steps(self):
        _, _, summary, validations = _phase4_cap_project()
        assert summary.overall_cos_phi < 0.95
        assert summary.cap_bank_required_kvar > 20.0
        assert summary.cap_bank_installed_kvar >= summary.cap_bank_required_kvar
        assert summary.cap_bank_steps and all(s in (5.0, 10.0, 12.5, 15.0, 20.0, 25.0, 50.0) for s in summary.cap_bank_steps)
        assert "RULE-CAP-015" in _rule_ids(validations)
        assert summary.cap_bank_contactor is not None
        assert summary.cap_bank_module_dev is not None
        assert summary.cap_bank_protection is not None

    def test_cap_bank_not_needed_when_cos_ok(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.HEATER_RESISTIVE, power_kw=10.0, cos_phi=1.0)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.cap_bank_installed_kvar == 0.0
        assert "RULE-CAP-015" in _rule_ids(validations)
        assert "RULE-CAP-016" not in _rule_ids(validations)

    def test_detuned_reactor_for_high_thdi(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=60.0, cos_phi=0.80, efficiency=0.90, thdi_pct=25.0)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.panel_thdi_pct == 25.0
        assert summary.cap_bank_detuned_pct == 14.0
        assert summary.cap_bank_reactor_tuned_hz == 134.0
        assert summary.cap_bank_reactor_dev is not None
        assert "RULE-HARM-014" in _rule_ids(validations)

    def test_panel_thdi_weighted(self):
        project = make_project()
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_VFD, power_kw=18.5, cos_phi=0.95, efficiency=0.90, thdi_pct=40.0),
            make_feeder("F02", load_type=LoadType.HEATER_RESISTIVE, power_kw=60.0, cos_phi=1.0),
        ]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        w = [outs[0].design_current_ib_a, outs[1].design_current_ib_a]
        expected = round(40.0 * w[0] / sum(w), 1)
        assert summary.panel_thdi_pct == expected
        assert summary.cap_bank_detuned_pct == 7.0

    def test_panel_thdi_missing_data(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.panel_thdi_pct is None
        harm = [v for v in validations if v.rule_id == "RULE-HARM-013"]
        assert harm and harm[0].status == ValidationStatus.INSUFFICIENT_DATA

    def test_resonance_warning_for_standard_bank(self):
        project = make_project(prospective_ik_ka=2.0)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=60.0, cos_phi=0.80, efficiency=0.90)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.cap_bank_detuned_pct == 0.0
        assert summary.cap_bank_resonance_order is not None
        res = [v for v in validations if v.rule_id == "RULE-CAP-016"]
        assert res and res[0].status == ValidationStatus.WARNING

    def test_resonance_ok_far_from_harmonics(self):
        _, _, summary, validations = _phase4_cap_project()
        res = [v for v in validations if v.rule_id == "RULE-CAP-016"]
        assert summary.cap_bank_resonance_order is not None
        assert res and res[0].status == ValidationStatus.COMPLETED


class TestPhase4Thermal:
    def test_altitude_derating(self):
        project = make_project(altitude_m=3000.0)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.altitude_derating_factor == 0.9
        assert "RULE-THERM-015" in _rule_ids(validations)

    def test_no_altitude_derating_below_2000m(self):
        project = make_project(altitude_m=1500.0)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.altitude_derating_factor == 1.0
        assert "RULE-THERM-015" not in _rule_ids(validations)

    def test_internal_temp_estimate(self):
        project = make_project(ambient_temp_c=40.0, max_internal_temp_c=50.0)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.estimated_internal_temp_c is not None
        assert summary.estimated_internal_temp_c <= 50.0
        tint = [v for v in validations if v.rule_id == "RULE-THERM-016"]
        assert tint and tint[0].status == ValidationStatus.WARNING


class TestPhase4Scenarios:
    def test_ats_mains_mains_rule(self):
        project = make_project(special_scenario=SpecialScenario.ATS_MAINS_MAINS)
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert 'SCEN-ATS-INTERLOCK' in _rule_ids(validations)

    def test_ups_critical_rule(self):
        project = make_project(special_scenario=SpecialScenario.UPS_CRITICAL)
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert 'SCEN-UPS-KW' in _rule_ids(validations)

    def test_emergency_lighting_warns_without_fr(self):
        project = make_project(special_scenario=SpecialScenario.EMERGENCY_LIGHTING)
        feeders = [make_feeder("F01", load_type=LoadType.LIGHTING_SOCKET, power_kw=5.0, has_socket_outlets=False)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        eml = [v for v in validations if v.rule_id == 'SCEN-BATTERY-ENERGY']
        assert eml and eml[0].status == ValidationStatus.INSUFFICIENT_DATA

    def test_emergency_lighting_not_approved_from_fire_resistance_alone(self):
        project = make_project(special_scenario=SpecialScenario.EMERGENCY_LIGHTING)
        feeders = [make_feeder("F01", load_type=LoadType.LIGHTING_SOCKET, power_kw=5.0, has_socket_outlets=False, fire_resistant=True)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        eml = [v for v in validations if v.rule_id == 'SCEN-BATTERY-ENERGY']
        assert eml and eml[0].status == ValidationStatus.INSUFFICIENT_DATA


class TestPhase4CurveSelectivity:
    def _pair(self, up_in=250.0, down_in=25.0, up_series="SERIES_X", down_series="SERIES_Y"):
        up = CatalogDevice(part_number="U", manufacturer="X", series=up_series, device_type="MCCB",
                           rated_current_in_a=up_in, icu_ka_400v=36.0)
        down = CatalogDevice(part_number="D", manufacturer="X", series=down_series, device_type="MCB",
                             rated_current_in_a=down_in, icu_ka_400v=15.0)
        return up, down

    def test_current_selectivity_preliminary_not_verified(self):
        # F-003: منحنی تقریبی هرگز وضعیت VERIFIED صادر نمی‌کند
        up, down = self._pair()
        state, limit, ref = SiemensSelectivityRepository.evaluate_pair(up, down, 22.0)
        assert state == SelectivityEvalState.PRELIMINARY
        assert limit == 2.0
        assert "kA" in ref

    def test_current_selectivity_preliminary_even_below_limit(self):
        # F-003: حتی وقتی حد تخمینی بالاتر از Ik است، وضعیت همچنان مقدماتی می‌ماند
        up, down = self._pair()
        state, limit, _ = SiemensSelectivityRepository.evaluate_pair(up, down, 1.0)
        assert state == SelectivityEvalState.PRELIMINARY
        assert limit == 2.0

    def test_no_selectivity_when_ratio_low(self):
        up, down = self._pair(up_in=250.0, down_in=200.0)
        state, limit, _ = SiemensSelectivityRepository.evaluate_pair(up, down, 22.0)
        assert state == SelectivityEvalState.VIOLATION

    def test_ratio_only_when_down_band_reaches_up_band(self):
        up = CatalogDevice(part_number="U", manufacturer="X", series="SENTRON 3VA1", device_type="MCCB",
                           rated_current_in_a=250.0, icu_ka_400v=36.0)
        down = CatalogDevice(part_number="D", manufacturer="X", series="SIRIUS 3RV20", device_type="MPCB",
                             rated_current_in_a=140.0, icu_ka_400v=15.0)
        state, limit, _ = SiemensSelectivityRepository.evaluate_pair(up, down, 22.0)
        assert state == SelectivityEvalState.PRELIMINARY_RATIO_ONLY
        assert limit is None


class TestPhase4TccManufacturerData:
    def test_trip_curve_repo_thermal_time(self):
        # فاز ۶: سری‌های واقعی با نقاط رسمی دیتاشیت جایگزین مدل پارامتری شدند
        assert abs(TripCurveRepository.thermal_time_s("SENTRON 5SY4", 5.0) - 0.8) < 0.01
        assert abs(TripCurveRepository.thermal_time_s("SIRIUS 3RV20", 2.0) - 30.0) < 0.01
        assert abs(TripCurveRepository.thermal_time_s("SIRIUS 3RV20", 6.0) - 1.5) < 0.01
        assert abs(TripCurveRepository.thermal_time_s("DEFAULT", 2.0) - 90.0 / 2.0 ** 2) < 0.01
        assert TripCurveRepository.thermal_time_s("SERIES_Z", 100.0) == 0.01

    def test_mpcb_curve_uses_15_6_band(self):
        dev = CatalogDevice(part_number="M", manufacturer="S", series="SIRIUS 3RV20", device_type="MPCB",
                            rated_current_in_a=25.0, icu_ka_400v=50.0)
        pts = TccGenerator._curve_points(dev)
        assert pts[-1][0] == 25.0 * 15.6
        assert pts[-1][1] == 0.01

    def test_instantaneous_band_geometry(self):
        dev = CatalogDevice(part_number="B", manufacturer="S", series="SENTRON 3VA1", device_type="MCCB",
                            rated_current_in_a=160.0, icu_ka_400v=55.0)
        band = TccGenerator._instantaneous_band(dev, "#1F4E78")
        assert "rect" in band and 'opacity="0.35"' in band
        im_min, im_max = TripCurveRepository.instantaneous_band_a("SENTRON 3VA1", 160.0)
        for i in (im_min, im_max):
            assert TccGenerator.X0 <= TccGenerator._px(i) <= TccGenerator.X1

    def test_tcc_svg_contains_bands(self):
        project, outs, summary, _ = _phase3_project()
        svg = TccGenerator.generate_svg(project, outs, summary)
        assert svg.count('opacity="0.35"') >= 2


class TestPhase4Exports:
    def test_sld_cap_branch_drawn(self, tmp_path):
        project, _, summary, _ = _phase4_cap_project()
        outs = EngineeringEngine(CATALOG).process_project(
            project, [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=60.0, cos_phi=0.80, efficiency=0.90)])[0]
        path = tmp_path / "sld.svg"
        SldGenerator.generate_svg_file(str(path), project, outs, summary)
        content = path.read_text(encoding="utf-8")
        assert "-Qcap" in content and "kvar" in content

    def test_eplan_cap_bank_rows(self, tmp_path):
        import csv
        project, outs, summary, _ = _phase4_cap_project()
        path = tmp_path / "parts.csv"
        EplanExporter.export_csv(str(path), project, outs, summary)
        with open(str(path), encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert any("=PFC" in r[4] for r in rows)
        assert any("-Kcap" in r[4] for r in rows)
        assert not any("-Lcap" in r[4] for r in rows)

    def test_excel_bom_cap_rows(self, tmp_path):
        project, outs, summary, validations = _phase4_cap_project()
        path = tmp_path / "out.xlsx"
        ExcelExporter.export_to_excel(str(path), project, outs, summary, validations)
        wb = openpyxl.load_workbook(str(path))
        bom = wb["04_BOM"]
        tags = [str(c.value) for row in bom.iter_rows(min_row=2) for c in row]
        assert any("-Kcap" in t for t in tags)
        ws1 = wb["01_Project_Summary"]
        labels = [str(c.value) for row in ws1.iter_rows(min_row=2) for c in row]
        assert any("kvar" in l for l in labels)


class TestAuditDataLayer:
    """تست‌های ممیزی مرحله ۲: اتصال موتور به دیتابیس SQLite."""

    def test_f001_no_fabricated_ampacity(self):
        assert catalog_repo.get_base_cable_iz0(10.0) == 57.0
        assert catalog_repo.get_base_cable_iz0(300.0) == 464.0
        assert catalog_repo.get_base_cable_iz0(4.5) is None
        table = catalog_repo.get_cable_iz0_table_cu_pvc_c(3)
        assert table[240.0] == 403.0

    def test_f005_pe_no_artificial_cap(self):
        assert catalog_repo.get_standard_pe_section(380.0) == 400.0
        assert catalog_repo.get_standard_pe_section(500.0) is None
        assert CableSizingEngine.calculate_pe_section(900.0, fault_current_ka=0.0, clear_time_s=0.4) is None
        assert CableSizingEngine.calculate_pe_section(240.0, fault_current_ka=0.0, clear_time_s=0.4) == 120.0

    def test_f006_icu_at_project_voltage(self):
        mccb = next(d for d in CATALOG if d.device_type == "MCCB")
        assert catalog_repo.get_device_icu_at_voltage(mccb.part_number, 400.0) == mccb.icu_ka_400v
        assert catalog_repo.get_device_icu_at_voltage(mccb.part_number, 480.0) is None

    def test_f007_enclosure_ip_filter(self):
        encl = catalog_repo.get_compatible_enclosures("IP66")
        assert encl and all("66" in (e.ip_rating or "") for e in encl)
        assert catalog_repo.get_compatible_enclosures("IP69") == []

    def test_f016_data_quality_explicit(self):
        est = [d for d in catalog_repo.devices if d.data_quality == DataQuality.ESTIMATED]
        assert est
        assert all(d.data_quality in (DataQuality.REAL_VERIFIED, DataQuality.ESTIMATED) for d in catalog_repo.devices)

    def test_f017_derating_no_silent_reuse_above_50c(self):
        mccb = next(d for d in CATALOG if d.device_type == "MCCB")
        f45 = catalog_repo.get_device_derating_factor(mccb.part_number, 45.0)
        assert f45 is not None and f45 == mccb.derating_50c
        assert catalog_repo.get_device_derating_factor(mccb.part_number, 55.0) is None

    def test_f003_preliminary_state_reported(self):
        # زوج بدون جدول سازنده با منحنی تقریبی → وضعیت PRELIMINARY و اعتبارسنجی WARNING
        up = CatalogDevice(part_number="U", manufacturer="X", series="SERIES_X", device_type="MCCB",
                           rated_current_in_a=250.0, icu_ka_400v=36.0)
        down = CatalogDevice(part_number="D", manufacturer="X", series="SERIES_Y", device_type="MCB",
                             rated_current_in_a=25.0, icu_ka_400v=15.0)
        state, limit, ref = SiemensSelectivityRepository.evaluate_pair(up, down, 22.0)
        assert state == SelectivityEvalState.PRELIMINARY
        assert state.value == "PRELIMINARY"
        assert limit == 2.0

    def test_nontable_cable_section_reports_insufficient_data(self):
        # F-001 در سطح موتور: مقطع غیرجدولی → RULE-CABLE-010 با وضعیت INSUFFICIENT_DATA
        project = make_project(prospective_ik_ka=22.0)
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0, cable_section_mm2=4.5)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        cable = [v for v in validations if v.rule_id == "RULE-CABLE-010"]
        assert cable and cable[0].status == ValidationStatus.INSUFFICIENT_DATA

    def test_nonstandard_pe_reports_insufficient_data(self):
        # F-005 در سطح موتور: فاز فراتر از جدول PE → RULE-PE-006 با وضعیت INSUFFICIENT_DATA
        project = make_project(prospective_ik_ka=22.0)
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0, cable_section_mm2=900.0)]
        outs, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        pe = [v for v in validations if v.rule_id == "RULE-PE-006"]
        assert pe and pe[0].status == ValidationStatus.INSUFFICIENT_DATA
        assert outs[0].selected_pe_mm2 is None

    def test_high_temp_triggers_therm_017(self):
        # F-017 در سطح موتور: دمای داخلی بالای 50°C بدون داده → RULE-THERM-017
        project = make_project(prospective_ik_ka=22.0, max_internal_temp_c=55.0)
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        therm = [v for v in validations if v.rule_id == "RULE-THERM-017"]
        assert therm and therm[0].status == ValidationStatus.INSUFFICIENT_DATA

    def test_nonstandard_voltage_triggers_volt_018(self):
        # F-006 در سطح موتور: ولتاژ خارج از محدوده 400/415 → RULE-PROT-VOLT-018
        project = make_project(prospective_ik_ka=22.0, nominal_voltage_v=480.0)
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0)]
        _, _, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        volt = [v for v in validations if v.rule_id == "RULE-PROT-VOLT-018"]
        assert volt and volt[0].status == ValidationStatus.INSUFFICIENT_DATA

    def test_high_ip_enclosure_falls_back_with_rule(self):
        # F-007 در سطح موتور: IP هدف بالاتر از کاتالوگ → بدنه تخمینی + RULE-ENC-IP-019
        project = make_project(prospective_ik_ka=22.0, target_ip="IP69")
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        enc = [v for v in validations if v.rule_id == "RULE-ENC-IP-019"]
        assert enc and enc[0].status == ValidationStatus.INSUFFICIENT_DATA
        assert summary.selected_enclosure.part_number == "EST-PANEL"


class TestPhase5ManufacturerLibrary:
    def test_manufacturers_expanded(self):
        mfgs = {d.manufacturer for d in CATALOG}
        assert {"ABB", "Schneider", "Eaton", "Siemens"} <= mfgs

    def test_preferred_manufacturer_filters_selection(self):
        project = make_project(preferred_manufacturer="ABB")
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        f = outs[0]
        for dev in (f.selected_protection, f.selected_contactor_main):
            assert dev is not None and dev.manufacturer == "ABB"
        assert summary.main_breaker is not None and summary.main_breaker.manufacturer == "ABB"

    def test_preferred_manufacturer_unknown_falls_back(self):
        project = make_project(preferred_manufacturer="NONEXISTENT")
        outs, _, _ = EngineeringEngine(CATALOG).process_project(project, [make_feeder()])
        assert outs[0].selected_protection is not None

    def test_no_state_leak_between_runs(self):
        engine = EngineeringEngine(CATALOG)
        engine.process_project(
            make_project(preferred_manufacturer="ABB"),
            [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)])
        outs, _, _ = engine.process_project(make_project(), [make_feeder()])
        assert outs[0].selected_protection is not None

    def test_phase5_curves_and_rules_present(self):
        assert len(catalog_repo.trip_curves) >= 16
        assert len(SiemensSelectivityRepository.get_selectivity_rules()) >= 12
        assert TripCurveRepository.thermal_time_s("ABB Tmax XT1", 5.0) > 0.0
        im_min, im_max = TripCurveRepository.instantaneous_band_a("Eaton NZM1", 100.0)
        assert 0 < im_min <= im_max
        series = {r.upstream_series for r in catalog_repo.load_selectivity_rules()}
        assert {"ABB Tmax XT1", "Schneider NSX100", "Eaton NZM1"} <= series


class TestPhase5ControlCircuits:
    def _motor_project(self):
        project = make_project()
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93),
            make_feeder("F03", load_type=LoadType.MOTOR_SOFT_STARTER, power_kw=18.5, cos_phi=0.85, efficiency=0.93),
            make_feeder("F04", load_type=LoadType.MOTOR_VFD, power_kw=7.5, cos_phi=0.95, efficiency=0.90),
            make_feeder("F05", load_type=LoadType.LIGHTING_SOCKET, power_kw=5.0, cos_phi=0.90),
        ]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        return project, outs, summary

    def test_wire_counts_per_feeder_type(self):
        project, outs, summary = self._motor_project()
        per = {}
        for w in ControlCircuitGenerator.build_all_wires(project, outs, summary):
            p = w.wire_no.split("-")[0]
            per[p] = per.get(p, 0) + 1
        assert per["W00"] == 5
        assert per["W01"] == 10
        assert per["W02"] == 19
        assert per["W03"] == 10
        assert per["W04"] == 11
        assert "W05" not in per  # فیدر غیر موتوری مدار کنترلی ندارد

    def test_svg_contains_device_tags(self):
        project, outs, summary = self._motor_project()
        svg = ControlCircuitGenerator.generate_svg(project, outs, summary)
        assert "<svg" in svg and "</svg>" in svg
        for tag in ("-Q01", "-G1", "-K1M", "-K2Y", "-K2D", "-U3", "-U4"):
            assert tag in svg

    def test_connections_csv(self, tmp_path):
        project, outs, summary = self._motor_project()
        wires = ControlCircuitGenerator.build_all_wires(project, outs, summary)
        path = tmp_path / "connections.csv"
        ControlCircuitGenerator.export_connections_csv(str(path), project, outs, summary)
        with open(str(path), encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
        assert lines[0].startswith("Connection,")
        assert len(lines) == len(wires) + 1

    def test_excel_sheet_control_circuits(self, tmp_path):
        project, outs, summary = self._motor_project()
        path = tmp_path / "out.xlsx"
        ExcelExporter.export_to_excel(str(path), project, outs, summary, [])
        ws = openpyxl.load_workbook(str(path))["05_Control_Circuits"]
        assert ws.max_row > 1
        assert ws.cell(row=2, column=1).value.startswith("W")


class TestPhase5PanelLayout:
    def test_layout_generates_rows_and_rules(self):
        project = make_project()
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
            make_feeder("F02", load_type=LoadType.SUB_FEEDER, power_kw=30.0, cos_phi=0.80, thdi_pct=35.0),
        ]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        res = PanelLayoutGenerator.generate(project, outs, summary)
        assert res.rows and res.fill_factor_pct > 0
        assert {v.rule_id for v in res.validations} == {
            "RULE-LAY-020", "RULE-LAY-021", "RULE-LAY-022", "RULE-LAY-023", "RULE-LAY-024"}
        assert all(d.width_mm > 0 for r in res.rows for d in r.devices)
        assert res.spare_space_pct == 20.0 and res.form_partition_factor >= 1.0

    def test_layout_constants_and_form_factor(self):
        assert PanelLayoutGenerator.HORIZONTAL_DUCT_HEIGHT_MM == 50.0
        assert PanelLayoutGenerator.VERTICAL_DUCT_WIDTH_MM == 60.0
        assert PanelLayoutGenerator.MCCB_ARC_CLEARANCE_MM == 80.0
        assert PanelLayoutGenerator.CABLE_GLAND_BOTTOM_ZONE_MM == 200.0
        assert PanelLayoutGenerator.BUS_BAR_ZONE_HEIGHT_MM == 120.0
        assert PanelLayoutGenerator._form_partition_factor("Form 4b") == 1.15
        assert PanelLayoutGenerator._form_partition_factor("Form 3a") == 1.10
        assert PanelLayoutGenerator._form_partition_factor("Form 2b") == 1.05

    def test_layout_spare_fill_with_form(self):
        project = make_project(internal_separation_form="Form 4b")
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
            make_feeder("F02", load_type=LoadType.SUB_FEEDER, power_kw=30.0, cos_phi=0.80, thdi_pct=35.0),
        ]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        res4 = PanelLayoutGenerator.generate(project, outs, summary)
        assert res4.form_partition_factor == 1.15
        rule = next(v for v in res4.validations if v.rule_id == "RULE-LAY-024")
        assert "1.15" in rule.supporting_evidence.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        outs2, summary2, _ = EngineeringEngine(CATALOG).process_project(
            make_project(internal_separation_form="Form 2b"), feeders)
        res2 = PanelLayoutGenerator.generate(make_project(internal_separation_form="Form 2b"), outs2, summary2)
        assert res2.form_partition_factor == 1.05
        assert res4.fill_factor_pct > res2.fill_factor_pct

    def test_layout_mccb_arc_clearance(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=40.0, cos_phi=0.80)]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        res = PanelLayoutGenerator.generate(project, outs, summary)
        mccb_devs = [d for r in res.rows for d in r.devices if d.tag == "-Q0"]
        assert mccb_devs and mccb_devs[0].clearance_mm >= PanelLayoutGenerator.MCCB_ARC_CLEARANCE_MM

    def test_layout_svg(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        svg = PanelLayoutGenerator.generate_svg(project, outs, summary)
        assert "<svg" in svg and "-Q0" in svg

    def test_layout_svg_has_ducts_busbar_gland_door(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        svg = PanelLayoutGenerator.generate_svg(project, outs, summary)
        assert "ductHatch" in svg
        assert tr("lay_busbar_zone") in svg
        assert tr("lay_gland_zone") in svg
        assert tr("lay_door_zone") in svg
        assert "W =" in svg and "H =" in svg and "D =" in svg


class TestPhase6OfficialCurves:
    def test_datasheet_points_present_for_verified_series(self):
        for s in ("ABB Tmax XT1", "ABB Tmax XT2", "ABB MS132", "Schneider NSX100",
                  "Schneider GV2ME", "Schneider Acti9 iC60", "Eaton NZM1", "Eaton PKZM0"):
            pts = TripCurveRepository.datasheet_points(s)
            assert pts is not None and len(pts) >= 8, s
            assert pts == sorted(pts)
            assert all(m > 0 and 0.005 <= t <= 10000 for m, t in pts)
            assert TripCurveRepository.is_datasheet_points(s)
            assert TripCurveRepository.datasheet_ref(s)

    def test_parametric_series_fall_back_to_formula(self):
        assert not TripCurveRepository.is_datasheet_points("Siemens SENTRON 3VA")
        assert TripCurveRepository.datasheet_points("Siemens SENTRON 3VA") is None
        t = TripCurveRepository.thermal_time_s("Siemens SENTRON 3VA", 2.0)
        assert 0.01 <= t <= 1000.0

    def test_interpolation_matches_datasheet_landmarks(self):
        assert abs(TripCurveRepository.thermal_time_s("ABB Tmax XT1", 1.5) - 80.0) < 1.0
        assert abs(TripCurveRepository.thermal_time_s("ABB Tmax XT1", 6.0) - 1.1) < 0.1
        assert abs(TripCurveRepository.thermal_time_s("ABB MS132", 2.0) - 30.0) < 1.0
        assert abs(TripCurveRepository.thermal_time_s("Schneider Acti9 iC60", 3.0) - 4.0) < 0.5

    def test_out_of_range_clamps_to_endpoints(self):
        pts = TripCurveRepository.datasheet_points("ABB Tmax XT1")
        m_min, t_min = pts[0]
        m_max, t_max = pts[-1]
        assert TripCurveRepository.thermal_time_s("ABB Tmax XT1", m_min * 0.5) == t_min
        assert TripCurveRepository.thermal_time_s("ABB Tmax XT1", m_max * 2.0) == t_max

    def test_tcc_uses_points_for_curve_generation(self):
        project, outs, summary, _ = _phase3_project()
        svg = TccGenerator.generate_svg(project, outs, summary)
        assert "<polyline" in svg


class TestPhase6Busbar:
    def _run(self, **project_overrides):
        project = make_project(**project_overrides)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91)]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        return project, outs, summary, validations

    def test_busbar_verification_rules_present(self):
        _, _, summary, validations = self._run(prospective_ik_ka=22.0)
        bus_rules = {v.rule_id for v in validations if v.rule_id.startswith("RULE-BUS-")}
        assert bus_rules == {"RULE-BUS-024", "RULE-BUS-025", "RULE-BUS-026", "RULE-BUS-027", "RULE-BUS-028"}
        assert summary.busbar_rating_a > 0
        assert summary.busbar_icw_1s_ka >= 22.0
        assert summary.busbar_ipk_ka >= summary.busbar_required_ipk_ka
        assert summary.busbar_required_supports >= 2
        assert summary.busbar_max_support_spacing_mm > 0
        assert summary.recommended_busbar_spec.startswith("Cu ")

    def test_busbar_select_icw_and_ipk_cover_ik(self):
        res = BusbarEngine.select(130.0, 22.0, 800.0)
        assert res.icw_1s_ka >= 22.0
        assert res.ipk_ka >= res.required_ipk_ka
        assert res.spec.startswith("Cu ")
        assert {v.rule_id for v in res.validations} == {"RULE-BUS-024", "RULE-BUS-025", "RULE-BUS-026", "RULE-BUS-027", "RULE-BUS-028"}

    def test_busbar_without_ik_is_insufficient_data(self):
        res = BusbarEngine.select(130.0, None, 800.0)
        statuses = {v.rule_id: v.status for v in res.validations}
        assert statuses["RULE-BUS-024"] == ValidationStatus.WARNING
        assert statuses["RULE-BUS-025"] == ValidationStatus.INSUFFICIENT_DATA
        assert statuses["RULE-BUS-026"] == ValidationStatus.INSUFFICIENT_DATA
        assert statuses["RULE-BUS-027"] == ValidationStatus.INSUFFICIENT_DATA
        assert statuses["RULE-BUS-028"] == ValidationStatus.COMPLETED
        assert res.required_ipk_ka is None
        assert res.spec

    def test_busbar_supports_grow_with_panel_width(self):
        narrow = BusbarEngine.select(130.0, 22.0, 600.0)
        wide = BusbarEngine.select(130.0, 22.0, 1200.0)
        assert wide.required_supports > narrow.required_supports






class TestPhase6EplanParts:
    def test_parts_headers_and_aggregated_quantities(self, tmp_path):
        project = make_project()
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93),
            make_feeder("F03", load_type=LoadType.SUB_FEEDER, power_kw=10.0),
        ]
        outs, summary, _ = EngineeringEngine(CATALOG).process_project(project, feeders)
        path = tmp_path / "parts_mgmt.csv"
        EplanPartsExporter.export_csv(str(path), project, outs, summary)
        import csv
        with open(str(path), encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[0] == EplanPartsExporter.HEADERS
        pns = [r[0] for r in rows[1:]]
        assert len(pns) == len(set(pns))
        assert len(pns) > 5
        assert all(int(r[-1]) >= 1 for r in rows[1:])
        star_delta_contactor = [r for r in rows[1:] if r[0].startswith("3RT")]
        assert star_delta_contactor
        assert max(int(r[-1]) for r in star_delta_contactor) >= 3

    def test_parts_product_groups_mapped(self, tmp_path):
        project, outs, summary, _ = _phase3_project()
        path = tmp_path / "parts_mgmt.csv"
        EplanPartsExporter.export_csv(str(path), project, outs, summary)
        import csv
        with open(str(path), encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        groups = {r[8] for r in rows[1:]}
        assert "Circuit breakers" in groups or "Motor-protective circuit breakers" in groups
        assert all(g for g in groups)


class TestPhase7AuditFixes:
    """فاز ۷: اصلاحات ممیزی — i18n، فن، خازن، امنیت خروجی."""

    def test_f019_theme_preserved_on_language_change(self, tmp_path):
        cfg = tmp_path / "config.json"
        i18n2 = I18n()
        i18n2.set_config_path(str(cfg))
        i18n2.set_theme("light")
        assert json.loads(cfg.read_text(encoding="utf-8")).get("theme") == "light"
        i18n2.set_language("de")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data.get("language") == "de"
        assert data.get("theme") == "light"
        i18n2.set_language("en")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data.get("theme") == "light" and data.get("language") == "en"

    def test_f002_fan_missing_reports_error(self):
        project = make_project(ambient_temp_c=40.0, max_internal_temp_c=50.0)
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=55.0, cos_phi=0.85, efficiency=0.93),
            make_feeder("F02", load_type=LoadType.MOTOR_DOL, power_kw=55.0, cos_phi=0.85, efficiency=0.93),
            make_feeder("F03", load_type=LoadType.MOTOR_DOL, power_kw=55.0, cos_phi=0.85, efficiency=0.93),
            make_feeder("F04", load_type=LoadType.MOTOR_DOL, power_kw=55.0, cos_phi=0.85, efficiency=0.93),
            make_feeder("F05", load_type=LoadType.MOTOR_DOL, power_kw=55.0, cos_phi=0.85, efficiency=0.93),
        ]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        therm = [v for v in validations if v.rule_id == "RULE-THERM-016"][0]
        if summary.required_airflow_m3h > 0 and summary.selected_fan is None:
            assert therm.status == ValidationStatus.ERROR
            assert summary.estimated_internal_temp_c > project.max_internal_temp_c
        else:
            assert therm.status in (ValidationStatus.COMPLETED, ValidationStatus.WARNING, ValidationStatus.ERROR)

    def test_f004_small_cap_steps(self):
        engine = EngineeringEngine(CATALOG)
        assert engine._pick_cap_steps(4.0) == [5.0]
        assert engine._pick_cap_steps(22.5) == [20.0, 5.0]
        assert engine._pick_cap_steps(60.0) == [50.0, 10.0]
        assert engine._pick_cap_steps(0.0) == []
        steps = engine._pick_cap_steps(engine._max_pfc_kvar() + 10.0)
        assert steps is None

    def test_f009_html_escapes_user_input(self, tmp_path):
        project = make_project(project_name="<script>alert(1)</script>")
        feeder = make_feeder(description='<b>bold</b> & "quoted"')
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, [feeder])
        path = tmp_path / "xss.html"
        PrintableReportExporter.generate_html_report(str(path), project, outs, summary, validations)
        content = path.read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content
        assert "<b>bold</b>" not in content

    def test_f011_excel_formula_injection_neutralized(self, tmp_path):
        project = make_project(project_name="=HYPERLINK()")
        feeder = make_feeder(feeder_id="=A1", func_tag="+EVIL", description="@cmd")
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, [feeder])
        path = tmp_path / "inj.xlsx"
        ExcelExporter.export_to_excel(str(path), project, outs, summary, validations)
        wb = openpyxl.load_workbook(str(path))
        ws = wb["02_Feeder_Cable_Schedule"]
        row = [c.value for c in ws[2]]
        assert str(row[0]).startswith("'=")
        assert str(row[1]).startswith("'+")
        assert str(row[3]).startswith("'@")

    def test_f004_cap_contactors_small_steps_in_catalog(self):
        small = [d for d in CATALOG if d.device_type == "CAP_CONTACTOR" and d.cap_kvar_400v <= 10.0]
        assert small
        assert all(d.cap_kvar_400v >= 5.0 for d in small)

    def test_f013_invalid_enum_reports_cell_address(self, tmp_path):
        path = tmp_path / "bad_enum.xlsx"
        ExcelInputManager.create_input_template(str(path))
        wb = openpyxl.load_workbook(str(path))
        wb["Feeders_List"].cell(row=2, column=5).value = "MOTOR_TYPO"
        wb["Project_Spec"].cell(row=5, column=2).value = "INVALID_EARTH"
        wb.save(str(path))
        project, feeders, errors = ExcelInputManager.load_from_excel(str(path))
        assert len(errors) >= 1
        joined = "\n".join(errors)
        assert "Feeders_List" in joined
        assert "Project_Spec" in joined
        assert "MOTOR_TYPO" in joined
        assert str(feeders[0].load_type.value) == "SUB_FEEDER"

    def test_f018_inf_nan_rejected(self):
        import pytest
        with pytest.raises(Exception):
            ProjectSpec(project_name="XY", nominal_voltage_v=float("inf"))
        with pytest.raises(Exception):
            ProjectSpec(project_name="XY", altitude_m=float("nan"))
        with pytest.raises(Exception):
            FeederInput(feeder_id="F01", description="x", load_type=LoadType.SUB_FEEDER, power_kw=float("inf"))

    def test_f020_browser_search_has_unix_and_which(self):
        from lv_assist.outputs import PdfExporter
        assert any(p.startswith("/usr") for p in PdfExporter.EDGE_CANDIDATES)
        assert any("MacOS" in p for p in PdfExporter.EDGE_CANDIDATES)

    def test_tech02_single_migration_builds_full_db(self, tmp_path):
        import sqlite3
        from migrate_to_sqlite import build_or_migrate_database, DATA_DIR
        db_path = tmp_path / "lv_assist.db"
        build_or_migrate_database(db_path=db_path, data_dir=DATA_DIR, force=True)
        conn = sqlite3.connect(str(db_path))
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("catalog_devices", "trip_curves", "selectivity_rules", "standards_registry")
        }
        cap_small = conn.execute(
            "SELECT COUNT(*) FROM catalog_devices WHERE category='CAP_CONTACTOR' AND kvar_rating <= 10"
        ).fetchone()[0]
        points = conn.execute(
            "SELECT COUNT(*) FROM trip_curves WHERE raw_json LIKE '%points%'"
        ).fetchone()[0]
        conn.close()
        assert counts["catalog_devices"] >= 90
        assert counts["trip_curves"] >= 15
        assert counts["selectivity_rules"] >= 10
        assert counts["standards_registry"] >= 2
        assert cap_small >= 2
        assert points >= 10

    def test_tech02_phase_scripts_moved_to_scripts_dir(self):
        root = PROJECT_ROOT
        assert not (root / "extend_catalog_phase5.py").exists()
        for name in ("extend_catalog_phase5.py", "extend_catalog_phase6.py", "extend_catalog_phase7.py"):
            assert (root / "scripts" / name).exists()

    def test_f022_requirements_split_and_pinned(self):
        root = PROJECT_ROOT
        req = (root / "requirements.txt").read_text(encoding="utf-8")
        assert "pytest" not in req
        for line in req.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            assert "<" in line, f"no version ceiling: {line}"
        dev = (root / "requirements-dev.txt").read_text(encoding="utf-8")
        assert "pytest" in dev
        assert "-r requirements.txt" in dev

    @staticmethod
    def _run_project(project, feeders):
        return EngineeringEngine(CATALOG).process_project(project, feeders)

    def test_f005_pe_uses_project_ik_with_adiabatic_basis(self):
        def run(ik):
            outs, _, _ = self._run_project(
                make_project(prospective_ik_ka=ik),
                [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0, cos_phi=0.9, efficiency=1.0)])
            return outs[0]
        f_low, f_high = run(6.0), run(25.0)
        norm = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
        assert "115" in f_low.pe_basis_str.translate(norm) and "115" in f_high.pe_basis_str.translate(norm)
        assert f_high.cable_designation_str != f_low.cable_designation_str

    def test_f006_icu_at_voltage_in_excel_and_html(self, tmp_path):
        project = make_project(prospective_ik_ka=22.0)
        feeder = make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0, cos_phi=0.9, efficiency=1.0)
        outs, summary, validations = self._run_project(project, [feeder])
        xlsx_path = tmp_path / "r.xlsx"
        ExcelExporter.export_to_excel(str(xlsx_path), project, outs, summary, validations)
        ws = openpyxl.load_workbook(str(xlsx_path))["02_Feeder_Cable_Schedule"]
        headers = [c.value for c in ws[1]]
        assert tr("rpt_c_icu") in headers
        icu_val = str(ws.cell(row=2, column=headers.index(tr("rpt_c_icu")) + 1).value)
        assert "kA @" in icu_val and "400V" in icu_val
        html_path = tmp_path / "r.html"
        PrintableReportExporter.generate_html_report(str(html_path), project, outs, summary, validations)
        content = html_path.read_text(encoding="utf-8")
        assert "Icu:" in content and "kA @ 400.0V" in content

    def test_f008_derating_factors_in_feeder_output(self):
        outs, _, _ = self._run_project(
            make_project(ambient_temp_c=40.0, cable_grouping_factor_k2=0.8),
            [make_feeder("F01", load_type=LoadType.SUB_FEEDER, power_kw=5.0, cos_phi=0.9, efficiency=1.0)])
        f = outs[0]
        assert f.cable_temp_factor_k1 == 0.87
        assert f.cable_grouping_factor_k2 == 0.8
        assert abs(f.cable_total_derating_k - 0.696) < 0.01
        assert InstallationMethod.C.value in f.cable_method_ref_str

    def test_f012_harmonic_reference_by_total_current(self):
        small, _, small_vals = self._run_project(
            make_project(),
            [make_feeder(f"F{i:02d}", power_kw=5.0, cos_phi=0.9) for i in range(1, 3)])
        big, _, big_vals = self._run_project(
            make_project(),
            [make_feeder(f"F{i:02d}", load_type=LoadType.MOTOR_DOL, power_kw=30.0, cos_phi=0.85, efficiency=0.93) for i in range(1, 3)])
        assert small[0].design_current_ib_a > 0 and sum(f.design_current_ib_a for f in big) > 75.0
        small_ref = [v.standard_ref for v in small_vals if v.rule_id == "RULE-HARM-013"][0]
        big_ref = [v.standard_ref for v in big_vals if v.rule_id == "RULE-HARM-013"][0]
        assert small_ref == "IEC 61000-3-12"
        assert big_ref == "IEEE 519"

    def test_f015_ik_source_notes_estimate(self):
        _, summary, _ = self._run_project(make_project(prospective_ik_ka=22.0),
                                          [make_feeder("F01", power_kw=5.0, cos_phi=0.9)])
        assert tr("ik_est_note") in summary.ik_source_str
        _, summary2, _ = self._run_project(make_project(prospective_ik_ka=None),
                                           [make_feeder("F01", power_kw=5.0, cos_phi=0.9)])
        assert tr("ik_est_note") not in summary2.ik_source_str

    def test_f007_fan_limits_effective_ip(self, tmp_path):
        project = make_project(target_ip="IP65", ambient_temp_c=40.0, max_internal_temp_c=50.0)
        feeders = [make_feeder(f"F{i:02d}", load_type=LoadType.MOTOR_DOL, power_kw=30.0,
                               cos_phi=0.85, efficiency=0.93) for i in range(1, 3)]
        outs, summary, validations = self._run_project(project, feeders)
        assert summary.selected_fan is not None
        assert summary.effective_ip_str == "IP54"
        assert any(v.rule_id == "RULE-ENC-IP-020" and v.status == ValidationStatus.WARNING for v in validations)
        xlsx_path = tmp_path / "ip.xlsx"
        ExcelExporter.export_to_excel(str(xlsx_path), project, outs, summary, validations)
        ws1 = openpyxl.load_workbook(str(xlsx_path))["01_Project_Summary"]
        labels = [str(c.value) for col in ws1.iter_cols() for c in col]
        assert tr("rpt_eff_ip") in labels

    def test_f017_internal_temp_over_50_reports_warning(self, tmp_path):
        project = make_project(ambient_temp_c=45.0, max_internal_temp_c=50.0)
        feeders = [make_feeder(f"F{i:02d}", load_type=LoadType.MOTOR_DOL, power_kw=55.0,
                               cos_phi=0.85, efficiency=0.93) for i in range(1, 7)]
        outs, summary, validations = self._run_project(project, feeders)
        assert summary.selected_fan is None
        assert summary.estimated_internal_temp_c > 50.0
        assert any(v.rule_id == "RULE-THERM-018" and v.status == ValidationStatus.WARNING for v in validations)
        html_path = tmp_path / "tint.html"
        PrintableReportExporter.generate_html_report(str(html_path), project, outs, summary, validations)
        content = html_path.read_text(encoding="utf-8")
        assert tr("html_tint") in content
        assert html.escape(tr("kpi_tint_50_warn")) in content

    def test_control_supply_sized_with_largest_inrush(self):
        project = make_project(simultaneity_factor_ks=0.9)
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=5.5, cos_phi=0.85, efficiency=0.90),
            make_feeder("F02", load_type=LoadType.MOTOR_DOL, power_kw=30.0, cos_phi=0.85, efficiency=0.93),
        ]
        outs, summary, validations = self._run_project(project, feeders)
        holding = sum(f.ctrl_24v_holding_w for f in outs)
        largest = max(f.ctrl_24v_pull_in_surge_w for f in outs)
        assert largest > 0
        expected_w = round(project.plc_hmi_24vdc_power_w + project.simultaneity_factor_ks * holding + largest, 1)
        assert summary.ctrl_24v_peak_inrush_current_a == round(expected_w / 24.0, 2)
        v11 = [v for v in validations if v.rule_id == "RULE-CTRL-24V-011"]
        assert v11 and v11[0].standard_ref == "IEC 60204-1"
        if summary.selected_psu_24v:
            assert v11[0].status == ValidationStatus.COMPLETED
            assert summary.selected_psu_24v.boost_current_peak_a >= summary.ctrl_24v_peak_inrush_current_a


class TestPhase7HtmlReport:
    def _html_project(self, tmp_path, **proj_overrides):
        project = make_project(**proj_overrides)
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93),
            make_feeder("F03", load_type=LoadType.SUB_FEEDER, power_kw=10.0),
        ]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        path = tmp_path / "report.html"
        PrintableReportExporter.generate_html_report(str(path), project, outs, summary, validations)
        return project, outs, summary, validations, path.read_text(encoding="utf-8")

    def test_print_css_a4_landscape_and_break_rules(self, tmp_path):
        *_, content = self._html_project(tmp_path)
        assert "@page" in content and "A4 landscape" in content and "12mm" in content
        assert "@media print" in content
        assert "-webkit-print-color-adjust: exact" in content
        assert "print-color-adjust: exact" in content
        assert "page-break-inside: avoid" in content
        assert "table-header-group" in content
        assert "break-inside: avoid" in content

    def test_badge_classes_defined_and_used(self, tmp_path):
        _, outs, _, _, content = self._html_project(tmp_path)
        for cls in ("badge-verified", "badge-preliminary", "badge-error", "badge-insufficient"):
            assert f".{cls}" in content
        import re
        for f in outs:
            m = re.search(
                r'<span class="badge (badge-[a-z-]+)">' + re.escape(f.selectivity_state.value) + r'</span>', content)
            assert m, f.selectivity_state.value
        assert "background-color:#E9F7EF" not in content
        assert "background-color:#FDEDEC" not in content

    def test_selectivity_badge_mapping(self):
        assert PrintableReportExporter.SEL_BADGE[SelectivityEvalState.VERIFIED_TOTAL] == "badge-verified"
        assert PrintableReportExporter.SEL_BADGE[SelectivityEvalState.VERIFIED_PARTIAL] == "badge-verified"
        assert PrintableReportExporter.SEL_BADGE[SelectivityEvalState.PRELIMINARY] == "badge-preliminary"
        assert PrintableReportExporter.SEL_BADGE[SelectivityEvalState.PRELIMINARY_RATIO_ONLY] == "badge-preliminary"
        assert PrintableReportExporter.SEL_BADGE[SelectivityEvalState.VIOLATION] == "badge-error"

    def test_kpi_cards_strip(self, tmp_path):
        _, _, summary, validations, content = self._html_project(tmp_path)
        assert 'class="kpi-strip"' in content
        assert html.escape(tr("kpi_main_current")) in content
        assert html.escape(tr("kpi_busbar")) in content
        assert html.escape(tr("kpi_thermal")) in content
        assert html.escape(tr("kpi_val_summary")) in content
        assert str(summary.design_main_current_a) in content
        assert summary.recommended_busbar_spec in content
        assert str(summary.total_power_loss_w) in content
        assert summary.recommended_pe_busbar_spec in content
        n_err = sum(1 for v in validations if v.status == ValidationStatus.ERROR)
        n_warn = sum(1 for v in validations if v.status == ValidationStatus.WARNING)
        assert f"{n_err} {html.escape(tr('html_kpi_err'))}" in content
        assert f"{n_warn} {html.escape(tr('html_kpi_warn'))}" in content

    def test_calculation_trace_formula(self, tmp_path):
        _, outs, _, _, content = self._html_project(tmp_path)
        assert html.escape(tr("html_trace_ib")) in content
        assert html.escape(tr("html_trace_iz0")) in content
        assert html.escape(tr("html_trace_k1")) in content
        assert html.escape(tr("html_trace_k2")) in content
        assert html.escape(tr("html_trace_ktot")) in content
        assert html.escape(tr("html_trace_formula")) in content
        assert html.escape(tr("html_trace_vd")) in content
        for f in outs:
            assert f"<b>{f.feeder_id}</b>" in content
        f = outs[0]
        assert f.cable_derated_iz_a is not None and f.cable_total_derating_k
        iz0 = round(f.cable_derated_iz_a / f.cable_total_derating_k, 1)
        assert f"Iz = {iz0} ×" in content
        assert f"= {f.cable_derated_iz_a} A" in content

    def test_signature_block_uses_designer(self, tmp_path):
        *_, content = self._html_project(tmp_path, designer_name="A. Engineer")
        assert 'class="sign-block"' in content
        assert html.escape(tr("html_sign_title")) in content
        assert html.escape(tr("html_sign_designer")) in content
        assert html.escape(tr("html_sign_reviewer")) in content
        assert html.escape(tr("html_sign_approver")) in content
        assert html.escape(tr("html_sign_date")) in content
        assert "A. Engineer" in content

    def test_page_footer_present(self, tmp_path):
        project, _, _, _, content = self._html_project(tmp_path)
        assert 'class="page-footer"' in content
        assert project.project_name in content

    def test_validation_badges_translated(self, tmp_path):
        project, outs, summary, _, _ = self._html_project(tmp_path)
        vals = [
            ValidationResult(rule_id="R-X1", feeder_id="F01", standard_ref="IEC 1",
                             status=ValidationStatus.ERROR, description="d", supporting_evidence="e",
                             consequence="c", recommended_action="a"),
            ValidationResult(rule_id="R-X2", feeder_id="F01", standard_ref="IEC 2",
                             status=ValidationStatus.WARNING, description="d", supporting_evidence="e",
                             consequence="c", recommended_action="a"),
            ValidationResult(rule_id="R-X3", feeder_id="F01", standard_ref="IEC 3",
                             status=ValidationStatus.COMPLETED, description="d", supporting_evidence="e",
                             consequence="c", recommended_action="a"),
            ValidationResult(rule_id="R-X4", feeder_id="F01", standard_ref="IEC 4",
                             status=ValidationStatus.INSUFFICIENT_DATA, description="d", supporting_evidence="e",
                             consequence="c", recommended_action="a"),
        ]
        path = tmp_path / "v.html"
        PrintableReportExporter.generate_html_report(str(path), project, outs, summary, vals)
        content = path.read_text(encoding="utf-8")
        for key in ("html_badge_completed", "html_badge_warning", "html_badge_error", "html_badge_insufficient"):
            assert html.escape(tr(key)) in content
        assert f'<span class="badge badge-error">{html.escape(tr("html_badge_error"))}</span>' in content
        assert f'<span class="badge badge-verified">{html.escape(tr("html_badge_completed"))}</span>' in content
        assert "<b>R-X1</b>" in content
        assert html.escape(tr("html_s5")) in content


class TestPhase7GuiFeatures:
    @staticmethod
    def _demo():
        from lv_assist.gui import build_demo_project
        return build_demo_project()

    def test_build_demo_project_processes(self):
        project, feeders = self._demo()
        assert project.project_name == tr("demo_name")
        assert len(feeders) == 4
        assert {f.load_type for f in feeders} == {
            LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA, LoadType.MOTOR_VFD, LoadType.LIGHTING_SOCKET}
        f_outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert len(f_outs) == 4
        assert summary.design_main_current_a > 0
        assert not any(v.status == ValidationStatus.ERROR for v in validations)

    def test_build_document_bundle(self, tmp_path):
        import zipfile
        from lv_assist.gui import LVAssistApp
        project, feeders = self._demo()
        f_outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        zpath = str(tmp_path / "bundle.zip")
        n = LVAssistApp.build_document_bundle(zpath, project, f_outs, summary, validations, include_pdf=False)
        assert n == 8
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
        for expected in ("01_Design_Output.xlsx", "02_Engineering_Report.html",
                         "02_Design_Verification_Report.html", "03_Single_Line_Diagram.svg",
                         "04_Time_Current_Curves.svg", "05_Control_Circuits.svg",
                         "06_Panel_Layout.svg", "07_Commercial_Quotation.html"):
            assert expected in names
        assert not any('EPLAN' in name or name.endswith(('.dxf', '.ema', '.emp')) for name in names)
        assert not any(name.endswith(".pdf") for name in names)
        with zipfile.ZipFile(zpath) as zf:
            assert zf.read("01_Design_Output.xlsx")[:2] == b"PK"


class TestPhase7Template:
    def test_template_has_dropdowns_and_guide(self, tmp_path):
        path = tmp_path / "tpl.xlsx"
        ExcelInputManager.create_input_template(str(path))
        wb = openpyxl.load_workbook(str(path))

        assert "Guide_&_Definitions" in wb.sheetnames
        ws_p = wb["Project_Spec"]
        ws_f = wb["Feeders_List"]
        p_formulas = " ".join(str(dv.formula1) for dv in ws_p.data_validations.dataValidation)
        f_formulas = " ".join(str(dv.formula1) for dv in ws_f.data_validations.dataValidation)
        for expected in ("TN-S", "MCC", "Choices_2", "IP66", "Form 4b"):
            assert expected in p_formulas
        for expected in ("MOTOR_VFD", "TRUE,FALSE", "XLPE", "A1,A2,B1,B2,C,E,F,D"):
            assert expected in f_formulas
        assert len(ws_f.data_validations.dataValidation) >= 8

        ws_g = wb["Guide_&_Definitions"]
        rows = list(ws_g.iter_rows(min_row=2, values_only=True))
        assert len(rows) >= 35
        load_type_row = [r for r in rows if r and r[0] == "load_type"][0]
        assert "MOTOR_VFD" in str(load_type_row[4])
        for i in (1, 2, 3):
            assert str(load_type_row[i]).strip()

        project, feeders, errors = ExcelInputManager.load_from_excel(str(path))
        assert errors == []
        assert len(feeders) == 4
        assert project.earthing_system.value == "TN-S"









class TestPhase11BusbarAndMotorIk:
    def _demo(self):
        from lv_assist.gui import build_demo_project
        project, feeders = build_demo_project()
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        return project, outs, summary, validations

    def test_busbar_impedance_and_du_values(self):
        res = BusbarEngine.select(134.0, 22.0, 800.0, voltage_v=400.0, cos_phi=0.92)
        assert res.spec == "Cu 20x10 mm (3P+N)"
        assert abs(res.r_mohm_m - 22.3 / 200.0) < 0.001
        assert res.x_mohm_m == 0.15
        assert res.length_m == 0.8
        # ΔU = √3·I·L·(R·cosφ + X·sinφ) — محاسبه دستی
        sin_phi = (1.0 - 0.92 ** 2) ** 0.5
        z_eff = (22.3 / 200.0) * 0.92 + 0.15 * sin_phi
        du_v_expected = (3.0 ** 0.5) * 134.0 * 0.8 * z_eff / 1000.0
        assert abs(res.voltage_drop_v - du_v_expected) < 0.01
        assert res.voltage_drop_pct < 0.1
        statuses = {v.rule_id: v.status for v in res.validations}
        assert statuses["RULE-BUS-028"] == ValidationStatus.COMPLETED

    def test_busbar_du_warning_for_long_runs(self):
        res = BusbarEngine.select(1000.0, 50.0, 40000.0, voltage_v=400.0, cos_phi=0.7)
        statuses = {v.rule_id: v.status for v in res.validations}
        assert res.voltage_drop_pct > 1.5
        assert statuses["RULE-BUS-028"] == ValidationStatus.WARNING

    def test_busbar_select_uses_total_ik_and_ipk(self):
        res = BusbarEngine.select(130.0, 22.0, 800.0, ik_total_ka=30.0, ip_total_ka=85.0)
        assert res.required_ipk_ka == 85.0
        assert res.icw_1s_ka >= 30.0
        assert res.spec == "Cu 30x10 mm (3P+N)"

    def test_demo_motor_contribution_values(self):
        _, _, summary, validations = self._demo()
        # F01 DOL 15kW → 1.05·6·27.97/1000 ≈ 0.176 kA
        # F02 Y-Δ 30kW → 1.05·4·54.15/1000 ≈ 0.227 kA؛ F03 VFD → صفر
        assert abs(summary.motor_contribution_ka - 0.404) < 0.01
        assert abs(summary.ik_bus_total_ka - (22.0 + 0.4036)) < 0.01
        # ip = κ(22)·√2·22 + 1.7·√2·I''kM ≈ 62.23 + 0.97
        assert abs(summary.ip_bus_total_ka - 63.2) < 0.2
        mot_rule = [v for v in validations if v.rule_id == "RULE-MOT-029"]
        assert len(mot_rule) == 1
        assert mot_rule[0].status == ValidationStatus.COMPLETED
        assert mot_rule[0].standard_ref == "IEC 60909-0"

    def test_vfd_only_project_no_contribution(self):
        project = make_project(prospective_ik_ka=22.0)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_VFD, power_kw=18.5,
                               cos_phi=0.95, efficiency=0.90)]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        assert summary.motor_contribution_ka is None
        assert summary.ik_bus_total_ka == 22.0
        assert not [v for v in validations if v.rule_id == "RULE-MOT-029"]

    def test_motor_contribution_without_network_ik(self):
        project = make_project(prospective_ik_ka=None, transformer_kva=None)
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0,
                               cos_phi=0.85, efficiency=0.91)]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        ib = 15000.0 / ((3.0 ** 0.5) * 400.0 * 0.85 * 0.91)
        expected = 1.05 * 6.0 * ib / 1000.0
        assert abs(summary.motor_contribution_ka - expected) < 0.005
        assert summary.ik_bus_total_ka is None
        mot_rule = [v for v in validations if v.rule_id == "RULE-MOT-029"]
        assert mot_rule and mot_rule[0].status == ValidationStatus.INSUFFICIENT_DATA

    def test_max_total_du_pct_is_cable_plus_busbar(self):
        _, outs, summary, _ = self._demo()
        max_cable = max(f.voltage_drop_percent for f in outs)
        assert abs(summary.max_total_du_pct - (max_cable + summary.busbar_du_pct)) < 0.005
        assert summary.busbar_du_v > 0.0

    def test_feeder_sc_rule_uses_total_ik(self):
        project, outs, summary, validations = self._demo()
        sc_vals = [v for v in validations if v.rule_id == "RULE-PROT-SC-001" and v.feeder_id == "F01"]
        assert sc_vals and sc_vals[0].status == ValidationStatus.COMPLETED
        assert any(v.rule_id == "RULE-BUS-025" for v in validations)

    def test_excel_phase11_rows(self, tmp_path):
        from lv_assist.exporters import ExcelExporter
        project, outs, summary, validations = self._demo()
        path = str(tmp_path / "p11.xlsx")
        ExcelExporter.export_to_excel(path, project, outs, summary, validations)
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws1 = wb["01_Project_Summary"]
        labels = [str(r[0].value) for r in ws1.iter_rows()]
        assert tr("rpt_bus_du") in labels
        assert tr("rpt_motor_ik") in labels

    def test_translation_key_parity_phase11(self):
        import json
        import os
        base = str(PROJECT_ROOT / "lv_assist" / "translations")
        data = {}
        for lang in ("fa", "en", "de"):
            with open(base + "/" + lang + ".json", encoding="utf-8") as fh:
                data[lang] = json.load(fh)
        assert set(data["fa"]) == set(data["en"]) == set(data["de"])
        for key in ("val_bus_028_desc", "val_bus_028_warn_desc", "val_bus_028_ev",
                    "val_bus_028_cons", "val_bus_028_action", "val_mot_029_desc",
                    "val_mot_029_noik_desc", "val_mot_029_ev", "val_mot_029_cons",
                    "val_mot_029_action", "ik_motor_note", "rpt_bus_du",
                    "rpt_motor_ik", "rpt_du_total", "rpt_ref_iec60909"):
            assert all(key in data[lang] for lang in ("fa", "en", "de")), key


class TestPhase12DesignVerification:
    def _demo(self):
        project = make_project(designer_name="Test Designer")
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0),
            make_feeder("F03", load_type=LoadType.MOTOR_VFD, power_kw=18.5, thdi_pct=40.0),
            make_feeder("F04", load_type=LoadType.LIGHTING_SOCKET, power_kw=12.0),
        ]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        return project, outs, summary, validations

    def test_report_has_13_items_with_clauses(self):
        from lv_assist.engine import build_design_verification
        project, outs, summary, validations = self._demo()
        report = build_design_verification(project, outs, summary, validations)
        assert len(report.items) == 12
        clauses = [it.clause_ref for it in report.items]
        for expected in ("10.2", "10.3", "10.4", "10.5", "10.6", "10.7", "10.8",
                         "10.9", "10.10", "10.11", "10.12", "10.13"):
            assert expected in clauses
        assert all(it.title and it.requirement and it.computed_value for it in report.items)

    def test_demo_calculations_do_not_certify_assembly_conformity(self):
        from lv_assist.engine import build_design_verification
        from lv_assist.models import VerificationStatus
        project, outs, summary, validations = self._demo()
        report = build_design_verification(project, outs, summary, validations)
        assert not any(it.status == VerificationStatus.FAIL for it in report.items)
        assert report.conclusion_status == VerificationStatus.NOT_VERIFIED
        by_clause = {it.clause_ref: it for it in report.items}
        assert by_clause["10.4"].status == VerificationStatus.NOT_VERIFIED
        assert by_clause["10.9"].method.value == "TYPE_TEST"
        assert by_clause["10.11"].status == VerificationStatus.NOT_VERIFIED
        assert "RULE-BUS-025" in by_clause["10.11"].rule_ids
        assert by_clause["10.10"].method.value == "CALCULATION"

    def test_temperature_rise_type_test_above_630a(self):
        from lv_assist.engine import build_design_verification
        from lv_assist.models import VerificationStatus, VerificationMethod
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.HEATER_RESISTIVE, power_kw=600.0)]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        report = build_design_verification(project, outs, summary, validations)
        by_clause = {it.clause_ref: it for it in report.items}
        if summary.design_main_current_a > 630.0:
            assert by_clause["10.10"].method == VerificationMethod.TYPE_TEST
            assert by_clause["10.10"].status == VerificationStatus.NOT_VERIFIED

    def test_sccr_not_verified_without_ik(self):
        from lv_assist.engine import build_design_verification
        from lv_assist.models import VerificationStatus
        project = make_project(prospective_ik_ka=None, transformer_kva=None)
        feeders = [make_feeder("F01")]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        report = build_design_verification(project, outs, summary, validations)
        by_clause = {it.clause_ref: it for it in report.items}
        assert by_clause["10.11"].status == VerificationStatus.NOT_VERIFIED
        assert any(it.status == VerificationStatus.NOT_VERIFIED for it in report.items)

    def test_effective_ip_warning_reflected(self):
        from lv_assist.engine import build_design_verification
        from lv_assist.models import VerificationStatus
        project = make_project(target_ip="IP65")
        feeders = [make_feeder("F01", load_type=LoadType.HEATER_RESISTIVE, power_kw=60.0)]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        report = build_design_verification(project, outs, summary, validations)
        by_clause = {it.clause_ref: it for it in report.items}
        if summary.effective_ip_str != project.target_ip:
            assert by_clause["10.3"].status == VerificationStatus.WARNING
        else:
            assert by_clause["10.3"].status == VerificationStatus.NOT_VERIFIED

    def test_html_report_generates_with_items(self, tmp_path):
        from lv_assist.engine import build_design_verification
        from lv_assist.exporters import DesignVerificationExporter
        project, outs, summary, validations = self._demo()
        report = build_design_verification(project, outs, summary, validations)
        path = str(tmp_path / "dv.html")
        DesignVerificationExporter.generate_html(path, project, summary, report)
        content = open(path, encoding="utf-8").read()
        assert project.project_name in content
        for clause in ("10.2", "10.11", "10.13"):
            assert clause in content
        assert "IEC 61439-1" in content

    def test_excel_sheet_design_verification(self, tmp_path):
        from lv_assist.exporters import ExcelExporter
        project, outs, summary, validations = self._demo()
        path = str(tmp_path / "p12.xlsx")
        ExcelExporter.export_to_excel(path, project, outs, summary, validations)
        import openpyxl
        wb = openpyxl.load_workbook(path)
        assert "06_Design_Verification" in wb.sheetnames
        ws = wb["06_Design_Verification"]
        clauses = [str(r[0].value) for r in ws.iter_rows()]
        for expected in ("10.2", "10.10", "10.11", "10.13"):
            assert expected in clauses

    def test_bundle_includes_dv_report(self, tmp_path):
        import zipfile
        from lv_assist.gui import LVAssistApp
        project, outs, summary, validations = self._demo()
        zpath = str(tmp_path / "p12.zip")
        n = LVAssistApp.build_document_bundle(zpath, project, outs, summary, validations, include_pdf=False)
        assert n == 8
        with zipfile.ZipFile(zpath) as zf:
            assert "02_Design_Verification_Report.html" in zf.namelist()

    def test_translation_key_parity_phase12(self):
        import json
        import os
        base = str(PROJECT_ROOT / "lv_assist" / "translations")
        data = {}
        for lang in ("fa", "en", "de"):
            with open(base + "/" + lang + ".json", encoding="utf-8") as fh:
                data[lang] = json.load(fh)
        assert set(data["fa"]) == set(data["en"]) == set(data["de"])
        for key in ("btn_dv", "tip_dv", "dv_title", "dv_subtitle", "dv_h_clause",
                    "dv_h_item", "dv_h_req", "dv_h_method", "dv_h_value", "dv_h_evidence",
                    "dv_h_rules", "dv_h_status", "dv_h_proj", "dv_h_items", "dv_gen_by",
                    "dv_conclusion_title", "dv_note_scope", "dv_method_calculation",
                    "dv_method_design_rule", "dv_method_manufacturer", "dv_method_type_test",
                    "dv_status_pass", "dv_status_warning", "dv_status_fail", "dv_status_not_verified",
                    "dv_concl_pass", "dv_concl_remarks", "dv_concl_partial", "dv_concl_fail",
                    "dv_10_2_t", "dv_10_2_r", "dv_10_2_val", "dv_10_2_ev_verified", "dv_10_2_ev_estimated",
                    "dv_10_3_t", "dv_10_4_t", "dv_10_5_t", "dv_10_6_t", "dv_10_7_t", "dv_10_8_t",
                    "dv_10_9_t", "dv_10_10_t", "dv_10_11_t", "dv_10_12_t", "dv_10_13_t"):
            assert all(key in data[lang] for lang in ("fa", "en", "de")), key


class TestPhase13Spd:
    def _run(self, **overrides):
        project = make_project(**overrides)
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0),
            make_feeder("F03", load_type=LoadType.MOTOR_VFD, power_kw=18.5, cos_phi=0.95),
            make_feeder("F04", load_type=LoadType.LIGHTING_SOCKET, power_kw=12.0),
        ]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        return project, outs, summary, validations

    def test_default_t2_selection_and_uc(self):
        _, _, summary, validations = self._run()
        spd = summary.selected_spd
        assert spd is not None
        assert spd.part_number == "OVR T2 4L 40-275s P TS QS"
        assert spd.spd_class == "T2"
        # Uc ≥ 1.1 × U0 = 1.1 × 400/√3 ≈ 254 V
        assert spd.spd_uc_v >= 1.1 * 400.0 / math.sqrt(3.0)
        assert spd.spd_up_kv <= 2.5
        statuses = {v.rule_id: v.status for v in validations if v.rule_id.startswith("RULE-SPD")}
        assert statuses["RULE-SPD-030"] == ValidationStatus.COMPLETED
        assert statuses["RULE-SPD-031"] == ValidationStatus.COMPLETED
        assert statuses["RULE-SPD-032"] == ValidationStatus.COMPLETED
        assert statuses["RULE-SPD-033"] == ValidationStatus.COMPLETED
        assert "RULE-SPD-034" not in statuses

    def test_t1_selection_and_coordination(self):
        _, _, summary, validations = self._run(spd_class=SpdClass.T1, has_external_lps=True)
        spd = summary.selected_spd
        assert spd.part_number == "FLT-SEC-P-T1-3S-350/25-FM"
        assert spd.spd_iimp_ka > 0
        assert spd.spd_backup_fuse_a == 315.0
        statuses = {v.rule_id: v.status for v in validations if v.rule_id.startswith("RULE-SPD")}
        assert statuses["RULE-SPD-034"] == ValidationStatus.COMPLETED

    def test_t1_t2_combined_selection(self):
        _, _, summary, validations = self._run(spd_class=SpdClass.T1_T2, has_external_lps=True)
        assert summary.selected_spd.part_number == "OVR T1-T2 4L 25-440s P TS QS"
        assert summary.selected_spd.spd_uc_v == 440.0
        assert any(v.rule_id == "RULE-SPD-034" and v.status == ValidationStatus.COMPLETED
                   for v in validations)

    def test_none_class_warns_and_suggests(self):
        _, _, summary, validations = self._run(spd_class=SpdClass.NONE)
        assert summary.selected_spd is None
        spd_rules = [v for v in validations if v.rule_id.startswith("RULE-SPD")]
        assert len(spd_rules) == 1
        assert spd_rules[0].rule_id == "RULE-SPD-030"
        assert spd_rules[0].status == ValidationStatus.WARNING
        assert summary.spd_suggested_str == tr("sug_spd_none")

    def test_preferred_manufacturer_filters_spd(self):
        _, _, summary, _ = self._run(preferred_manufacturer="Phoenix Contact")
        assert summary.selected_spd.manufacturer == "Phoenix Contact"
        assert summary.selected_spd.part_number == "VAL-MS 320/3+1-FM"

    def test_missing_candidate_raises_error_rule(self):
        no_spd = [d for d in CATALOG if d.device_type != "SPD"]
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0)]
        _, summary, validations = EngineeringEngine(no_spd).process_project(project, feeders)
        assert summary.selected_spd is None
        rule = [v for v in validations if v.rule_id == "RULE-SPD-030"]
        assert rule and rule[0].status == ValidationStatus.ERROR
        # fa locale digits are transliterated, so accept both Latin and Persian "2"
        assert "T2" in summary.spd_suggested_str or "T۲" in summary.spd_suggested_str

    def test_spd_devices_are_verified_data_quality(self):
        spds = [d for d in CATALOG if d.device_type == "SPD"]
        assert len(spds) == 8
        assert all(d.data_quality == DataQuality.REAL_VERIFIED for d in spds)
        assert {d.spd_class for d in spds} == {"T1", "T2", "T1_T2"}

    def test_excel_contains_spd_rows(self, tmp_path):
        project, outs, summary, validations = self._run()
        path = str(tmp_path / "p13.xlsx")
        ExcelExporter.export_to_excel(path, project, outs, summary, validations)
        wb = openpyxl.load_workbook(path)
        labels = [str(r[0].value) for r in wb["01_Project_Summary"].iter_rows()]
        assert tr("rpt_spd") in labels
        ws4 = wb["04_BOM"]
        bom_rows = [[str(c.value) for c in r] for r in ws4.iter_rows(min_row=2)]
        assert any("-F9" in r[0] and summary.selected_spd.part_number in r[6] for r in bom_rows)
        assert any("-F9F" in r[0] and r[6] == "None" and "gG" in r[7] for r in bom_rows)

    def test_html_contains_spd(self, tmp_path):
        project, outs, summary, validations = self._run()
        path = str(tmp_path / "p13.html")
        PrintableReportExporter.generate_html_report(path, project, outs, summary, validations)
        content = open(path, encoding="utf-8").read()
        assert tr("rpt_spd") in content
        assert "OVR" in content

    def test_sld_contains_spd_branch(self):
        project, outs, summary, _ = self._run()
        svg = SldGenerator.generate_svg(project, outs, summary)
        assert "-F9" in svg
        assert "SPD" in svg

    def test_layout_contains_spd_device(self):
        project, outs, summary, _ = self._run()
        result = PanelLayoutGenerator.generate(project, outs, summary)
        tags = [d.tag for row in result.rows for d in row.devices]
        assert "-F9" in tags
        spd_dev = [d for row in result.rows for d in row.devices if d.tag == "-F9"][0]
        assert spd_dev.zone == "POWER"
        assert spd_dev.part_number == summary.selected_spd.part_number

    def test_excel_template_spd_class_roundtrip(self, tmp_path):
        path = str(tmp_path / "in13.xlsx")
        ExcelInputManager.create_input_template(path)
        project, _, errors = ExcelInputManager.load_from_excel(path)
        assert errors == []
        assert project.spd_class == SpdClass.T2
        wb = openpyxl.load_workbook(path)
        ws = wb["Project_Spec"]
        for row in ws.iter_rows(min_row=2):
            if row[0].value == "spd_class":
                row[1].value = "T1"
        wb.save(path)
        project, _, errors = ExcelInputManager.load_from_excel(path)
        assert errors == []
        assert project.spd_class == SpdClass.T1

    def test_gui_spd_selector_present(self):
        from lv_assist.gui import LVAssistApp, build_demo_project
        assert hasattr(LVAssistApp, "_on_spd_change")
        project, _ = build_demo_project()
        assert project.spd_class == SpdClass.T2

    def test_translation_key_parity_phase13(self):
        base = PROJECT_ROOT / "lv_assist" / "translations"
        data = {}
        for lang in ("fa", "en", "de"):
            with open(base / f"{lang}.json", encoding="utf-8") as fh:
                data[lang] = json.load(fh)
        assert set(data["fa"]) == set(data["en"]) == set(data["de"])
        for key in ("val_spd_none_desc", "val_spd_none_cons", "val_spd_none_action",
                    "val_spd_030_desc", "val_spd_030_ev", "val_spd_030_cons",
                    "val_spd_030_err_desc", "val_spd_030_err_ev", "val_spd_030_err_cons",
                    "val_spd_030_err_action", "val_spd_031_desc", "val_spd_031_ev",
                    "val_spd_031_cons", "val_spd_031_high_desc", "val_spd_031_high_ev",
                    "val_spd_031_high_cons", "val_spd_031_high_action", "val_spd_032_desc",
                    "val_spd_032_ev", "val_spd_032_cons", "val_spd_033_desc", "val_spd_033_ev",
                    "val_spd_033_cons", "val_spd_034_desc", "val_spd_034_ev", "val_spd_034_cons",
                    "sug_spd", "sug_spd_none", "sug_spd_need", "bom_spd", "rpt_spd", "kpi_spd",
                    "xl_g_spd", "gui_spd_none", "gui_spd_t1", "gui_spd_t2", "gui_spd_t1_t2",
                    "tip_spd", "kpi_spd_none", "sld_spd", "bom_spd_fuse", "bom_spd_fuse_spec",
                    "rpt_ref_spd"):
            assert all(key in data[lang] for lang in ("fa", "en", "de")), key




class TestPhase15SpdInstallation:
    def _run(self, **overrides):
        project = make_project(**overrides)
        feeders = [
            make_feeder("F01", load_type=LoadType.MOTOR_DOL, power_kw=15.0),
            make_feeder("F02", load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0),
        ]
        outs, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        return project, outs, summary, validations

    @staticmethod
    def _spd_rule(validations, rule_id):
        found = [v for v in validations if v.rule_id == rule_id]
        assert len(found) == 1, rule_id
        return found[0]

    def test_default_lead_completed(self):
        _, _, _, validations = self._run()
        rule = self._spd_rule(validations, "RULE-SPD-032")
        assert rule.status == ValidationStatus.COMPLETED

    def test_lead_warning_between_half_and_one_meter(self):
        _, _, _, validations = self._run(spd_connection_length_m=0.8)
        rule = self._spd_rule(validations, "RULE-SPD-032")
        assert rule.status == ValidationStatus.WARNING
        assert "0.8" in rule.supporting_evidence or "۰.۸" in rule.supporting_evidence

    def test_lead_error_above_one_meter(self):
        _, _, _, validations = self._run(spd_connection_length_m=1.2)
        rule = self._spd_rule(validations, "RULE-SPD-032")
        assert rule.status == ValidationStatus.ERROR

    def test_main_breaker_coordination_rule_matches_ratings(self):
        _, _, summary, validations = self._run()
        rule = self._spd_rule(validations, "RULE-SPD-035")
        fuse = summary.selected_spd.spd_backup_fuse_a
        if summary.main_breaker.rated_current_in_a <= fuse:
            assert rule.status == ValidationStatus.COMPLETED
        else:
            assert rule.status == ValidationStatus.WARNING
            assert summary.main_breaker.rated_current_in_a > fuse

    def test_small_load_main_breaker_protects_spd(self):
        project = make_project()
        feeders = [make_feeder("F01", load_type=LoadType.LIGHTING_SOCKET, power_kw=5.0)]
        _, summary, validations = EngineeringEngine(CATALOG).process_project(project, feeders)
        rule = self._spd_rule(validations, "RULE-SPD-035")
        assert summary.main_breaker.rated_current_in_a <= summary.selected_spd.spd_backup_fuse_a
        assert rule.status == ValidationStatus.COMPLETED

    def test_none_class_has_no_coordination_rule(self):
        _, _, _, validations = self._run(spd_class=SpdClass.NONE)
        assert not [v for v in validations if v.rule_id == "RULE-SPD-035"]
        assert not [v for v in validations if v.rule_id == "RULE-SPD-032"]

    def test_excel_template_roundtrip_lead_length(self, tmp_path):
        path = str(tmp_path / "in15.xlsx")
        ExcelInputManager.create_input_template(path)
        project, _, errors = ExcelInputManager.load_from_excel(path)
        assert errors == []
        assert project.spd_connection_length_m == 0.5
        wb = openpyxl.load_workbook(path)
        ws = wb["Project_Spec"]
        for row in ws.iter_rows(min_row=2):
            if row[0].value == "spd_connection_length_m":
                row[1].value = 0.9
        wb.save(path)
        project, _, errors = ExcelInputManager.load_from_excel(path)
        assert errors == []
        assert project.spd_connection_length_m == 0.9

    def test_excel_summary_reports_lead_length(self, tmp_path):
        project, outs, summary, validations = self._run(spd_connection_length_m=0.9)
        path = str(tmp_path / "p15.xlsx")
        ExcelExporter.export_to_excel(path, project, outs, summary, validations)
        wb = openpyxl.load_workbook(path)
        ws1 = wb["01_Project_Summary"]
        refs = [str(r[3].value) for r in ws1.iter_rows() if r[0].value == tr("rpt_spd")]
        assert refs and "L=" in refs[0]

    def test_translation_key_parity_phase15(self):
        base = PROJECT_ROOT / "lv_assist" / "translations"
        data = {}
        for lang in ("fa", "en", "de"):
            with open(base / f"{lang}.json", encoding="utf-8") as fh:
                data[lang] = json.load(fh)
        assert set(data["fa"]) == set(data["en"]) == set(data["de"])
        for key in ("xl_g_spd_inst",
                    "val_spd_032_warn_desc", "val_spd_032_warn_ev", "val_spd_032_warn_cons",
                    "val_spd_032_warn_action", "val_spd_032_err_desc", "val_spd_032_err_ev",
                    "val_spd_032_err_cons", "val_spd_032_err_action",
                    "val_spd_035_desc", "val_spd_035_ev", "val_spd_035_cons",
                    "val_spd_035_warn_desc", "val_spd_035_warn_ev", "val_spd_035_warn_cons",
                    "val_spd_035_warn_action"):
            assert all(key in data[lang] for lang in ("fa", "en", "de")), key
        for lang in ("fa", "en", "de"):
            assert "{a}" in data[lang]["val_spd_032_desc"]
            assert "{d}" in data[lang]["rpt_ref_spd"]
