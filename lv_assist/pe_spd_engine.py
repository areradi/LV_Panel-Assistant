# -*- coding: utf-8 -*-
"""PE (protective earth) and SPD (surge protection) engineering logic.

Priority 4 of the audit fixes:

1. ``PE_K_FACTOR_TABLE`` / ``select_pe_k_factor`` — proper k-factor lookup per
   IEC 60364-5-54 Table 54.2 (Annex A), replacing the hardcoded 143.

2. ``calculate_pe_adiabatic_section`` — adiabatic PE cross-section with
   explicit k-factor selection and engineering notes.

3. ``evaluate_spd_requirements`` — multi-criteria SPD pre-selection that
   refuses to auto-approve when mandatory data is missing.

Pure stdlib + ``lv_assist.models``. No ``customtkinter`` import at module
load time, so it is unit-testable in CI without a display.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from lv_assist.models import (
    SPDSelectionResult,
    SPDType,
    StepEngStatus,
)


# IEC 60364-5-54 Table 54.2 / Annex A
# Key: (material, insulation, arrangement)
PE_K_FACTOR_TABLE: Dict[Tuple[str, str, str], int] = {
    ("Cu", "PVC", "in_cable"): 115,
    ("Cu", "PVC", "separate"): 143,
    ("Cu", "XLPE", "in_cable"): 143,
    ("Cu", "XLPE", "separate"): 176,
    ("Al", "PVC", "in_cable"): 76,
    ("Al", "XLPE", "in_cable"): 94,
    ("Steel", "Bare", "separate"): 52,
}


def select_pe_k_factor(
    material: str = "Cu",
    insulation: str = "PVC",
    arrangement: str = "separate",
) -> Tuple[int, str]:
    """Return a tabulated k-factor; unsupported conductor arrangements require input correction."""
    key = (material, insulation, arrangement)
    k = PE_K_FACTOR_TABLE.get(key)
    if k is None:
        raise ValueError(f"Unsupported PE material/insulation/arrangement: {key}")
    return k, f"ضریب k={k} بر اساس ({material}/{insulation}/{arrangement})."


def calculate_pe_adiabatic_section(
    fault_current_a: float,
    clearing_time_s: float,
    material: str = "Cu",
    insulation: str = "PVC",
    arrangement: str = "separate",
) -> Dict[str, Any]:
    """Adiabatic PE cross-section per IEC 60364-5-54.

    Returns a dict with:
    - ``s_adiabatic_mm2``  — minimum required cross-section (mm²)
    - ``k_factor_used``    — the k value applied
    - ``engineering_note`` — human-readable explanation
    """
    if not math.isfinite(fault_current_a) or fault_current_a <= 0:
        raise ValueError("fault_current_a must be > 0")
    if not math.isfinite(clearing_time_s) or not 0 < clearing_time_s <= 5:
        raise ValueError("Adiabatic clearing_time_s must be finite and in (0, 5]")

    k, note = select_pe_k_factor(material, insulation, arrangement)
    s_mm2 = (fault_current_a * math.sqrt(clearing_time_s)) / k

    return {
        "s_adiabatic_mm2": round(s_mm2, 2),
        "k_factor_used": k,
        "material": material,
        "insulation": insulation,
        "arrangement": arrangement,
        "engineering_note": note,
    }


def evaluate_spd_requirements(
    earthing_system: Optional[str] = None,
    nominal_voltage_ln_v: Optional[float] = None,
    has_external_lps: Optional[bool] = None,
    is_sensitive_terminal_load: bool = False,
    prospective_ik_ka: Optional[float] = None,
    candidates: Optional[List[Dict[str, Any]]] = None,
) -> SPDSelectionResult:
    """Multi-criteria SPD pre-selection per IEC 61643-11.

    Refuses to return a final device if mandatory inputs are missing
    (``engineering_status = INSUFFICIENT_DATA``). Otherwise returns a
    ``WARNING`` status — final confirmation still requires datasheet review.
    """
    candidates = candidates or []
    missing: List[str] = []
    notes: List[str] = []

    if earthing_system not in {'TN-S', 'TN-C-S', 'TT', 'IT'}:
        missing.append("earthing_system")
    if nominal_voltage_ln_v is None or not math.isfinite(nominal_voltage_ln_v) or nominal_voltage_ln_v <= 0:
        missing.append("nominal_voltage_ln_v")
    if not isinstance(has_external_lps, bool):
        missing.append("external_lps")
    if prospective_ik_ka is None or not math.isfinite(prospective_ik_ka) or prospective_ik_ka <= 0:
        missing.append("prospective_ik_ka")

    required_type: Optional[SPDType] = None
    if has_external_lps is True:
        required_type = SPDType.TYPE_1_2
        notes.append("به دلیل وجود LPS خارجی، SPD نوع Type 1 یا Type 1+2 با ظرفیت Iimp الزامی است.")
    elif has_external_lps is False:
        required_type = SPDType.TYPE_2
        notes.append("برای تابلو توزیع بدون LPS خارجی، SPD نوع Type 2 مبنای پیش‌انتخاب است.")

    if is_sensitive_terminal_load:
        notes.append("برای تجهیزات حساس پایین‌دست (فاصله بیش از 10m)، بررسی SPD مکمل Type 3 ضروری است.")

    if missing:
        return SPDSelectionResult(
            spd_type=required_type,
            engineering_status=StepEngStatus.INSUFFICIENT_DATA,
            missing_parameters=missing,
            review_notes=notes + [
                "اطلاعات ناکافی: پیش از نهایی‌سازی SPD، پارامترهای کسری را تکمیل کنید."
            ],
        )

    if earthing_system == "IT":
        min_uc_v = round(nominal_voltage_ln_v * 1.5, 1)
    else:
        min_uc_v = round(nominal_voltage_ln_v * 1.15, 1)

    allowed_types = ({SPDType.TYPE_1.value, SPDType.TYPE_1_2.value} if has_external_lps else
                     {SPDType.TYPE_2.value, SPDType.TYPE_2_3.value, SPDType.TYPE_1_2.value})
    matched = [
        c for c in candidates
        if (c.get("uc_v") or 0) >= min_uc_v
        and c.get('spd_type') in allowed_types
    ]

    if not matched:
        return SPDSelectionResult(
            spd_type=required_type,
            engineering_status=StepEngStatus.WARNING,
            missing_parameters=[],
            review_notes=notes + [
                f"هیچ تجهیز کاتالوگی با Uc ≥ {min_uc_v} V و نوع درخواستی یافت نشد."
            ],
        )

    best = matched[0]
    notes.append(
        "پیش‌انتخاب اولیه انجام شد؛ هماهنگی انرژی (Cascading)، سطح حفاظت Up و "
        "فیوز پشتیبان باید با دیتاشیت سازنده تطبیق داده شود."
    )

    return SPDSelectionResult(
        spd_type=SPDType(best.get('spd_type')),
        model_name=best.get("model_name"),
        uc_v=best.get("uc_v"),
        up_kv=best.get("up_kv"),
        iimp_ka=best.get("iimp_ka"),
        in_ka=best.get("in_ka"),
        imax_ka=best.get("imax_ka"),
        backup_fuse_a=best.get("backup_fuse_a"),
        engineering_status=StepEngStatus.WARNING,
        missing_parameters=[],
        review_notes=notes,
    )
