# -*- coding: utf-8 -*-
"""تحلیل‌گر منحنی‌های قطع (TCC Analyzer) — نسخه پکیجی با محاسبه ریاضی تقاطع منحنی‌ها.

برخلاف نسخه اولیه (چندجمله‌ای هاردکد)، این نسخه مستقیماً از منحنی‌های واقعی
trip_curves (نقاط دیتاشیت یا مدل پارامتری k/I^alpha) استفاده می‌کند:

  • trip_time_s(series, in_a, current_a): زمان قطع در جریان دلخواه (درونیابی لگاریتمی)
  • find_intersection(upstream, downstream): جریان تقاطع دو منحنی t-I با
    جستجوی دوبخشی در فضای لگاریتمی — دقیق تا ~۱٪
  • evaluate_pair(up, down, ik_ka): وضعیت سلکتیویته بر مبنای تقاطع واقعی منحنی‌ها
    (همیشه PRELIMINARY — داده منحنی هرگز «تأییدشده سازنده» صادر نمی‌کند؛ F-003)

نمودار SVG با دقت بالا در outputs.TccGenerator رسم می‌شود و نقطه تقاطع روی آن
علامت‌گذاری می‌گردد.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from lv_assist.catalog import TripCurveRepository
from lv_assist.i18n import tr
from lv_assist.models import CatalogDevice

GRID_MIN_MULT = 1.05     # کف محدوده حرارتی (I/In)
GRID_MAX_MULT = 100.0    # سقف جستجوی تقاطع (خارج از این محدوده ناحیه آنی است)
GRID_POINTS = 220        # دقت نمونه‌برداری لگاریتمی


@dataclass
class CurveIntersection:
    """نتیجه تحلیل تقاطع دو منحنی قطع."""
    intersection_a: Optional[float]      # جریان تقاطع (A)؛ None یعنی تقاطع در محدوده نیست
    intersection_s: Optional[float]      # زمان در نقطه تقاطع
    limit_ka: Optional[float]            # حد سلکتیویته تخمینی (kA) = جریان تقاطع
    total_selective_to_ik: Optional[bool]  # آیا تا Ik هرگز تقاطع نمی‌کنند (سلکتیویته کامل تخمینی)
    note: str = ""


class TccAnalyzer:
    """موتور ریاضی مقایسه t-I برای سلکتیویته بالادست/پایین‌دست."""

    # ------------------------------------------------------------- زمان قطع
    @staticmethod
    def trip_time_s(series: str, rated_in_a: float, current_a: float) -> Optional[float]:
        """زمان قطع تخمینی (s) در جریان dataشده؛ زیر ۱.۰۵×In → None (نمی‌پرد)."""
        if not math.isfinite(rated_in_a) or not math.isfinite(current_a) or rated_in_a <= 0 or current_a <= 0:
            return None
        mult = current_a / rated_in_a
        if mult < GRID_MIN_MULT:
            return None
        return TripCurveRepository.thermal_time_s(series, mult)

    @staticmethod
    def instantaneous_pickup_a(series: str, rated_in_a: float) -> float:
        im_min_a, _ = TripCurveRepository.instantaneous_band_a(series, rated_in_a)
        return im_min_a

    # ------------------------------------------------------------- تقاطع منحنی‌ها
    @classmethod
    def _delta_log_t(cls, up: CatalogDevice, down: CatalogDevice, current_a: float) -> float:
        """log10(t_up) - log10(t_down) در ناحیه حرارتی؛ Δ>0 یعنی پایین‌دست سریع‌تر (سلکتیو)."""
        t_up = cls.trip_time_s(up.series, up.rated_current_in_a, current_a)
        t_down = cls.trip_time_s(down.series, down.rated_current_in_a, current_a)
        t_up = t_up if t_up and t_up > 0 else 1e-3
        t_down = t_down if t_down and t_down > 0 else 1e-3
        return math.log10(t_up) - math.log10(t_down)

    @classmethod
    def find_intersection(cls, upstream: CatalogDevice, downstream: CatalogDevice) -> CurveIntersection:
        """جریان تقاطع مؤثر دو منحنی t-I — جایی که هماهنگی بالادست/پایین‌دست تمام می‌شود.

        منطق مهندسی:
        ۱. در پنجره حرارتی مشترک [max(In)·1.05 تا min(Im_up، Im_down)) اگر Δ از مثبت به
           منفی بگذرد، جریان تقاطع با جستجوی دوبخشی لگاریتمی (دقت ~۰.۵٪) پیدا می‌شود.
        ۲. اگر در کل پنجره حرارتی Δ>0 بماند، هماهنگی تا ورود بالادست به ناحیه آنی
           ادامه دارد → حد = Im,min بالادست.
        ۳. اگر از ابتدا Δ≤0 باشد (بالادست هم‌زمان یا سریع‌تر می‌پرد) سلکتیویته ندارد.
        """
        up_in, down_in = upstream.rated_current_in_a, downstream.rated_current_in_a
        if up_in <= 0 or down_in <= 0:
            return CurveIntersection(None, None, None, None, "invalid_rated_current")
        if up_in <= down_in:
            return CurveIntersection(None, None, 0.0, False,
                                     "upstream_not_larger_than_downstream")

        up_im = cls.instantaneous_pickup_a(upstream.series, up_in)
        down_im = cls.instantaneous_pickup_a(downstream.series, down_in)
        i_lo = max(up_in, down_in) * GRID_MIN_MULT
        i_end = min(up_im, down_im)

        if i_end > i_lo:
            d_lo = cls._delta_log_t(upstream, downstream, i_lo)
            if d_lo <= 0.0:
                return CurveIntersection(i_lo, cls.trip_time_s(upstream.series, up_in, i_lo),
                                         round(i_lo / 1000.0, 2), False, "overlap_from_start")
            # جستجوی تغییر علامت Δ در بازه لگاریتمی
            lo, hi = i_lo, i_end
            if cls._delta_log_t(upstream, downstream, i_end * 0.999) > 0.0:
                # کل پنجره حرارتی سلکتیو → حد در ورود بالادست به ناحیه آنی
                return CurveIntersection(up_im, 0.02, round(up_im / 1000.0, 2), False,
                                         "thermal_window_selective_limit_at_instant_pickup")
            for _ in range(40):
                mid = math.sqrt(lo * hi)
                if cls._delta_log_t(upstream, downstream, mid) > 0.0:
                    lo = mid
                else:
                    hi = mid
                if hi / lo < 1.005:
                    break
            cross_a = math.sqrt(lo * hi)
            return CurveIntersection(round(cross_a, 1),
                                     cls.trip_time_s(upstream.series, up_in, cross_a),
                                     round(cross_a / 1000.0, 2), False, "curve_intersection")

        # پنجره حرارتی وارونه: پایین‌دست خیلی زود آنی می‌شود → حد همان Im بالادست است
        if down_im < up_im:
            return CurveIntersection(up_im, 0.02, round(up_im / 1000.0, 2), False,
                                     "downstream_instant_first_limit_at_upstream_pickup")
        return CurveIntersection(i_lo, cls.trip_time_s(upstream.series, up_in, i_lo),
                                 round(i_lo / 1000.0, 2), False, "overlap_from_start")

    # ------------------------------------------------------------- ارزیابی زوج
    @classmethod
    def evaluate_pair(cls, upstream: CatalogDevice, downstream: CatalogDevice,
                      prospective_ik_ka: Optional[float]) -> Tuple[str, Optional[float], str]:
        """ارزیابی تخمینی بر مبنای تقاطع منحنی — خروجی: (state_tag, limit_ka, note).

        state_tag: TOTAL_ESTIMATED / PARTIAL / NONE / UNKNOWN
        این ارزیابی هرگز جای قواعد تأییدشده سازنده را نمی‌گیرد (F-003).
        """
        inter = cls.find_intersection(upstream, downstream)
        if inter.limit_ka is None:
            return ("UNKNOWN", None, tr("tcc_unknown_note"))
        if inter.limit_ka <= 0.0:
            return ("NONE", 0.0, tr("tcc_none_note",
                                    reason=tr("tcc_reason_" + (
                                        inter.note if inter.note.startswith("upstream_not")
                                        else "other"))))
        if prospective_ik_ka is not None and inter.limit_ka >= prospective_ik_ka:
            return ("TOTAL_ESTIMATED", inter.limit_ka,
                    tr("tcc_cross_above_ik_note", a=inter.limit_ka, b=prospective_ik_ka))
        return ("PARTIAL", inter.limit_ka, tr("tcc_partial_note", a=inter.limit_ka))
