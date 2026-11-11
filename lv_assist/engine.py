# -*- coding: utf-8 -*-
import math
import cmath
from typing import List, Optional, Tuple, Dict
from lv_assist.models import (
    ProjectSpec, FeederInput, CatalogDevice, ValidationResult, FeederCalcOutput,
    PanelSummaryOutput, LoadType, ValidationStatus, SelectivityEvalState, SpecialScenario, DataQuality, SpdClass,
    DesignVerificationItem, DesignVerificationReport, VerificationMethod, VerificationStatus, EnclosureMounting
)

from lv_assist.pe_spd_engine import evaluate_spd_requirements, select_pe_k_factor
from lv_assist.catalog import SiemensSelectivityRepository, TripCurveRepository, catalog_repo
from lv_assist.busbar import BusbarEngine
from lv_assist.i18n import i18n, tr
from lv_assist.scenario_rules import evaluate_scenario
# --- [AUDIT SAFE IMPORTS] ---
from lv_assist.core_verification import (
    ValidationStatus as AuditValidationStatus,
    CheckResult as AuditCheckResult,
    TripTimeEstimate as AuditTripTimeEstimate,
    ShortCircuitProfile as AuditShortCircuitProfile,
    estimate_clear_time_s as audit_estimate_clear_time,
    calculate_adiabatic_pe_mm2 as audit_calculate_adiabatic_pe_mm2,
    calculate_network_ik_profile as audit_calculate_network_ik_profile,
    verify_breaking_capacity_icu as audit_verify_breaking_capacity_icu,
    aggregate_status as audit_aggregate_status,
)
from lv_assist.catalog_provenance import (
    evaluate_selectivity_status as audit_evaluate_selectivity_status,
)
# --- end audit safe imports ---
# --- [AUDIT P0 POLICY FLAGS] ---
# Backward-compatible by default.
# Flip these only after reference tests are updated.
ENGINE_AUDIT_STRICT_CLEAR_TIME = True
ENGINE_AUDIT_ICU_UNKNOWN_AS_PASS = False
ENGINE_AUDIT_ENABLE_FEEDER_IK_PROFILE = True
# --- end audit P0 policy flags ---

_FAULT_BASIS_UNAVAILABLE = {
    "fa": "مبنای آدیاباتیک قابل محاسبه نیست",
    "en": "Adiabatic basis cannot be calculated",
    "de": "Die adiabatische Grundlage kann nicht berechnet werden",
}


def _is_valid_clear_time(t):
    return t is not None and isinstance(t, (int, float)) and math.isfinite(t) and t > 0




# --- نگاشت استانداردهای IEC به معادل رسمی DIN EN / VDE آلمان ---
IEC_TO_VDE_STD_MAP: Dict[str, str] = {
    "IEC 61439-1": "DIN EN 61439-1 (VDE 0660-600-1)",
    "IEC 61439-2": "DIN EN 61439-2 (VDE 0660-600-2)",
    "IEC 61439-2 / IEC TR 60890": "DIN EN 61439-2 (VDE 0660-600-2) / DIN EN 60890",
    "IEC 60364-5-52": "DIN VDE 0100-520 / DIN VDE 0298-4",
    "IEC 60364-4-43": "DIN VDE 0100-430",
    "IEC 60364-5-54": "DIN VDE 0100-540",
    "IEC 60364-5-56": "DIN VDE 0100-560",
    "IEC 60204-1": "DIN EN 60204-1 (VDE 0113-1)",
    "IEC 60909-0": "DIN EN 60909-0 (VDE 0102)",
    "IEC 60947-2": "DIN EN 60947-2 (VDE 0660-101)",
    "IEC 60947-4-1": "DIN EN 60947-4-1 (VDE 0660-102)",
    "IEC 60947-6-1": "DIN EN 60947-6-1 (VDE 0660-114)",
    "IEC 60529": "DIN EN 60529 (VDE 0470-1)",
    "IEC 60831-1": "DIN EN 60831-1 (VDE 0560-46)",
    "IEC 61642": "DIN EN 61642 (VDE 0560-410)",
    "IEC 61643-11": "DIN EN 61643-11 (VDE 0675-6-11)",
    "IEC 61643-12": "DIN CLC/TS 61643-12 (VDE V 0675-6-12)",
    "IEC 60034-1": "DIN EN 60034-1 (VDE 0530-1)",
    "IEC 60034-30-1": "DIN EN 60034-30-1 (VDE 0530-30-1)",
    "IEC 61000-3-12": "DIN EN 61000-3-12 (VDE 0838-12)",
    "IEC 62040-3": "DIN EN 62040-3 (VDE 0558-530)",
}

def is_vde_project(project: ProjectSpec) -> bool:
    ref = (getattr(project, "standard_ref", "") or "").upper()
    return "VDE" in ref or "DIN" in ref

def apply_vde_standard_refs(project: ProjectSpec, validations: List[ValidationResult]) -> None:
    if not is_vde_project(project):
        return
    for v in validations:
        if v.standard_ref in IEC_TO_VDE_STD_MAP:
            v.standard_ref = IEC_TO_VDE_STD_MAP[v.standard_ref]


class CableSizingEngine:
    MATERIAL_IZ_FACTOR: Dict[str, float] = {"CU": 1.0, "AL": 0.78}
    INSULATION_IZ_FACTOR: Dict[str, float] = {"PVC": 1.0, "XLPE": 1.17}
    # ضرایب روش نصب (Verlegungsarten) مطابق DIN VDE 0298-4 / IEC 60364-5-52 نسبت به روش مرجع C
    METHOD_IZ_FACTOR: Dict[str, float] = {
        "A1": 0.70, "A2": 0.68, "B1": 0.80, "B2": 0.77,
        "C": 1.00, "E": 1.12, "F": 0.91, "D": 0.85,
    }
    RESISTIVITY_OHM_MM2_KM: Dict[str, float] = {"CU": 22.5, "AL": 36.0}
    # R در دمای کارکرد کامل (PVC=70°C، XLPE=90°C) نسبت به R20 (ممیزی دور ۱۰)
    VD_TEMP_FACTOR: Dict[str, float] = {"PVC": 1.20, "XLPE": 1.28}

    @classmethod
    def get_iz0_table(cls, loaded_conductors: int = 3) -> Dict[float, float]:
        # جدول مرجع از دیتابیس SQLite (IEC 60364-5-52)؛ بدون هیچ مقدار ساختگی (F-001)
        return catalog_repo.get_cable_iz0_table_cu_pvc_c(loaded_conductors=loaded_conductors)

    @classmethod
    def get_temp_factor_k1(cls, ambient_temp_c: float, insulation: str = "PVC") -> float:
        """ضریب تصحیح دمای محیط (k1) بر اساس DIN VDE 0298-4 جدول ۱۷ (مرجع ۳۰°C هوا)."""
        if str(insulation).upper() == "XLPE":
            if ambient_temp_c <= 30.0: return 1.00
            elif ambient_temp_c <= 35.0: return 0.96
            elif ambient_temp_c <= 40.0: return 0.91
            elif ambient_temp_c <= 45.0: return 0.87
            elif ambient_temp_c <= 50.0: return 0.82
            return 0.76
        if ambient_temp_c <= 30.0: return 1.00
        elif ambient_temp_c <= 35.0: return 0.94
        elif ambient_temp_c <= 40.0: return 0.87
        elif ambient_temp_c <= 45.0: return 0.79
        elif ambient_temp_c <= 50.0: return 0.71
        return 0.61

    @classmethod
    def get_derating_summary(cls, ambient_temp_c: float, grouping_k2: float,
                             conductor: str = "CU", insulation: str = "PVC",
                             installation_method: str = "C") -> Tuple[float, float, float]:
        """ضرایب تصحیح قابل ردیابی برای گزارش: k1 دما، k2 تجمع، k_total (DIN VDE 0298-4)."""
        k1 = cls.get_temp_factor_k1(ambient_temp_c, insulation=insulation)
        mat_k = cls.MATERIAL_IZ_FACTOR.get(conductor, 1.0)
        ins_k = cls.INSULATION_IZ_FACTOR.get(insulation, 1.0)
        meth_k = cls.METHOD_IZ_FACTOR.get(installation_method, 1.0)
        ktotal = round(k1 * grouping_k2 * mat_k * ins_k * meth_k, 3)
        return k1, grouping_k2, ktotal

    @classmethod
    def calc_voltage_drop_pct(cls, ib_a: float, length_m: float, section_mm2: float, cos_phi: float, voltage_v: float, phases: int, conductor: str = "CU", insulation: str = "PVC") -> float:
        # ضریب دمای کارکرد هادی (۷۰°C PVC / ۹۰°C XLPE) روی مقاومت R20 اعمال می‌شود
        temp_k = cls.VD_TEMP_FACTOR.get(insulation, 1.0)
        r_ohm_km = cls.RESISTIVITY_OHM_MM2_KM.get(conductor, 22.5) / section_mm2 * temp_k
        x_ohm_km = 0.08
        length_km = length_m / 1000.0
        sin_phi = math.sqrt(max(0.0, 1.0 - min(1.0, cos_phi)**2))
        factor = math.sqrt(3) if phases == 3 else 2.0
        u_base = voltage_v if phases == 3 else (voltage_v / math.sqrt(3))
        delta_u = factor * ib_a * length_km * (r_ohm_km * cos_phi + x_ohm_km * sin_phi)
        return round((delta_u / u_base) * 100.0, 2)

    @classmethod
    def calculate_pe_section(
        cls,
        phase_section_mm2: float,
        fault_current_ka: Optional[float] = None,
        clear_time_s: Optional[float] = None,
        material: str = "Cu",
        insulation: str = "PVC",
        arrangement: str = "separate",
    ) -> Optional[float]:
        _k, _ = select_pe_k_factor(material, insulation, arrangement)
        if (fault_current_ka is None or not math.isfinite(fault_current_ka)
                or not _is_valid_clear_time(clear_time_s)):
            return None
        if phase_section_mm2 <= 16.0: s_table = phase_section_mm2
        elif phase_section_mm2 <= 35.0: s_table = 16.0
        else: s_table = phase_section_mm2 / 2.0
        if clear_time_s > 5:
            return None
        i_fault_a = fault_current_ka * 1000.0
        s_adiabatic = (i_fault_a * math.sqrt(clear_time_s)) / float(_k)
        req_pe = max(s_table, s_adiabatic)
        # اولین مقطع استاندارد از جدول PE دیتابیس؛ فراتر از جدول → None (F-005، بدون سقف ساختگی)
        return catalog_repo.get_standard_pe_section(req_pe)

    @classmethod
    def select_feeder_cable(
        cls, ib_a: float, protection_in_a: float, is_adjustable_prot: bool, length_m: float,
        cos_phi: float, voltage_v: float, phases: int, ambient_temp_c: float, grouping_k2: float,
        max_vdrop_pct: float, load_type: LoadType, user_specified_mm2: Optional[float] = None,
        conductor: str = "CU", insulation: str = "PVC", installation_method: str = "C",
        fire_resistant: bool = False, thdi_pct: Optional[float] = None,
        fault_current_ka: Optional[float] = None, clear_time_s: Optional[float] = None,
        overload_i2_factor: Optional[float] = None, additional_check=None
    ) -> Tuple[float, float, Optional[float], Optional[float], float, str]:
        k1, k2, total_k = cls.get_derating_summary(ambient_temp_c, grouping_k2, conductor, insulation, installation_method)
        required_iz = ib_a if is_adjustable_prot else protection_in_a
        if overload_i2_factor is not None:
            required_iz = max(required_iz, overload_i2_factor * protection_in_a / 1.45)
        material = "Cu" if conductor == "CU" else "Al"
        phase_k, _ = select_pe_k_factor(material, insulation, "in_cable")
        adiabatic_min = 0.0
        if fault_current_ka is not None and clear_time_s is not None and 0 < clear_time_s <= 5:
            adiabatic_min = fault_current_ka * 1000 * math.sqrt(clear_time_s) / phase_k
        min_allowed_section = 1.5 if load_type == LoadType.LIGHTING_SOCKET else 2.5

        table = cls.get_iz0_table(loaded_conductors=3)
        if user_specified_mm2 is not None:
            s_ph = user_specified_mm2
            iz0 = table.get(s_ph)
            # مقطع غیرجدولی → None به‌جای ۱۰۰ ساختگی قدیمی (F-001)
            iz_derated = round(iz0 * total_k, 1) if iz0 is not None else None
            vdrop = cls.calc_voltage_drop_pct(ib_a, length_m, s_ph, cos_phi, voltage_v, phases, conductor, insulation)
        else:
            s_ph = 240.0
            iz_derated, vdrop = None, 0.0
            sections = sorted(table.items()) if table else []
            if sections:
                s_ph, iz0_largest = sections[-1]
                iz_derated = round(iz0_largest * total_k, 1)
                vdrop = cls.calc_voltage_drop_pct(ib_a, length_m, s_ph, cos_phi, voltage_v, phases, conductor, insulation)
                for sec, iz0 in sections:
                    if sec < min_allowed_section: continue
                    curr_iz = round(iz0 * total_k, 1)
                    curr_vd = cls.calc_voltage_drop_pct(ib_a, length_m, sec, cos_phi, voltage_v, phases, conductor, insulation)
                    pe = cls.calculate_pe_section(sec, fault_current_ka, clear_time_s,
                                                  material, insulation, 'in_cable')
                    extra_ok = additional_check is None or additional_check(sec, pe)
                    if curr_iz >= required_iz and curr_vd <= max_vdrop_pct and sec >= adiabatic_min and extra_ok:
                        s_ph = sec; iz_derated = curr_iz; vdrop = curr_vd; break

        # F-005: جریان خطا و زمان قطع واقعی پروژه (نه فرض ثابت ۱۰ kA / ۲۰ ms)
        s_pe = cls.calculate_pe_section(
            s_ph,
            fault_current_ka,
            clear_time_s,
            material=material, insulation=insulation, arrangement="in_cable",
        )
        s_neutral = 0.0
        if phases == 3 and load_type in (LoadType.LIGHTING_SOCKET, LoadType.SUB_FEEDER):
            if thdi_pct is not None and thdi_pct >= 33.0:
                s_neutral = s_ph
            else:
                half_s = s_ph / 2.0
                s_neutral = next((s for s in sorted(table.keys()) if s >= half_s), s_ph)

        s_pe_lbl = f"{s_pe:g}" if s_pe is not None else tr("desig_pe_nostd")
        mat_lbl = "Cu" if conductor == "CU" else "Al"
        if phases == 1:
            s_neutral = s_ph
            desig = f"2x{s_ph:g}+{s_pe_lbl} mm² {mat_lbl} (L+N+PE)"
        elif load_type == LoadType.MOTOR_STAR_DELTA:
            i_delta = ib_a / math.sqrt(3)
            s_delta = next((sec for sec, iz0 in sorted(table.items()) if sec >= 2.5 and (iz0 * total_k) >= i_delta), s_ph)
            desig = f"Line: 3x{s_ph:g}+{s_pe_lbl} mm² | Motor Y-Δ: 2x(3x{s_delta:g})+{s_pe_lbl} mm² {mat_lbl}"
        elif load_type == LoadType.MOTOR_VFD:
            desig = f"3x{s_ph:g}+{s_pe_lbl} mm² {mat_lbl} (Shielded EMC CY/NYCWY)"
        elif phases == 3 and s_neutral > 0:
            if s_neutral == s_ph:
                desig = f"4x{s_ph:g}+{s_pe_lbl} mm² {mat_lbl} (3P+N+PE)"
            else:
                desig = f"3x{s_ph:g}+N{s_neutral:g}+{s_pe_lbl} mm² {mat_lbl} (3P+N+PE)"
        else:
            desig = f"3x{s_ph:g}+{s_pe_lbl} mm² {mat_lbl} (3P+PE)"
        if fire_resistant:
            desig += " FR"
        return s_ph, s_neutral, s_pe, iz_derated, vdrop, desig

