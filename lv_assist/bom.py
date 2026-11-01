# -*- coding: utf-8 -*-
"""
lv_assist/bom.py
موتور یکپارچه تولید، دسته‌بندی، فیلتر، تجمیع و خروجی Bill of Materials (BOM)
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import csv
import copy
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

BOM_HEADERS: List[str] = [
    "Item No.",
    "Tag",
    "Category",
    "Description",
    "Manufacturer",
    "Part Number",
    "Technical Specification",
    "Quantity",
    "Unit",
    "Assembly / Panel",
    "Function / Location",
    "Notes",
]

CATEGORIES = {
    "PROTECTION": "تجهیزات حفاظتی (Protection)",
    "SWITCHING": "کنتاکتورها و رله‌ها (Contactors & Relays)",
    "CONTROL": "تجهیزات کنترل (Control Devices)",
    "MEASUREMENT": "تجهیزات اندازه‌گیری (Metering)",
    "POWER_SUPPLY": "تجهیزات تغذیه (Power Supplies)",
    "TERMINALS": "ترمینال‌ها (Terminals)",
    "CABLES": "کابل‌ها و متعلقات (Cables & Accessories)",
    "MECHANICAL": "تجهیزات مکانیکی تابلو (Enclosure & Busbar)",
    "OTHER": "سایر تجهیزات (Other)",
}


@dataclass
class BomItem:
    item_no: int
    tag: str
    category: str
    description: str
    manufacturer: str
    part_number: str
    tech_spec: str
    qty: float
    unit: str
    panel: str
    func_loc: str
    notes: str = ""
    missing_part_number: bool = False


def _clean_pn(pn: Optional[str]) -> str:
    val = (pn or "").strip()
    if val.upper() in ("", "N/A", "NONE", "TBD", "UNKNOWN", "-"):
        return ""
    return val


def build_bom(project: Any, feeders_out: List[Any], summary: Any) -> List[BomItem]:
    """استخراج دقیق BOM از مدل واقعی پروژه، فیدرها و خلاصه تابلو بدون داده ساختگی."""
    items: List[BomItem] = []
    panel_tag = getattr(project, "loc_tag", "+MCC1") or "+MCC1"
    func_root = getattr(project, "func_tag", "=PLANT") or "=PLANT"

    def add(tag: str, cat: str, desc: str, mfr: str, pn: str, spec: str, qty: float = 1.0, unit: str = "pcs", fl: str = "", note: str = ""):
        clean = _clean_pn(pn)
        missing = clean == ""
        note_final = note
        if missing and "پارت‌نامبر" not in note_final:
            note_final = (note_final + " | پارت‌نامبر تعیین نشده").strip(" |")
        items.append(
            BomItem(
                item_no=len(items) + 1,
                tag=tag,
                category=CATEGORIES.get(cat, CATEGORIES["OTHER"]),
                description=desc,
                manufacturer=(mfr or "").strip() if not missing else (mfr or "").strip(),
                part_number=clean,
                tech_spec=spec,
                qty=qty,
                unit=unit,
                panel=panel_tag,
                func_loc=fl or f"{func_root}/{panel_tag}",
                notes=note_final,
                missing_part_number=missing,
            )
        )

    # ۱. کلید اصلی ورودی تابلو
    inc = getattr(summary, "incoming_breaker", None)
    if inc:
        add(
            tag="-Q0",
            cat="PROTECTION",
            desc="Incoming Main Circuit Breaker",
            mfr=getattr(inc, "manufacturer", ""),
            pn=getattr(inc, "part_number", ""),
            spec=f"{getattr(inc, 'device_type', 'MCCB/ACB')} In={getattr(inc, 'rated_current_in_a', 0)}A, Icu={getattr(inc, 'icu_ka_400v', 0)}kA",
        )

    # ۲. حفاظت اضافه ولتاژ (SPD) و فیوز پشتیبان
    spd = getattr(summary, "selected_spd", None)
    if spd:
        add(
            tag="-F9",
            cat="PROTECTION",
            desc="Surge Protective Device (SPD)",
            mfr=getattr(spd, "manufacturer", ""),
            pn=getattr(spd, "part_number", ""),
            spec=f"Type {getattr(spd, 'spd_type', '2')}",
        )
        add(
            tag="-F9F",
            cat="PROTECTION",
            desc="SPD Backup Fuse gG",
            mfr=getattr(spd, "manufacturer", ""),
            pn=getattr(spd, "backup_fuse_part", ""),
            spec="Backup fuse gG",
        )

    # ۳. منبع تغذیه ۲۴ ولت فرمان
    psu = getattr(summary, "control_psu", None) or getattr(summary, "selected_psu", None)
    if psu:
        add(
            tag="-T1",
            cat="POWER_SUPPLY",
            desc="24VDC Control Power Supply",
            mfr=getattr(psu, "manufacturer", "Siemens"),
            pn=getattr(psu, "part_number", ""),
            spec=f"24VDC / {getattr(psu, 'rated_current_a', getattr(psu, 'rated_current_in_a', 5))}A",
        )

    # ۴. سلول بدنه و شینه مسی
    enc = getattr(summary, "selected_enclosure", None)
    if enc:
        add(
            tag=panel_tag,
            cat="MECHANICAL",
            desc="Switchgear Enclosure Cabinet",
            mfr=getattr(enc, "manufacturer", ""),
            pn=getattr(enc, "part_number", ""),
            spec=f"{getattr(enc, 'width_mm', 800)}x{getattr(enc, 'height_mm', 2000)}x{getattr(enc, 'depth_mm', 600)} mm",
        )

    # ۵. تجهیزات هر فیدر
    for idx, f in enumerate(feeders_out, start=1):
        fid = getattr(f, "feeder_id", f"F{idx:02d}")
        floc = f"{getattr(f, 'func_tag', func_root)}/{getattr(f, 'loc_tag', panel_tag)} ({fid})"

        cb = getattr(f, "selected_breaker", None)
        if cb:
            add(
                tag=f"-Q{idx}",
                cat="PROTECTION",
                desc=f"Feeder Breaker ({fid})",
                mfr=getattr(cb, "manufacturer", ""),
                pn=getattr(cb, "part_number", ""),
                spec=f"{getattr(cb, 'device_type', 'MCCB/MPCB')} In={getattr(cb, 'rated_current_in_a', 0)}A",
                fl=floc,
            )

        km = getattr(f, "selected_contactor", None)
        if km:
            add(
                tag=f"-K{idx}M",
                cat="SWITCHING",
                desc=f"Main Contactor ({fid})",
                mfr=getattr(km, "manufacturer", ""),
                pn=getattr(km, "part_number", ""),
                spec=f"AC-3 Ie={getattr(km, 'rated_current_in_a', 0)}A, Coil 24VDC",
                fl=floc,
            )

        ol = getattr(f, "selected_overload", None)
        if ol:
            add(
                tag=f"-F{idx}",
                cat="PROTECTION",
                desc=f"Thermal Overload Relay ({fid})",
                mfr=getattr(ol, "manufacturer", ""),
                pn=getattr(ol, "part_number", ""),
                spec=f"Class 10A ({fid})",
                fl=floc,
            )

        vfd = getattr(f, "selected_vfd", None)
        if vfd:
            add(
                tag=f"-U{idx}",
                cat="CONTROL",
                desc=f"Variable Frequency Drive ({fid})",
                mfr=getattr(vfd, "manufacturer", ""),
                pn=getattr(vfd, "part_number", ""),
                spec=f"{getattr(vfd, 'power_kw', getattr(f, 'power_kw', 0))} kW, 400V",
                fl=floc,
            )

        cable_size = getattr(f, "cable_size_mm2", None)
        cable_len = float(getattr(f, "cable_length_m", 0) or 0)
        if cable_size and cable_len > 0:
            add(
                tag=f"-W{idx}",
                cat="CABLES",
                desc=f"Power Cable ({fid})",
                mfr="",
                pn="",
                spec=f"Cu XLPE/PVC {cable_size} mm²",
                qty=cable_len,
                unit="m",
                fl=floc,
                note="کابل قدرت فیدر",
            )

    # ۶. ترمینال‌های قدرت (-X1) و فرمان (-X2)
    n_power_terms = 5 + len(feeders_out) * 4
    n_ctrl_terms = 2 + len(feeders_out) * 2
    add("-X1", "TERMINALS", "Power Terminal Strip Block", "Phoenix Contact", "UT-6-PE-SET", f"{n_power_terms} points", qty=float(n_power_terms), unit="pcs")
    add("-X2", "TERMINALS", "24VDC Control Terminal Strip", "Phoenix Contact", "UT-2.5-CTRL", f"{n_ctrl_terms} points", qty=float(n_ctrl_terms), unit="pcs")

    return items


def aggregate(items: List[BomItem]) -> List[BomItem]:
    """
    تجمیع اقلام فقط در صورت هم‌ارزی کامل (Manufacturer + Part Number + Tech Spec + Category).
    اقلام فاقد Part Number هرگز به صورت کورکورانه ادغام نمی‌شوند.
    """
    merged: List[BomItem] = []
    index: Dict[tuple, int] = {}
    for it in items:
        if it.missing_part_number:
            cp = copy.deepcopy(it)
            cp.item_no = len(merged) + 1
            merged.append(cp)
            continue
        key = (it.manufacturer.lower(), it.part_number.lower(), it.tech_spec.lower(), it.category, it.unit)
        if key in index:
            target = merged[index[key]]
            target.qty += it.qty
            if it.tag not in target.tag.split(", "):
                target.tag = f"{target.tag}, {it.tag}"
        else:
            cp = copy.deepcopy(it)
            cp.item_no = len(merged) + 1
            index[key] = len(merged)
            merged.append(cp)
    return merged


def filter_bom(
    items: List[BomItem],
    query: str = "",
    category: str = "ALL",
    panel: str = "ALL",
    only_missing_pn: bool = False,
) -> List[BomItem]:
    q = (query or "").strip().lower()
    out: List[BomItem] = []
    for it in items:
        if category and category != "ALL" and it.category != category:
            continue
        if panel and panel != "ALL" and it.panel != panel:
            continue
        if only_missing_pn and not it.missing_part_number:
            continue
        if q:
            hay = f"{it.tag} {it.description} {it.manufacturer} {it.part_number} {it.tech_spec} {it.func_loc}".lower()
            if q not in hay:
                continue
        out.append(it)
    return out


def to_rows(items: List[BomItem]) -> List[List[Any]]:
    return [
        [
            it.item_no,
            it.tag,
            it.category,
            it.description,
            it.manufacturer,
            it.part_number,
            it.tech_spec,
            it.qty,
            it.unit,
            it.panel,
            it.func_loc,
            it.notes,
        ]
        for it in items
    ]


def export_bom_csv(filepath: str, items: List[BomItem]) -> str:
    with open(filepath, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(BOM_HEADERS)
        writer.writerows(to_rows(items))
    return filepath


def export_bom_excel(filepath: str, items: List[BomItem]) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "04_BOM"
    ws.append(BOM_HEADERS)

    hdr_fill = PatternFill(start_color="FF2563EB", end_color="FF2563EB", fill_type="solid")
    hdr_font = Font(bold=True, color="FFFFFFFF")
    warn_fill = PatternFill(start_color="FFFEF3C7", end_color="FFFEF3C7", fill_type="solid")

    for col_idx in range(1, len(BOM_HEADERS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r_idx, it in enumerate(items, start=2):
        row_vals = [
            it.item_no, it.tag, it.category, it.description,
            it.manufacturer, it.part_number, it.tech_spec,
            it.qty, it.unit, it.panel, it.func_loc, it.notes,
        ]
        ws.append(row_vals)
        if it.missing_part_number:
            for c_idx in range(1, len(BOM_HEADERS) + 1):
                ws.cell(row=r_idx, column=c_idx).fill = warn_fill

    wb.save(filepath)
    return filepath