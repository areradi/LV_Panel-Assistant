"""Standalone cable-selection oracle, intentionally independent of lv_assist."""

from __future__ import annotations

import argparse
import json
import math


# Source: IEC 60364-5-52 Table B.52.4 (Cu/PVC, 3 loaded conductors, method C).
# Values were copied from migrate_to_sqlite.py:164. Verify against the IEC
# edition adopted by the project before using this snapshot for design approval.
IZ0_TABLE_CU_PVC_METHOD_C = {
    1.5: 17.5,
    2.5: 24.0,
    4.0: 32.0,
    6.0: 41.0,
    10.0: 57.0,
    16.0: 76.0,
    25.0: 96.0,
    35.0: 119.0,
    50.0: 144.0,
    70.0: 184.0,
    95.0: 223.0,
    120.0: 259.0,
    150.0: 299.0,
    185.0: 341.0,
    240.0: 403.0,
    300.0: 464.0,
}

# Source: engine.py:108, DIN VDE 0298-4 temperature factors (30 C reference).
# Copied for isolation; verify against the applicable standard edition.
TEMP_FACTORS_PVC = ((30.0, 1.00), (35.0, 0.94), (40.0, 0.87),
                    (45.0, 0.79), (50.0, 0.71))
TEMP_FACTORS_XLPE = ((30.0, 1.00), (35.0, 0.96), (40.0, 0.91),
                     (45.0, 0.87), (50.0, 0.82))
TEMP_FACTOR_ABOVE_MAX = {"PVC": 0.61, "XLPE": 0.76}

# Source: engine.py:91-94.
K_MATERIAL = {"CU": 1.0, "AL": 0.78}
K_INSULATION = {"PVC": 1.0, "XLPE": 1.17}
K_INSTALLATION = {
    "A1": 0.70, "A2": 0.68, "B1": 0.80, "B2": 0.77,
    "C": 1.00, "E": 1.12, "F": 0.91, "D": 0.85,
}

# Source: migrate_to_sqlite.py:183.
STANDARD_PE_SECTIONS_MM2 = (
    1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0, 35.0,
    50.0, 70.0, 95.0, 120.0, 150.0, 185.0, 240.0, 300.0, 400.0,
)

# Source: pe_spd_engine.py:30, IEC 60364-5-54 Table 54.2 / Annex A.
PE_K_FACTOR = {
    ("CU", "PVC", "IN_CABLE"): 115,
    ("CU", "PVC", "SEPARATE"): 143,
    ("CU", "XLPE", "IN_CABLE"): 143,
    ("CU", "XLPE", "SEPARATE"): 176,
    ("AL", "XLPE", "IN_CABLE"): 94,
}

# Source: engine.py:93-95, calc_voltage_drop_pct.
RHO_CU_20C = 22.5
RHO_AL_20C = 36.0
TEMP_COEFF = {"PVC": 1.20, "XLPE": 1.28}
X_OHM_PER_KM = 0.08

_CABLE_SECTIONS = tuple(sorted(IZ0_TABLE_CU_PVC_METHOD_C))


def _temp_factor(ambient_temp_c: float, insulation: str) -> float:
    rows = TEMP_FACTORS_XLPE if insulation == "XLPE" else TEMP_FACTORS_PVC
    for limit_c, factor in rows:
        if ambient_temp_c <= limit_c:
            return factor
    return TEMP_FACTOR_ABOVE_MAX[insulation]


def _voltage_drop_pct(
    ib_a: float, length_m: float, section_mm2: float, cos_phi: float,
    voltage_v: float, phases: int, material: str, insulation: str,
) -> float:
    rho = RHO_CU_20C if material == "CU" else RHO_AL_20C
    r_ohm_km = rho / section_mm2 * TEMP_COEFF[insulation]
    sin_phi = math.sqrt(max(0.0, 1.0 - min(1.0, cos_phi) ** 2))
    multiplier = math.sqrt(3.0) if phases == 3 else 2.0
    base_voltage = voltage_v if phases == 3 else voltage_v / math.sqrt(3.0)
    drop_v = multiplier * ib_a * (length_m / 1000.0) * (
        r_ohm_km * cos_phi + X_OHM_PER_KM * sin_phi
    )
    return round(drop_v / base_voltage * 100.0, 2)


def _next_pe_section(required_mm2: float) -> float | None:
    return next((size for size in STANDARD_PE_SECTIONS_MM2 if size >= required_mm2), None)


