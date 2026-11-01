# -*- coding: utf-8 -*-
"""انتخاب و صحت‌سنجی شینه اصلی بر اساس IEC 61439-1:
جریان‌دهی پیوسته (بند 10.10)، تحمل اتصال کوتاه Icw/Ipk (بند 10.11)
و فاصله ساپورت‌ها در برابر نیروهای الکترودینامیکی (پیوست D)."""
import math
from typing import List, Optional, Tuple

from lv_assist.models import BusbarResult, ValidationResult, ValidationStatus
from lv_assist.i18n import tr


class BusbarEngine:
    # ظرفیت جریان‌دهی پیوسته شینه‌های مسی رنگ‌شده (هر فاز یک شینه، +35K)
    # بر اساس جداول مرجع سازندگان (DIN 43671 / Rittal) — مقادیر تیپیکال
    CU_RATINGS: List[Tuple[float, float, float]] = [
        (15.0, 3.0, 162.0), (20.0, 3.0, 198.0), (20.0, 5.0, 274.0),
        (20.0, 10.0, 427.0), (25.0, 5.0, 327.0), (30.0, 5.0, 379.0),
        (30.0, 10.0, 573.0), (40.0, 5.0, 482.0), (40.0, 10.0, 715.0),
        (50.0, 5.0, 583.0), (50.0, 10.0, 852.0), (60.0, 5.0, 688.0),
        (60.0, 10.0, 982.0), (80.0, 5.0, 894.0), (80.0, 10.0, 1231.0),
        (100.0, 5.0, 1090.0), (100.0, 10.0, 1464.0),
    ]
    K_CU = 159.0            # A·s^0.5/mm² (IEC 60865-1: مس، 65→300°C)
    SIGMA_ALLOW = 120.0     # N/mm² تنش مجاز مس با ضریب اطمینان
    PHASE_SPACING_M = 0.06  # فاصله فازها (متر)
    RHO_CU_OHM_MM2_M = 22.3  # مقاومت ویژه مس در دمای کارکرد ~80°C (Ω·mm²/m)
    X_MOHM_M = 0.15          # راکتانس تیپیکال شینه LV (mΩ/m، فاصله فاز ~60mm)
    MAX_BUSBAR_DU_PCT = 1.5  # سقف طراحی افت ولتاژ شینه (عمل مهندسی رایج)

    @staticmethod
    def _peak_factor(icw_ka: float) -> float:
        """ضریب n = Ipk/Icw طبق جدول 101 IEC 61439-1."""
        if icw_ka <= 5.0: return 1.5
        if icw_ka <= 10.0: return 1.7
        if icw_ka <= 20.0: return 2.0
        if icw_ka <= 50.0: return 2.1
        return 2.2

    @staticmethod
    def _kappa_iec60909(ik_ka: float) -> float:
        if ik_ka <= 5.0: return 1.41
        if ik_ka <= 10.0: return 1.7
        if ik_ka <= 20.0: return 1.9
        if ik_ka <= 50.0: return 2.0
        return 2.2

    @classmethod
    def _bar_withstand(cls, width_mm: float, thick_mm: float) -> Tuple[float, float, float]:
        """(Icw یک ثانیه kA، Ipk kA، ممان مقاومت W در mm³)"""
        s_mm2 = width_mm * thick_mm
        icw = s_mm2 * cls.K_CU / 1000.0
        ipk = cls._peak_factor(icw) * icw
        w_mm3 = thick_mm * width_mm ** 2 / 6.0
        return icw, ipk, w_mm3

    @classmethod
    def _max_support_spacing_mm(cls, ipk_req_ka: float, w_mm3: float) -> float:
        """حداکثر فاصله ساپورت از نیروی الکترودینامیکی سه‌فاز (IEC 61439-1 پیوست D)."""
        f_n_per_m = 0.173 * ipk_req_ka ** 2 / cls.PHASE_SPACING_M
        if f_n_per_m <= 0.0:
            return 1000.0
        l_m = math.sqrt(cls.SIGMA_ALLOW * 8.0 * w_mm3 * 1e-3 / f_n_per_m)
        return min(1000.0, l_m * 1000.0)

    @classmethod
    def _choose_bar(cls, design_current_a: float, ik_ka: Optional[float],
                    req_ipk: Optional[float]) -> Tuple[Tuple[float, float, float], bool]:
        """کوچک‌ترین شینه‌ای که جریان (و در صورت معلوم بودن Ik، تحمل Icw/Ipk) را تأمین کند."""
        cands = [(w, t, r) for (w, t, r) in cls.CU_RATINGS if r >= design_current_a]
        if not cands:
            return (100.0, 10.0, 1464.0), False
        if ik_ka is None:
            return cands[0], True
        for w, t, r in cands:
            icw, ipk, _ = cls._bar_withstand(w, t)
            if icw >= ik_ka and ipk >= (req_ipk or 0.0):
                return (w, t, r), True
        return cands[-1], False

    @classmethod
    def select(cls, design_current_a: float, ik_ka: Optional[float], panel_width_mm: float,
               voltage_v: float = 400.0, cos_phi: float = 1.0,
               ik_total_ka: Optional[float] = None, ip_total_ka: Optional[float] = None) -> BusbarResult:
        """انتخاب شینه با جریان و تحمل اتصال کوتاه کل (شبکه + موتورها) و محاسبه افت ولتاژ.

        ik_total_ka/ip_total_ka: مجموع مشارکت شبکه و موتورها (IEC 60909)؛ اگر داده نشود
        از ik_ka شبکه با ضریب پیک κ استاندارد استفاده می‌شود."""
        vals: List[ValidationResult] = []
        sc_ik = ik_total_ka if ik_total_ka is not None else ik_ka
        if sc_ik is None:
            req_ipk = None
        elif ip_total_ka is not None:
            req_ipk = round(ip_total_ka, 1)
        else:
            req_ipk = round(cls._kappa_iec60909(sc_ik) * math.sqrt(2.0) * sc_ik, 1)
        (w, t, rating), current_ok = cls._choose_bar(design_current_a, sc_ik, req_ipk)

        # ۱. جریان‌دهی پیوسته (بند 10.10)
        vals.append(ValidationResult(
            rule_id="RULE-BUS-024", feeder_id="PANEL", standard_ref="IEC 61439-1",
            status=ValidationStatus.COMPLETED if current_ok else ValidationStatus.ERROR,
            description=tr("val_bus_024_desc", a=round(design_current_a, 1)) if current_ok
                        else tr("val_bus_024_over_desc", a=round(design_current_a, 1)),
            supporting_evidence=tr("val_bus_024_ev", a=rating, b=f"{w:g}x{t:g}"),
            consequence=tr("val_bus_024_cons"),
            recommended_action=tr("val_no_action") if current_ok else tr("val_bus_024_over_action")))

        icw, ipk, w_mm3 = cls._bar_withstand(w, t)
        spec = f"Cu {w:g}x{t:g} mm (3P+N)"
        max_span: Optional[float] = None
        supports = 2

        if sc_ik is None:
            for rule_id in ("RULE-BUS-025", "RULE-BUS-026", "RULE-BUS-027"):
                vals.append(ValidationResult(
                    rule_id=rule_id, feeder_id="PANEL", standard_ref="IEC 61439-1",
                    status=ValidationStatus.INSUFFICIENT_DATA, description=tr("val_bus_noik_desc"),
                    supporting_evidence="-", consequence=tr("val_bus_noik_cons"),
                    recommended_action=tr("val_bus_noik_action")))
        else:
            sc_ok = icw >= sc_ik and ipk >= req_ipk

            # ۲. تحمل حرارتی Icw یک ثانیه ≥ Ik (بند 10.11)
            vals.append(ValidationResult(
                rule_id="RULE-BUS-025", feeder_id="PANEL", standard_ref="IEC 61439-1",
                status=ValidationStatus.COMPLETED if icw >= sc_ik else ValidationStatus.ERROR,
                description=tr("val_bus_025_desc") if icw >= sc_ik else tr("val_bus_025_err_desc"),
                supporting_evidence=tr("val_bus_025_ev", a=round(icw, 1), b=sc_ik),
                consequence=tr("val_bus_025_cons"),
                recommended_action=tr("val_no_action") if icw >= sc_ik else tr("val_bus_025_action")))

            # ۳. تحمل پیک Ipk ≥ κ·√2·Ik
            vals.append(ValidationResult(
                rule_id="RULE-BUS-026", feeder_id="PANEL", standard_ref="IEC 61439-1",
                status=ValidationStatus.COMPLETED if ipk >= req_ipk else ValidationStatus.ERROR,
                description=tr("val_bus_026_desc") if ipk >= req_ipk else tr("val_bus_026_err_desc"),
                supporting_evidence=tr("val_bus_026_ev", a=round(ipk, 1), b=req_ipk),
                consequence=tr("val_bus_026_cons"),
                recommended_action=tr("val_no_action") if ipk >= req_ipk else tr("val_bus_026_action")))

            # ۴. فاصله ساپورت‌ها از نیروی الکترودینامیکی
            max_span = round(cls._max_support_spacing_mm(req_ipk, w_mm3), 0)
            supports = math.ceil(max(1.0, panel_width_mm) / max(max_span, 1.0)) + 1
            if supports <= 3:
                sup_status, sup_desc, sup_action = ValidationStatus.COMPLETED, tr("val_bus_027_desc"), tr("val_no_action")
            elif supports <= 5:
                sup_status, sup_desc, sup_action = ValidationStatus.WARNING, tr("val_bus_027_warn_desc"), tr("val_bus_027_action")
            else:
                sup_status, sup_desc, sup_action = ValidationStatus.ERROR, tr("val_bus_027_err_desc"), tr("val_bus_027_action")
            vals.append(ValidationResult(
                rule_id="RULE-BUS-027", feeder_id="PANEL", standard_ref="IEC 61439-1",
                status=sup_status, description=sup_desc,
                supporting_evidence=tr("val_bus_027_ev", a=max_span, b=supports, c=panel_width_mm),
                consequence=tr("val_bus_027_cons"), recommended_action=sup_action))

        # ۵. افت ولتاژ شینه: R از مقاومت ویژه مس در دمای کارکرد، X تیپیکال،
        # طول = امتداد افقی شینه معادل عرض پنل (تقریب محافظه‌کارانه)
        r_mohm_m = round(cls.RHO_CU_OHM_MM2_M / (w * t), 4)
        x_mohm_m = cls.X_MOHM_M
        length_m = panel_width_mm / 1000.0
        sin_phi = math.sqrt(max(0.0, 1.0 - min(1.0, cos_phi) ** 2))
        du_v = math.sqrt(3.0) * design_current_a * length_m * (r_mohm_m * cos_phi + x_mohm_m * sin_phi) / 1000.0
        du_pct = (du_v / voltage_v) * 100.0 if voltage_v > 0.0 else 0.0
        du_ok = du_pct <= cls.MAX_BUSBAR_DU_PCT
        vals.append(ValidationResult(
            rule_id="RULE-BUS-028", feeder_id="PANEL", standard_ref="IEC 61439-1",
            status=ValidationStatus.COMPLETED if du_ok else ValidationStatus.WARNING,
            description=tr("val_bus_028_desc") if du_ok else tr("val_bus_028_warn_desc", a=cls.MAX_BUSBAR_DU_PCT),
            supporting_evidence=tr("val_bus_028_ev", r=r_mohm_m, x=x_mohm_m, l=round(length_m, 2),
                                   v=round(du_v, 2), pct=round(du_pct, 3)),
            consequence=tr("val_bus_028_cons"),
            recommended_action=tr("val_no_action") if du_ok else tr("val_bus_028_action")))

        return BusbarResult(
            spec=spec, rating_a=rating, cross_section_mm2=w * t,
            icw_1s_ka=round(icw, 1), ipk_ka=round(ipk, 1),
            required_ipk_ka=req_ipk, max_support_spacing_mm=max_span,
            required_supports=supports, r_mohm_m=r_mohm_m, x_mohm_m=x_mohm_m,
            length_m=round(length_m, 2), voltage_drop_v=round(du_v, 2),
            voltage_drop_pct=round(du_pct, 3), validations=vals)
