# -*- coding: utf-8 -*-
"""بهینه‌سازی چیدمان فیزیکی پانل: جانمایی تجهیزات روی ریل DIN با ابعاد کاتالوگ، فواصل IEC 61439-2 و تفکیک سینی/درب."""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from lv_assist.models import (
    ProjectSpec, FeederCalcOutput, PanelSummaryOutput, CatalogDevice,
    LoadType, LayoutDevice, LayoutRow, PanelLayoutResult, ValidationResult, ValidationStatus,
)
from lv_assist.i18n import tr


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PanelLayoutGenerator:
    """جانمایی تجهیزات در چهار ناحیه: خنک‌سازی، قدرت، PFC و کنترل (با کانال سیم‌کشی، حریم قوس و فضای رزرو)."""

    HORIZONTAL_DUCT_HEIGHT_MM = 50.0       # داکت افقی بین ردیف‌ها
    VERTICAL_DUCT_WIDTH_MM = 60.0          # داکت عمودی دو طرف سینی مونتاژ
    MCCB_ARC_CLEARANCE_MM = 80.0           # حریم قوس/تخلیه گاز کلیدهای قدرت
    CABLE_GLAND_BOTTOM_ZONE_MM = 200.0     # ناحیه گلند و ترمینال پایین تابلو
    BUS_BAR_ZONE_HEIGHT_MM = 120.0         # ناحیه شینه اصلی (بالا)
    DEVICE_HORIZONTAL_GAP_MM = 12.0        # حداقل فاصله افقی تهویه و نصب بین دو تجهیز روی ریل
    RAIL_SIDE_PADDING_MM = 15.0            # حاشیه ایمنی دو سر ریل تا داکت عمودی
    MAX_FILL_PCT = 85.0                    # حد مجاز اشغال ریل (IEC 61439-2)
    SPARE_SPACE_PCT = 20.0                 # فضای رزرو الزامی
    ZONE_ORDER = ["COOLING", "POWER", "PFC", "CONTROL"]

    # حداقل فواصل هوایی عمودی (Clearance) بر اساس نوع تجهیز طبق IEC 61439-2
    DEFAULT_CLEARANCE_BY_TYPE: Dict[str, float] = {
        "ACB": 120.0,
        "MCCB": 80.0,
        "VFD": 100.0,
        "SOFT_STARTER": 100.0,
        "PSU": 35.0,
        "CONTACTOR": 25.0,
        "MCB": 25.0,
        "MPCB": 30.0,
    }

    @classmethod
    def _form_partition_factor(cls, form: str) -> float:
        f = str(form or "").lower()
        if f.startswith("form 4"):
            return 1.15
        if f.startswith("form 3"):
            return 1.10
        if f.startswith("form 2"):
            return 1.05
        return 1.0

    @classmethod
    def _dev(cls, tag: str, dev: Optional[CatalogDevice], zone: str, clearance: float = 0.0,
             qty: int = 1, extra_loss_w: float = 0.0) -> List[LayoutDevice]:
        if dev is None or dev.width_mm <= 0:
            return []
        dtype = str(getattr(dev, "device_type", "") or "").upper()
        min_clr = cls.DEFAULT_CLEARANCE_BY_TYPE.get(dtype, 20.0)
        if dtype == "MCCB":
            min_clr = max(min_clr, cls.MCCB_ARC_CLEARANCE_MM)
        clearance = max(clearance, min_clr)
        return [LayoutDevice(
            tag=tag, part_number=dev.part_number, zone=zone,
            width_mm=dev.width_mm * qty + 10.0 * (qty - 1),
            height_mm=dev.height_mm, depth_mm=dev.depth_mm,
            loss_w=dev.power_loss_w * qty + extra_loss_w,
            clearance_mm=clearance,
        )]

    @classmethod
    def _collect_devices(cls, project: ProjectSpec, feeders: List[FeederCalcOutput],
                         summary: PanelSummaryOutput) -> List[LayoutDevice]:
        devs: List[LayoutDevice] = []
        devs += cls._dev("-E1", summary.selected_fan, "COOLING")
        devs += cls._dev("-Q0", summary.main_breaker, "POWER")
        devs += cls._dev("-F9", summary.selected_spd, "POWER")
        for i, f in enumerate(feeders, start=1):
            devs += cls._dev(f"-Q{i}", f.selected_protection, "POWER",
                             extra_loss_w=f.total_feeder_loss_w)
            if f.load_type == LoadType.MOTOR_STAR_DELTA:
                devs += cls._dev(f"-K{i}M", f.selected_contactor_main, "POWER")
                devs += cls._dev(f"-K{i}D", f.selected_contactor_delta, "POWER")
                devs += cls._dev(f"-K{i}Y", f.selected_contactor_star, "POWER")
                devs += cls._dev(f"-F{i}", f.selected_bimetal, "POWER")
                devs += cls._dev(f"-K{i}T", f.selected_timer_yd, "CONTROL")
            elif f.load_type == LoadType.MOTOR_DOL:
                devs += cls._dev(f"-K{i}", f.selected_contactor_main, "POWER")
            devs += cls._dev(f"-G{i}", f.selected_soft_starter, "POWER", clearance=100.0)
            devs += cls._dev(f"-U{i}", f.selected_vfd, "POWER", clearance=100.0)
        n_steps = len(summary.cap_bank_steps) or 1
        devs += cls._dev("-Qcap", summary.cap_bank_protection, "PFC")
        devs += cls._dev("-Kcap", summary.cap_bank_contactor, "PFC", qty=n_steps)
        devs += cls._dev("-Lcap", summary.cap_bank_reactor_dev, "PFC", qty=n_steps)
        devs += cls._dev("-Ccap", summary.cap_bank_module_dev, "PFC", qty=n_steps)
        devs += cls._dev("-Q01", summary.selected_psu_primary_mcb, "CONTROL")
        devs += cls._dev("-G1", summary.selected_psu_24v, "CONTROL")
        devs += cls._dev("-F0", summary.selected_dc_selectivity_mod, "CONTROL")
        return devs

    @classmethod
    def generate(cls, project: ProjectSpec, feeders: List[FeederCalcOutput],
                 summary: PanelSummaryOutput, spare_space_pct: float = 20.0) -> PanelLayoutResult:
        panel_w = summary.estimated_panel_width_mm
        panel_h = summary.estimated_panel_height_mm
        panel_d = summary.estimated_panel_depth_mm
        if summary.selected_enclosure is not None:
            panel_w = panel_w or summary.selected_enclosure.width_mm
            panel_h = panel_h or summary.selected_enclosure.height_mm
            panel_d = panel_d or summary.selected_enclosure.depth_mm

        usable = max(panel_w - 2.0 * cls.VERTICAL_DUCT_WIDTH_MM, 100.0)
        effective_rail_w = max(usable - 2.0 * cls.RAIL_SIDE_PADDING_MM, 80.0)

        devices = cls._collect_devices(project, feeders, summary)
        rows: List[LayoutRow] = []
        y_mm = cls.BUS_BAR_ZONE_HEIGHT_MM
        row_no = 0
        for zone in cls.ZONE_ORDER:
            zone_devs = sorted(
                [d for d in devices if d.zone == zone],
                key=lambda d: (-d.clearance_mm, -d.loss_w, -d.width_mm),
            )
            row_devs: List[LayoutDevice] = []
            row_w = 0.0
            for d in zone_devs:
                gap = cls.DEVICE_HORIZONTAL_GAP_MM if row_devs else 0.0
                if row_devs and (row_w + gap + d.width_mm > effective_rail_w):
                    row_h = max(x.height_mm for x in row_devs) + max(x.clearance_mm for x in row_devs)
                    row_no += 1
                    rows.append(LayoutRow(row_no=row_no, zone=zone, y_mm=y_mm,
                                          used_width_mm=round(row_w, 1), devices=row_devs))
                    y_mm += row_h + cls.HORIZONTAL_DUCT_HEIGHT_MM
                    row_devs, row_w = [], 0.0
                    gap = 0.0
                row_devs.append(d)
                row_w += gap + d.width_mm
            if row_devs:
                row_h = max(x.height_mm for x in row_devs) + max(x.clearance_mm for x in row_devs)
                row_no += 1
                rows.append(LayoutRow(row_no=row_no, zone=zone, y_mm=y_mm,
                                      used_width_mm=round(row_w, 1), devices=row_devs))
                y_mm += row_h + cls.HORIZONTAL_DUCT_HEIGHT_MM

        form_factor = cls._form_partition_factor(project.internal_separation_form)
        total_w = sum(d.width_mm for d in devices) * form_factor
        n_rows = max(len(rows), 1)
        spare_frac = max(0.0, min(0.9, spare_space_pct / 100.0))
        fill_pct = round(100.0 * total_w / max(usable * n_rows * (1.0 - spare_frac), 1.0), 1)

        validations = cls._build_validations(project, summary, devices, rows, fill_pct, usable,
                                             spare_space_pct, form_factor)
        return PanelLayoutResult(
            panel_width_mm=panel_w, panel_height_mm=panel_h, panel_depth_mm=panel_d,
            usable_width_mm=round(usable, 1), rows=rows, fill_factor_pct=fill_pct,
            total_loss_w=round(summary.total_power_loss_w, 1),
            natural_dissipation_w=round(summary.enclosure_natural_dissipation_w, 1),
            spare_space_pct=spare_space_pct, form_partition_factor=form_factor,
            validations=validations,
        )

    @classmethod
    def _build_validations(cls, project: ProjectSpec, summary: PanelSummaryOutput,
                           devices: List[LayoutDevice], rows: List[LayoutRow],
                           fill_pct: float, usable: float, spare_space_pct: float,
                           form_factor: float) -> List[ValidationResult]:
        vals: List[ValidationResult] = []

        if fill_pct > 100.0:
            fill_status, fill_action = ValidationStatus.ERROR, tr("val_lay_fill_action")
        elif fill_pct > cls.MAX_FILL_PCT:
            fill_status, fill_action = ValidationStatus.WARNING, tr("val_lay_fill_action")
        else:
            fill_status, fill_action = ValidationStatus.COMPLETED, tr("val_no_action")
        vals.append(ValidationResult(
            rule_id="RULE-LAY-020", feeder_id="PANEL", standard_ref="IEC 61439-2",
            status=fill_status,
            description=tr("val_lay_fill_desc"),
            supporting_evidence=tr("val_lay_fill_ev", a=fill_pct, b=usable),
            consequence=tr("val_lay_fill_cons"),
            recommended_action=fill_action,
        ))

        used_h = max((r.y_mm + max(d.height_mm for d in r.devices) + max(d.clearance_mm for d in r.devices)
                      for r in rows), default=0.0)
        avail_h = (summary.estimated_panel_height_mm or 0.0) - cls.CABLE_GLAND_BOTTOM_ZONE_MM - cls.BUS_BAR_ZONE_HEIGHT_MM
        spare_ok = fill_pct <= 100.0 - spare_space_pct
        height_ok = used_h <= avail_h
        vals.append(ValidationResult(
            rule_id="RULE-LAY-024", feeder_id="PANEL", standard_ref="IEC 61439-2",
            status=ValidationStatus.COMPLETED if (spare_ok and height_ok) else ValidationStatus.WARNING,
            description=tr("val_lay_spare_desc"),
            supporting_evidence=tr("val_lay_spare_ev", a=fill_pct, b=100.0 - spare_space_pct,
                                   c=round(used_h, 1), d=round(avail_h, 1),
                                   e=cls.HORIZONTAL_DUCT_HEIGHT_MM, f=cls.VERTICAL_DUCT_WIDTH_MM,
                                   g=cls.CABLE_GLAND_BOTTOM_ZONE_MM, h=form_factor),
            consequence=tr("val_lay_spare_cons"),
            recommended_action=tr("val_no_action" if (spare_ok and height_ok) else "val_lay_spare_action"),
        ))

        dissip = summary.enclosure_natural_dissipation_w
        if summary.selected_fan is not None:
            dissipation_w = dissip + summary.selected_fan.airflow_m3h * 3.0
        else:
            dissipation_w = dissip
        loss_ok = summary.total_power_loss_w <= dissipation_w
        vals.append(ValidationResult(
            rule_id="RULE-LAY-021", feeder_id="PANEL", standard_ref="IEC 61439-2 / IEC TR 60890",
            status=ValidationStatus.COMPLETED if loss_ok else ValidationStatus.WARNING,
            description=tr("val_lay_loss_desc"),
            supporting_evidence=tr("val_lay_loss_ev", a=summary.total_power_loss_w, b=dissipation_w),
            consequence=tr("val_lay_loss_cons"),
            recommended_action=tr("val_no_action" if loss_ok else "val_lay_loss_action"),
        ))

        max_depth = max((d.depth_mm for d in devices), default=0.0)
        # لحاظ کردن 30mm فاصله نصب سینی و تجهیزات روی درب (پوشانده شدن تداخل عمق)
        depth_ok = max_depth <= (summary.estimated_panel_depth_mm or 0) - 30.0
        vals.append(ValidationResult(
            rule_id="RULE-LAY-022", feeder_id="PANEL", standard_ref="IEC 61439-2",
            status=ValidationStatus.COMPLETED if depth_ok else ValidationStatus.WARNING,
            description=tr("val_lay_depth_desc"),
            supporting_evidence=tr("val_lay_depth_ev", a=max_depth, b=summary.estimated_panel_depth_mm),
            consequence=tr("val_lay_depth_cons"),
            recommended_action=tr("val_no_action" if depth_ok else "val_lay_depth_action"),
        ))

        zones_seen = [r.zone for r in rows]
        separated = not ("CONTROL" in zones_seen and "POWER" in zones_seen
                         and zones_seen.index("CONTROL") < zones_seen.index("POWER"))
        vals.append(ValidationResult(
            rule_id="RULE-LAY-023", feeder_id="PANEL", standard_ref="IEC 61439-2",
            status=ValidationStatus.COMPLETED if separated else ValidationStatus.WARNING,
            description=tr("val_lay_zone_desc"),
            supporting_evidence=tr("val_lay_zone_ev"),
            consequence=tr("val_lay_zone_cons"),
            recommended_action=tr("val_no_action" if separated else "val_lay_zone_action"),
        ))
        return vals

    # ---------------------------------------------------------------- SVG front view (Mounting Plate + Separate Door Region)
    @staticmethod
    def _zone_colors(zone: str) -> Tuple[str, str]:
        return {
            "POWER": ("#1F4E78", "#EBF5FB"),
            "CONTROL": ("#117A65", "#E8F8F5"),
            "PFC": ("#7D3C98", "#F4ECF7"),
            "COOLING": ("#566573", "#F2F3F4"),
        }.get(zone, ("#566573", "#F2F3F4"))

    @classmethod
    def _collect_door_devices(cls, project: ProjectSpec, feeders: List[FeederCalcOutput],
                              summary: PanelSummaryOutput) -> List[str]:
        door: List[str] = []
        if project.plc_hmi_24vdc_power_w > 0:
            door.append(tr("lay_door_hmi"))
        for i, f in enumerate(feeders, start=1):
            if f.load_type in (LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA,
                               LoadType.MOTOR_SOFT_STARTER, LoadType.MOTOR_VFD):
                door.append(f"-S{i}0/-S{i}1")
                door.append(f"-H{i}1/-H{i}2")
        door.append(tr("lay_door_estop"))
        return door

    @staticmethod
    def _parse_busbar_dims(spec_str: str) -> Tuple[float, float]:
        """استخراج عرض و ضخامت واقعی شینه مسی از رشته (مثلاً 'Cu 20x10 mm' -> (20.0, 10.0))."""
        import re
        m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", str(spec_str or ""))
        if m:
            return float(m.group(1)), float(m.group(2))
        return 20.0, 10.0

    @staticmethod
    def _draw_device_symbol_overlay(x: float, y: float, w: float, h: float, tag: str, border: str) -> str:
        """ترسیم جزئیات عملکردی و نماد گرافیکی تجهیز روی بدنه فیزیکی در نقشه جانمایی."""
        elems: List[str] = []
        # ترمینال‌های ورودی/خروجی بالا و پایین تجهیز
        term_r = min(2.2, max(1.0, w * 0.08))
        for tx in (x + w * 0.25, x + w * 0.5, x + w * 0.75):
            if w >= 12.0:
                elems.append(f'<circle cx="{tx:.1f}" cy="{y + 3.2:.1f}" r="{term_r:.1f}" fill="none" stroke="{border}" stroke-width="0.6"/>')
                elems.append(f'<circle cx="{tx:.1f}" cy="{y + h - 3.2:.1f}" r="{term_r:.1f}" fill="none" stroke="{border}" stroke-width="0.6"/>')
        # نماد عملکردی بر اساس پیشوند تگ استاندارد IEC 81346
        if tag.startswith("-Q"):
            # دستگیره قطع و وصل کلید (Toggle / Rotary Actuator) + نماد قطع کلید
            hw = min(w * 0.36, 12.0)
            hh = min(h * 0.18, 8.0)
            elems.append(f'<rect x="{x + (w - hw) / 2:.1f}" y="{y + h * 0.18:.1f}" width="{hw:.1f}" height="{hh:.1f}" fill="{border}" fill-opacity="0.18" stroke="{border}" stroke-width="0.7" rx="1"/>')
        elif tag.startswith("-K"):
            # پنجره کنتاکتور
            cw = min(w * 0.5, 14.0)
            elems.append(f'<rect x="{x + (w - cw) / 2:.1f}" y="{y + 6.0:.1f}" width="{cw:.1f}" height="4.0" fill="none" stroke="{border}" stroke-width="0.6"/>')
        elif tag.startswith("-E"):
            # پروانه فن خنک‌کننده
            cx, cy, r = x + w / 2.0, y + h / 2.0, min(w, h) * 0.32
            elems.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="{border}" stroke-width="0.7"/>')
        return "".join(elems)

    @classmethod
    def generate_svg(cls, project: ProjectSpec, feeders: List[FeederCalcOutput],
                     summary: PanelSummaryOutput) -> str:
        res = cls.generate(project, feeders, summary)
        scale = 0.36
        bus_h_px = cls.BUS_BAR_ZONE_HEIGHT_MM * scale
        duct_w_px = cls.VERTICAL_DUCT_WIDTH_MM * scale
        duct_h_px = cls.HORIZONTAL_DUCT_HEIGHT_MM * scale
        gland_h_px = cls.CABLE_GLAND_BOTTOM_ZONE_MM * scale
        gap_px = cls.DEVICE_HORIZONTAL_GAP_MM * scale
        pad_px = cls.RAIL_SIDE_PADDING_MM * scale

        mp_w_px = res.panel_width_mm * scale
        # اختصاص دو بوم مجزا (Region 1: سینی داخلی +MP1 در چپ، Region 2: درب تابلو +DR1 در راست)
        region_gap_px = 44.0
        total_svg_w = mp_w_px * 2.0 + region_gap_px + 36.0

        top_margin = 76.0
        bus_top = top_margin
        bus_bottom = bus_top + bus_h_px

        # محاسبه دقیق موقعیت عمودی ردیف‌ها بدون هیچ‌گونه همپوشانی
        row_positions: List[Tuple[LayoutRow, float, float, float]] = []
        current_y_px = bus_bottom + 14.0
        for r in res.rows:
            max_dev_h_mm = max((d.height_mm for d in r.devices), default=80.0)
            max_clr_mm = max((d.clearance_mm for d in r.devices), default=20.0)
            dev_h_px = max_dev_h_mm * scale
            clr_px = max(max_clr_mm * scale * 0.35, 8.0)
            row_box_h_px = dev_h_px + clr_px + 12.0
            row_positions.append((r, current_y_px, row_box_h_px, dev_h_px))
            current_y_px += row_box_h_px + duct_h_px + 14.0

        plate_bottom = max(current_y_px + 6.0, bus_top + (res.panel_height_mm - cls.CABLE_GLAND_BOTTOM_ZONE_MM) * scale)
        gland_bottom = plate_bottom + gland_h_px
        total_svg_h = gland_bottom + 54.0

        mp_x0 = 14.0
        door_x0 = mp_x0 + mp_w_px + region_gap_px

        parts: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_svg_w:.1f}" height="{total_svg_h:.1f}" font-family="Tahoma, Segoe UI, Arial, sans-serif">',
            f'<rect width="{total_svg_w:.1f}" height="{total_svg_h:.1f}" fill="white"/>',
            '<defs>'
            '<pattern id="ductHatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            '<rect width="7" height="7" fill="#F4F6F7"/><line x1="0" y1="0" x2="0" y2="7" stroke="#BFC9CA" stroke-width="1.2"/>'
            '</pattern>'
            '</defs>',
            f'<text x="14" y="22" font-size="15" font-weight="bold" fill="#1F4E78">{_esc(tr("lay_title"))} — {_esc(project.project_name)} ({_esc(project.panel_tag)})</text>',
            f'<text x="14" y="40" font-size="9.5" fill="#566573">{datetime.now().strftime("%Y-%m-%d %H:%M")} | {_esc(tr("lay_dims", a=res.panel_width_mm, b=res.panel_height_mm, c=res.panel_depth_mm))} | {_esc(tr("lay_fill", a=res.fill_factor_pct))} | {_esc(tr("lay_spare", a=res.spare_space_pct, b=res.form_partition_factor))} | Form: {_esc(project.internal_separation_form)}</text>',
            f'<text x="14" y="54" font-size="9.5" fill="#566573">{_esc(tr("lay_losses", a=res.total_loss_w, b=res.natural_dissipation_w, c=summary.selected_fan.part_number if summary.selected_fan else "-"))}</text>',
            # عناوین دو Region مجزا (سینی مونتاژ و درب تابلو)
            f'<text x="{mp_x0 + mp_w_px / 2:.1f}" y="{bus_top - 6:.1f}" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#1F4E78">REGION 1: MOUNTING PLATE (+MP1)</text>',
            f'<text x="{door_x0 + mp_w_px / 2:.1f}" y="{bus_top - 6:.1f}" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#117A65">REGION 2: ENCLOSURE DOOR (+DR1)</text>',
        ]

        # =====================================================================
        # REGION 1: سینی مونتاژ داخلی (+MP1)
        # =====================================================================
        # ۱. ناحیه شینه اصلی (R1) با ترسیم شینه‌های مسی با ابعاد واقعی (مثلاً Cu 20x10mm)
        parts.append(f'<rect x="{mp_x0}" y="{bus_top}" width="{mp_w_px:.1f}" height="{bus_h_px:.1f}" fill="#FEF9E7" stroke="#B7950B" stroke-width="1.4"/>')
        bus_w_mm, bus_t_mm = cls._parse_busbar_dims(summary.recommended_busbar_spec)
        bar_h_px = max(2.8, min(bus_w_mm * scale * 0.45, 7.5))
        bus_x1 = mp_x0 + duct_w_px + 10.0
        bus_x2 = mp_x0 + mp_w_px - duct_w_px - 10.0
        phases = [
            ("L1", "#C0392B", bus_top + 9.0),
            ("L2", "#D35400", bus_top + 17.5),
            ("L3", "#8E44AD", bus_top + 26.0),
            ("N",  "#2980B9", bus_top + 34.5),
        ]
        for ph_name, ph_col, py in phases:
            parts.append(f'<rect x="{bus_x1:.1f}" y="{py:.1f}" width="{bus_x2 - bus_x1:.1f}" height="{bar_h_px:.1f}" fill="{ph_col}" rx="1"/>')
            parts.append(f'<text x="{bus_x1 - 4:.1f}" y="{py + bar_h_px:.1f}" text-anchor="end" font-size="6.5" font-weight="bold" fill="{ph_col}" dir="ltr">{ph_name}</text>')
        parts.append(f'<text x="{mp_x0 + mp_w_px / 2:.1f}" y="{bus_top + 8.0:.1f}" text-anchor="middle" font-size="7.5" font-weight="bold" fill="#7D6608" dir="ltr">{_esc(tr("lay_busbar_zone"))}: {_esc(summary.recommended_busbar_spec)} ({bus_w_mm:g}x{bus_t_mm:g}mm) | PE: {_esc(summary.recommended_pe_busbar_spec)}</text>')

        # ۲. قاب اصلی سینی مونتاژ + داکت‌های عمودی چپ و راست
        parts.append(f'<rect x="{mp_x0}" y="{bus_bottom:.1f}" width="{mp_w_px:.1f}" height="{plate_bottom - bus_bottom:.1f}" fill="#FBFCFC" stroke="#1F4E78" stroke-width="1.6"/>')
        parts.append(f'<rect x="{mp_x0}" y="{bus_bottom:.1f}" width="{duct_w_px:.1f}" height="{plate_bottom - bus_bottom:.1f}" fill="url(#ductHatch)" stroke="#95A5A6" stroke-width="0.8"/>')
        parts.append(f'<rect x="{mp_x0 + mp_w_px - duct_w_px:.1f}" y="{bus_bottom:.1f}" width="{duct_w_px:.1f}" height="{plate_bottom - bus_bottom:.1f}" fill="url(#ductHatch)" stroke="#95A5A6" stroke-width="0.8"/>')

        # دیواره جداکننده فیزیکی بین شینه اصلی و ناحیه تجهیزات (Form 2b / 3b / 4)
        parts.append(f'<line x1="{mp_x0}" y1="{bus_bottom:.1f}" x2="{mp_x0 + mp_w_px:.1f}" y2="{bus_bottom:.1f}" stroke="#C0392B" stroke-width="2.0" stroke-dasharray="6,3"/>')

        plate_l = mp_x0 + duct_w_px + pad_px
        plate_r = mp_x0 + mp_w_px - duct_w_px - pad_px
        prev_zone: Optional[str] = None

        for r, ry, rh, dev_h_px in row_positions:
            border, fill = cls._zone_colors(r.zone)
            # ترسیم دیواره جداسازی فیزیکی (Partition Wall) بین زون‌های مختلف (مثلاً POWER و CONTROL)
            if prev_zone is not None and prev_zone != r.zone:
                part_y = ry - 11.0
                parts.append(f'<line x1="{mp_x0 + duct_w_px:.1f}" y1="{part_y:.1f}" x2="{mp_x0 + mp_w_px - duct_w_px:.1f}" y2="{part_y:.1f}" stroke="#C0392B" stroke-width="1.5" stroke-dasharray="5,3"/>')
                parts.append(f'<text x="{plate_r:.1f}" y="{part_y - 2.0:.1f}" text-anchor="end" font-size="6.5" font-weight="bold" fill="#C0392B" dir="ltr">PARTITION ({_esc(project.internal_separation_form)})</text>')
            prev_zone = r.zone

            # کادر ناحیه ردیف و ریل DIN استاندارد 35mm در مرکز ردیف
            parts.append(f'<rect x="{plate_l:.1f}" y="{ry:.1f}" width="{plate_r - plate_l:.1f}" height="{rh:.1f}" fill="{fill}" stroke="{border}" stroke-width="0.9" rx="3"/>')
            parts.append(f'<text x="{plate_l + 4:.1f}" y="{ry - 3.0:.1f}" font-size="8.0" font-weight="bold" fill="{border}">{_esc(tr("lay_zone_" + r.zone.lower()))} · R{r.row_no}</text>')
            rail_cy = ry + rh / 2.0
            parts.append(f'<rect x="{plate_l + 2:.1f}" y="{rail_cy - 6.0:.1f}" width="{plate_r - plate_l - 4:.1f}" height="12.0" fill="#EAEDED" stroke="#ABB2B9" stroke-width="0.6"/>')

            # داکت افقی زیر هر ردیف
            duct_y = ry + rh + 2.0
            parts.append(f'<rect x="{plate_l:.1f}" y="{duct_y:.1f}" width="{plate_r - plate_l:.1f}" height="{max(duct_h_px - 3.0, 7.0):.1f}" fill="url(#ductHatch)" stroke="#95A5A6" stroke-width="0.6"/>')

            x_cursor = plate_l + 4.0
            for d in r.devices:
                dw = d.width_mm * scale
                dh = d.height_mm * scale
                dy = ry + (rh - dh) / 2.0
                # جلوگیری تضمینی از بیرون‌زدگی از مرز راست ریل
                if x_cursor + dw > plate_r - 2.0:
                    dw = max(8.0, (plate_r - 2.0) - x_cursor)

                parts.append(f'<rect x="{x_cursor:.1f}" y="{dy:.1f}" width="{dw:.1f}" height="{dh:.1f}" fill="white" stroke="{border}" stroke-width="1.1" rx="1.5"/>')
                parts.append(cls._draw_device_symbol_overlay(x_cursor, dy, dw, dh, d.tag, border))

                cx = x_cursor + dw / 2.0
                cy = dy + dh / 2.0
                short_pn = d.part_number[:14]
                # چرخش خودکار متن برای تجهیزات باریک (مانند R2) جهت حذف کامل همپوشانی متون
                if dw < 26.0:
                    parts.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="6.5" font-weight="bold" fill="{border}" transform="rotate(-90 {cx:.1f} {cy:.1f})" dir="ltr">{_esc(d.tag)}</text>')
                elif dw < 46.0:
                    parts.append(f'<text x="{cx:.1f}" y="{cy - 2.0:.1f}" text-anchor="middle" font-size="7.5" font-weight="bold" fill="{border}" dir="ltr">{_esc(d.tag)}</text>')
                    parts.append(f'<text x="{cx:.1f}" y="{cy + 6.5:.1f}" text-anchor="middle" font-size="5.5" fill="#566573" dir="ltr">{_esc(short_pn[:9])}</text>')
                else:
                    parts.append(f'<text x="{cx:.1f}" y="{cy - 2.0:.1f}" text-anchor="middle" font-size="8.0" font-weight="bold" fill="{border}" dir="ltr">{_esc(d.tag)}</text>')
                    parts.append(f'<text x="{cx:.1f}" y="{cy + 7.5:.1f}" text-anchor="middle" font-size="6.2" fill="#566573" dir="ltr">{_esc(short_pn)}</text>')

                x_cursor += dw + gap_px

        # ۳. ناحیه گلند و شینه PE پایین تابلو (R4)
        parts.append(f'<rect x="{mp_x0}" y="{plate_bottom:.1f}" width="{mp_w_px:.1f}" height="{gland_h_px:.1f}" fill="url(#ductHatch)" stroke="#95A5A6" stroke-width="1.2"/>')
        pe_y = plate_bottom + 12.0
        parts.append(f'<rect x="{bus_x1:.1f}" y="{pe_y:.1f}" width="{bus_x2 - bus_x1:.1f}" height="4.5" fill="#27AE60" stroke="#F1C40F" stroke-width="0.9"/>')
        parts.append(f'<text x="{mp_x0 + mp_w_px / 2:.1f}" y="{plate_bottom + gland_h_px / 2 + 4:.1f}" text-anchor="middle" font-size="9" font-weight="bold" fill="#566573">{_esc(tr("lay_gland_zone"))} — {cls.CABLE_GLAND_BOTTOM_ZONE_MM:g} mm (PE Bar Installed)</text>')

        # =====================================================================
        # REGION 2: نمای مجزای درب تابلو (+DR1) با چیدمان استاندارد شستی‌ها، چراغ‌ها و HMI
        # =====================================================================
        door_h_total = gland_bottom - bus_top
        parts.append(f'<rect x="{door_x0:.1f}" y="{bus_top:.1f}" width="{mp_w_px:.1f}" height="{door_h_total:.1f}" fill="#FDFEFE" stroke="#117A65" stroke-width="1.6" rx="2"/>')
        # لولاها (سمت چپ درب) و دستگیره قفل (سمت راست درب)
        for hy in (bus_top + 45.0, bus_top + door_h_total / 2.0, gland_bottom - 45.0):
            parts.append(f'<rect x="{door_x0 - 4.0:.1f}" y="{hy - 8.0:.1f}" width="6.0" height="16.0" fill="#566573" rx="1"/>')
        parts.append(f'<rect x="{door_x0 + mp_w_px - 18.0:.1f}" y="{bus_top + door_h_total / 2.0 - 20.0:.1f}" width="8.0" height="40.0" fill="#2C3E50" rx="2"/>')
        parts.append(f'<text x="{door_x0 + 14.0:.1f}" y="{bus_top + 18.0:.1f}" font-size="9" font-weight="bold" fill="#117A65">{_esc(tr("lay_door_zone"))}</text>')

        door_items = cls._collect_door_devices(project, feeders, summary)
        dx_cur = door_x0 + 24.0
        dy_cur = bus_top + 36.0
        door_max_x = door_x0 + mp_w_px - 28.0
        for item in door_items:
            item_w = max(48.0, min(mp_w_px - 52.0, len(item) * 5.0 + 14.0))
            item_h = 26.0
            if dx_cur + item_w > door_max_x:
                dx_cur = door_x0 + 24.0
                dy_cur += item_h + 14.0
            parts.append(f'<rect x="{dx_cur:.1f}" y="{dy_cur:.1f}" width="{item_w:.1f}" height="{item_h:.1f}" fill="#E8F8F5" stroke="#117A65" stroke-width="0.9" rx="3"/>')
            parts.append(f'<circle cx="{dx_cur + 10.0:.1f}" cy="{dy_cur + item_h / 2.0:.1f}" r="4.5" fill="white" stroke="#117A65" stroke-width="0.9"/>')
            parts.append(f'<text x="{dx_cur + item_w / 2.0 + 4.0:.1f}" y="{dy_cur + item_h / 2.0 + 3.0:.1f}" text-anchor="middle" font-size="7.2" font-weight="bold" fill="#117A65" dir="ltr">{_esc(item)}</text>')
            dx_cur += item_w + 10.0

        # =====================================================================
        # خطوط اندازه‌گذاری استاندارد (W × H × D)
        # =====================================================================
        dim_y = gland_bottom + 18.0
        parts.append(f'<line x1="{mp_x0}" y1="{dim_y:.1f}" x2="{mp_x0 + mp_w_px:.1f}" y2="{dim_y:.1f}" stroke="#566573" stroke-width="0.9"/>')
        parts.append(f'<line x1="{mp_x0}" y1="{dim_y - 4:.1f}" x2="{mp_x0}" y2="{dim_y + 4:.1f}" stroke="#566573" stroke-width="0.9"/>')
        parts.append(f'<line x1="{mp_x0 + mp_w_px:.1f}" y1="{dim_y - 4:.1f}" x2="{mp_x0 + mp_w_px:.1f}" y2="{dim_y + 4:.1f}" stroke="#566573" stroke-width="0.9"/>')
        parts.append(f'<text x="{mp_x0 + mp_w_px / 2:.1f}" y="{dim_y + 12:.1f}" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#566573" dir="ltr">W = {res.panel_width_mm:g} mm</text>')

        dim_x = mp_x0 + mp_w_px + 14.0
        parts.append(f'<line x1="{dim_x:.1f}" y1="{bus_top:.1f}" x2="{dim_x:.1f}" y2="{gland_bottom:.1f}" stroke="#566573" stroke-width="0.9"/>')
        parts.append(f'<line x1="{dim_x - 4:.1f}" y1="{bus_top:.1f}" x2="{dim_x + 4:.1f}" y2="{bus_top:.1f}" stroke="#566573" stroke-width="0.9"/>')
        parts.append(f'<line x1="{dim_x - 4:.1f}" y1="{gland_bottom:.1f}" x2="{dim_x + 4:.1f}" y2="{gland_bottom:.1f}" stroke="#566573" stroke-width="0.9"/>')
        parts.append(f'<text x="{dim_x - 4:.1f}" y="{(bus_top + gland_bottom) / 2:.1f}" font-size="8.5" font-weight="bold" fill="#566573" text-anchor="middle" transform="rotate(-90 {dim_x - 4:.1f} {(bus_top + gland_bottom) / 2:.1f})" dir="ltr">H = {res.panel_height_mm:g} mm</text>')

        parts.append(f'<text x="{door_x0 + mp_w_px / 2:.1f}" y="{dim_y + 12:.1f}" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#566573" dir="ltr">D = {res.panel_depth_mm:g} mm (Clearance Verified)</text>')
        parts.append(f'<text x="14" y="{total_svg_h - 8:.1f}" font-size="9" fill="#566573">{_esc(tr("lay_note"))}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

    @classmethod
    def generate_svg_file(cls, filepath: str, project: ProjectSpec,
                          feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(cls.generate_svg(project, feeders, summary))