def _pe_section(
    phase_mm2: float, ik_ka: float | None, fault_time_s: float | None,
    material: str, insulation: str,
) -> tuple[float | None, str | None]:
    if ik_ka is None or fault_time_s is None:
        return None, "PE not calculated: Ik and fault clearing time are required."
    if not math.isfinite(ik_ka) or ik_ka <= 0 or not math.isfinite(fault_time_s):
        return None, "PE not calculated: Ik and clearing time must be finite and positive."
    if not 0 < fault_time_s <= 5:
        return None, "PE not calculated: adiabatic clearing time must be in (0, 5] seconds."

    key = (material, insulation, "IN_CABLE")
    k_factor = PE_K_FACTOR.get(key)
    if k_factor is None:
        return None, f"PE not calculated: no k-factor snapshot for {key}."

    if phase_mm2 <= 16.0:
        table_minimum = phase_mm2
    elif phase_mm2 <= 35.0:
        table_minimum = 16.0
    else:
        table_minimum = phase_mm2 / 2.0
    adiabatic_minimum = ik_ka * 1000.0 * math.sqrt(fault_time_s) / k_factor
    return _next_pe_section(max(table_minimum, adiabatic_minimum)), None


def select_cable_oracle(
    ib_a: float,
    voltage_v: float,
    phases: int,
    length_m: float,
    cos_phi: float,
    ambient_temp_c: float,
    grouping_k2: float,
    insulation: str,
    material: str,
    installation_method: str,
    max_vdrop_pct: float,
    protection_in_a: float,
    is_adjustable_prot: bool,
    thdi_pct: float | None,
    load_type: str,
    user_specified_mm2: float | None,
    ik_ka: float | None,
    fault_time_s: float | None,
    overload_i2_factor: float = 1.45,
) -> dict:
    """Select a cable using a standalone snapshot and return intermediate values.

    ``overload_i2_factor`` is the protection's I2/In ratio. The required
    ampacity follows Ib or In, as applicable, and the IEC I2 <= 1.45 Iz check.
    """
    material = str(material).upper()
    insulation = str(insulation).upper()
    installation_method = str(installation_method).upper()
    load_type = str(load_type).upper()
    if phases not in (1, 3):
        raise ValueError("phases must be 1 or 3")
    if material not in K_MATERIAL or insulation not in K_INSULATION:
        raise ValueError("material must be CU/AL and insulation must be PVC/XLPE")
    if installation_method not in K_INSTALLATION:
        raise ValueError(f"unsupported installation method: {installation_method}")
    if not (0 < grouping_k2 <= 1):
        raise ValueError("grouping_k2 must be in (0, 1]")
    if not (0 < cos_phi <= 1):
        raise ValueError("cos_phi must be in (0, 1]")
    for name, value in (("ib_a", ib_a), ("voltage_v", voltage_v),
                        ("length_m", length_m), ("ambient_temp_c", ambient_temp_c),
                        ("max_vdrop_pct", max_vdrop_pct),
                        ("protection_in_a", protection_in_a),
                        ("overload_i2_factor", overload_i2_factor)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if ib_a <= 0 or voltage_v <= 0 or length_m < 0 or protection_in_a <= 0:
        raise ValueError("current, voltage and protection rating must be positive; length cannot be negative")

    k1 = _temp_factor(ambient_temp_c, insulation)
    k_material = K_MATERIAL[material]
    k_insulation = K_INSULATION[insulation]
    k_installation = K_INSTALLATION[installation_method]
    k_total = round(k1 * grouping_k2 * k_material * k_insulation * k_installation, 3)

    # Match the engine's protective-current coordination rule (not In * I2/In).
    required_iz = ib_a if is_adjustable_prot else protection_in_a
    required_iz = max(required_iz, protection_in_a * overload_i2_factor / 1.45)

    assumptions = ["Ampacity snapshot is Cu/PVC/method C; other conditions use copied correction factors."]
    if material != "CU" or insulation != "PVC" or installation_method != "C":
        assumptions.append("Non-reference cable conditions are modeled with multiplicative correction factors.")

    if user_specified_mm2 is not None:
        phase_mm2 = float(user_specified_mm2)
        iz0 = IZ0_TABLE_CU_PVC_METHOD_C.get(phase_mm2)
        if iz0 is None:
            return {
                "phase_mm2": phase_mm2, "neutral_mm2": phase_mm2 if phases == 1 else 0.0,
                "pe_mm2": None, "iz0_a": None, "k1": k1, "k2": grouping_k2,
                "k_material": k_material, "k_insulation": k_insulation,
                "k_installation": k_installation, "k_total": k_total,
                "iz_corrected_a": None, "required_iz_a": required_iz,
                "delta_u_pct": _voltage_drop_pct(ib_a, length_m, phase_mm2, cos_phi,
                    voltage_v, phases, material, insulation),
                "reason": "OUT_OF_TABLE", "assumptions": assumptions + [
                    "User section is absent from the ampacity snapshot; PE sizing was not inferred."
                ],
            }
        selected_iz = round(iz0 * k_total, 1)
        delta_u_pct = _voltage_drop_pct(ib_a, length_m, phase_mm2, cos_phi,
            voltage_v, phases, material, insulation)
        reason = "USER_FIXED"
    else:
        selected = None
        for section_mm2 in _CABLE_SECTIONS:
            if section_mm2 < (1.5 if load_type == "LIGHTING_SOCKET" else 2.5):
                continue
            iz0_candidate = IZ0_TABLE_CU_PVC_METHOD_C[section_mm2]
            iz_candidate = round(iz0_candidate * k_total, 1)
            du_candidate = _voltage_drop_pct(ib_a, length_m, section_mm2, cos_phi,
                voltage_v, phases, material, insulation)
            if iz_candidate >= required_iz and du_candidate <= max_vdrop_pct:
                selected = (section_mm2, iz0_candidate, iz_candidate, du_candidate)
                break
        if selected is None:
            phase_mm2 = _CABLE_SECTIONS[-1]
            iz0 = IZ0_TABLE_CU_PVC_METHOD_C[phase_mm2]
            selected_iz = round(iz0 * k_total, 1)
            delta_u_pct = _voltage_drop_pct(ib_a, length_m, phase_mm2, cos_phi,
                voltage_v, phases, material, insulation)
            reason = "NO_FEASIBLE_SECTION"
            assumptions.append("No table section met both ampacity and voltage-drop limits; largest table section returned.")
        else:
            phase_mm2, iz0, selected_iz, delta_u_pct = selected
            reason = "OK"

    if phases == 1:
        neutral_mm2 = phase_mm2
    elif load_type in ("LIGHTING_SOCKET", "SUB_FEEDER"):
        if thdi_pct is not None and thdi_pct >= 33.0:
            neutral_mm2 = phase_mm2
        else:
            neutral_mm2 = next((section for section in _CABLE_SECTIONS
                                if section >= phase_mm2 / 2.0), phase_mm2)
    else:
        neutral_mm2 = 0.0

    pe_mm2, pe_note = _pe_section(phase_mm2, ik_ka, fault_time_s, material, insulation)
    if pe_note:
        assumptions.append(pe_note)

    return {
        "phase_mm2": phase_mm2, "neutral_mm2": neutral_mm2, "pe_mm2": pe_mm2,
        "iz0_a": iz0, "k1": k1, "k2": grouping_k2,
        "k_material": k_material, "k_insulation": k_insulation,
        "k_installation": k_installation, "k_total": k_total,
        "iz_corrected_a": selected_iz, "required_iz_a": required_iz,
        "delta_u_pct": delta_u_pct, "reason": reason, "assumptions": assumptions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone cable-sizing oracle")
    parser.add_argument("--ib", type=float, required=True, help="Design current in A")
    parser.add_argument("--voltage", type=float, required=True, help="Nominal voltage in V")
    parser.add_argument("--phases", type=int, choices=(1, 3), required=True)
    parser.add_argument("--length", type=float, required=True, help="Cable length in m")
    parser.add_argument("--cos-phi", type=float, required=True)
    parser.add_argument("--ambient", type=float, required=True, help="Ambient temperature in C")
    parser.add_argument("--grouping-k2", type=float, required=True)
    parser.add_argument("--insulation", choices=("PVC", "XLPE"), required=True)
    parser.add_argument("--material", choices=("CU", "AL"), required=True)
    parser.add_argument("--method", choices=tuple(K_INSTALLATION), required=True)
    parser.add_argument("--max-vdrop", type=float, required=True)
    parser.add_argument("--protection-in", type=float, required=True)
    parser.add_argument("--adjustable", action="store_true")
    parser.add_argument("--thdi", type=float)
    parser.add_argument("--load-type", default="SUB_FEEDER")
    parser.add_argument("--user-section", type=float)
    parser.add_argument("--ik-ka", type=float)
    parser.add_argument("--fault-time", type=float)
    parser.add_argument("--overload-i2-factor", type=float, default=1.45)
    args = parser.parse_args()
    result = select_cable_oracle(
        ib_a=args.ib, voltage_v=args.voltage, phases=args.phases,
        length_m=args.length, cos_phi=args.cos_phi,
        ambient_temp_c=args.ambient, grouping_k2=args.grouping_k2,
        insulation=args.insulation, material=args.material,
        installation_method=args.method, max_vdrop_pct=args.max_vdrop,
        protection_in_a=args.protection_in, is_adjustable_prot=args.adjustable,
        thdi_pct=args.thdi, load_type=args.load_type,
        user_specified_mm2=args.user_section, ik_ka=args.ik_ka,
        fault_time_s=args.fault_time, overload_i2_factor=args.overload_i2_factor,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
