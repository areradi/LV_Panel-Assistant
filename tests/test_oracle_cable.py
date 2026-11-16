from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from tools.oracle_cable import select_cable_oracle
from tools.oracle_reference_cases import REFERENCE_CASES


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda case: case["name"])
def test_reference_cases(case):
    result = select_cable_oracle(**case["inputs"])
    expected = case["expected"]

    if "phase_mm2" in expected:
        assert result["phase_mm2"] == expected["phase_mm2"]
    if "iz0_a" in expected:
        assert result["iz0_a"] == expected["iz0_a"]
    if "k_total" in expected:
        assert result["k_total"] == expected["k_total"]
    if "delta_u_pct" in expected:
        assert abs(result["delta_u_pct"] - expected["delta_u_pct"]) <= 0.1
    if "pe_mm2" in expected:
        assert result["pe_mm2"] == expected["pe_mm2"]


def test_demo_project_feeder_cross_check_against_engine():
    from lv_assist.catalog import CatalogRepository
    from lv_assist.engine import CableSizingEngine, EngineeringEngine
    from lv_assist.gui import build_demo_project

    project, feeders = build_demo_project()
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, _, _ = engine.process_project(project, feeders)
    by_id = {feeder.feeder_id: feeder for feeder in feeders}

    for output in outputs:
        source = by_id[output.feeder_id]
        protection = output.selected_protection
        protection_in_a = (
            protection.rated_current_in_a
            if protection is not None
            else output.design_current_ib_a * 1.25
        )
        adjustable = protection is None or protection.device_type in ("MPCB", "MCCB")
        i2_factor = None
        if protection is not None:
            i2_factor = protection.overload_i2_factor or {
                "MCB": 1.45, "MCCB": 1.3, "MPCB": 1.3, "FUSE_GG": 1.6,
            }.get(protection.device_type)

        inputs = {
            "ib_a": output.design_current_ib_a,
            "voltage_v": project.nominal_voltage_v,
            "phases": source.phases,
            "length_m": output.cable_length_m,
            "cos_phi": output.cos_phi_resolved or source.cos_phi or 0.9,
            "ambient_temp_c": project.ambient_temp_c,
            "grouping_k2": project.cable_grouping_factor_k2,
            "insulation": source.insulation.value,
            "material": source.conductor_material.value,
            "installation_method": source.installation_method.value,
            "max_vdrop_pct": 3.0 if source.load_type.value == "LIGHTING_SOCKET" else 5.0,
            "protection_in_a": protection_in_a,
            "is_adjustable_prot": adjustable,
            "thdi_pct": source.thdi_pct,
            "load_type": source.load_type.value,
            "user_specified_mm2": source.cable_section_mm2,
            "ik_ka": None,
            "fault_time_s": None,
            "overload_i2_factor": i2_factor or 1.45,
        }
        result = select_cable_oracle(**inputs)
        engine_base = CableSizingEngine.select_feeder_cable(
            ib_a=inputs["ib_a"], protection_in_a=inputs["protection_in_a"],
            is_adjustable_prot=inputs["is_adjustable_prot"], length_m=inputs["length_m"],
            cos_phi=inputs["cos_phi"], voltage_v=inputs["voltage_v"], phases=inputs["phases"],
            ambient_temp_c=inputs["ambient_temp_c"], grouping_k2=inputs["grouping_k2"],
            max_vdrop_pct=inputs["max_vdrop_pct"], load_type=source.load_type,
            user_specified_mm2=inputs["user_specified_mm2"], conductor=inputs["material"],
            insulation=inputs["insulation"], installation_method=inputs["installation_method"],
            thdi_pct=inputs["thdi_pct"], fault_current_ka=None, clear_time_s=None,
            overload_i2_factor=i2_factor, additional_check=None,
        )
        diagnostics = (
            f"feeder={output.feeder_id}; inputs={inputs}; "
            f"oracle={result}; engine={{'phase_mm2': {output.selected_phase_mm2}, "
            f"'iz_corrected_a': {output.cable_derated_iz_a}, "
            f"'delta_u_pct': {output.voltage_drop_percent}}}; "
            f"engine_base={{'phase_mm2': {engine_base[0]}, 'iz_corrected_a': {engine_base[3]}, "
            f"'delta_u_pct': {engine_base[4]}}}"
        )

        assert result["phase_mm2"] == engine_base[0], diagnostics
        if engine_base[3] is not None:
            assert abs(result["iz_corrected_a"] - engine_base[3]) <= max(
                0.01, abs(engine_base[3]) * 0.01
            ), diagnostics
        assert abs(result["delta_u_pct"] - engine_base[4]) <= 0.5, diagnostics


def test_oracle_source_has_no_lv_assist_imports_and_cli_help_runs():
    oracle_path = ROOT / "tools" / "oracle_cable.py"
    tree = ast.parse(oracle_path.read_text(encoding="utf-8"))
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")

    assert not any(name == "lv_assist" or name.startswith("lv_assist.")
                   for name in imported_modules)
    completed = subprocess.run(
        [sys.executable, str(oracle_path), "--help"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Standalone cable-sizing oracle" in completed.stdout


def test_user_fixed_section_and_out_of_table_behavior():
    base = REFERENCE_CASES[0]["inputs"].copy()
    base["user_specified_mm2"] = 4.0
    assert select_cable_oracle(**base)["reason"] == "USER_FIXED"

    base["user_specified_mm2"] = 3.0
    result = select_cable_oracle(**base)
    assert result["reason"] == "OUT_OF_TABLE"
    assert result["pe_mm2"] is None
