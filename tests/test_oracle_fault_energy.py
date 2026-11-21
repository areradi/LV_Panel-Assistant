from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest

import tools.oracle_fault_energy as fault_oracle
from tools.oracle_fault_energy import (
    STANDARD_PE_SECTIONS,
    compute_required_pe_mm2,
    get_i2t,
    get_i2t_assessment,
    get_k_factor,
    select_cable_with_fault_energy,
    select_pe_from_required,
)


ROOT = Path(__file__).resolve().parents[1]


def test_k_factors_match_requested_iec_snapshot():
    assert get_k_factor("Cu", "PVC") == 115
    assert get_k_factor("Cu", "XLPE") == 143
    assert get_k_factor("Al", "PVC") == 76
    assert get_k_factor("Al", "XLPE") == 94


def test_required_pe_and_standard_section_selection():
    assert compute_required_pe_mm2(1_000_000, 100) == pytest.approx(10.0)
    assert select_pe_from_required(10.01, list(STANDARD_PE_SECTIONS)) == 16.0
    assert select_pe_from_required(500, list(STANDARD_PE_SECTIONS)) is None


def test_unverified_siemens_fuse_table_is_quarantined():
    with (ROOT / "tools" / "i2t_curves_unverified.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    fuse_rows = [row for row in rows if row["device_type"] == "FUSE_GG_SIEMENS_5SE2"]
    assert len(fuse_rows) == 15
    assert all(row["verification_status"] == "UNVERIFIED" for row in fuse_rows)
    assert all(row["source_file"] == "catalogo-fusivel-2012-ingles.pdf" for row in fuse_rows)
    assert all(row["source_page"] == "15" for row in fuse_rows)
    assert all(not row["ik_ka"] for row in fuse_rows)
    assert all(
        row["applicability_condition"] == "400 V AC current-limiting region; t < 4 ms"
        for row in fuse_rows
    )

    assessment = get_i2t_assessment(
        "FUSE_GG_SIEMENS_5SE2", 32, 10.0, fault_time_s=0.02
    )
    assert assessment.source == "RMS Ik²t fallback"
    assert assessment.verified_curve is False
    assert assessment.warnings


def test_generic_gg_32a_uses_source_data_instead_of_ik_squared_time():
    assessment = get_i2t_assessment("fuse_gG", 32, 22.4, fault_time_s=0.02)
    assert assessment.i2t_a2s == pytest.approx(22_400**2 * 0.02)
    assert assessment.source == "RMS Ik²t fallback"
    assert assessment.approximate is True
    assert any("No verified Ik-indexed FUSE_GG curve" in warning for warning in assessment.warnings)


def test_ik_curve_interpolates_between_source_points(monkeypatch):
    rows = (
        {"device_type": "TEST_FUSE", "rated_a": "32", "ik_ka": "10", "i2t_a2s": "10000",
         "source_file": "test datasheet", "source_page": "2", "source_note": "curve",
         "verification_status": "VERIFIED"},
        {"device_type": "TEST_FUSE", "rated_a": "32", "ik_ka": "50", "i2t_a2s": "30000",
         "source_file": "test datasheet", "source_page": "2", "source_note": "curve",
         "verification_status": "VERIFIED"},
    )
    monkeypatch.setattr(fault_oracle, "_load_curve_rows", lambda: rows)
    assessment = get_i2t_assessment("TEST_FUSE", 32, 20)
    assert assessment.i2t_a2s == 15000
    assert assessment.approximate is True


def test_verified_curve_does_not_extrapolate_outside_source_points(monkeypatch):
    rows = (
        {"device_type": "TEST_FUSE", "rated_a": "32", "ik_ka": "10", "i2t_a2s": "10000",
         "source_file": "test datasheet", "source_page": "2", "source_note": "curve",
         "verification_status": "VERIFIED"},
        {"device_type": "TEST_FUSE", "rated_a": "32", "ik_ka": "50", "i2t_a2s": "30000",
         "source_file": "test datasheet", "source_page": "2", "source_note": "curve",
         "verification_status": "VERIFIED"},
    )
    monkeypatch.setattr(fault_oracle, "_load_curve_rows", lambda: rows)
    with pytest.raises(ValueError, match="extrapolation is not allowed"):
        get_i2t_assessment("TEST_FUSE", 32, 60, fault_time_s=0.02)


@pytest.mark.parametrize("device_type", ["MCCB", "MPCB"])
def test_unmatched_device_uses_rms_i2t_and_returns_warning(device_type):
    ik_a, clearing_time_s = 5000.0, 0.01
    assessment = get_i2t_assessment(
        device_type, 63, ik_a / 1000.0, fault_time_s=clearing_time_s
    )
    assert assessment.i2t_a2s == pytest.approx(
        ik_a**2 * clearing_time_s, rel=1e-6
    )
    assert assessment.approximate is True
    assert assessment.warnings


@pytest.mark.parametrize("fault_time_s", [None, 0, -0.01, 5.001])
def test_fallback_requires_valid_clearing_time(fault_time_s):
    with pytest.raises(ValueError, match="fault_time_s"):
        get_i2t_assessment("MCCB", 63, 5.0, fault_time_s=fault_time_s)


def test_selection_reports_fault_energy_and_approximation_warning():
    inputs = dict(
        ib_a=20, voltage_v=400, phases=3, length_m=10, cos_phi=0.9,
        ambient_temp_c=30, grouping_k2=1, insulation="PVC", material="CU",
        installation_method="C", max_vdrop_pct=5, protection_in_a=25,
        is_adjustable_prot=True, thdi_pct=None, load_type="MOTOR_DOL",
        user_specified_mm2=None, ik_ka=1, fault_time_s=0.1,
        overload_i2_factor=1.45, device_type="MCCB",
    )
    result = select_cable_with_fault_energy(**inputs)
    assert result["fault_energy_i2t_a2s"] > 0
    assert result["required_fault_pe_mm2"] > 0
    assert result["phase_mm2"] >= result["required_fault_pe_mm2"]
    assert result["pe_mm2"] >= result["required_fault_pe_mm2"]
    assert result["warnings"]
    assert result["reason"] == "AUTO"
    assert result["selection_status"] == "PROVISIONAL"
    assert result["is_safety_recommendation"] is False
    assert any("Assumption impact" in warning for warning in result["warnings"])

    inputs["user_specified_mm2"] = 10
    fixed = select_cable_with_fault_energy(**inputs)
    assert fixed["reason"] == "USER_FIXED"
    assert fixed["selection_status"] == "PROVISIONAL"


def test_selected_device_type_is_required():
    with pytest.raises(ValueError, match="device_type is required"):
        get_i2t_assessment(None, 32, 22.4)
    with pytest.raises(ValueError, match="device_type is required"):
        select_cable_with_fault_energy(
            ib_a=20, voltage_v=400, phases=3, length_m=10, cos_phi=0.9,
            ambient_temp_c=30, grouping_k2=1, insulation="PVC", material="CU",
            installation_method="C", max_vdrop_pct=5, protection_in_a=25,
            is_adjustable_prot=True, thdi_pct=None, load_type="MOTOR_DOL",
            user_specified_mm2=None, ik_ka=1, fault_time_s=0.02,
            overload_i2_factor=1.45,
        )


def test_f01_formula_level_cross_check_with_shared_clearing_time_input():
    """Formula-level comparison using engine-derived Ik and clearing time.

    F01's bus-total Ik is read from PanelSummaryOutput.ik_bus_total_ka; the
    demo engine resolves it to 22.404 kA. The 1.3 overload ratio follows the
    engine fallback for MPCB in engine.py; 1.45 is
    the IEC I2/Iz coordination factor, not the MPCB-specific I2/In input.
    """
    gui_module = pytest.importorskip("lv_assist.gui")
    from lv_assist.catalog import CatalogRepository
    from lv_assist.engine import EngineeringEngine

    project, feeders = gui_module.build_demo_project()
    outputs, summary, _ = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(
        project, feeders
    )
    feeder = next(row for row in feeders if row.feeder_id == "F01")
    engine_result = next(row for row in outputs if row.feeder_id == "F01")
    protection = engine_result.selected_protection
    assert protection is not None and protection.device_type == "MPCB"
    assert feeder.cable_section_mm2 is None
    assert summary.ik_bus_total_ka == pytest.approx(22.404)
    assert engine_result.clearing_time_s == pytest.approx(0.02)
    overload_i2_factor = protection.overload_i2_factor or {
        "MPCB": 1.3,
    }.get(protection.device_type)
    assert overload_i2_factor == pytest.approx(1.3)

    oracle_result = select_cable_with_fault_energy(
        ib_a=engine_result.design_current_ib_a,
        voltage_v=project.nominal_voltage_v,
        phases=feeder.phases,
        length_m=engine_result.cable_length_m,
        cos_phi=engine_result.cos_phi_resolved,
        ambient_temp_c=project.ambient_temp_c,
        grouping_k2=project.cable_grouping_factor_k2,
        insulation=feeder.insulation.value,
        material=feeder.conductor_material.value,
        installation_method=feeder.installation_method.value,
        max_vdrop_pct=3.0 if feeder.load_type.value == "LIGHTING_SOCKET" else 5.0,
        protection_in_a=protection.rated_current_in_a,
        is_adjustable_prot=protection.device_type in ("MPCB", "MCCB"),
        thdi_pct=feeder.thdi_pct,
        load_type=feeder.load_type.value,
        user_specified_mm2=feeder.cable_section_mm2,
        ik_ka=summary.ik_bus_total_ka,
        fault_time_s=engine_result.clearing_time_s,
        overload_i2_factor=overload_i2_factor,
        device_type=protection.device_type,
    )

    assert oracle_result["phase_mm2"] == engine_result.selected_phase_mm2 == 35.0
    assert oracle_result["pe_mm2"] == engine_result.selected_pe_mm2 == 35.0
    assert oracle_result["reason"] == "AUTO"
    assert oracle_result["neutral_mm2"] == 0.0
    assert oracle_result["selection_status"] == "PROVISIONAL"
    assert oracle_result["is_safety_recommendation"] is False
    assert any("Assumption impact" in warning for warning in oracle_result["warnings"])


@pytest.mark.parametrize(
    ("fault_time_s", "expected_section"),
    [(0.016, 25.0), (0.025, 35.0), (0.033, 50.0), (0.100, 70.0)],
)
def test_adiabatic_section_sensitivity_to_clearing_time(fault_time_s, expected_section):
    ik_ka = 22.404
    ik_a = ik_ka * 1000.0
    required_mm2 = compute_required_pe_mm2(ik_a**2 * fault_time_s, 115)
    assert select_pe_from_required(required_mm2) == expected_section


def test_three_phase_lighting_with_high_thdi_keeps_full_neutral():
    result = fault_oracle.select_cable_oracle(
        ib_a=20, voltage_v=400, phases=3, length_m=10, cos_phi=0.9,
        ambient_temp_c=30, grouping_k2=1, insulation="PVC", material="CU",
        installation_method="C", max_vdrop_pct=3, protection_in_a=25,
        is_adjustable_prot=True, thdi_pct=40, load_type="LIGHTING_SOCKET",
        user_specified_mm2=None, ik_ka=None, fault_time_s=None,
        overload_i2_factor=1.45,
    )
    assert result["neutral_mm2"] == result["phase_mm2"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"i2t": -1, "k": 115},
        {"i2t": float("inf"), "k": 115},
        {"i2t": 10, "k": 0},
    ],
)
def test_invalid_energy_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        compute_required_pe_mm2(kwargs["i2t"], kwargs["k"])


def test_active_csv_contains_only_verified_ik_indexed_rows():
    with (ROOT / "tools" / "i2t_curves.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows == []
    assert fault_oracle._load_curve_rows() == ()


def test_oracle_has_no_lv_assist_imports():
    source = (ROOT / "tools" / "oracle_fault_energy.py").read_text(encoding="utf-8")
    assert "from lv_assist" not in source
    tree = ast.parse(source)
    imported = [
        node.module or "" for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    imported.extend(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(name == "lv_assist" or name.startswith("lv_assist.") for name in imported)
