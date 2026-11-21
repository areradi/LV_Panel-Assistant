"""Standalone fault-energy cross-check built from an auditable CSV snapshot."""

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from tools.oracle_cable import STANDARD_PE_SECTIONS_MM2, select_cable_oracle


STANDARD_PE_SECTIONS = STANDARD_PE_SECTIONS_MM2
_CURVE_FILE = Path(__file__).with_name("i2t_curves.csv")

_K_FACTORS = {
    ("CU", "PVC"): 115,
    ("CU", "XLPE"): 143,
    ("AL", "PVC"): 76,
    ("AL", "XLPE"): 94,
}


@dataclass(frozen=True)
class I2TAssessment:
    i2t_a2s: float
    source: str
    source_page: str | None
    approximate: bool
    notes: str
    warnings: tuple[str, ...] = ()
    verified_curve: bool = False


@lru_cache(maxsize=1)
def _load_curve_rows() -> tuple[dict[str, str], ...]:
    with _CURVE_FILE.open(encoding="utf-8", newline="") as stream:
        return tuple(
            row for row in csv.DictReader(stream)
            if row.get("verification_status", "").strip().upper() == "VERIFIED"
            and row.get("ik_ka", "").strip()
        )


def get_k_factor(material: str, insulation: str) -> int:
    """Return the requested in-cable PE k factor from IEC 60364-5-54."""
    key = (str(material).strip().upper(), str(insulation).strip().upper())
    try:
        return _K_FACTORS[key]
    except KeyError as exc:
        raise ValueError("material must be Cu/Al and insulation must be PVC/XLPE") from exc


def compute_required_pe_mm2(i2t: float, k: int) -> float:
    """Calculate the adiabatic PE area from energy and the material k factor."""
    try:
        energy = float(i2t)
    except (TypeError, ValueError) as exc:
        raise ValueError("i2t must be a finite non-negative number") from exc
    if not math.isfinite(energy) or energy < 0:
        raise ValueError("i2t must be a finite non-negative number")
    try:
        k_value = float(k)
    except (TypeError, ValueError) as exc:
        raise ValueError("k must be a finite positive number") from exc
    if not math.isfinite(k_value) or k_value <= 0:
        raise ValueError("k must be a finite positive number")
    return math.sqrt(energy) / k_value


def select_pe_from_required(
    required_mm2: float, standard_sections: list[float] | tuple[float, ...] = STANDARD_PE_SECTIONS,
) -> float | None:
    """Select the next listed PE section that meets the calculated minimum."""
    try:
        required = float(required_mm2)
    except (TypeError, ValueError) as exc:
        raise ValueError("required_mm2 must be finite and non-negative") from exc
    if not math.isfinite(required) or required < 0:
        raise ValueError("required_mm2 must be finite and non-negative")
    sections = sorted(float(section) for section in standard_sections)
    if any(not math.isfinite(section) or section <= 0 for section in sections):
        raise ValueError("standard sections must be finite and positive")
    return next((section for section in sections if section >= required), None)


