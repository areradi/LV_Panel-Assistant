# -*- coding: utf-8 -*-
"""
lv_assist/commercial.py
موتور برآورد قیمت تمام‌شده تابلو، قیمت‌گذاری پایه کاتالوگ و صدور پیش‌فاکتور رسمی (Commercial Offer)
"""
from lv_assist.calculation_state import require_current_calculation
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import html
import re
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from lv_assist.catalog import CatalogRepository, _ensure_user_tables
from lv_assist.models import ProjectSpec, FeederCalcOutput, PanelSummaryOutput, CatalogDevice, LoadType
from lv_assist.bom import build_bom
from lv_assist.i18n import tr, i18n


def estimate_catalog_unit_price_eur(dev: CatalogDevice) -> float:
    """تخمین مهندسی قیمت واحد پایه (EUR) بر اساس نوع تجهیز و مشخصات نامی."""
    dt = (dev.device_type or "").upper()
    in_a = float(dev.rated_current_in_a or 0.0)
    kw = float(dev.motor_kw_400v or 0.0)
    kvar = float(dev.cap_kvar_400v or 0.0)
    icu = float(dev.icu_ka_400v or 0.0)

    if dt == "MCB_2P_CTRL":
        return 18.5
    if dt == "MCB":
        return round(22.0 + in_a * 0.45, 1)
    if dt == "MCCB":
        base = 145.0 if icu <= 36.0 else 235.0
        return round(base + in_a * 1.15, 1)
    if dt == "ACB":
        return round(1850.0 + in_a * 1.4, 1)
    if dt == "MPCB":
        return round(48.0 + in_a * 1.35, 1)
    if dt == "CONTACTOR":
        return round(26.0 + in_a * 1.45, 1)
    if dt == "CAP_CONTACTOR":
        return round(55.0 + kvar * 2.1, 1)
    if dt == "BIMETAL":
        return round(34.0 + in_a * 0.85, 1)
    if dt == "TIMER_YD":
        return 42.0
    if dt == "VFD":
        return round(260.0 + kw * 48.0, 1)
    if dt == "SOFT_STARTER":
        return round(190.0 + kw * 26.0, 1)
    if dt == "RCD":
        return round(68.0 + in_a * 0.6, 1)
    if dt == "PSU_24V":
        return round(75.0 + in_a * 11.5, 1)
    if dt == "DC_SEL_MOD":
        return 135.0
    if dt == "FAN_FILTER":
        return round(95.0 + float(dev.airflow_m3h or 100.0) * 0.32, 1)
    if dt == "ENCLOSURE":
        vol_factor = (float(dev.width_mm or 800) * float(dev.height_mm or 2000) * float(dev.depth_mm or 600)) / 1e9
        return round(380.0 + vol_factor * 620.0, 1)
    if dt == "SPD":
        return 195.0 if (dev.spd_class or "T2") == "T2" else 340.0
    if dt == "DETUNED_REACTOR":
        return round(180.0 + kvar * 9.5, 1)
    if dt == "CAP_MODULE":
        return round(65.0 + kvar * 5.8, 1)
    return 45.0


def seed_default_catalog_prices(currency: str = "EUR") -> int:
    """ثبت قیمت پایه برای تمام قطعاتی که هنوز در جدول device_prices قیمت ندارند."""
    repo = CatalogRepository()
    _ensure_user_tables(repo.db_path)
    existing = repo.list_prices()
    added = 0
    for dev in repo.devices:
        if dev.part_number not in existing:
            price = estimate_catalog_unit_price_eur(dev)
            repo.set_device_price(dev.part_number, price, currency=currency, source='ESTIMATED')
            added += 1
    return added


@dataclass
class QuoteLineItem:
    item_no: int
    category: str
    tag: str
    part_number: str
    manufacturer: str
    description: str
    qty: float
    unit: str
    unit_price: Optional[float]
    total_price: Optional[float]
    currency: str = "EUR"
    price_source: str = "CATALOG"


@dataclass
class CommercialQuoteSummary:
    project_name: str
    panel_tag: str
    currency: str
    lines: List[QuoteLineItem] = field(default_factory=list)
    equipment_subtotal: float = 0.0
    busbar_copper_cost: float = 0.0
    wiring_and_accessories_cost: float = 0.0
    engineering_and_fat_cost: float = 0.0
    subtotal_net: float = 0.0
    margin_pct: float = 15.0
    margin_amount: float = 0.0
    total_offer_ex_vat: float = 0.0
    vat_pct: float = 19.0
    vat_amount: float = 0.0
    grand_total_inc_vat: float = 0.0