class EngineeringEngine:
    START_K_FACTOR: Dict[LoadType, float] = {
        LoadType.MOTOR_DOL: 7.0,
        LoadType.MOTOR_STAR_DELTA: 2.2,
        LoadType.MOTOR_SOFT_STARTER: 3.5,
        LoadType.MOTOR_VFD: 1.2,
    }
    # مشارکت موتور در اتصال کوتاه (IEC 60909-0): I''_kM = c·(I_LR/I_rM)·I_rM
    # VFD: رکتیفایر ورودی جریان برگشتی نمی‌دهد → مشارکت صفر
    MOTOR_IK_K_FACTOR: Dict[LoadType, float] = {
        LoadType.MOTOR_DOL: 6.0,
        LoadType.MOTOR_STAR_DELTA: 4.0,
        LoadType.MOTOR_SOFT_STARTER: 3.0,
        LoadType.MOTOR_VFD: 0.0,
    }
    MOTOR_IK_KAPPA = 1.7   # ضریب پیک موتورها (IEC 60909-0)
    C_IK_MAX = 1.05        # ضریب ولتاژ c_max در LV (جدول ۱ استاندارد)

    def __init__(self, catalog: List[CatalogDevice]):
        self._full_catalog = list(catalog)
        self.catalog = list(catalog)

    @staticmethod
    def _resolve_cos_phi_eff(load_type: LoadType, cos_phi: Optional[float],
                             eff: Optional[float]) -> Tuple[float, float]:
        motor = load_type in (LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA,
                              LoadType.MOTOR_SOFT_STARTER, LoadType.MOTOR_VFD)
        if cos_phi is None:
            cos_phi = 0.95 if load_type == LoadType.MOTOR_VFD else (
                0.86 if motor else (1.0 if load_type == LoadType.HEATER_RESISTIVE else 0.90))
        if not motor:
            eff = 1.0
        elif eff is None:
            eff = 0.91 if motor else 1.0
        return cos_phi, eff

    PFC_STEP_OPTIONS = (50.0, 25.0, 20.0, 15.0, 12.5, 10.0, 5.0)
    MAX_PFC_STEPS = 12

    @classmethod
    def _max_pfc_kvar(cls) -> float:
        return cls.MAX_PFC_STEPS * cls.PFC_STEP_OPTIONS[0]

    @classmethod
    def _pick_cap_steps(cls, qc_required_kvar: float):
        """پله‌بندی حریصانه با پله‌های استاندارد؛ None یعنی فراتر از ظرفیت حداکثر (F-004)."""
        if qc_required_kvar <= 0.0:
            return []
        if qc_required_kvar < cls.PFC_STEP_OPTIONS[-1]:
            return [cls.PFC_STEP_OPTIONS[-1]]
        steps, remaining = [], qc_required_kvar
        while remaining > 0.49 and len(steps) < cls.MAX_PFC_STEPS:
            chosen = next((s for s in cls.PFC_STEP_OPTIONS if s <= remaining + 0.01), cls.PFC_STEP_OPTIONS[-1])
            steps.append(chosen)
            remaining -= chosen
        if remaining <= 0.49:
            return sorted(steps, reverse=True)
        n50 = int(math.ceil(qc_required_kvar / 50.0))
        if n50 <= cls.MAX_PFC_STEPS:
            return [50.0] * n50
        return None

    def _get_derating_factor(self, dev: CatalogDevice, internal_temp_c: float) -> float:
        # اولویت با جدول دمای دیتابیس؛ در نبود داده برای دماهای بالا، بازگشت به مشخصه دستگاه (با هشدار RULE-THERM-017)
        factor = catalog_repo.get_device_derating_factor(dev.part_number, internal_temp_c)
        if factor is not None:
            return factor
        return dev.derating_40c if internal_temp_c <= 40.0 else dev.derating_50c

    @staticmethod
    def _ip_numeric(ip_str: str) -> Optional[int]:
        digits = "".join(ch for ch in str(ip_str) if ch.isdigit())
        return int(digits[:2]) if len(digits) >= 2 else None

    @staticmethod
    def _estimate_clear_time_s(prot: CatalogDevice, ik_ka: float) -> float:
        """Approximate clearing time using the upper pickup tolerance; thermal times are never capped."""
        i_fault_a = ik_ka * 1000.0
        im_min_a, im_max_a = TripCurveRepository.instantaneous_band_a(prot.series, prot.rated_current_in_a)
        if i_fault_a >= max(im_min_a, im_max_a):
            return 0.02
        mult = i_fault_a / max(1.0, prot.rated_current_in_a)
        raw_t = TripCurveRepository.thermal_time_s(prot.series, mult)
        if raw_t is None or not math.isfinite(raw_t) or raw_t <= 0:
            return math.inf
        return float(raw_t)
    def _device_icu_ka(self, dev: CatalogDevice, project: ProjectSpec) -> Optional[float]:
        # Icu در ولتاژ واقعی پروژه از جدول قدرت قطع دیتابیس؛ در نبود داده → None (F-006)
        return catalog_repo.get_device_icu_at_voltage(dev.part_number, project.nominal_voltage_v)

    def _icu_ok(self, dev: CatalogDevice, project: ProjectSpec, ik_ka: Optional[float]) -> bool:
        # Catalog PRE-FILTER only: never reject a device merely because Ik''/Icu is unknown.
        # The strict engineering verdict lives in _icu_check() (4-state) and in ValidationResult.
        if ik_ka is None:
            return True
        icu = self._device_icu_ka(dev, project)
        if icu is None:
            return True
        return icu >= ik_ka

    def _icu_check(self, dev: CatalogDevice, project: ProjectSpec, ik_ka: Optional[float], is_preliminary: bool = False):
        icu = self._device_icu_ka(dev, project)
        return _audit_verify_icu_status(icu, ik_ka, is_preliminary)

    @staticmethod
    def _ik_from_transformer(project: ProjectSpec) -> float:
        uk = project.transformer_uk_pct / 100.0
        u_kv = project.nominal_voltage_v / 1000.0
        return round(project.voltage_factor_c_max * project.transformer_kva / (math.sqrt(3.0) * u_kv * uk) / 1000.0, 2)

    @staticmethod
    def _feeder_ik_profile(
        project: ProjectSpec,
        feeder_length_m=None,
        feeder_phase_mm2=None,
        feeder_pe_mm2=None,
    ):
        return _audit_calculate_feeder_ik_profile(
            transformer_kva=getattr(project, "transformer_kva", None),
            uk_percent=getattr(project, "transformer_uk_pct", None),
            voltage_v=getattr(project, "nominal_voltage_v", 400.0),
            feeder_length_m=feeder_length_m,
            feeder_phase_mm2=feeder_phase_mm2,
            feeder_pe_mm2=feeder_pe_mm2,
        )

    def _resolve_ik(self, project: ProjectSpec):
        if project.prospective_ik_ka is not None:
            src = tr("ik_src_explicit")
            if project.transformer_kva:
                calc = self._ik_from_transformer(project)
                src = tr("ik_src_explicit_checked", a=project.prospective_ik_ka, b=calc)
            return project.prospective_ik_ka, src, []
        if project.transformer_kva:
            calc = self._ik_from_transformer(project)
            v = ValidationResult(
                rule_id="RULE-IK-012", feeder_id="NETWORK", standard_ref="IEC 60909-0",
                status=ValidationStatus.COMPLETED, description=tr("val_ik_tr_desc"),
                supporting_evidence=tr("val_ik_tr_ev", a=project.transformer_kva, b=project.transformer_uk_pct, c=calc),
                consequence=tr("val_ik_tr_cons"), recommended_action=tr("val_no_action")
            )
            return calc, tr("ik_src_transformer", a=calc), [v]
        v = ValidationResult(
            rule_id="RULE-IK-012", feeder_id="NETWORK", standard_ref="IEC 60909-0",
            status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_ik_none_desc"),
            supporting_evidence="-", consequence=tr("val_ik_none_cons"),
            recommended_action=tr("val_ik_none_action")
        )
        return None, tr("ik_src_none"), [v]

    def _motor_contribution(self, project: ProjectSpec, feeders: List[FeederInput]) -> Tuple[float, List[str]]:
        """I''_kM = c·k_LR·I_rM به ازای هر موتور (IEC 60909-0)؛ خروجی: (مجموع kA، شرح اجزا)."""
        total_ka, parts = 0.0, []
        for f in feeders:
            k = self.MOTOR_IK_K_FACTOR.get(f.load_type)
            if k is None or k <= 0.0:
                continue
            cos_phi, eff = self._resolve_cos_phi_eff(f.load_type, f.cos_phi, f.efficiency)
            if f.phases == 3:
                ib_a = (f.power_kw * 1000.0) / (math.sqrt(3) * project.nominal_voltage_v * cos_phi * eff)
            else:
                u_ph = project.nominal_voltage_v / math.sqrt(3)
                ib_a = (f.power_kw * 1000.0) / (u_ph * cos_phi * eff)
            i_k = self.C_IK_MAX * k * ib_a / 1000.0
            total_ka += i_k
            parts.append(f"{f.feeder_id}:{k:g}xIr")
        return total_ka, parts

    def process_project(self, project: ProjectSpec, feeders: List[FeederInput]):
        ids = [f.feeder_id for f in feeders]
        if len(ids) != len(set(ids)):
            raise ValueError(tr('paste_duplicate'))
        input_hash = project.compute_input_hash(feeders)
        self.catalog = list(self._full_catalog)
        if project.preferred_manufacturer != "ANY":
            filtered = [d for d in self.catalog if d.manufacturer == project.preferred_manufacturer]
            if filtered:
                self.catalog = filtered
        ik_ka, ik_source, ik_vals = self._resolve_ik(project)

        # فاز ۱۱: مشارکت موتورها در جریان اتصال کوتاه باس (IEC 60909-0)
        mot_ka, mot_parts = self._motor_contribution(project, feeders)
        ik_total = ip_total = None
        if ik_ka is not None:
            ip_net = BusbarEngine._kappa_iec60909(ik_ka, project.source_r_x) * math.sqrt(2.0) * ik_ka
            ip_mot = self.MOTOR_IK_KAPPA * math.sqrt(2.0) * mot_ka
            ik_total = round(ik_ka + mot_ka, 3)
            ip_total = round(ip_net + ip_mot, 3)
        mot_vals: List[ValidationResult] = []
        if mot_ka > 0.0:
            if ik_ka is not None:
                mot_vals.append(ValidationResult(
                    rule_id="RULE-MOT-029", feeder_id="PANEL", standard_ref="IEC 60909-0",
                    status=ValidationStatus.COMPLETED,
                    description=tr("val_mot_029_desc", a=round(mot_ka, 3), b=ik_total),
                    supporting_evidence=tr("val_mot_029_ev", a=round(mot_ka, 3), b=", ".join(mot_parts)),
                    consequence=tr("val_mot_029_cons"), recommended_action=tr("val_no_action")))
            else:
                mot_vals.append(ValidationResult(
                    rule_id="RULE-MOT-029", feeder_id="PANEL", standard_ref="IEC 60909-0",
                    status=ValidationStatus.INSUFFICIENT_DATA,
                    description=tr("val_mot_029_noik_desc", a=round(mot_ka, 3)),
                    supporting_evidence=tr("val_mot_029_ev", a=round(mot_ka, 3), b=", ".join(mot_parts)),
                    consequence=tr("val_mot_029_cons"), recommended_action=tr("val_mot_029_action")))

        feeder_outputs, validations = [], list(ik_vals) + mot_vals
        for f in feeders:
            f_out, f_vals = self._process_single_feeder(project, f, ik_ka, ik_total)
            feeder_outputs.append(f_out)
            validations.extend(f_vals)
        summary, panel_vals = self._process_panel_summary(
            project, feeder_outputs, ik_ka, ik_source, ik_total, ip_total, mot_ka)
        validations.extend(panel_vals)
        for check in validations:
            check.application_scope = ('DBO' if '61439-3' in project.standard_ref else 'PSC') + (' / Machinery' if '60204' in project.standard_ref else '')
            if check.rule_id in {'RULE-PROT-SC-001', 'RULE-CABLE-009', 'RULE-CABLE-I2', 'RULE-PHASE-I2T', 'RULE-PE-I2T', 'RULE-ADS-TN', 'RULE-ADS-TT'}:
                check.rule_category = 'IEC_MANDATORY_CLAUSE'
            elif check.rule_id.startswith('RULE-VDROP'):
                check.rule_category = 'IEC_INFORMATIVE_ANNEX'
            elif check.rule_id in {'RULE-COORD-002', 'RULE-RCD-VFD'}:
                check.rule_category = 'OEM_MANUFACTURER_RULE'
        apply_vde_standard_refs(project, validations)
        summary.verified_input_hash = input_hash
        summary.assumptions = {'PROJECT': {name: project.model_dump(mode='json')[name]
                                          for name in project.assumed_fields}}
        for source, output in zip(feeders, feeder_outputs):
            summary.assumptions[source.feeder_id] = {
                **{name: source.model_dump(mode='json')[name] for name in source.assumed_fields},
                'resolved_defaults': output.assumptions_used}
        summary.calculation_inputs = [f.model_copy(deep=True) for f in feeders]
        summary._source_feeders = feeders
        for output in feeder_outputs:
            output.verified_input_hash = input_hash
        return feeder_outputs, summary, validations

    def _process_single_feeder(self, project: ProjectSpec, f: FeederInput, ik_ka: Optional[float],
                               ik_total_ka: Optional[float]):
        vals, assumptions = [], []
        cos_phi, eff = self._resolve_cos_phi_eff(f.load_type, f.cos_phi, f.efficiency)

        if f.load_type in (LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA, LoadType.MOTOR_SOFT_STARTER, LoadType.MOTOR_VFD):
            if f.cos_phi is None or f.efficiency is None:
                vals.append(ValidationResult(
                    rule_id="RULE-DATA-001", feeder_id=f.feeder_id, standard_ref="IEC 60034-30-1",
                    status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_data_desc"),
                    supporting_evidence=f"cos_phi={f.cos_phi}, efficiency={f.efficiency}", consequence=tr("val_data_cons"),
                    recommended_action=tr("val_data_action")
                ))
            if f.cos_phi is None: assumptions.append(f"cos_phi={cos_phi}")
            if f.efficiency is None: assumptions.append(f"efficiency={eff}")
        else:
            if f.cos_phi is None: assumptions.append(f"cos_phi={cos_phi}")

        if f.phases == 3:
            ib_a = (f.power_kw * 1000.0) / (math.sqrt(3) * project.nominal_voltage_v * cos_phi * eff)
        else:
            u_ph = project.nominal_voltage_v / math.sqrt(3)
            ib_a = (f.power_kw * 1000.0) / (u_ph * cos_phi * eff)

        p_elec_kw = (f.power_kw / eff) * f.demand_factor_kd
        tan_phi = math.tan(math.acos(min(max(cos_phi, 0.1), 1.0)))
        q_elec_kvar = p_elec_kw * tan_phi

        sel_prot, sel_cont_main, sel_cont_delta, sel_cont_star, sel_bimetal, sel_timer_yd, sel_vfd, sel_soft, sel_rcd = None, None, None, None, None, None, None, None, None
        i_delta_a, i_star_a, ctrl_holding_w, ctrl_pull_in_surge_w = None, None, 0.0, 0.0
        reason_parts = []

        if f.load_type == LoadType.MOTOR_DOL:
            mpcbs = [d for d in self.catalog if d.device_type == "MPCB" and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= ib_a and self._icu_ok(d, project, ik_total_ka)]
            mpcbs.sort(key=lambda x: x.rated_current_in_a)
            if mpcbs: sel_prot = mpcbs[0]; reason_parts.append(f"MPCB {sel_prot.part_number}")
            contactors = [d for d in self.catalog if d.device_type == "CONTACTOR" and d.rated_current_in_a >= ib_a
                          and (sel_prot is None or d.manufacturer == sel_prot.manufacturer)]
            contactors.sort(key=lambda x: x.rated_current_in_a)
            if contactors:
                sel_cont_main = contactors[0]
                ctrl_holding_w = sel_cont_main.coil_holding_24v_w
                ctrl_pull_in_surge_w = max(0.0, sel_cont_main.coil_pull_in_24v_w - sel_cont_main.coil_holding_24v_w)
                reason_parts.append(f"Contactor {sel_cont_main.part_number}")
            if sel_prot and sel_cont_main:
                coord_ok = sel_cont_main.rated_current_in_a >= ib_a and self._icu_ok(sel_prot, project, ik_total_ka)
                vals.append(ValidationResult(
                    rule_id="RULE-COORD-002", feeder_id=f.feeder_id, standard_ref="IEC 60947-4-1",
                    status=ValidationStatus.WARNING if coord_ok else ValidationStatus.ERROR,
                    description=tr("val_coord_desc"),
                    supporting_evidence=tr("val_coord_ev", a=sel_prot.part_number, b=sel_cont_main.part_number, c=round(ib_a, 1)),
                    consequence=tr("val_coord_cons"),
                    recommended_action=tr("audit_review")
                ))

        elif f.load_type == LoadType.MOTOR_STAR_DELTA:
            i_delta_a = round(ib_a / math.sqrt(3), 2)
            i_star_a = round(ib_a / 3.0, 2)
            prot_cands = [d for d in self.catalog if d.device_type in ("MPCB", "MCCB") and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= ib_a and self._icu_ok(d, project, ik_total_ka)]
            prot_cands.sort(key=lambda x: (0 if x.device_type == "MPCB" else 1, x.rated_current_in_a))
            if prot_cands: sel_prot = prot_cands[0]; reason_parts.append(f"Line Prot: {sel_prot.part_number}")
            delta_conts = [d for d in self.catalog if d.device_type == "CONTACTOR" and d.rated_current_in_a >= i_delta_a
                           and (sel_prot is None or d.manufacturer == sel_prot.manufacturer)]
            delta_conts.sort(key=lambda x: x.rated_current_in_a)
            if delta_conts: sel_cont_main = delta_conts[0]; sel_cont_delta = delta_conts[0]; reason_parts.append(f"KM & KD: {sel_cont_main.part_number}")
            star_conts = [d for d in self.catalog if d.device_type == "CONTACTOR" and d.rated_current_in_a >= i_star_a
                          and (sel_prot is None or d.manufacturer == sel_prot.manufacturer)]
            star_conts.sort(key=lambda x: x.rated_current_in_a)
            if star_conts: sel_cont_star = star_conts[0]; reason_parts.append(f"KY: {sel_cont_star.part_number}")
            bimetals = [d for d in self.catalog if d.device_type == "BIMETAL" and d.setting_min_a <= i_delta_a <= d.setting_max_a
                        and (sel_prot is None or d.manufacturer == sel_prot.manufacturer)]
            bimetals.sort(key=lambda x: x.setting_max_a)
            if bimetals: sel_bimetal = bimetals[0]; reason_parts.append(f"Bimetal: {sel_bimetal.part_number}")
            timers = [d for d in self.catalog if d.device_type == "TIMER_YD"]
            if timers: sel_timer_yd = timers[0]
            if sel_cont_main and sel_cont_delta:
                ctrl_holding_w += sel_cont_main.coil_holding_24v_w + sel_cont_delta.coil_holding_24v_w
                ctrl_pull_in_surge_w = max(0.0, sel_cont_delta.coil_pull_in_24v_w - sel_cont_delta.coil_holding_24v_w)
            if sel_timer_yd: ctrl_holding_w += sel_timer_yd.coil_holding_24v_w

            vals.append(ValidationResult(
                rule_id="RULE-MOT-YD-008", feeder_id=f.feeder_id, standard_ref="IEC 60947-4-1",
                status=ValidationStatus.COMPLETED if (sel_cont_main and sel_cont_star and sel_bimetal) else ValidationStatus.ERROR,
                description=tr("val_yd_desc"), supporting_evidence=tr("val_yd_ev", a=i_delta_a, b=i_star_a),
                consequence=tr("val_yd_cons"), recommended_action=tr("val_yd_action")
            ))
            if sel_cont_delta and sel_bimetal:
                coord_ok = sel_cont_delta.rated_current_in_a >= i_delta_a and sel_bimetal.setting_max_a >= i_delta_a
                vals.append(ValidationResult(
                    rule_id="RULE-COORD-002", feeder_id=f.feeder_id, standard_ref="IEC 60947-4-1",
                    status=ValidationStatus.WARNING if coord_ok else ValidationStatus.ERROR,
                    description=tr("val_coord_desc"),
                    supporting_evidence=tr("val_coord_ev", a=sel_bimetal.part_number, b=sel_cont_delta.part_number, c=i_delta_a),
                    consequence=tr("val_coord_cons"),
                    recommended_action=tr("audit_review")
                ))

        elif f.load_type == LoadType.MOTOR_SOFT_STARTER:
            softs = [d for d in self.catalog if d.device_type == "SOFT_STARTER" and d.rated_current_in_a >= ib_a and d.motor_kw_400v >= f.power_kw]
            softs.sort(key=lambda x: x.rated_current_in_a)
            if softs:
                sel_soft = softs[0]
                ctrl_holding_w += sel_soft.coil_holding_24v_w
                reason_parts.append(f"Soft Starter {sel_soft.part_number}")
            mccbs = [d for d in self.catalog if d.device_type == "MCCB" and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= ib_a and self._icu_ok(d, project, ik_total_ka)]
            mccbs.sort(key=lambda x: x.rated_current_in_a)
            if mccbs: sel_prot = mccbs[0]

        elif f.load_type == LoadType.MOTOR_VFD:
            vfds = [d for d in self.catalog if d.device_type == "VFD" and d.motor_kw_400v >= f.power_kw]
            vfds.sort(key=lambda x: x.motor_kw_400v)
            if vfds: sel_vfd = vfds[0]; reason_parts.append(f"VFD {sel_vfd.part_number}")
            mccbs = [d for d in self.catalog if d.device_type == "MCCB" and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= (ib_a * 1.25) and self._icu_ok(d, project, ik_total_ka)]
            mccbs.sort(key=lambda x: x.rated_current_in_a)
            if mccbs: sel_prot = mccbs[0]
            ctrl_holding_w = 3.5
        else:
            candidates = [d for d in self.catalog if d.device_type in ("MCB", "MCCB") and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= ib_a and self._icu_ok(d, project, ik_total_ka)]
            candidates.sort(key=lambda x: (
                x.rated_current_in_a,
                x.icu_ka_400v if x.icu_ka_400v is not None else 0.0,
            ))
            if candidates: sel_prot = candidates[0]; reason_parts.append(f"{sel_prot.device_type} {sel_prot.part_number}")
            if f.has_socket_outlets:
                rcds = [d for d in self.catalog if d.device_type == "RCD" and d.rated_current_in_a >= ib_a]
                if rcds: sel_rcd = rcds[0]

        cable_len_m = f.cable_length_m if f.cable_length_m is not None else 25.0
        if f.cable_length_m is None:
            assumptions.append("ASSUMED_DEFAULT: cable_length_m=25")
        max_vd = 3.0 if f.load_type == LoadType.LIGHTING_SOCKET else 5.0
        prot_in = sel_prot.rated_current_in_a if sel_prot else ib_a * 1.25
        is_adj_prot = (sel_prot.device_type in ("MPCB", "MCCB")) if sel_prot else True

        # F-005: جریان خطای واقعی پروژه و زمان قطع حفاظ (به‌جای فرض ثابت ۱۰ kA / ۲۰ ms)
        # فاز ۱۱: جریان کل باس شامل مشارکت موتورها (خطای داخل شاخه فیدر از همه منابع تغذیه می‌شود)
        fault_ka = ik_total_ka
        clear_t = self._estimate_clear_time_s(sel_prot, fault_ka) if (sel_prot and fault_ka is not None) else None
        protection_icu_ka = self._device_icu_ka(sel_prot, project) if sel_prot is not None else None
        i2_factor = (sel_prot.overload_i2_factor or
                     {"MCB": 1.45, "MCCB": 1.3, "MPCB": 1.3, "FUSE_GG": 1.6}.get(sel_prot.device_type)
                     if sel_prot else None)

        s_ph, s_neutral, s_pe, iz_derated, v_drop_pct, cable_desig = CableSizingEngine.select_feeder_cable(
            ib_a=ib_a, protection_in_a=prot_in, is_adjustable_prot=is_adj_prot, length_m=cable_len_m,
            cos_phi=cos_phi, voltage_v=project.nominal_voltage_v, phases=f.phases, ambient_temp_c=project.ambient_temp_c,
            grouping_k2=project.cable_grouping_factor_k2, max_vdrop_pct=max_vd, load_type=f.load_type,
            user_specified_mm2=f.cable_section_mm2, conductor=f.conductor_material.value,
            insulation=f.insulation.value, installation_method=f.installation_method.value,
            fire_resistant=f.fire_resistant, thdi_pct=f.thdi_pct,
            fault_current_ka=fault_ka, clear_time_s=clear_t, overload_i2_factor=i2_factor,
            additional_check=lambda phase, pe: self._candidate_fault_compatible(
                project, f, sel_prot, phase, pe, ik_ka, ik_total_ka, clear_t)
        )

        # F-008: ضرایب تصحیح دقیق و روش نصب مرجع برای گزارش
        k1_f, k2_f, ktotal_f = CableSizingEngine.get_derating_summary(
            project.ambient_temp_c, project.cable_grouping_factor_k2,
            f.conductor_material.value, f.insulation.value, f.installation_method.value
        )
        method_ref_str = (f"Verlegungsart {f.installation_method.value} (DIN VDE 0298-4)" if ("is_vde_project" in globals() and is_vde_project(project)) else tr("cable_method_ref", a=f.installation_method.value))

        # F-005: نمایش فرمول آدیاباتیک مبنای انتخاب PE در گزارش
        i_pe_ka = fault_ka
        k_pe, _ = select_pe_k_factor("Cu" if f.conductor_material.value == "CU" else "Al", f.insulation.value, "in_cable")
        s_adiabatic = None
        if (fault_ka is not None and math.isfinite(fault_ka)
                and _is_valid_clear_time(clear_t) and clear_t <= 5):
            s_adiabatic = (fault_ka * 1000.0 * math.sqrt(clear_t)) / k_pe
        if s_adiabatic is None:
            pe_basis_str = _FAULT_BASIS_UNAVAILABLE.get(i18n.get_language(), _FAULT_BASIS_UNAVAILABLE["en"])
        else:
            pe_basis_str = tr("pe_adia_basis", a=fault_ka, b=clear_t, c=round(i_pe_ka, 1),
                              d=round(s_adiabatic, 1), e=(f"{s_pe:g}" if s_pe is not None else "?"), k=k_pe)

        profile = audit_calculate_network_ik_profile(
            project.transformer_kva, project.transformer_uk_pct, project.nominal_voltage_v,
            feeder_cable_length_m=cable_len_m, feeder_phase_mm2=s_ph, feeder_pe_mm2=s_pe,
            source_ik_ka=ik_total_ka if ik_total_ka is not None else ik_ka,
            source_min_ik_ka=ik_ka, source_r_x=project.source_r_x,
            voltage_factor_c_max=project.voltage_factor_c_max, voltage_factor_c_min=project.voltage_factor_c_min,
            conductor=f.conductor_material.value, insulation=f.insulation.value)
        vals.extend(self._verify_feeder_safety(project, f, sel_prot, profile, s_ph, s_pe,
                                              iz_derated, prot_in, i2_factor, clear_t, ik_total_ka))

        req_iz_ref = ib_a if is_adj_prot else prot_in
        if iz_derated is None:
            vals.append(ValidationResult(rule_id="RULE-CABLE-010", feeder_id=f.feeder_id, standard_ref="IEC 60364-5-52",
                status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_cable_nontable_desc", a=f"{s_ph:g}"),
                supporting_evidence=tr("val_cable_nontable_ev", a=f"{s_ph:g}"), consequence=tr("val_cable_nontable_cons"),
                recommended_action=tr("val_cable_nontable_action")))
        elif iz_derated >= req_iz_ref:
            vals.append(ValidationResult(rule_id="RULE-CABLE-009", feeder_id=f.feeder_id, standard_ref="IEC 60364-5-52", status=ValidationStatus.COMPLETED, description=tr("val_cable_ok_desc"), supporting_evidence=tr("val_cable_ok_ev", a=iz_derated, b=f"{req_iz_ref:.1f}"), consequence=tr("val_cable_ok_cons"), recommended_action=tr("val_no_action")))
        else:
            vals.append(ValidationResult(rule_id="RULE-CABLE-009", feeder_id=f.feeder_id, standard_ref="IEC 60364-4-43", status=ValidationStatus.ERROR, description=tr("val_cable_err_desc"), supporting_evidence=tr("val_cable_err_ev", a=iz_derated, b=f"{req_iz_ref:.1f}"), consequence=tr("val_cable_err_cons"), recommended_action=tr("val_cable_err_action")))

        if s_pe is None:
            vals.append(ValidationResult(rule_id="RULE-PE-006", feeder_id=f.feeder_id, standard_ref="IEC 60364-5-54",
                status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_pe_nostd_desc", a=f"{s_ph:g}"),
                supporting_evidence=tr("val_pe_nostd_ev", a=f"{s_ph:g}"), consequence=tr("val_pe_nostd_cons"),
                recommended_action=tr("val_pe_nostd_action")))

        if fault_ka is None or not _is_valid_clear_time(clear_t):
            vals.append(ValidationResult(
                rule_id="RULE-FAULT-NOIK-FALLBACK-001", feeder_id=f.feeder_id,
                standard_ref="IEC 60909-0 / IEC 60364-5-54",
                status=ValidationStatus.INSUFFICIENT_DATA,
                description=_FAULT_BASIS_UNAVAILABLE.get(i18n.get_language(), _FAULT_BASIS_UNAVAILABLE["en"]),
                supporting_evidence=f"Ik_total={fault_ka if fault_ka is not None else '?'} kA; t_clear={clear_t if clear_t is not None else '?'} s",
                consequence=tr("val_pe_nostd_cons"), recommended_action=tr("val_pe_nostd_action"),
            ))

        vals.append(ValidationResult(rule_id="RULE-VDROP-003", feeder_id=f.feeder_id, standard_ref="IEC 60364-5-52", status=ValidationStatus.COMPLETED if v_drop_pct <= max_vd else ValidationStatus.ERROR, description=tr("val_vdrop_desc", max=max_vd), supporting_evidence=tr("val_vdrop_ev", pct=v_drop_pct), consequence=tr("val_vdrop_cons"), recommended_action=tr("val_no_action")))

        if sel_prot is not None:
            icu_ka = protection_icu_ka
            if ik_total_ka is None:
                vals.append(ValidationResult(rule_id="RULE-PROT-SC-001", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_sc_noik_desc"), supporting_evidence=f"Icu={'?' if icu_ka is None else icu_ka}kA, Ik=? kA", consequence=tr("val_sc_noik_cons"), recommended_action=tr("val_sc_noik_action")))
            elif icu_ka is None:
                vals.append(ValidationResult(rule_id="RULE-PROT-SC-001", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_sc_noicu_desc", a=sel_prot.part_number, b=project.nominal_voltage_v), supporting_evidence=tr("val_sc_noicu_ev", a=sel_prot.part_number, b=project.nominal_voltage_v), consequence=tr("val_sc_noicu_cons"), recommended_action=tr("val_sc_noicu_action")))
            elif icu_ka >= ik_total_ka:
                vals.append(ValidationResult(rule_id="RULE-PROT-SC-001", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.COMPLETED, description=tr("val_sc_ok_desc"), supporting_evidence=tr("val_sc_ok_ev", a=icu_ka, b=ik_total_ka), consequence=tr("val_sc_ok_cons"), recommended_action=tr("val_no_action")))
            else:
                vals.append(ValidationResult(rule_id="RULE-PROT-SC-001", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.ERROR, description=tr("val_sc_err_desc"), supporting_evidence=tr("val_sc_err_ev", a=icu_ka, b=ik_total_ka), consequence=tr("val_sc_err_cons"), recommended_action=tr("val_sc_err_action")))

        if f.thdi_pct is not None and f.thdi_pct > 0.0:
            if f.thdi_pct >= 33.0:
                vals.append(ValidationResult(rule_id="RULE-HARM-011", feeder_id=f.feeder_id, standard_ref="IEC 60364-5-52",
                    status=ValidationStatus.WARNING, description=tr("val_harm_desc", a=f.thdi_pct),
                    supporting_evidence=tr("val_harm_ev", a=f.thdi_pct), consequence=tr("val_harm_cons"),
                    recommended_action=tr("val_harm_action")))
            if f.thdi_pct > 50.0:
                harm_ref = "IEC 61000-3-12" if ib_a <= 75.0 else "IEEE 519"
                vals.append(ValidationResult(rule_id="RULE-HARM-012", feeder_id=f.feeder_id, standard_ref=harm_ref,
                    status=ValidationStatus.WARNING, description=tr("val_harm_mit_desc", a=f.thdi_pct),
                    supporting_evidence=f"THDi={f.thdi_pct}%", consequence=tr("val_harm_mit_cons"),
                    recommended_action=tr("val_harm_mit_action")))

        if f.fire_pump_service:
            vals.append(ValidationResult(rule_id="RULE-SCEN-FP-020", feeder_id=f.feeder_id, standard_ref="NFPA 20",
                status=ValidationStatus.WARNING, description=tr("val_fp_desc"),
                supporting_evidence=tr("val_fp_ev", a=round(ib_a, 1)), consequence=tr("val_fp_cons"),
                recommended_action=tr("val_fp_action")))

        starting_kva = 0.0
        starting_dip_pct = None
        if f.load_type in self.START_K_FACTOR:
            starting_kva = round(math.sqrt(3.0) * project.nominal_voltage_v * ib_a * self.START_K_FACTOR[f.load_type] / 1000.0, 1)
            if f.locked_rotor_current_a is not None:
                voltage_factor = math.sqrt(3.0) * project.nominal_voltage_v if f.phases == 3 else project.nominal_voltage_v / math.sqrt(3.0)
                starting_kva = round(voltage_factor * f.locked_rotor_current_a / 1000.0, 1)
            if ik_ka is not None:
                s_sc_kva = math.sqrt(3.0) * project.nominal_voltage_v * ik_ka
                starting_dip_pct = round(starting_kva / (starting_kva + s_sc_kva) * 100.0, 1)

        total_loss_w = 0.0
        if sel_prot: total_loss_w += sel_prot.power_loss_w * min(1.0, ib_a / max(1.0, sel_prot.rated_current_in_a)) ** 2
        if sel_cont_main: total_loss_w += sel_cont_main.power_loss_w
        if sel_cont_delta: total_loss_w += sel_cont_delta.power_loss_w
        if sel_bimetal: total_loss_w += sel_bimetal.power_loss_w
        if sel_timer_yd: total_loss_w += sel_timer_yd.power_loss_w
        if sel_vfd: total_loss_w += sel_vfd.power_loss_w
        if sel_soft: total_loss_w += sel_soft.power_loss_w * min(1.0, ib_a / max(1.0, sel_soft.rated_current_in_a))
        if sel_rcd: total_loss_w += sel_rcd.power_loss_w

        sug_parts = []
        if sel_prot is None:
            sug_parts.append(tr("sug_prot", a=round(ib_a * 1.25, 1), b=(ik_ka if ik_ka is not None else "?")))
        if f.load_type == LoadType.MOTOR_DOL and sel_cont_main is None:
            sug_parts.append(tr("sug_contactor", a=round(ib_a, 1)))
        if f.load_type == LoadType.MOTOR_STAR_DELTA:
            if sel_cont_main is None: sug_parts.append(tr("sug_contactor", a=(i_delta_a or ib_a)))
            if sel_bimetal is None: sug_parts.append(tr("sug_bimetal", a=(i_delta_a or ib_a)))
            if sel_timer_yd is None: sug_parts.append(tr("sug_timer"))
        if f.load_type == LoadType.MOTOR_VFD and sel_vfd is None:
            sug_parts.append(tr("sug_vfd", a=f.power_kw))
        if f.load_type == LoadType.MOTOR_SOFT_STARTER and sel_soft is None:
            sug_parts.append(tr("sug_soft", a=round(ib_a, 1), b=f.power_kw))
        if f.has_socket_outlets and sel_rcd is None:
            sug_parts.append(tr("sug_rcd", a=round(ib_a, 1)))

        k_derate_ref = self._get_derating_factor(sel_prot, project.max_internal_temp_c) if sel_prot else 0.90
        out = FeederCalcOutput(
            phases=f.phases, supply_phase=f.supply_phase,
            feeder_id=f.feeder_id, func_tag=f.func_tag, loc_tag=f.loc_tag, description=f.description, load_type=f.load_type,
            power_kw=f.power_kw, active_power_demand_kw=round(p_elec_kw, 2), reactive_power_demand_kvar=round(q_elec_kvar, 2),
            design_current_ib_a=round(ib_a, 2), delta_loop_current_a=i_delta_a, star_current_a=i_star_a,
            required_in_after_derating_a=round(ib_a / k_derate_ref, 2), cable_length_m=cable_len_m,
            selected_phase_mm2=s_ph, selected_pe_mm2=s_pe, cable_derated_iz_a=iz_derated, cable_Auto_sized=(f.cable_section_mm2 is None),
            cable_designation_str=cable_desig,
            conductor_material=f.conductor_material.value if f.conductor_material else None,
            insulation_type=f.insulation.value if f.insulation else None,
            cable_temp_factor_k1=k1_f, cable_grouping_factor_k2=k2_f,
            cable_total_derating_k=ktotal_f, cable_method_ref_str=method_ref_str, pe_basis_str=pe_basis_str,
            ik_end_min_ka=profile.ik_feeder_end_min_1p_ka, ik_end_max_ka=profile.ik_feeder_end_max_3p_ka,
            clearing_time_s=clear_t if _is_valid_clear_time(clear_t) else None,
            protection_icu_ka=protection_icu_ka, voltage_drop_percent=v_drop_pct, assumptions_used=assumptions,
            selected_protection=sel_prot, selected_contactor_main=sel_cont_main, selected_contactor_delta=sel_cont_delta,
            selected_contactor_star=sel_cont_star, selected_bimetal=sel_bimetal, selected_timer_yd=sel_timer_yd,
            selected_vfd=sel_vfd, selected_soft_starter=sel_soft, selected_rcd=sel_rcd,
            ctrl_24v_holding_w=round(ctrl_holding_w, 1),
            ctrl_24v_pull_in_surge_w=round(ctrl_pull_in_surge_w, 1), total_feeder_loss_w=round(total_loss_w, 1),
            selection_reason=" | ".join(reason_parts), suggested_spec_str=" | ".join(sug_parts),
            starting_kva=starting_kva, starting_dip_pct=starting_dip_pct, fire_pump_service=f.fire_pump_service,
            locked_rotor_current_a=f.locked_rotor_current_a,
            thdi_pct=f.thdi_pct, fire_resistant=f.fire_resistant
        )
        return out, vals

    @staticmethod
    def _tn_disconnection_limit_s(project, feeder, rated_current_a):
        u0 = project.nominal_voltage_v / math.sqrt(3)
        final_limit = 0.8 if u0 <= 120 else (0.4 if u0 <= 230.95 else (0.2 if u0 <= 400 else 0.1))
        return final_limit if feeder.load_type != LoadType.SUB_FEEDER and rated_current_a <= 32 else 5.0

    def _candidate_fault_compatible(self, project, feeder, protection, phase, pe, source_ik, total_ik, clear_s):
        if (protection is None or source_ik is None or clear_s is None
                or not math.isfinite(clear_s) or not 0 < clear_s <= 5):
            return False
        if pe is None or not 0 < clear_s <= 5:
            return False
        profile = audit_calculate_network_ik_profile(
            project.transformer_kva, project.transformer_uk_pct, project.nominal_voltage_v,
            feeder_cable_length_m=feeder.cable_length_m or 25, feeder_phase_mm2=phase, feeder_pe_mm2=pe,
            source_ik_ka=total_ik or source_ik, source_min_ik_ka=source_ik, source_r_x=project.source_r_x,
            voltage_factor_c_max=project.voltage_factor_c_max, voltage_factor_c_min=project.voltage_factor_c_min,
            conductor=feeder.conductor_material.value, insulation=feeder.insulation.value)
        if profile.ik_feeder_end_min_1p_ka is None:
            return True
        end_s = self._estimate_clear_time_s(protection, profile.ik_feeder_end_min_1p_ka)
        if not 0 < end_s <= 5:
            return False
        if project.earthing_system.value.startswith('TN') and end_s > self._tn_disconnection_limit_s(project, feeder, protection.rated_current_in_a):
            return False
        k, _ = select_pe_k_factor('Cu' if feeder.conductor_material.value == 'CU' else 'Al', feeder.insulation.value, 'in_cable')
        energy = max(((total_ik or source_ik)*1000)**2 * clear_s,
                     (profile.ik_feeder_end_min_1p_ka*1000)**2 * end_s)
        return energy <= min((k*phase)**2, (k*pe)**2)

    def _verify_feeder_safety(self, project, f, protection, profile, phase_mm2, pe_mm2,
                              iz_a, in_a, i2_factor, clear_s, bus_ik_ka):
        checks = []

        def add(rule, key, status, evidence, standard="IEC 60364-4-43"):
            checks.append(ValidationResult(
                rule_id=rule, feeder_id=f.feeder_id, standard_ref=standard, status=status,
                description=tr("audit_" + key), supporting_evidence=evidence,
                consequence=tr("audit_preliminary"), recommended_action=tr("audit_review")))

        if protection is None:
            add("RULE-PROT-SC-001", "catalog_failed", ValidationStatus.ERROR,
                "CATALOG_MATCH_FAILED: no protective device satisfies current and available breaking capacity", "IEC 60947-2")

        add("RULE-FAULT-END", "fault_end", ValidationStatus.WARNING if profile.ik_feeder_end_min_1p_ka else ValidationStatus.INSUFFICIENT_DATA,
            f"Ik_min={profile.ik_feeder_end_min_1p_ka} kA; Ik_max={profile.ik_feeder_end_max_3p_ka} kA; {profile.scope_warning_note}", "IEC 60909-0")
        if project.earthing_system.value.startswith("TN") and protection and profile.ik_feeder_end_min_1p_ka:
            end_s = self._estimate_clear_time_s(protection, profile.ik_feeder_end_min_1p_ka)
            limit_s = self._tn_disconnection_limit_s(project, f, in_a)
            add("RULE-ADS-TN", "ads", ValidationStatus.ERROR if end_s > limit_s else ValidationStatus.WARNING,
                f"t_est={end_s:g} s; limit={limit_s:g} s; approximate curve; source sequence impedances require verification", "IEC 60364-4-41")
        elif project.earthing_system.value.startswith("TN"):
            add("RULE-ADS-TN", "ads", ValidationStatus.INSUFFICIENT_DATA, "No protection or end-of-line fault current", "IEC 60364-4-41")
        if project.earthing_system.value == "TT":
            if f.rcd_type is None or f.rcd_sensitivity_ma is None or f.earth_resistance_ohm is None:
                status, evidence = ValidationStatus.INSUFFICIENT_DATA, "RCD type, sensitivity and earth-electrode resistance required"
            else:
                touch_v = f.rcd_sensitivity_ma / 1000 * f.earth_resistance_ohm
                status = ValidationStatus.ERROR if touch_v > 50 else ValidationStatus.WARNING
                evidence = f"RA * I_delta_n={touch_v:g} V; limit=50 V; verify RCD disconnection time"
            add("RULE-ADS-TT", "tt", status, evidence, "IEC 60364-4-41")
        if f.load_type == LoadType.MOTOR_VFD and f.rcd_type is not None:
            add("RULE-RCD-VFD", "vfd_rcd", ValidationStatus.ERROR if f.rcd_type in ("AC", "A") else ValidationStatus.WARNING,
                f"RCD={f.rcd_type}; drive manufacturer's residual-current protection requirements apply", "IEC 60364-5-53")
        if protection and iz_a is not None and i2_factor is not None:
            i2 = i2_factor * in_a
            add("RULE-CABLE-I2", "i2", ValidationStatus.ERROR if i2 > 1.45 * iz_a else ValidationStatus.WARNING,
                f"I2={i2:g} A; 1.45*Iz={1.45 * iz_a:g} A; verify actual protective setting and product standard")
        material = "Cu" if f.conductor_material.value == "CU" else "Al"
        k, _ = select_pe_k_factor(material, f.insulation.value, "in_cable")
        energies = []
        if bus_ik_ka is not None and protection and math.isfinite(clear_s) and 0 < clear_s <= 5:
            energies.append((bus_ik_ka * 1000) ** 2 * clear_s)
            if profile.ik_feeder_end_min_1p_ka:
                end_s = self._estimate_clear_time_s(protection, profile.ik_feeder_end_min_1p_ka)
                if 0 < end_s <= 5:
                    energies.append((profile.ik_feeder_end_min_1p_ka * 1000) ** 2 * end_s)
                else:
                    energies = []
        for section, rule, key in ((phase_mm2, "RULE-PHASE-I2T", "phase_i2t"), (pe_mm2, "RULE-PE-I2T", "pe_i2t")):
            if not energies or section is None:
                status, evidence = ValidationStatus.INSUFFICIENT_DATA, "Fault current, valid clearing time <=5 s and conductor section required"
            else:
                energy, withstand = max(energies), (k * section) ** 2
                status = ValidationStatus.ERROR if energy > withstand else ValidationStatus.WARNING
                evidence = f"max(I^2*t)={energy:g} A^2s; (k*S)^2={withstand:g} A^2s; k={k}; estimated curve"
            add(rule, key, status, evidence, "IEC 60364-5-54" if key == "pe_i2t" else "IEC 60364-4-43")
        return checks

    def _process_panel_summary(self, project: ProjectSpec, feeders: List[FeederCalcOutput],
                               ik_ka: Optional[float], ik_source: str,
                               ik_total_ka: Optional[float] = None,
                               ip_total_ka: Optional[float] = None,
                               mot_ka: float = 0.0):
        vals = []
        sum_p = sum(f.active_power_demand_kw for f in feeders)
        sum_q = sum(f.reactive_power_demand_kvar for f in feeders)
        s_raw = math.sqrt(sum_p**2 + sum_q**2)
        overall_cos_phi = round(sum_p / s_raw, 2) if s_raw > 0 else 1.0

        s_design_kva = s_raw * project.simultaneity_factor_ks * (1.0 + project.spare_factor)
        i_design_main_a = (s_design_kva * 1000.0) / (math.sqrt(3) * project.nominal_voltage_v)
        phase_power = {phase: 0j for phase in ('L1', 'L2', 'L3')}
        unassigned_power = 0j
        for feeder in feeders:
            power = complex(feeder.active_power_demand_kw, feeder.reactive_power_demand_kvar)
            if feeder.phases == 3:
                for phase in phase_power:
                    phase_power[phase] += power / 3
            elif feeder.supply_phase is not None:
                phase_power[feeder.supply_phase] += power
            else:
                unassigned_power += power
        if unassigned_power:
            worst_phase = max(phase_power, key=lambda phase: abs(phase_power[phase] + unassigned_power))
            phase_power[worst_phase] += unassigned_power
        u_ln = project.nominal_voltage_v / math.sqrt(3)
        demand_margin = project.simultaneity_factor_ks * (1 + project.spare_factor)
        phase_currents = {phase: abs(power) * 1000 / u_ln * demand_margin for phase, power in phase_power.items()}
        i_design_main_a = max(phase_currents.values(), default=i_design_main_a)
        neutral_a = abs(sum(power.conjugate() * cmath.exp(1j * angle) for power, angle in
                           zip(phase_power.values(), (0, -2*math.pi/3, 2*math.pi/3)))) * 1000 / u_ln * demand_margin
        average_a = sum(phase_currents.values()) / 3
        imbalance = max((abs(current - average_a) for current in phase_currents.values()), default=0) / average_a * 100 if average_a else 0
        if unassigned_power or imbalance > 10:
            vals.append(ValidationResult(rule_id='RULE-PHASE-BALANCE', feeder_id='PANEL',
                standard_ref='Engineering phase allocation',
                status=ValidationStatus.INSUFFICIENT_DATA if unassigned_power else ValidationStatus.WARNING,
                description=tr('audit_phase_balance'),
                supporting_evidence=f'{phase_currents}; IN={neutral_a:.2f} A; imbalance={imbalance:.1f}%; '
                                    + ('unassigned single-phase loads placed on worst phase; ' if unassigned_power else '')
                                    + 'fundamental sinusoidal model; harmonic neutral currents require separate verification',
                consequence=tr('audit_preliminary'), recommended_action=tr('audit_phase_action')))
        sum_ib = sum(f.design_current_ib_a for f in feeders)

        i_main_req_a = i_design_main_a

        # ---------- Phase 4: panel harmonics + capacitor bank ----------
        has_thdi_data = any(f.thdi_pct is not None for f in feeders)
        thdi_pairs = [(f.design_current_ib_a, (f.thdi_pct or 0.0)) for f in feeders]
        total_weight = sum(w for w, _ in thdi_pairs)
        panel_thdi = round(sum(w * t for w, t in thdi_pairs) / total_weight, 1) if (total_weight > 0 and has_thdi_data) else None
        # F-012: مرجع تجمیعی هارمونیک تابلو بر اساس جریان کل (نه IEC 61000-3-2 مخصوص تجهیزات <= 16A)
        harm_ref = "IEC 61000-3-12" if i_design_main_a <= 75.0 else "IEEE 519"
        if not has_thdi_data:
            vals.append(ValidationResult(rule_id="RULE-HARM-013", feeder_id="PANEL", standard_ref=harm_ref,
                status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_harm_panel_none_desc"),
                supporting_evidence="-", consequence=tr("val_harm_panel_none_cons"),
                recommended_action=tr("val_harm_panel_none_action")))
        else:
            thdi_status = ValidationStatus.WARNING if panel_thdi >= 20.0 else ValidationStatus.COMPLETED
            vals.append(ValidationResult(rule_id="RULE-HARM-013", feeder_id="PANEL", standard_ref=harm_ref,
                status=thdi_status, description=tr("val_harm_panel_desc", a=panel_thdi),
                supporting_evidence=tr("val_harm_panel_ev", a=panel_thdi), consequence=tr("val_harm_panel_cons"),
                recommended_action=tr("val_no_action" if thdi_status == ValidationStatus.COMPLETED else "val_harm_panel_action")))

        detuned_pct = 14.0 if (panel_thdi is not None and panel_thdi >= 20.0) else (7.0 if (panel_thdi is not None and panel_thdi >= 10.0) else 0.0)

        target_cos_phi = 0.95
        cap_steps, cap_suggested = [], ""
        if overall_cos_phi < target_cos_phi and sum_p > 0.0:
            tan_cur = math.tan(math.acos(min(max(overall_cos_phi, 0.1), 1.0)))
            tan_tgt = math.tan(math.acos(target_cos_phi))
            qc_required = sum_p * (tan_cur - tan_tgt)
            cap_steps = self._pick_cap_steps(qc_required)
            if cap_steps is None:
                vals.append(ValidationResult(rule_id="RULE-CAP-015", feeder_id="PANEL", standard_ref="IEC 60831-1",
                    status=ValidationStatus.INSUFFICIENT_DATA,
                    description=tr("val_cap_oob_desc", a=round(qc_required, 1), b=self._max_pfc_kvar()),
                    supporting_evidence=tr("val_cap_req_ev", a=overall_cos_phi, b=target_cos_phi, c=round(qc_required, 1)),
                    consequence=tr("val_cap_oob_cons"), recommended_action=tr("val_cap_oob_action")))
                cap_steps = []
            else:
                vals.append(ValidationResult(rule_id="RULE-CAP-015", feeder_id="PANEL", standard_ref="IEC 60831-1",
                    status=ValidationStatus.COMPLETED, description=tr("val_cap_req_desc", a=round(qc_required, 1), b=round(sum(cap_steps), 1)),
                    supporting_evidence=tr("val_cap_req_ev", a=overall_cos_phi, b=target_cos_phi, c=round(qc_required, 1)),
                    consequence=tr("val_cap_req_cons"), recommended_action=tr("val_no_action")))
        elif sum_p > 0.0:
            vals.append(ValidationResult(rule_id="RULE-CAP-015", feeder_id="PANEL", standard_ref="IEC 60831-1",
                status=ValidationStatus.COMPLETED, description=tr("val_cap_notneeded_desc", a=overall_cos_phi),
                supporting_evidence=tr("val_cap_notneeded_ev", a=target_cos_phi), consequence=tr("val_cap_notneeded_cons"),
                recommended_action=tr("val_no_action")))

        qc_installed = sum(cap_steps)
        cap_contactor, cap_prot, cap_reactor_dev, cap_module_dev, res_order = None, None, None, None, None
        if qc_installed > 0.0:
            if detuned_pct > 0.0:
                vals.append(ValidationResult(rule_id="RULE-HARM-014", feeder_id="PANEL", standard_ref="IEC 61642",
                    status=ValidationStatus.COMPLETED, description=tr("val_detuned_desc", a=detuned_pct),
                    supporting_evidence=tr("val_detuned_ev", a=detuned_pct, hz=(189.0 if detuned_pct == 7.0 else 134.0)),
                    consequence=tr("val_detuned_cons"), recommended_action=tr("val_no_action")))
            cont_cands = [d for d in self.catalog if d.device_type == "CAP_CONTACTOR" and d.cap_kvar_400v >= max(cap_steps)]
            cont_cands.sort(key=lambda x: x.cap_kvar_400v)
            cap_contactor = cont_cands[0] if cont_cands else None
            if detuned_pct > 0.0:
                react_cands = [d for d in self.catalog if d.device_type == "DETUNED_REACTOR" and d.detuned_pct == detuned_pct]
                cap_reactor_dev = react_cands[0] if react_cands else None
            mod_cands = [d for d in self.catalog if d.device_type == "CAP_MODULE" and d.cap_kvar_400v >= max(cap_steps)]
            mod_cands.sort(key=lambda x: x.cap_kvar_400v)
            cap_module_dev = mod_cands[0] if mod_cands else None
            ic_cap_a = (qc_installed * 1000.0) / (math.sqrt(3) * project.nominal_voltage_v * (1.0 - detuned_pct / 100.0)) if detuned_pct < 100.0 else 0.0
            prot_cands = [d for d in self.catalog if d.device_type == "MCCB" and d.rated_current_in_a >= (ic_cap_a * 1.5) and self._icu_ok(d, project, ik_total_ka)]
            prot_cands.sort(key=lambda x: x.rated_current_in_a)
            cap_prot = prot_cands[0] if prot_cands else None
            if cap_prot:
                vals.append(ValidationResult(rule_id="RULE-CAP-017", feeder_id="PANEL", standard_ref="IEC 60831-1",
                    status=ValidationStatus.COMPLETED, description=tr("val_cap_prot_desc"),
                    supporting_evidence=tr("val_cap_prot_ev", a=round(ic_cap_a, 1), pn=cap_prot.part_number),
                    consequence=tr("val_cap_prot_cons"), recommended_action=tr("val_no_action")))
            if ik_ka is not None:
                s_sc_kva = math.sqrt(3.0) * project.nominal_voltage_v * ik_ka
                if detuned_pct > 0.0:
                    h_tuned = math.sqrt(100.0 / detuned_pct)
                    vals.append(ValidationResult(rule_id="RULE-CAP-016", feeder_id="PANEL", standard_ref="IEC 61642",
                        status=ValidationStatus.COMPLETED, description=tr("val_cap_res_detuned_desc", a=round(h_tuned, 1)),
                        supporting_evidence=tr("val_cap_res_detuned_ev", a=detuned_pct), consequence=tr("val_cap_res_detuned_cons"),
                        recommended_action=tr("val_no_action")))
                else:
                    res_order = round(math.sqrt(s_sc_kva / qc_installed), 2)
                    near = [h for h in (5.0, 7.0, 11.0, 13.0) if abs(res_order - h) / h <= 0.10]
                    if near:
                        vals.append(ValidationResult(rule_id="RULE-CAP-016", feeder_id="PANEL", standard_ref="IEC 61642",
                            status=ValidationStatus.WARNING, description=tr("val_cap_res_desc", a=res_order, b=near[0]),
                            supporting_evidence=tr("val_cap_res_ev", a=round(s_sc_kva, 1), b=qc_installed),
                            consequence=tr("val_cap_res_cons"), recommended_action=tr("val_cap_res_action")))
                    else:
                        vals.append(ValidationResult(rule_id="RULE-CAP-016", feeder_id="PANEL", standard_ref="IEC 61642",
                            status=ValidationStatus.COMPLETED, description=tr("val_cap_res_ok_desc", a=res_order),
                            supporting_evidence=tr("val_cap_res_ev", a=round(s_sc_kva, 1), b=qc_installed),
                            consequence=tr("val_cap_res_cons"), recommended_action=tr("val_no_action")))
            if cap_contactor is None or cap_module_dev is None or cap_prot is None:
                cap_suggested = tr("sug_cap_bank", a=qc_installed, b=detuned_pct)
        cap_loss_w = qc_installed * 8.0

        # ---------- فاز ۱۳: انتخاب و هماهنگی SPD (IEC 61643-11) ----------
        selected_spd, spd_suggested = None, ""
        u0_v = project.nominal_voltage_v / math.sqrt(3.0)
        uc_required = round(1.1 * u0_v, 1)
        if project.spd_class == SpdClass.NONE:
            vals.append(ValidationResult(rule_id="RULE-SPD-030", feeder_id="PANEL", standard_ref="IEC 61643-11",
                status=ValidationStatus.WARNING, description=tr("val_spd_none_desc"),
                supporting_evidence="-", consequence=tr("val_spd_none_cons"),
                recommended_action=tr("val_spd_none_action")))
            spd_suggested = tr("sug_spd_none")
        else:
            cls_value = project.spd_class.value
            cands = [d for d in self.catalog if d.device_type == "SPD" and d.spd_class == cls_value and d.spd_uc_v >= uc_required]
            cands.sort(key=lambda x: (x.spd_up_kv, x.spd_uc_v))
            if cands:
                selected_spd = cands[0]
                vals.append(ValidationResult(rule_id="RULE-SPD-030", feeder_id="PANEL", standard_ref="IEC 61643-11",
                    status=ValidationStatus.COMPLETED, description=tr("val_spd_030_desc", a=selected_spd.spd_uc_v, b=uc_required),
                    supporting_evidence=tr("val_spd_030_ev", pn=selected_spd.part_number, a=selected_spd.spd_uc_v, b=uc_required),
                    consequence=tr("val_spd_030_cons"), recommended_action=tr("val_no_action")))
            else:
                vals.append(ValidationResult(rule_id="RULE-SPD-030", feeder_id="PANEL", standard_ref="IEC 61643-11",
                    status=ValidationStatus.ERROR, description=tr("val_spd_030_err_desc", a=uc_required),
                    supporting_evidence=tr("val_spd_030_err_ev", a=uc_required, b=cls_value),
                    consequence=tr("val_spd_030_err_cons"), recommended_action=tr("val_spd_030_err_action")))
                spd_suggested = tr("sug_spd_need", a=cls_value, b=uc_required)
            if selected_spd:
                if selected_spd.spd_up_kv <= 2.5:
                    vals.append(ValidationResult(rule_id="RULE-SPD-031", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.COMPLETED, description=tr("val_spd_031_desc", a=selected_spd.spd_up_kv),
                        supporting_evidence=tr("val_spd_031_ev", pn=selected_spd.part_number, a=selected_spd.spd_up_kv, b=2.5),
                        consequence=tr("val_spd_031_cons"), recommended_action=tr("val_no_action")))
                else:
                    vals.append(ValidationResult(rule_id="RULE-SPD-031", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.WARNING, description=tr("val_spd_031_high_desc", a=selected_spd.spd_up_kv),
                        supporting_evidence=tr("val_spd_031_high_ev", pn=selected_spd.part_number, a=selected_spd.spd_up_kv, b=2.5),
                        consequence=tr("val_spd_031_high_cons"), recommended_action=tr("val_spd_031_high_action")))
                lead_m = project.spd_connection_length_m
                if lead_m <= 0.5:
                    vals.append(ValidationResult(rule_id="RULE-SPD-032", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.COMPLETED, description=tr("val_spd_032_desc", a=f"{lead_m:g}"),
                        supporting_evidence=tr("val_spd_032_ev", a=f"{lead_m:g}"), consequence=tr("val_spd_032_cons"),
                        recommended_action=tr("val_no_action")))
                elif lead_m <= 1.0:
                    vals.append(ValidationResult(rule_id="RULE-SPD-032", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.WARNING, description=tr("val_spd_032_warn_desc", a=f"{lead_m:g}"),
                        supporting_evidence=tr("val_spd_032_warn_ev", a=f"{lead_m:g}"), consequence=tr("val_spd_032_warn_cons"),
                        recommended_action=tr("val_spd_032_warn_action")))
                else:
                    vals.append(ValidationResult(rule_id="RULE-SPD-032", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.ERROR, description=tr("val_spd_032_err_desc", a=f"{lead_m:g}"),
                        supporting_evidence=tr("val_spd_032_err_ev", a=f"{lead_m:g}"), consequence=tr("val_spd_032_err_cons"),
                        recommended_action=tr("val_spd_032_err_action")))
                backup_fuse = selected_spd.spd_backup_fuse_a
                if backup_fuse is None or backup_fuse <= 0:
                    vals.append(ValidationResult(
                        rule_id="RULE-SPD-033",
                        feeder_id="PANEL",
                        standard_ref="IEC 61643-11",
                        status=ValidationStatus.INSUFFICIENT_DATA,
                        description=tr("val_spd_033_insufficient_desc"),
                        supporting_evidence=tr("val_spd_033_insufficient_ev", pn=selected_spd.part_number),
                        consequence=tr("val_spd_033_insufficient_cons"),
                        recommended_action=tr("val_spd_033_insufficient_action"),
                    ))
                else:
                    vals.append(ValidationResult(rule_id="RULE-SPD-033", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.COMPLETED, description=tr("val_spd_033_desc", a=selected_spd.spd_backup_fuse_a),
                        supporting_evidence=tr("val_spd_033_ev", pn=selected_spd.part_number, a=selected_spd.spd_backup_fuse_a),
                        consequence=tr("val_spd_033_cons"), recommended_action=tr("val_no_action")))
                if project.spd_class in (SpdClass.T1, SpdClass.T1_T2):
                    if project.has_external_lps is None:
                        vals.append(ValidationResult(
                            rule_id="RULE-SPD-034",
                            feeder_id="PANEL",
                            standard_ref="IEC 61643-12",
                            status=ValidationStatus.WARNING,
                            description=tr("val_spd_034_provisional_desc"),
                            supporting_evidence=tr("val_spd_034_provisional_ev"),
                            consequence=tr("val_spd_034_provisional_cons"),
                            recommended_action=tr("val_spd_034_provisional_action"),
                        ))
                    elif project.has_external_lps is False:
                        vals.append(ValidationResult(
                            rule_id="RULE-SPD-034",
                            feeder_id="PANEL",
                            standard_ref="IEC 61643-12",
                            status=ValidationStatus.WARNING,
                            description=tr("val_spd_034_mismatch_desc"),
                            supporting_evidence=tr("val_spd_034_mismatch_ev"),
                            consequence=tr("val_spd_034_mismatch_cons"),
                            recommended_action=tr("val_spd_034_mismatch_action"),
                        ))
                    else:
                        vals.append(ValidationResult(rule_id="RULE-SPD-034", feeder_id="PANEL", standard_ref="IEC 61643-12",
                            status=ValidationStatus.COMPLETED, description=tr("val_spd_034_desc"),
                            supporting_evidence=tr("val_spd_034_ev"), consequence=tr("val_spd_034_cons"),
                            recommended_action=tr("val_no_action")))
                spd_suggested = tr("sug_spd", a=cls_value, b=selected_spd.part_number, c=selected_spd.spd_up_kv)

        # Provisional warning when external LPS status is unknown
        if project.spd_class != SpdClass.NONE and project.has_external_lps is None:
            vals.append(ValidationResult(
                rule_id="RULE-SPD-PROVISIONAL",
                feeder_id="PANEL",
                standard_ref="IEC 61643-12",
                status=ValidationStatus.WARNING,
                description=tr("val_spd_provisional_desc"),
                supporting_evidence=tr("val_spd_provisional_ev"),
                consequence=tr("val_spd_provisional_cons"),
                recommended_action=tr("val_spd_provisional_action"),
            ))

        main_candidates = [d for d in self.catalog if d.device_type == "MCCB" and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= i_main_req_a and self._icu_ok(d, project, ik_total_ka)]
        main_candidates.sort(key=lambda x: x.rated_current_in_a)
        main_breaker = main_candidates[0] if main_candidates else None

        if (main_breaker and selected_spd
                and selected_spd.spd_backup_fuse_a is not None
                and selected_spd.spd_backup_fuse_a > 0):
            fuse_a = selected_spd.spd_backup_fuse_a
            if main_breaker.rated_current_in_a <= fuse_a:
                vals.append(ValidationResult(rule_id="RULE-SPD-035", feeder_id="PANEL", standard_ref="IEC 61643-11",
                    status=ValidationStatus.COMPLETED,
                    description=tr("val_spd_035_desc", a=f"{main_breaker.rated_current_in_a:g}", b=f"{fuse_a:g}"),
                    supporting_evidence=tr("val_spd_035_ev", a=f"{main_breaker.rated_current_in_a:g}", b=f"{fuse_a:g}"),
                    consequence=tr("val_spd_035_cons"), recommended_action=tr("val_no_action")))
            else:
                vals.append(ValidationResult(rule_id="RULE-SPD-035", feeder_id="PANEL", standard_ref="IEC 61643-11",
                    status=ValidationStatus.WARNING,
                    description=tr("val_spd_035_warn_desc", a=f"{main_breaker.rated_current_in_a:g}", b=f"{fuse_a:g}"),
                    supporting_evidence=tr("val_spd_035_warn_ev", a=f"{main_breaker.rated_current_in_a:g}", b=f"{fuse_a:g}"),
                    consequence=tr("val_spd_035_warn_cons"),
                    recommended_action=tr("val_spd_035_warn_action", b=f"{fuse_a:g}")))

        if project.max_internal_temp_c > 50.0:
            temp_devs = [f.selected_protection for f in feeders if f.selected_protection]
            if main_breaker: temp_devs.append(main_breaker)
            no_rate = [d.part_number for d in temp_devs if catalog_repo.get_device_derating_factor(d.part_number, project.max_internal_temp_c) is None]
            if no_rate:
                vals.append(ValidationResult(rule_id="RULE-THERM-017", feeder_id="PANEL", standard_ref="IEC 61439-1",
                    status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_therm_noderate_desc", a=project.max_internal_temp_c),
                    supporting_evidence=tr("val_therm_noderate_ev", a=", ".join(no_rate)), consequence=tr("val_therm_noderate_cons"),
                    recommended_action=tr("val_therm_noderate_action")))

        if abs(project.nominal_voltage_v - 400.0) > 20.0 and abs(project.nominal_voltage_v - 415.0) > 20.0:
            prot_devs = [f.selected_protection for f in feeders if f.selected_protection]
            if prot_devs:
                missing_icu = [d.part_number for d in prot_devs if self._device_icu_ka(d, project) is None]
                if missing_icu:
                    vals.append(ValidationResult(rule_id="RULE-PROT-VOLT-018", feeder_id="PANEL", standard_ref="IEC 60947-2",
                        status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_volt_icu_desc", a=project.nominal_voltage_v),
                        supporting_evidence=tr("val_volt_icu_ev", a=project.nominal_voltage_v, b=", ".join(missing_icu)),
                        consequence=tr("val_volt_icu_cons"), recommended_action=tr("val_volt_icu_action")))
                else:
                    vals.append(ValidationResult(rule_id="RULE-PROT-VOLT-018", feeder_id="PANEL", standard_ref="IEC 60947-2",
                        status=ValidationStatus.COMPLETED, description=tr("val_volt_icu_ok_desc", a=project.nominal_voltage_v),
                        supporting_evidence=tr("val_volt_icu_ev", a=project.nominal_voltage_v, b="-"),
                        consequence=tr("val_volt_icu_cons"), recommended_action=tr("val_no_action")))

        if main_breaker:
            for f in feeders:
                if not f.selected_protection: continue
                if ik_ka is None:
                    f.selectivity_state = SelectivityEvalState.PRELIMINARY_RATIO_ONLY
                    f.selectivity_ref_doc = tr("sel_ref_no_ik")
                    vals.append(ValidationResult(rule_id="RULE-SEL-005", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.WARNING, description=tr("val_sel_noik_desc"), supporting_evidence=tr("sel_ref_no_ik"), consequence=tr("val_sel_noik_cons"), recommended_action=tr("val_sel_noik_action")))
                    continue
                sel_state, is_limit, ref_doc = SiemensSelectivityRepository.evaluate_pair(main_breaker, f.selected_protection, ik_ka)
                f.selectivity_state = sel_state; f.selectivity_limit_is_ka = is_limit; f.selectivity_ref_doc = ref_doc

                if sel_state == SelectivityEvalState.VERIFIED_TOTAL:
                    vals.append(ValidationResult(rule_id="RULE-SEL-005", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.COMPLETED, description=tr("val_sel_total_desc"), supporting_evidence=tr("val_sel_total_ev", a=is_limit, ref=ref_doc), consequence=tr("val_sel_total_cons"), recommended_action=tr("val_no_action")))
                elif sel_state == SelectivityEvalState.VERIFIED_PARTIAL:
                    vals.append(ValidationResult(rule_id="RULE-SEL-005", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.WARNING, description=tr("val_sel_partial_desc", a=is_limit), supporting_evidence=tr("val_sel_partial_ev", a=is_limit), consequence=tr("val_sel_partial_cons"), recommended_action=tr("val_sel_partial_action")))
                elif sel_state == SelectivityEvalState.PRELIMINARY:
                    vals.append(ValidationResult(rule_id="RULE-SEL-005", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.WARNING, description=tr("val_sel_prelim_desc", a=is_limit), supporting_evidence=tr("val_sel_prelim_ev", a=is_limit, ref=ref_doc), consequence=tr("val_sel_prelim_cons"), recommended_action=tr("val_sel_prelim_action")))
                elif sel_state == SelectivityEvalState.PRELIMINARY_RATIO_ONLY:
                    vals.append(ValidationResult(rule_id="RULE-SEL-005", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.WARNING, description=tr("val_sel_ratio_desc"), supporting_evidence=ref_doc, consequence=tr("val_sel_ratio_cons"), recommended_action=tr("val_sel_ratio_action")))
                else:
                    vals.append(ValidationResult(rule_id="RULE-SEL-005", feeder_id=f.feeder_id, standard_ref="IEC 60947-2", status=ValidationStatus.ERROR, description=tr("val_sel_viol_desc"), supporting_evidence=ref_doc, consequence=tr("val_sel_viol_cons"), recommended_action=tr("val_sel_viol_action")))

        vals.extend(evaluate_scenario(project, feeders, i_main_req_a, ik_total_ka if ik_total_ka is not None else ik_ka))

        pe_busbar_spec = "Cu 20x5 mm (PE - 100 mm²)" if i_main_req_a <= 400 else "Cu 30x5 mm (PE - 150 mm²)"

        _, _, _, _, _, inc_cable_str = CableSizingEngine.select_feeder_cable(
            ib_a=i_main_req_a, protection_in_a=main_breaker.rated_current_in_a if main_breaker else i_main_req_a,
            is_adjustable_prot=True, length_m=30.0, cos_phi=overall_cos_phi, voltage_v=project.nominal_voltage_v,
            phases=3, ambient_temp_c=project.ambient_temp_c, grouping_k2=project.cable_grouping_factor_k2,
            max_vdrop_pct=2.0, load_type=LoadType.SUB_FEEDER
        )

        coils_holding_w = round(sum(f.ctrl_24v_holding_w for f in feeders), 1)
        plc_hmi_w = round(project.plc_hmi_24vdc_power_w, 1)
        total_cont_24v_w = round(plc_hmi_w + coils_holding_w, 1)
        i_cont_24v_a = round(total_cont_24v_w / 24.0, 2)
        i_design_24v_a = round(i_cont_24v_a * (1.0 + project.spare_factor), 2)

        # سایزینگ منبع فرمان با Inrush بزرگ‌ترین کنتاکتور: S_req = K_sim·ΣS_holding + S_inrush,max (+ بار دائمی PLC/HMI)
        ks_ctrl = project.simultaneity_factor_ks
        largest_surge_w = max((f.ctrl_24v_pull_in_surge_w for f in feeders), default=0.0)
        peak_24v_w = round(plc_hmi_w + ks_ctrl * coils_holding_w + largest_surge_w, 1)
        i_peak_24v_a = round(peak_24v_w / 24.0, 2)

        psu_candidates = [d for d in self.catalog if d.device_type == "PSU_24V" and (d.rated_current_in_a * self._get_derating_factor(d, project.max_internal_temp_c)) >= i_design_24v_a and d.boost_current_peak_a >= i_peak_24v_a]
        psu_candidates.sort(key=lambda x: x.rated_current_in_a)
        selected_psu = psu_candidates[0] if psu_candidates else None
        selected_dc_sel_mod = next((d for d in self.catalog if d.device_type == "DC_SEL_MOD"), None)
        selected_psu_mcb = next((d for d in self.catalog if d.device_type == "MCB_2P_CTRL"), None)

        if selected_psu:
            vals.append(ValidationResult(rule_id="RULE-CTRL-24V-010", feeder_id="CTRL_24VDC", standard_ref="IEC 60204-1", status=ValidationStatus.COMPLETED, description=tr("val_ctrl_desc"), supporting_evidence=tr("val_ctrl_ev", a=i_design_24v_a, b=i_peak_24v_a, pn=selected_psu.part_number), consequence=tr("val_ctrl_cons"), recommended_action=tr("val_ctrl_action")))
            vals.append(ValidationResult(rule_id="RULE-CTRL-24V-011", feeder_id="CTRL_24VDC", standard_ref="IEC 60204-1",
                status=ValidationStatus.COMPLETED, description=tr("val_ctrl_inrush_desc"),
                supporting_evidence=tr("val_ctrl_inrush_ev", req=peak_24v_w, ksim=ks_ctrl, holding=coils_holding_w,
                                       surge=largest_surge_w, ipeak=i_peak_24v_a, boost=selected_psu.boost_current_peak_a),
                consequence=tr("val_ctrl_inrush_cons"), recommended_action=tr("val_no_action")))
        else:
            vals.append(ValidationResult(rule_id="RULE-CTRL-24V-011", feeder_id="CTRL_24VDC", standard_ref="IEC 60204-1",
                status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_ctrl_inrush_none_desc"),
                supporting_evidence=tr("val_ctrl_inrush_none_ev", a=peak_24v_w, b=i_peak_24v_a),
                consequence=tr("val_ctrl_inrush_cons"), recommended_action=tr("val_ctrl_inrush_action")))

        feeder_losses = sum(f.total_feeder_loss_w for f in feeders)
        main_loss = main_breaker.power_loss_w * 0.8 if main_breaker else 25.0
        psu_and_sel_loss = (selected_psu.power_loss_w if selected_psu else 25.0) + (selected_dc_sel_mod.power_loss_w if selected_dc_sel_mod else 5.0) + 20.0
        total_loss_w = round(feeder_losses + main_loss + psu_and_sel_loss + cap_loss_w, 1)

        has_vfd_or_yd = any(f.load_type in (LoadType.MOTOR_VFD, LoadType.MOTOR_STAR_DELTA) for f in feeders)
        enclosures = catalog_repo.get_compatible_enclosures(project.target_ip)
        if project.enclosure_mounting != EnclosureMounting.UNSPECIFIED:
            enclosures = [device for device in enclosures if device.enclosure_mounting == project.enclosure_mounting]
        enclosures.sort(key=lambda d: (d.width_mm, d.height_mm))
        if enclosures:
            idx = 2 if (i_main_req_a > 160 or len(feeders) >= 5) else (1 if (has_vfd_or_yd or len(feeders) >= 3) else 0)
            selected_enc = enclosures[min(idx, len(enclosures) - 1)]
        else:
            selected_enc = CatalogDevice(part_number="EST-PANEL", manufacturer="?", series=tr("est_series"), device_type="ENCLOSURE",
                                         width_mm=800.0, height_mm=2000.0, depth_mm=600.0, data_quality=DataQuality.ESTIMATED)
            vals.append(ValidationResult(rule_id="RULE-ENC-IP-019", feeder_id="PANEL", standard_ref="IEC 60529",
                status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_enc_ip_desc", a=project.target_ip),
                supporting_evidence=tr("val_enc_ip_ev", a=project.target_ip), consequence=tr("val_enc_ip_cons"),
                recommended_action=tr("val_enc_ip_action")))

        dimensions = {name: getattr(project, 'enclosure_' + name) for name in ('width_mm', 'height_mm', 'depth_mm')}
        if any(value is not None for value in dimensions.values()):
            selected_enc = selected_enc.model_copy(update={
                **{name: value for name, value in dimensions.items() if value is not None},
                'part_number': 'EST-PANEL', 'data_quality': DataQuality.ESTIMATED,
                'enclosure_mounting': project.enclosure_mounting})
        if project.enclosure_mounting != EnclosureMounting.UNSPECIFIED:
            vals.append(ValidationResult(rule_id='SCEN-MOUNTING', feeder_id='PANEL', standard_ref='IEC 61439-1; IEC 62208',
                status=ValidationStatus.INSUFFICIENT_DATA, description=tr('mounting_review'),
                supporting_evidence=f'{project.enclosure_mounting.value}; {selected_enc.width_mm}×{selected_enc.height_mm}×{selected_enc.depth_mm} mm',
                consequence=tr('mounting_review_note'), recommended_action=tr('mounting_review_note')))
        # ---------- Priority 8: SPD pre-check via pe_spd_engine ----------
        if project.spd_class != SpdClass.NONE:
            try:
                _spd_diag = evaluate_spd_requirements(
                    earthing_system=getattr(project.earthing_system, "value", str(project.earthing_system)),
                    nominal_voltage_ln_v=u0_v,
                    has_external_lps=None,
                    is_sensitive_terminal_load=False,
                    prospective_ik_ka=ik_ka,
                    candidates=[],
                )
                if _spd_diag.engineering_status.value == "insufficient_data" and _spd_diag.missing_parameters:
                    vals.append(ValidationResult(
                        rule_id="RULE-SPD-PRECHECK", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.WARNING,
                        description=tr('spd_precheck_desc', fields=", ".join(_spd_diag.missing_parameters)),
                        supporting_evidence="pe_spd_engine.evaluate_spd_requirements",
                        consequence=tr('spd_precheck_consequence'),
                        recommended_action=tr('spd_precheck_action', fields=", ".join(_spd_diag.missing_parameters)),
                    ))
            except Exception:
                pass

        # ---------- Phase 6: صحت‌سنجی شینه اصلی طبق IEC 61439-1 ----------
        # فاز ۱۱: Ik و Ipk کل (شبکه + موتورها) مبنای تحمل اتصال کوتاه؛ امپدانس شینه → افت ولتاژ
        bus_res = BusbarEngine.select(
            i_main_req_a, ik_ka, selected_enc.width_mm,
            voltage_v=project.nominal_voltage_v, cos_phi=overall_cos_phi,
            ik_total_ka=ik_total_ka, ip_total_ka=ip_total_ka,
            internal_temp_c=project.max_internal_temp_c, source_r_x=project.source_r_x,
            phase_spacing_mm=project.busbar_phase_spacing_mm, support_span_mm=project.busbar_support_span_mm,
            allowable_stress_mpa=project.busbar_allowable_stress_mpa)
        busbar_spec = bus_res.spec
        vals.extend(bus_res.validations)

        h_m, w_m, d_m = selected_enc.height_mm / 1000.0, selected_enc.width_mm / 1000.0, selected_enc.depth_mm / 1000.0
        ae_m2 = (1.4 * w_m * h_m) + (1.4 * w_m * d_m) + (1.8 * d_m * h_m)
        delta_t = max(1.0, project.max_internal_temp_c - project.ambient_temp_c)
        alt_factor = 1.0 if project.altitude_m <= 2000.0 else max(0.6, 1.0 - 0.1 * (project.altitude_m - 2000.0) / 1000.0)
        p_diss_natural_w = round(5.5 * ae_m2 * delta_t * alt_factor, 1)
        if alt_factor < 1.0:
            vals.append(ValidationResult(rule_id="RULE-THERM-015", feeder_id="PANEL", standard_ref="IEC 61439-1",
                status=ValidationStatus.WARNING, description=tr("val_alt_desc", a=project.altitude_m),
                supporting_evidence=tr("val_alt_ev", a=alt_factor, b=round(p_diss_natural_w, 1)),
                consequence=tr("val_alt_cons"), recommended_action=tr("val_alt_action")))

        req_airflow_m3h, selected_fan = 0.0, None
        if total_loss_w > p_diss_natural_w:
            req_airflow_m3h = round((3.3 * (total_loss_w - p_diss_natural_w)) / (delta_t * alt_factor), 1)
            fans = [d for d in self.catalog if d.device_type == "FAN_FILTER" and d.airflow_m3h >= (req_airflow_m3h * 1.2)]
            fans.sort(key=lambda x: x.airflow_m3h)
            if fans: selected_fan = fans[0]

        # F-007: نصب فیلترفن، درجه حفاظت مؤثر تابلو را به حداکثر IP فن محدود می‌کند
        effective_ip_str = project.target_ip
        if selected_fan is not None:
            ip_num = self._ip_numeric(project.target_ip)
            if ip_num is not None and ip_num >= 55:
                effective_ip_str = "IP54"
                vals.append(ValidationResult(rule_id="RULE-ENC-IP-020", feeder_id="PANEL", standard_ref="IEC 60529",
                    status=ValidationStatus.WARNING, description=tr("val_enc_fan_ip_desc", a=project.target_ip, b=effective_ip_str),
                    supporting_evidence=tr("val_enc_fan_ip_ev", a=selected_fan.part_number, b=selected_fan.ip_rating),
                    consequence=tr("val_enc_fan_ip_cons"), recommended_action=tr("val_enc_fan_ip_action")))

        est_internal_c = project.ambient_temp_c + (delta_t if selected_fan else delta_t * total_loss_w / max(p_diss_natural_w, 1.0))
        est_internal_c = round(est_internal_c, 1)
        fan_missing = total_loss_w > p_diss_natural_w and selected_fan is None
        therm_status = ValidationStatus.ERROR if fan_missing else ValidationStatus.WARNING
        if fan_missing:
            therm_action = tr("val_tint_nofan_action")
        elif est_internal_c <= project.max_internal_temp_c:
            therm_action = tr("val_no_action")
        else:
            therm_action = tr("val_tint_action")
        vals.append(ValidationResult(rule_id="RULE-THERM-016", feeder_id="PANEL", standard_ref="IEC 61439-1",
            status=therm_status,
            description=tr("val_tint_desc", a=est_internal_c, b=project.max_internal_temp_c),
            supporting_evidence=tr("val_tint_ev", a=total_loss_w, b=p_diss_natural_w, c=req_airflow_m3h),
            consequence=tr("val_tint_cons"), recommended_action=therm_action))
        selected = [dev for f in feeders for dev in (f.selected_protection, f.selected_contactor_main,
                    f.selected_contactor_delta, f.selected_contactor_star, f.selected_bimetal,
                    f.selected_vfd, f.selected_soft_starter) if dev is not None]
        selected += [dev for dev in (main_breaker, selected_enc, selected_fan) if dev is not None]
        missing_sources = [dev.part_number for dev in selected if not dev.has_verified_datasheet]
        if missing_sources:
            vals.append(ValidationResult(rule_id='RULE-CATALOG-PROVENANCE', feeder_id='PANEL',
                standard_ref='OEM catalog evidence', status=ValidationStatus.INSUFFICIENT_DATA,
                description=tr('audit_provenance'), supporting_evidence=', '.join(sorted(set(missing_sources))),
                consequence=tr('audit_preliminary'), recommended_action=tr('audit_review'),
                rule_category='OEM_MANUFACTURER_RULE'))
        known_limits = [dev.max_operating_temp_c for dev in selected if dev.max_operating_temp_c is not None]
        if known_limits and est_internal_c > min(known_limits):
            vals.append(ValidationResult(rule_id='RULE-THERM-COMPONENT', feeder_id='PANEL',
                standard_ref='OEM operating temperature', status=ValidationStatus.ERROR,
                description=tr('audit_component_temp'), supporting_evidence=f'T_est={est_internal_c:g} C; limit={min(known_limits):g} C',
                consequence=tr('audit_preliminary'), recommended_action=tr('audit_review'),
                rule_category='OEM_MANUFACTURER_RULE'))

        # F-017: هشدار صریح در گزارش وقتی دمای داخلی از ۵۰°C (مرجع derating تجهیزات) فراتر می‌رود
        if est_internal_c > 50.0:
            vals.append(ValidationResult(rule_id="RULE-THERM-018", feeder_id="PANEL", standard_ref="IEC 61439-1",
                status=ValidationStatus.WARNING, description=tr("val_tint_50_desc", a=est_internal_c),
                supporting_evidence=tr("val_tint_50_ev", a=est_internal_c, b=50.0),
                consequence=tr("val_tint_50_cons"), recommended_action=tr("val_tint_50_action")))

        max_dip, dip_motor = None, ""
        for f in feeders:
            if f.starting_dip_pct is not None and (max_dip is None or f.starting_dip_pct > max_dip):
                max_dip = f.starting_dip_pct; dip_motor = f.feeder_id
        if max_dip is not None:
            dip_ok = max_dip <= 15.0
            vals.append(ValidationResult(rule_id="RULE-VDIP-013", feeder_id=dip_motor, standard_ref="IEC 60034-1",
                status=ValidationStatus.COMPLETED if dip_ok else ValidationStatus.WARNING,
                description=tr("val_dip_desc", a=max_dip), supporting_evidence=tr("val_dip_ev", a=max_dip),
                consequence=tr("val_dip_cons"), recommended_action=tr("val_no_action" if dip_ok else "val_dip_action")))

        suggested_main = tr("sug_main", a=round(i_main_req_a, 1), b=(ik_total_ka if ik_total_ka is not None else "?")) if main_breaker is None else ""
        suggested_psu = tr("sug_psu", a=i_design_24v_a, b=i_peak_24v_a) if selected_psu is None else ""
        suggested_fan = tr("sug_fan", a=req_airflow_m3h) if (total_loss_w > p_diss_natural_w and selected_fan is None) else ""

        # F-015: Ik تخمینی در نقطه اتصال بالادست است؛ امپدانس کابل رابط لحاظ نشده
        ik_note_str = (ik_source + " — " + tr("ik_est_note")) if ik_ka is not None else ik_source
        if ik_ka is not None and mot_ka > 0.0:
            ik_note_str += " — " + tr("ik_motor_note", a=round(mot_ka, 3), b=ik_total_ka)

        max_feeder_du = max((f.voltage_drop_percent for f in feeders), default=0.0)

        summary = PanelSummaryOutput(
            phase_design_currents_a={phase: round(current, 2) for phase, current in phase_currents.items()},
            neutral_current_a=round(neutral_a, 2), phase_imbalance_pct=round(imbalance, 2),
            total_active_kw=round(sum_p, 2), total_reactive_kvar=round(sum_q, 2), total_apparent_kva=round(s_design_kva, 2),
            overall_cos_phi=overall_cos_phi, sum_feeder_currents_a=round(sum_ib, 2), design_main_current_a=round(i_main_req_a, 2),
            main_breaker=main_breaker, recommended_busbar_spec=busbar_spec, recommended_pe_busbar_spec=pe_busbar_spec,
            busbar_length_m=bus_res.length_m if bus_res.length_m > 0 else None,
            pe_busbar_length_m=bus_res.length_m if bus_res.length_m > 0 else None,
            busbar_rating_a=bus_res.rating_a, busbar_icw_1s_ka=bus_res.icw_1s_ka, busbar_ipk_ka=bus_res.ipk_ka,
            busbar_required_ipk_ka=bus_res.required_ipk_ka, busbar_max_support_spacing_mm=bus_res.max_support_spacing_mm,
            busbar_required_supports=bus_res.required_supports,
            busbar_bending_stress_mpa=bus_res.bending_stress_mpa,
            busbar_force_n_per_m=bus_res.force_n_per_m, busbar_temperature_factor=bus_res.temperature_factor,
            recommended_incoming_cable_str=inc_cable_str, ctrl_24v_plc_hmi_w=plc_hmi_w, ctrl_24v_coils_holding_w=coils_holding_w,
            incoming_cable_length_m=None,
            ctrl_24v_total_continuous_w=total_cont_24v_w, ctrl_24v_continuous_current_a=i_cont_24v_a,
            ctrl_24v_design_current_with_spare_a=i_design_24v_a, ctrl_24v_peak_inrush_current_a=i_peak_24v_a,
            selected_psu_24v=selected_psu, selected_dc_selectivity_mod=selected_dc_sel_mod, selected_psu_primary_mcb=selected_psu_mcb,
            total_power_loss_w=total_loss_w, enclosure_natural_dissipation_w=p_diss_natural_w, required_airflow_m3h=req_airflow_m3h,
            selected_fan=selected_fan, selected_enclosure=selected_enc, estimated_panel_width_mm=selected_enc.width_mm,
            estimated_panel_height_mm=selected_enc.height_mm, estimated_panel_depth_mm=selected_enc.depth_mm,
            ik_used_ka=ik_ka, motor_contribution_ka=(round(mot_ka, 3) if mot_ka > 0.0 else None),
            ik_bus_total_ka=(ik_total_ka if ik_ka is not None else None),
            ip_bus_total_ka=(ip_total_ka if ik_ka is not None else None),
            busbar_du_v=bus_res.voltage_drop_v, busbar_du_pct=bus_res.voltage_drop_pct,
            max_total_du_pct=round(max_feeder_du + bus_res.voltage_drop_pct, 3),
            ik_source_str=ik_note_str, effective_ip_str=effective_ip_str, suggested_main_breaker_str=suggested_main,
            suggested_psu_str=suggested_psu, suggested_fan_str=suggested_fan,
            max_motor_starting_dip_pct=max_dip, max_starting_dip_motor=dip_motor,
            panel_thdi_pct=panel_thdi, cap_bank_required_kvar=round(sum_p * (math.tan(math.acos(min(max(overall_cos_phi, 0.1), 1.0))) - math.tan(math.acos(0.95))), 1) if (overall_cos_phi < 0.95 and sum_p > 0.0) else 0.0,
            cap_bank_installed_kvar=qc_installed, cap_bank_steps=cap_steps, cap_bank_detuned_pct=detuned_pct,
            cap_bank_reactor_tuned_hz=(189.0 if detuned_pct == 7.0 else (134.0 if detuned_pct == 14.0 else 0.0)),
            cap_bank_contactor=cap_contactor, cap_bank_protection=cap_prot, cap_bank_reactor_dev=cap_reactor_dev,
            cap_bank_module_dev=cap_module_dev, cap_bank_resonance_order=res_order, cap_bank_suggested_str=cap_suggested,
            selected_spd=selected_spd, spd_suggested_str=spd_suggested,
            estimated_internal_temp_c=est_internal_c, altitude_derating_factor=alt_factor
        )
        return summary, vals


def build_design_verification(project: ProjectSpec, feeders: List[FeederCalcOutput],
                              summary: PanelSummaryOutput,
                              validations: List[ValidationResult]) -> DesignVerificationReport:
    """فاز ۱۲: گزارش تأیید طراحی مطابق IEC 61439-1 بند ۱۰ — چک‌لیست خودکار ۱۳ آیتم
    با مقدار محاسبه‌شده، روش تأیید، قاعده مرجع و وضعیت."""
    from lv_assist.calculation_state import require_current_calculation
    require_current_calculation(project, summary, feeders)

    def _worst(rule_ids) -> VerificationStatus:
        rel = [v for v in validations if v.rule_id in rule_ids]
        if not rel:
            return VerificationStatus.NOT_VERIFIED
        if any(v.status == ValidationStatus.ERROR for v in rel):
            return VerificationStatus.FAIL
        if any(v.status == ValidationStatus.WARNING for v in rel):
            return VerificationStatus.WARNING
        if any(v.status == ValidationStatus.INSUFFICIENT_DATA for v in rel):
            return VerificationStatus.NOT_VERIFIED
        return VerificationStatus.PASS

    items: List[DesignVerificationItem] = []
    enc = summary.selected_enclosure
    enc_pn = enc.part_number if enc else "-"
    enc_verified = enc is not None and enc.has_verified_datasheet

    # 10.2 — استحکام مصالح و قطعات (مقاومت در برابر خوردگی)
    items.append(DesignVerificationItem(
        clause_ref="10.2", title=tr("dv_10_2_t"), requirement=tr("dv_10_2_r"),
        method=VerificationMethod.MANUFACTURER_DATA,
        status=VerificationStatus.PASS if enc_verified else VerificationStatus.WARNING,
        computed_value=tr("dv_10_2_val", pn=enc_pn),
        evidence=tr("dv_10_2_ev_verified", pn=enc_pn) if enc_verified else tr("dv_10_2_ev_estimated", pn=enc_pn),
        rule_ids=["RULE-ENC-IP-019"]))

    # 10.3 — درجه حفاظت IP
    eff_ip = summary.effective_ip_str or project.target_ip
    items.append(DesignVerificationItem(
        clause_ref="10.3", title=tr("dv_10_3_t"), requirement=tr("dv_10_3_r"),
        method=VerificationMethod.CALCULATION,
        status=VerificationStatus.PASS if eff_ip == project.target_ip else VerificationStatus.WARNING,
        computed_value=tr("dv_10_3_val", a=eff_ip, b=project.target_ip),
        evidence=tr("dv_10_3_ev", a=eff_ip, b=project.target_ip),
        rule_ids=["RULE-ENC-IP-019", "RULE-ENC-IP-020"]))

    # 10.4 — فواصل هوایی و خزشی (جدول ۱ و ۲ استاندارد، درجه آلودگی ۲، گروه مصالح IIIa)
    u_v = project.nominal_voltage_v
    clr = 3.0 if u_v <= 400.0 else (5.5 if u_v <= 690.0 else 8.0)
    crp = 6.3 if u_v <= 400.0 else (10.0 if u_v <= 690.0 else 12.5)
    items.append(DesignVerificationItem(
        clause_ref="10.4", title=tr("dv_10_4_t"), requirement=tr("dv_10_4_r"),
        method=VerificationMethod.DESIGN_RULE, status=VerificationStatus.PASS,
        computed_value=tr("dv_10_4_val", a=clr, b=crp),
        evidence=tr("dv_10_4_ev", a=u_v),
        rule_ids=[]))

    # 10.5 — مدارهای حفاظتی (PE + سطح مقطع آدیاباتیک)
    n_pe = sum(1 for f in feeders if f.selected_pe_mm2 is not None)
    items.append(DesignVerificationItem(
        clause_ref="10.5", title=tr("dv_10_5_t"), requirement=tr("dv_10_5_r"),
        method=VerificationMethod.CALCULATION,
        status=VerificationStatus.PASS if n_pe == len(feeders) else VerificationStatus.FAIL,
        computed_value=tr("dv_10_5_val", a=n_pe, b=len(feeders)),
        evidence=tr("dv_10_5_ev", a=summary.recommended_pe_busbar_spec, b=project.earthing_system.value),
        rule_ids=[]))

    # 10.6 — اجزای کلیدزنی و قطعات (Icu و هماهنگی)
    ik_txt = summary.ik_bus_total_ka if summary.ik_bus_total_ka is not None else summary.ik_used_ka
    items.append(DesignVerificationItem(
        clause_ref="10.6", title=tr("dv_10_6_t"), requirement=tr("dv_10_6_r"),
        method=VerificationMethod.CALCULATION,
        status=_worst(["RULE-PROT-SC-001", "RULE-COORD-002"]),
        computed_value=tr("dv_10_6_val", a=len(feeders)),
        evidence=tr("dv_10_6_ev", a=ik_txt if ik_txt is not None else "?"),
        rule_ids=["RULE-PROT-SC-001", "RULE-COORD-002"]))

    # 10.7 — مدارهای داخلی و اتصالات (شینه: جریان‌دهی و افت ولتاژ)
    bus_ok = summary.busbar_rating_a >= summary.design_main_current_a and summary.busbar_du_pct <= 1.5
    items.append(DesignVerificationItem(
        clause_ref="10.7", title=tr("dv_10_7_t"), requirement=tr("dv_10_7_r"),
        method=VerificationMethod.CALCULATION,
        status=VerificationStatus.PASS if bus_ok else VerificationStatus.WARNING,
        computed_value=tr("dv_10_7_val", a=summary.recommended_busbar_spec, b=summary.busbar_rating_a, c=round(summary.design_main_current_a, 1)),
        evidence=tr("dv_10_7_ev", a=summary.busbar_du_v, b=summary.busbar_du_pct),
        rule_ids=["RULE-BUS-024", "RULE-BUS-028"]))

    # 10.8 — ترمینال‌های هادی‌های خارجی (سایزینگ کابل فیدرها)
    n_cable = sum(1 for f in feeders if f.cable_derated_iz_a is not None)
    max_vd = max((f.voltage_drop_percent for f in feeders), default=0.0)
    items.append(DesignVerificationItem(
        clause_ref="10.8", title=tr("dv_10_8_t"), requirement=tr("dv_10_8_r"),
        method=VerificationMethod.CALCULATION,
        status=VerificationStatus.PASS if n_cable == len(feeders) else VerificationStatus.WARNING,
        computed_value=tr("dv_10_8_val", a=n_cable, b=len(feeders)),
        evidence=tr("dv_10_8_ev", a=max_vd),
        rule_ids=[]))

    # 10.9 — خواص دی‌الکتریک (آزمون فرکانس قدرت مطابق جدول ۸ استاندارد)
    test_v = 2000.0 if u_v <= 300.0 else 2500.0
    items.append(DesignVerificationItem(
        clause_ref="10.9", title=tr("dv_10_9_t"), requirement=tr("dv_10_9_r"),
        method=VerificationMethod.DESIGN_RULE, status=VerificationStatus.PASS,
        computed_value=tr("dv_10_9_val", a=test_v),
        evidence=tr("dv_10_9_ev", a=u_v),
        rule_ids=[]))

    # 10.10 — حدود افزایش دما (محاسبه تا ۶۳۰A مجاز؛ فراتر → آزمون نوعی)
    tint = summary.estimated_internal_temp_c
    if tint is None:
        t_method, t_status, t_val = VerificationMethod.TYPE_TEST, VerificationStatus.NOT_VERIFIED, "-"
    elif summary.design_main_current_a > 630.0:
        t_method, t_status = VerificationMethod.TYPE_TEST, VerificationStatus.NOT_VERIFIED
        t_val = tr("dv_10_10_val", a=tint, b=project.max_internal_temp_c)
    else:
        t_method = VerificationMethod.CALCULATION
        t_status = VerificationStatus.PASS if tint <= project.max_internal_temp_c else VerificationStatus.WARNING
        t_val = tr("dv_10_10_val", a=tint, b=project.max_internal_temp_c)
    items.append(DesignVerificationItem(
        clause_ref="10.10", title=tr("dv_10_10_t"), requirement=tr("dv_10_10_r"),
        method=t_method, status=t_status, computed_value=t_val,
        evidence=tr("dv_10_10_ev", a=summary.total_power_loss_w, b=summary.enclosure_natural_dissipation_w, c=summary.required_airflow_m3h),
        rule_ids=["RULE-THERM-015", "RULE-THERM-016", "RULE-THERM-018"]))

    # 10.11 — تحمل اتصال کوتاه (SCCR): شینه Icw/Ipk و کلید اصلی Icu در برابر Ik کل
    ik_chk = summary.ik_bus_total_ka if summary.ik_bus_total_ka is not None else summary.ik_used_ka
    ip_chk = summary.busbar_required_ipk_ka
    if ik_chk is None:
        scc_status = VerificationStatus.NOT_VERIFIED
    else:
        icw_ok = summary.busbar_icw_1s_ka >= ik_chk
        ipk_ok = (ip_chk is None) or (summary.busbar_ipk_ka >= ip_chk)
        main_ok = summary.main_breaker is not None
        scc_status = VerificationStatus.PASS if (icw_ok and ipk_ok and main_ok) else VerificationStatus.FAIL
    items.append(DesignVerificationItem(
        clause_ref="10.11", title=tr("dv_10_11_t"), requirement=tr("dv_10_11_r"),
        method=VerificationMethod.CALCULATION, status=scc_status,
        computed_value=tr("dv_10_11_val", a=summary.busbar_icw_1s_ka, b=summary.busbar_ipk_ka),
        evidence=tr("dv_10_11_ev", a=ik_chk if ik_chk is not None else "?",
                    b=ip_chk if ip_chk is not None else "?",
                    c=summary.main_breaker.part_number if summary.main_breaker else "-"),
        rule_ids=["RULE-BUS-025", "RULE-BUS-026", "RULE-PROT-SC-001"]))

    # 10.12 — سازگاری الکترومغناطیسی (EMC)
    n_vfd = sum(1 for f in feeders if f.load_type == LoadType.MOTOR_VFD)
    items.append(DesignVerificationItem(
        clause_ref="10.12", title=tr("dv_10_12_t"), requirement=tr("dv_10_12_r"),
        method=VerificationMethod.DESIGN_RULE, status=VerificationStatus.PASS,
        computed_value=tr("dv_10_12_val", a=n_vfd),
        evidence=tr("dv_10_12_ev"),
        rule_ids=[]))

    # 10.13 — عملکرد مکانیکی
    items.append(DesignVerificationItem(
        clause_ref="10.13", title=tr("dv_10_13_t"), requirement=tr("dv_10_13_r"),
        method=VerificationMethod.MANUFACTURER_DATA,
        status=VerificationStatus.PASS if enc_verified else VerificationStatus.WARNING,
        computed_value=tr("dv_10_13_val", pn=enc_pn),
        evidence=tr("dv_10_13_ev"),
        rule_ids=[]))

    if project.special_scenario != SpecialScenario.NONE:
        from lv_assist.scenario_rules import PROFILES, localized
        profile = PROFILES[project.special_scenario.value]
        items.append(DesignVerificationItem(clause_ref='SCENARIO', title=tr('scenario_settings'),
            requirement=profile.standards, method=VerificationMethod.MANUFACTURER_DATA,
            status=VerificationStatus.NOT_VERIFIED, computed_value=tr('scenario_' + project.special_scenario.value),
            evidence=localized(profile.notes), rule_ids=['SCEN-REVIEW']))
    if project.enclosure_mounting != EnclosureMounting.UNSPECIFIED:
        items.append(DesignVerificationItem(clause_ref='MOUNTING', title=tr('mounting_review'),
            requirement='IEC 61439-1; IEC 62208', method=VerificationMethod.MANUFACTURER_DATA,
            status=VerificationStatus.NOT_VERIFIED, computed_value=tr('mount_' + project.enclosure_mounting.value),
            evidence=tr('mounting_review_note'), rule_ids=['SCEN-MOUNTING']))

    for item in items:
        if item.clause_ref == '10.5':
            item.rule_ids = ['RULE-PE-I2T', 'RULE-ADS-TN', 'RULE-ADS-TT']
        elif item.clause_ref == '10.8':
            item.rule_ids = ['RULE-CABLE-009', 'RULE-CABLE-I2', 'RULE-PHASE-I2T']
        if item.rule_ids and _worst(item.rule_ids) == VerificationStatus.FAIL:
            item.status = VerificationStatus.FAIL
        elif item.status == VerificationStatus.PASS:
            item.status = VerificationStatus.NOT_VERIFIED
        item.evidence += ' ' + tr('audit_no_assembly_proof')
        if item.clause_ref == '10.9':
            item.method = VerificationMethod.TYPE_TEST
    n_pass = sum(1 for it in items if it.status == VerificationStatus.PASS)
    n_warn = sum(1 for it in items if it.status == VerificationStatus.WARNING)
    n_fail = sum(1 for it in items if it.status == VerificationStatus.FAIL)
    n_nv = sum(1 for it in items if it.status == VerificationStatus.NOT_VERIFIED)
    if n_fail:
        c_status, c_text = VerificationStatus.FAIL, tr("dv_concl_fail", a=n_pass, b=n_warn, c=n_fail, d=n_nv)
    elif n_nv:
        c_status, c_text = VerificationStatus.NOT_VERIFIED, tr("dv_concl_partial", a=n_pass, b=n_warn, c=n_fail, d=n_nv)
    elif n_warn:
        c_status, c_text = VerificationStatus.WARNING, tr("dv_concl_remarks", a=n_pass, b=n_warn, c=n_fail, d=n_nv)
    else:
        c_status, c_text = VerificationStatus.PASS, tr("dv_concl_pass", a=n_pass, b=n_warn, c=n_fail, d=n_nv)
    std_hdr = 'DIN EN 61439-1 (VDE 0660-600-1)' if is_vde_project(project) else 'IEC 61439-1'
    return DesignVerificationReport(standard_ref=std_hdr, items=items, conclusion_status=c_status, conclusion_text=c_text)


# --- [AUDIT SAFE HELPERS] ---
def _audit_status_to_models_status(audit_status):
    """
    Convert audit ValidationStatus to models.ValidationStatus.

    Safe because inspect_audit.py confirmed:
    ENUM_MATCH True
    values = COMPLETED / WARNING / INSUFFICIENT_DATA / ERROR
    """
    return ValidationStatus(audit_status.value)


def _audit_estimate_clear_time_detailed(prot, fault_multiple):
    """
    Non-breaking detailed trip-time estimator.

    Legacy `_estimate_clear_time_s()` still returns float.
    This helper returns TripTimeEstimate and exposes whether the real
    thermal curve exceeds the IEC adiabatic 5-second boundary.
    """
    series = getattr(prot, "series", "GENERIC")
    return audit_estimate_clear_time(
        series=series,
        fault_multiple=fault_multiple,
        thermal_curve_lookup=TripCurveRepository.thermal_time_s,
        is_approximated_curve=True,
    )


def _audit_verify_icu_status(device_icu_ka, ik_ka, is_preliminary=False):
    """
    Four-state ICu verification helper.

    This does NOT replace legacy `_icu_ok()` which returns bool and is
    used for catalog filtering. It is intended for final validation/reporting.
    """
    return audit_verify_breaking_capacity_icu(
        device_icu_ka=device_icu_ka,
        prospective_ik_ka=ik_ka,
        is_ik_preliminary=is_preliminary,
    )


def _audit_calculate_feeder_ik_profile(
    transformer_kva,
    uk_percent,
    voltage_v=400.0,
    feeder_length_m=None,
    feeder_phase_mm2=None,
    feeder_pe_mm2=None,
):
    """
    Network short-circuit profile helper.

    Separates transformer/busbar Ik from feeder-end Ik when cable data exists.
    """
    return audit_calculate_network_ik_profile(
        transformer_kva=transformer_kva,
        uk_percent=uk_percent,
        line_voltage_v=voltage_v,
        feeder_cable_length_m=feeder_length_m,
        feeder_phase_mm2=feeder_phase_mm2,
        feeder_pe_mm2=feeder_pe_mm2,
    )


def _audit_selectivity_status(
    upstream_icu_ka,
    downstream_icu_ka,
    selectivity_ratio,
    rule_source="catalog",
    data_quality="EXACT",
):
    """
    Selectivity provenance helper.

    Prevents missing/approximate selectivity data from being silently
    treated as fully verified.
    """
    return audit_evaluate_selectivity_status(
        upstream_icu_ka=upstream_icu_ka,
        downstream_icu_ka=downstream_icu_ka,
        selectivity_ratio=selectivity_ratio,
        rule_source=rule_source,
        data_quality=data_quality,
    )
# --- end audit safe helpers ---