def _validated_positive(name: str, value: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return numeric


def _validated_clearing_time(fault_time_s: float | None) -> float:
    if fault_time_s is None:
        raise ValueError("fault_time_s is required when no verified Ik-indexed curve is available")
    clearing_time = _validated_positive("fault_time_s", fault_time_s)
    if clearing_time > 5.0:
        raise ValueError("fault_time_s must be <= 5 seconds for the adiabatic method")
    return clearing_time


def _value_at_ik(rows: list[dict[str, str]], ik_ka: float):
    points = sorted(
        (float(row["ik_ka"]), float(row["i2t_a2s"]), row)
        for row in rows if row.get("ik_ka", "").strip()
    )
    if not points:
        return None
    exact = next((point for point in points if math.isclose(point[0], ik_ka)), None)
    if exact:
        return exact[1], exact[2], False, ""
    lower = next((point for point in reversed(points) if point[0] < ik_ka), None)
    upper = next((point for point in points if point[0] > ik_ka), None)
    if lower and upper:
        ratio = (ik_ka - lower[0]) / (upper[0] - lower[0])
        energy = lower[1] + ratio * (upper[1] - lower[1])
        return energy, lower[2], True, "Linear interpolation between Ik curve points."
    return None


def _curve_value_for_rating(rows: list[dict[str, str]], rated_a: float, ik_ka: float):
    rated_values = sorted({float(row["rated_a"]) for row in rows})
    exact_rating = next((rating for rating in rated_values if math.isclose(rating, rated_a)), None)
    if exact_rating is not None:
        return _value_at_ik([row for row in rows if float(row["rated_a"]) == exact_rating], ik_ka)

    lower = next((rating for rating in reversed(rated_values) if rating < rated_a), None)
    upper = next((rating for rating in rated_values if rating > rated_a), None)
    if lower is None or upper is None:
        return None
    low = _value_at_ik([row for row in rows if float(row["rated_a"]) == lower], ik_ka)
    high = _value_at_ik([row for row in rows if float(row["rated_a"]) == upper], ik_ka)
    if low is None or high is None:
        return None
    ratio = (rated_a - lower) / (upper - lower)
    energy = low[0] + ratio * (high[0] - low[0])
    if energy <= 0:
        return None
    extrapolated = rated_a < rated_values[0] or rated_a > rated_values[-1]
    note = "Linear interpolation across rated current and Ik curve points."
    if extrapolated:
        note = "Linear extrapolation beyond available rated-current points."
    return energy, low[1], True, note


def get_i2t_assessment(
    device_type: str,
    rated_a: float,
    ik_ka: float,
    material: str = "Cu",
    insulation: str = "PVC",
    fault_time_s: float | None = None,
) -> I2TAssessment:
    """Resolve source table energy or return a clearly marked estimate.

    Only verified, Ik-indexed source points in the active CSV are eligible.
    Unverified rows are quarantined separately and never loaded here.
    """
    get_k_factor(material, insulation)
    rating = _validated_positive("rated_a", rated_a)
    ik = _validated_positive("ik_ka", ik_ka)
    if not device_type or not str(device_type).strip():
        raise ValueError("device_type is required; pass the selected protective-device type")
    if fault_time_s is not None:
        _validated_clearing_time(fault_time_s)
    normalized_type = str(device_type).strip().upper()
    rows = [
        row for row in _load_curve_rows()
        if row["device_type"].strip().upper() == normalized_type
    ]

    if rows:
        ik_curve_rows = [row for row in rows if row.get("ik_ka", "").strip()]
        if ik_curve_rows:
            curve_value = _curve_value_for_rating(ik_curve_rows, rating, ik)
            if curve_value:
                energy, source_row, approximate, note = curve_value
                caveats = [note] if approximate else []
                return I2TAssessment(
                    i2t_a2s=energy, source=source_row["source_file"],
                    source_page=source_row["source_page"], approximate=approximate,
                    notes=note or source_row["source_note"], warnings=tuple(caveats),
                    verified_curve=True,
                )
            raise ValueError(
                f"Verified {normalized_type} curve has no bracketing points for "
                f"rated current={rating:g} A and Ik={ik:g} kA; extrapolation is not allowed"
            )

    clearing_time = _validated_clearing_time(fault_time_s)
    current_a = ik * 1000.0
    energy = current_a * current_a * clearing_time
    return I2TAssessment(
        i2t_a2s=energy, source="RMS Ik²t fallback", source_page=None, approximate=True,
        notes=f"RMS Ik={ik:g} kA and supplied clearing time={clearing_time:g} s.",
        warnings=(
            f"No verified Ik-indexed {normalized_type} curve was available; I²t uses RMS Ik={ik:g} kA and supplied t={clearing_time:g} s.",
        ),
    )


def get_i2t(
    device_type: str,
    rated_a: float,
    ik_ka: float,
    material: str,
    insulation: str,
    fault_time_s: float | None = None,
) -> float:
    """Return I²t in A²s; use get_i2t_assessment for its source and warnings."""
    assessment = get_i2t_assessment(
        device_type, rated_a, ik_ka, material, insulation, fault_time_s
    )
    if assessment.warnings:
        warnings.warn(" ".join(assessment.warnings), RuntimeWarning, stacklevel=2)
    return assessment.i2t_a2s


def select_cable_with_fault_energy(
    ib_a, voltage_v, phases, length_m, cos_phi,
    ambient_temp_c, grouping_k2, insulation, material,
    installation_method, max_vdrop_pct, protection_in_a,
    is_adjustable_prot, thdi_pct, load_type,
    user_specified_mm2, ik_ka, fault_time_s, overload_i2_factor,
    device_type=None,
) -> dict:
    """Run cable selection and apply an independent PE/fault-energy check.

    This checks the supplied Ik at one fault location. It does not model the
    engine's source-to-feeder-end network profile or device-specific trip curve.
    """
    assessment = get_i2t_assessment(
        device_type, protection_in_a, ik_ka, material, insulation, fault_time_s
    )
    k_factor = get_k_factor(material, insulation)
    required_pe = compute_required_pe_mm2(assessment.i2t_a2s, k_factor)
    base_inputs = {
        "ib_a": ib_a, "voltage_v": voltage_v, "phases": phases,
        "length_m": length_m, "cos_phi": cos_phi,
        "ambient_temp_c": ambient_temp_c, "grouping_k2": grouping_k2,
        "insulation": insulation, "material": material,
        "installation_method": installation_method,
        "max_vdrop_pct": max_vdrop_pct, "protection_in_a": protection_in_a,
        "is_adjustable_prot": is_adjustable_prot, "thdi_pct": thdi_pct,
        "load_type": load_type, "user_specified_mm2": user_specified_mm2,
        "ik_ka": None, "fault_time_s": None,
        "overload_i2_factor": overload_i2_factor,
    }
    base = select_cable_oracle(**base_inputs)
    initial_phase = float(base["phase_mm2"])
    fixed_section = user_specified_mm2 is not None
    candidates = [initial_phase] if fixed_section else [
        section for section in STANDARD_PE_SECTIONS if section >= initial_phase
    ]

    selected = None
    for candidate in candidates:
        candidate_inputs = dict(base_inputs)
        candidate_inputs["user_specified_mm2"] = candidate
        result = select_cable_oracle(**candidate_inputs)
        pe_base = result["pe_mm2"] or 0.0
        pe_selected = select_pe_from_required(max(required_pe, pe_base))
        if pe_selected is None:
            continue
        ampacity_ok = result["iz_corrected_a"] is not None and result["iz_corrected_a"] >= result["required_iz_a"]
        voltage_drop_ok = result["delta_u_pct"] <= max_vdrop_pct
        energy_ok = candidate >= required_pe and pe_selected >= required_pe
        if ampacity_ok and voltage_drop_ok and energy_ok:
            selected = (candidate, pe_selected, result)
            break

    warnings = list(assessment.warnings)
    warnings.append(
        "Single-point Ik check only; engine parity needs source and feeder-end Ik profiles and trip-time curves."
    )
    if selected is None:
        mode = "USER_FIXED" if fixed_section else "AUTO"
        warnings.append(
            f"Assumption impact: I2t={assessment.i2t_a2s:.6g} A²s requires at least {required_pe:.3g} mm²; no compatible standard phase/PE pair was found."
        )
        provisional = assessment.approximate or not assessment.verified_curve
        return {
            **base, "required_fault_pe_mm2": required_pe,
            "fault_energy_i2t_a2s": assessment.i2t_a2s,
            "fault_energy_source": assessment.source,
            "fault_energy_ok": False,
            "warnings": warnings,
            "reason": mode,
            "selection_status": "PROVISIONAL" if provisional else "FAULT_ENERGY_INCOMPATIBLE",
            "selection_result": "FAULT_ENERGY_INCOMPATIBLE",
            "is_safety_recommendation": False,
        }

    phase, pe, result = selected
    mode = "USER_FIXED" if fixed_section else "AUTO"
    warnings.append(
        f"Assumption impact: I2t={assessment.i2t_a2s:.6g} A²s requires {required_pe:.3g} mm²; selected phase={phase:g} mm² and PE={pe:g} mm²."
    )
    provisional = assessment.approximate or not assessment.verified_curve
    return {
        **result, "phase_mm2": phase, "pe_mm2": pe,
        "required_fault_pe_mm2": required_pe,
        "fault_energy_i2t_a2s": assessment.i2t_a2s,
        "fault_energy_source": assessment.source,
        "fault_energy_ok": True, "warnings": warnings,
        "reason": mode,
        "selection_status": "PROVISIONAL" if provisional else ("USER_FIXED" if fixed_section else "OK"),
        "selection_result": "USER_FIXED" if fixed_section else "OK",
        "is_safety_recommendation": False,
    }