class CommercialEngine:
    """موتور محاسبه بهای تمام‌شده و تولید پیش‌فاکتور تجاری تابلو."""

    @staticmethod
    def _estimate_busbar_cost(summary: PanelSummaryOutput) -> Tuple[float, str]:
        m = re.search(r"(\d+)\s*x\s*(\d+)", summary.recommended_busbar_spec or "")
        w_mm, t_mm = (float(m.group(1)), float(m.group(2))) if m else (20.0, 5.0)
        panel_w_m = max(0.6, float(summary.estimated_panel_width_mm or 800.0) / 1000.0)
        total_bar_length_m = panel_w_m * 4.5 + 2.2
        area_mm2 = w_mm * t_mm
        weight_kg = area_mm2 * total_bar_length_m * 0.00896
        supports_cost = float(summary.busbar_required_supports or 2) * 28.0
        cu_cost = round(weight_kg * 16.5 + supports_cost, 2)
        spec_desc = f"{summary.recommended_busbar_spec} + PE ({weight_kg:.1f} kg Cu + {summary.busbar_required_supports} Supports)"
        return cu_cost, spec_desc

    @classmethod
    def build_quote(
        cls,
        project: ProjectSpec,
        feeders: List[FeederCalcOutput],
        summary: PanelSummaryOutput,
        currency: str = "EUR",
        margin_pct: float = 15.0,
        vat_pct: float = 19.0,
    ) -> CommercialQuoteSummary:
        require_current_calculation(project, summary, feeders)
        seed_default_catalog_prices(currency=currency)
        repo = CatalogRepository()
        prices = repo.list_prices()

        lines: List[QuoteLineItem] = []
        bom = build_bom(project, feeders, summary)
        raw_entries = [(item.func_loc, '', item.tag, item.category, item.device,
                        item.description + ' ' + item.tech_spec, item.qty) for item in bom]
        units = {f'{item.func_loc}{item.tag}': item.unit for item in bom}
        quote_excluded_tags = {item.tag for item in bom if item.quote_exclude}

        grouped: Dict[str, List[Any]] = {}
        unassigned_idx = 0
        for func, loc, bmk, cat, dev, sug_spec, qty in raw_entries:
            # Rows with qty=None (busbar/cable with length TBD) are BOM items
            # but not quotable yet — skip them from the commercial quote.
            # They remain visible in the 04_BOM sheet with notes='length TBD'.
            if qty is None:
                continue
            if bmk in quote_excluded_tags:
                continue
            full_tag = f"{func}{loc}{bmk}"
            if dev is not None:
                key = dev.part_number
                if key not in grouped:
                    grouped[key] = [cat, [full_tag], dev, None, float(qty)]
                else:
                    grouped[key][1].append(full_tag)
                    grouped[key][4] += float(qty)
            else:
                unassigned_idx += 1
                grouped[f"SUG_{unassigned_idx}"] = [cat, [full_tag], None, sug_spec or "TBD", float(qty)]

        idx = 0
        eq_subtotal = 0.0
        for key, (cat, tags, dev, sug_spec, qty) in grouped.items():
            idx += 1
            tag_str = ", ".join(tags[:4]) + (f" (+{len(tags)-4})" if len(tags) > 4 else "")
            if dev is not None:
                pr_info = prices.get(dev.part_number)
                u_price = float(pr_info["unit_price"]) if pr_info else estimate_catalog_unit_price_eur(dev)
                p_src = pr_info["source"] if pr_info else "ESTIMATED"
                desc = f"{dev.series} ({dev.device_type})"
                pn = dev.part_number
                mfg = dev.manufacturer
            else:
                u_price = None
                p_src = "TBD"
                desc = sug_spec or "Auxiliary / Fuse"
                pn = "TBD"
                mfg = "-"

            t_price = round(qty * u_price, 2) if u_price is not None else None
            if t_price is not None:
                eq_subtotal += t_price
            lines.append(QuoteLineItem(
                item_no=idx, category=cat, tag=tag_str, part_number=pn,
                manufacturer=mfg, description=desc, qty=qty, unit=units.get(tags[0], "pcs"),
                unit_price=u_price, total_price=t_price, currency=currency, price_source=p_src
            ))

        bus_cost, bus_desc = cls._estimate_busbar_cost(summary)
        idx += 1
        lines.append(QuoteLineItem(
            item_no=idx, category="Busbar System", tag="-W_BUS", part_number="CU-BUSBAR-SET",
            manufacturer="Custom / Rittal", description=bus_desc, qty=1.0, unit="SET",
            unit_price=bus_cost, total_price=bus_cost, currency=currency, price_source="CALC"
        ))

        wiring_cost = round(120.0 + len(feeders) * 42.0, 2)
        idx += 1
        lines.append(QuoteLineItem(
            item_no=idx, category="Wiring & Terminals", tag="-X1 / -X2", part_number="TERM-DUCT-SET",
            manufacturer="Phoenix / Lapp", description=f"Power/Control Terminals, DIN Rails, Ducts & H07V-K Wiring ({len(feeders)} Feeders)",
            qty=1.0, unit="LOT", unit_price=wiring_cost, total_price=wiring_cost, currency=currency, price_source="CALC"
        ))

        eng_cost = round(250.0 + len(feeders) * 55.0, 2)
        idx += 1
        lines.append(QuoteLineItem(
            item_no=idx, category="Engineering & FAT", tag="SERVICE", part_number="ENG-ASSY-FAT",
            manufacturer="Panel Builder", description="Electrical Engineering, Assembly Labor & Routine Verification Test (IEC/EN 61439)",
            qty=1.0, unit="LOT", unit_price=eng_cost, total_price=eng_cost, currency=currency, price_source="CALC"
        ))

        subtotal_net = round(eq_subtotal + bus_cost + wiring_cost + eng_cost, 2)
        margin_amount = round(subtotal_net * (margin_pct / 100.0), 2)
        offer_ex_vat = round(subtotal_net + margin_amount, 2)
        vat_amount = round(offer_ex_vat * (vat_pct / 100.0), 2)
        grand_total = round(offer_ex_vat + vat_amount, 2)

        return CommercialQuoteSummary(
            project_name=project.project_name,
            panel_tag=project.panel_tag,
            currency=currency,
            lines=lines,
            equipment_subtotal=round(eq_subtotal, 2),
            busbar_copper_cost=bus_cost,
            wiring_and_accessories_cost=wiring_cost,
            engineering_and_fat_cost=eng_cost,
            subtotal_net=subtotal_net,
            margin_pct=margin_pct,
            margin_amount=margin_amount,
            total_offer_ex_vat=offer_ex_vat,
            vat_pct=vat_pct,
            vat_amount=vat_amount,
            grand_total_inc_vat=grand_total,
        )

    @classmethod
    def export_quote_html(cls, filepath: str, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> str:
        require_current_calculation(project, summary, feeders)
        q = cls.build_quote(project, feeders, summary)
        esc = lambda s: html.escape(str(s or ""))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        direction = i18n.direction()

        rows_html = ""
        for it in q.lines:
            unit_price = f"{it.unit_price:,.2f}" if it.unit_price is not None else "—"
            total_price = f"{it.total_price:,.2f}" if it.total_price is not None else "—"
            rows_html += f"""
            <tr>
                <td style="text-align:center;">{it.item_no}</td>
                <td dir="auto">{esc(it.category)}</td>
                <td dir="auto"><b><bdi dir="ltr">{esc(it.tag)}</bdi></b></td>
                <td dir="auto"><b><bdi dir="ltr">{esc(it.part_number)}</bdi></b></td>
                <td dir="auto"><span class="bidi-isolate" dir="auto">{esc(it.manufacturer)}</span></td>
                <td dir="auto"><span class="bidi-isolate" dir="auto">{esc(it.description)}</span></td>
                <td dir="auto" style="text-align:right;"><bdi dir="ltr">{it.qty:g}</bdi></td>
                <td dir="auto" style="text-align:center;"><bdi dir="auto">{esc(it.unit)}</bdi></td>
                <td dir="auto" style="text-align:right;"><bdi dir="ltr">{unit_price}</bdi></td>
                <td dir="auto" style="text-align:right;"><b><bdi dir="ltr">{total_price}</bdi></b></td>
            </tr>"""

        unpriced_count = sum(1 for item in q.lines if item.price_source == "TBD")
        unpriced_notice = (
            f'<p class="unpriced-warning" dir="auto">توجه: <bdi dir="ltr">{unpriced_count}</bdi> قلم '
            "قیمت‌گذاری نشده‌اند و در جمع کل لحاظ نشده‌اند.</p>"
            if unpriced_count else ""
        )

        html_doc = f"""<!DOCTYPE html>
<html lang="{i18n.get_language()}" dir="{direction}">
<head><meta charset="UTF-8"><title>Commercial Quotation — {esc(project.project_name)}</title>
<style>
@page {{ size: A4 portrait; margin: 14mm; }}
body {{ font-family: Tahoma, Segoe UI, sans-serif; font-size: 12px; color: #1E293B; background: #F8FAFC; margin: 20px; }}
.container {{ max-width: 1020px; margin: auto; background: #FFFFFF; padding: 26px; border: 1px solid #CBD5E1; border-radius: 8px; }}
.hdr {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #2563EB; padding-bottom: 12px; margin-bottom: 18px; }}
h1 {{ font-size: 18px; color: #0F172A; margin: 0 0 6px 0; }}
.kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }}
.kpi {{ background: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 6px; padding: 10px 14px; }}
.kpi b {{ display: block; font-size: 15px; color: #2563EB; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; font-size: 11px; }}
th, td {{ border: 1px solid #CBD5E1; padding: 7px 8px; }}
th {{ background: #EFF6FF; color: #1E3A8A; text-align: center; }}
.ltr-isolate {{ direction: ltr; unicode-bidi: isolate; }}
.bidi-isolate {{ unicode-bidi: isolate; }}
.totals {{ width: 420px; margin-right: auto; border: 2px solid #1E3A8A; border-radius: 6px; overflow: hidden; }}
.totals tr td {{ padding: 8px 12px; font-size: 12px; }}
.totals tr.grand {{ background: #1E3A8A; color: #FFFFFF; font-weight: bold; font-size: 13px; }}
.btn {{ background: #2563EB; color: #FFF; border: none; padding: 9px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; }}
@media print {{
  .no-print {{ display: none !important; }}
  body {{ background: #FFF; margin: 0; }}
  .container {{ border: none; padding: 0; max-width: none; width: 100%; }}
  table {{ orphans: 3; widows: 3; }}
  tr {{ break-inside: auto; page-break-inside: auto; page-break-after: auto; }}
  td, th {{ break-inside: avoid; page-break-inside: avoid; }}
  p, blockquote {{ orphans: 2; widows: 2; }}
  th {{ background-color: #e0e0e0 !important; color: #000 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .bom-table {{ width: 100%; max-width: 100%; table-layout: auto; }}
  .bom-table th, .bom-table td {{ word-break: normal; overflow-wrap: break-word; padding: 3px 4px; line-height: 1.15; }}
  .bom-table thead {{ display: table-header-group; }}
  .totals {{ break-inside: avoid; page-break-inside: avoid; margin-top: 0; }}
  .totals tr, .totals td {{ break-inside: avoid; page-break-inside: avoid; }}
}}
</style></head>
<body><div class="container">
<div class="hdr">
  <div>
    <h1 dir="auto">پیش‌فاکتور تجاری و برآورد مالی تابلو <span class="ltr-isolate" dir="ltr">(Commercial Quotation &amp; Cost Breakdown)</span></h1>
    <div dir="auto">پروژه: <b><span class="bidi-isolate" dir="auto">{esc(project.project_name)}</span> (<span class="ltr-isolate" dir="ltr">{esc(project.panel_tag)}</span>)</b> | استاندارد: <b><span class="ltr-isolate" dir="ltr">{esc(project.standard_ref)}</span></b> | تاریخ: <span class="ltr-isolate" dir="ltr">{now_str}</span></div>
  </div>
  <div class="no-print"><button class="btn" onclick="window.print()">چاپ / دریافت PDF</button></div>
</div>

<div class="kpi-row">
  <div class="kpi" dir="auto">هزینه تجهیزات کاتالوگ<b dir="ltr">{q.equipment_subtotal:,.2f} {q.currency}</b></div>
  <div class="kpi" dir="auto">شینه مسی و ترمینال‌بندی<b dir="ltr">{(q.busbar_copper_cost + q.wiring_and_accessories_cost):,.2f} {q.currency}</b></div>
  <div class="kpi" dir="auto">مهندسی، مونتاژ و تست FAT<b dir="ltr">{q.engineering_and_fat_cost:,.2f} {q.currency}</b></div>
  <div class="kpi" dir="auto">مبلغ کل نهایی (با ارزش افزوده)<b dir="ltr">{q.grand_total_inc_vat:,.2f} {q.currency}</b></div>
</div>

{unpriced_notice}
<table class="bom-table">
  <thead>
    <tr>
      <th rowspan="2">ردیف</th><th rowspan="2">دسته</th><th rowspan="2">تگ (IEC 81346)</th><th rowspan="2">پارت‌نامبر</th><th rowspan="2">سازنده</th>
      <th rowspan="2">شرح فنی</th><th rowspan="2">تعداد</th><th rowspan="2">واحد</th><th colspan="2">مبالغ ({esc(q.currency)})</th>
    </tr>
    <tr><th>قیمت واحد</th><th>قیمت کل</th></tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>

<table class="totals">
  <tr><td dir="auto">جمع خالص تجهیزات، شینه و ساخت (Net Cost)</td><td dir="auto" style="text-align:right;"><b><span class="ltr-isolate" dir="ltr">{q.subtotal_net:,.2f}</span></b></td></tr>
  <tr><td dir="auto">بالاسری و حاشیه سود پیمانکار ({q.margin_pct:g}%)</td><td dir="auto" style="text-align:right;"><span class="ltr-isolate" dir="ltr">{q.margin_amount:,.2f}</span></td></tr>
  <tr><td dir="auto"><b>مبلغ قابل پیشنهاد بدون مالیات (Total Excl. VAT)</b></td><td dir="auto" style="text-align:right;"><b><span class="ltr-isolate" dir="ltr">{q.total_offer_ex_vat:,.2f}</span></b></td></tr>
  <tr><td dir="auto">مالیات بر ارزش افزوده (VAT / MwSt {q.vat_pct:g}%)</td><td dir="auto" style="text-align:right;"><span class="ltr-isolate" dir="ltr">{q.vat_amount:,.2f}</span></td></tr>
  <tr class="grand"><td dir="auto">مبلغ کل پیش‌فاکتور (Grand Total Incl. VAT)</td><td dir="auto" style="text-align:right;"><b><span class="ltr-isolate" dir="ltr">{q.grand_total_inc_vat:,.2f}</span></b></td></tr>
</table>
<p style="font-size:10.5px; color:#64748B; margin-top:14px;">
* قیمت‌های واحد از بانک اطلاعاتی SQLite پروژه (تب مدیریت کاتالوگ و قیمت‌ها) استخراج شده‌اند و قابل ویرایش توسط مهندس طراح/فروش هستند.
</p>
</div></body></html>"""
        with open(filepath, "w", encoding="utf-8") as fp:
            fp.write(html_doc)
        return filepath

    @classmethod
    def append_commercial_sheet(cls, wb: openpyxl.Workbook, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        require_current_calculation(project, summary, feeders)
        q = cls.build_quote(project, feeders, summary)
        ws = wb.create_sheet("07_Commercial_Quote")
        ws.append(["Item No.", "Category", "Tag", "Part Number", "Manufacturer", "Description", "Qty", "Unit", f"Unit Price ({q.currency})", f"Total Price ({q.currency})", "Price Source"])
        for it in q.lines:
            ws.append([it.item_no, it.category, it.tag, it.part_number, it.manufacturer, it.description, it.qty, it.unit, it.unit_price, it.total_price, it.price_source])
        ws.append([])
        ws.append(["", "", "", "", "", "Subtotal Net Cost (Equipment + Busbar + Labor)", "", "", "", q.subtotal_net, ""])
        ws.append(["", "", "", "", "", f"Overhead & Margin ({q.margin_pct:g}%)", "", "", "", q.margin_amount, ""])
        ws.append(["", "", "", "", "", "Total Offer Price (Excl. VAT)", "", "", "", q.total_offer_ex_vat, ""])
        ws.append(["", "", "", "", "", f"VAT / MwSt ({q.vat_pct:g}%)", "", "", "", q.vat_amount, ""])
        ws.append(["", "", "", "", "", "GRAND TOTAL (Incl. VAT)", "", "", "", q.grand_total_inc_vat, ""])
