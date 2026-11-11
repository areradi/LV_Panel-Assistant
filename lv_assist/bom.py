# -*- coding: utf-8 -*-
"""
lv_assist/bom.py
موتور یکپارچه تولید، دسته‌بندی، فیلتر، تجمیع و خروجی Bill of Materials (BOM)
"""
from lv_assist.models import feeder_reference_tag
from lv_assist.calculation_state import require_current_calculation
from lv_assist.models import ProjectSpec, FeederCalcOutput, PanelSummaryOutput, CatalogDevice, LoadType
from lv_assist.i18n import tr
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
    "BUSBAR": "Busbar",
    "INCOMING_CABLE": "Cable",
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
    qty: Optional[float]
    unit: str
    panel: str
    func_loc: str
    notes: str = ""
    missing_part_number: bool = False
    quote_exclude: bool = False
    device: Optional[CatalogDevice] = None


def _clean_pn(pn: Optional[str]) -> str:
    val = (pn or "").strip()
    if val.upper() in ("", "N/A", "NONE", "TBD", "UNKNOWN", "-"):
        return ""
    return val


def iter_device_entries(project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> List[tuple]:
    """فهرست تجهیزات BOM به صورت [(func, loc, bmk, cat, dev|None, suggested_spec|None, qty)]."""
    require_current_calculation(project, summary, feeders)
    entries: List[tuple] = []
    def add(func, loc, bmk, cat, dev: CatalogDevice, qty=1):
        if dev is not None:
            entries.append((func, loc, bmk, cat, dev, None, qty))
    def add_suggested(func, loc, bmk, cat, spec: str):
        entries.append((func, loc, bmk, cat, None, spec, 1))

    if summary.main_breaker:
        add("=INCOMING", project.panel_tag, "-Q0", tr("bom_main"), summary.main_breaker)
    elif summary.suggested_main_breaker_str:
        add_suggested("=INCOMING", project.panel_tag, "-Q0", tr("bom_main"), summary.suggested_main_breaker_str)
    if summary.selected_spd:
        add("=INCOMING", project.panel_tag, "-F-SPD", tr("bom_spd"), summary.selected_spd)
        add_suggested("=INCOMING", project.panel_tag, "-F-SPDF", tr("bom_spd_fuse"),
                      tr("bom_spd_fuse_spec", a=summary.selected_spd.spd_backup_fuse_a, b=summary.selected_spd.spd_class))
    if summary.selected_psu_primary_mcb:
        add("=CTRL", project.panel_tag, "-Q01", tr("bom_psu_mcb"), summary.selected_psu_primary_mcb)
    if summary.selected_psu_24v:
        add("=CTRL", project.panel_tag, "-G1", tr("bom_psu"), summary.selected_psu_24v)
    elif summary.suggested_psu_str:
        add_suggested("=CTRL", project.panel_tag, "-G1", tr("bom_psu"), summary.suggested_psu_str)
    if summary.selected_dc_selectivity_mod:
        add("=CTRL", project.panel_tag, "-F0", tr("bom_selmod"), summary.selected_dc_selectivity_mod)
    for idx, f in enumerate(feeders, start=1):
        if f.selected_protection:
            add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'protection'), tr("bom_prot"), f.selected_protection)
        elif f.suggested_spec_str:
            add_suggested(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'protection'), tr("bom_prot"), f.suggested_spec_str)
        if f.load_type == LoadType.MOTOR_STAR_DELTA:
            if f.selected_contactor_main: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'contactor_main'), tr("bom_km"), f.selected_contactor_main)
            if f.selected_contactor_delta: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'contactor_delta'), tr("bom_kd"), f.selected_contactor_delta)
            if f.selected_contactor_star: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'contactor_star'), tr("bom_ky"), f.selected_contactor_star)
            if f.selected_bimetal: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'overload'), tr("bom_bim"), f.selected_bimetal)
            if f.selected_timer_yd: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'timer'), tr("bom_timer"), f.selected_timer_yd)
        elif f.selected_contactor_main:
            add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'contactor_main'), tr("bom_contactor"), f.selected_contactor_main)
        if f.selected_vfd: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'drive'), tr("bom_vfd"), f.selected_vfd)
        if f.selected_soft_starter: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'drive'), tr("bom_soft_starter"), f.selected_soft_starter)
        if f.selected_rcd: add(f.func_tag, f.loc_tag, feeder_reference_tag(idx, 'rcd'), tr("bom_rcd"), f.selected_rcd)
    if summary.selected_fan: add("=COOLING", project.panel_tag, "-E1", tr("bom_fan"), summary.selected_fan)
    if summary.selected_enclosure: add("=CABINET", project.panel_tag, "-U0", tr("bom_enclosure"), summary.selected_enclosure)
    if summary.cap_bank_installed_kvar > 0:
        n_steps = len(summary.cap_bank_steps) or 1
        steps_txt = " + ".join(f"{s:g}" for s in summary.cap_bank_steps)
        if summary.cap_bank_protection: add("=PFC", project.panel_tag, "-Qcap", tr("bom_cap_prot"), summary.cap_bank_protection)
        if summary.cap_bank_contactor: add("=PFC", project.panel_tag, "-Kcap", tr("bom_cap_contactor"), summary.cap_bank_contactor, qty=n_steps)
        if summary.cap_bank_reactor_dev: add("=PFC", project.panel_tag, "-Lcap", tr("bom_cap_reactor"), summary.cap_bank_reactor_dev, qty=n_steps)
        if summary.cap_bank_module_dev: add("=PFC", project.panel_tag, "-Ccap", tr("bom_cap_module"), summary.cap_bank_module_dev, qty=n_steps)
        if summary.cap_bank_suggested_str and not (summary.cap_bank_protection and summary.cap_bank_contactor and summary.cap_bank_module_dev):
            add_suggested("=PFC", project.panel_tag, "-SUGcap", tr("bom_cap_bank"), f"{summary.cap_bank_suggested_str} ({steps_txt} kvar)")
    return entries



def build_bom(project: Any, feeders_out: List[Any], summary: Any, final: bool = False) -> List[BomItem]:
    require_current_calculation(project, summary, feeders_out)
    items = []

    def add(tag, category, description, device=None, spec='', qty=1, unit='pcs', func_loc=''):
        verified = device is not None and device.has_verified_datasheet
        items.append(BomItem(
            item_no=len(items) + 1, tag=tag, category=category, description=description,
            manufacturer=device.manufacturer if device else '',
            part_number=device.part_number if device else '', tech_spec=spec,
            qty=qty, unit=unit, panel=project.panel_tag, func_loc=func_loc,
            notes='VERIFIED_OEM_CATALOG' if verified else 'GENERIC_ESTIMATE; engineering review required',
            missing_part_number=device is None, device=device))

    for func, loc, tag, category, device, suggestion, qty in iter_device_entries(project, feeders_out, summary):
        add(tag, category, f'{device.series} ({device.device_type})' if device else (suggestion or category),
            device, suggestion or '', qty, func_loc=f'{func}{loc}')
    if summary.recommended_busbar_spec:
        phase_spec = summary.recommended_busbar_spec
        if summary.busbar_rating_a:
            phase_spec = (
                f"{phase_spec}; In={summary.busbar_rating_a:g}A; "
                f"Icw={summary.busbar_icw_1s_ka:g}kA/1s; Ipk={summary.busbar_ipk_ka:g}kA"
            )
        phase_length = summary.busbar_length_m
        items.append(BomItem(
            item_no=len(items) + 1, tag='-BUS-PH', category=CATEGORIES['BUSBAR'],
            description=tr('bom_busbar_phase'), manufacturer='', part_number='',
            tech_spec=phase_spec, qty=phase_length, unit='m', panel=project.panel_tag,
            func_loc='=BUS', notes='PRELIMINARY' if phase_length is not None else 'length TBD',
            missing_part_number=True,
        ))
    if summary.recommended_pe_busbar_spec:
        pe_length = summary.pe_busbar_length_m or summary.busbar_length_m
        items.append(BomItem(
            item_no=len(items) + 1, tag='-BUS-PE', category=CATEGORIES['BUSBAR'],
            description=tr('bom_busbar_pe'), manufacturer='', part_number='',
            tech_spec=summary.recommended_pe_busbar_spec, qty=pe_length, unit='m',
            panel=project.panel_tag, func_loc='=BUS',
            notes='PRELIMINARY' if pe_length is not None else 'length TBD',
            missing_part_number=True,
        ))
    if summary.recommended_incoming_cable_str:
        incoming_length = summary.incoming_cable_length_m
        items.append(BomItem(
            item_no=len(items) + 1, tag='-W-IN', category=CATEGORIES['INCOMING_CABLE'],
            description=tr('bom_incoming_cable'), manufacturer='', part_number='',
            tech_spec=summary.recommended_incoming_cable_str, qty=incoming_length,
            unit='m', panel=project.panel_tag, func_loc='=INCOMING',
            notes='PRELIMINARY' if incoming_length is not None else 'length TBD',
            missing_part_number=True,
        ))
    for index, feeder in enumerate(feeders_out, 1):
        cable_spec_parts = [feeder.cable_designation_str] if feeder.cable_designation_str else []
        if feeder.selected_phase_mm2:
            cable_spec_parts.append(f"Phase: {feeder.selected_phase_mm2:g} mm²")
        if feeder.selected_pe_mm2:
            cable_spec_parts.append(f"PE: {feeder.selected_pe_mm2:g} mm²")
        if feeder.conductor_material:
            cable_spec_parts.append(f"Conductor: {feeder.conductor_material}")
        if feeder.insulation_type:
            cable_spec_parts.append(f"Insulation: {feeder.insulation_type}")
        add(f'-W{index}', CATEGORIES['CABLES'], f'Power cable ({feeder.feeder_id})',
            spec='; '.join(cable_spec_parts), qty=feeder.cable_length_m, unit='m',
            func_loc=f'{feeder.func_tag}{feeder.loc_tag}')

    from lv_assist.gui_output_bridge import GuiOutputBridge
    wires, terminals = GuiOutputBridge.generate_all_wire_and_terminal_schedules(project, feeders_out, summary)
    strips = {}
    for terminal in terminals:
        strips.setdefault(terminal['terminal_strip'], set()).add(terminal['terminal_pin'])
    for strip, pins in sorted(strips.items()):
        add(strip, CATEGORIES['TERMINALS'], tr('bom_terminal_strip'),
            qty=len(pins), unit='pcs', spec=tr('bom_terminal_pending_spec'))
        items[-1].notes = 'informational; aggregated in Wiring & Terminals quote line'
        items[-1].quote_exclude = True
    known = {item.tag for item in items}
    for wire in wires:
        for pin in (wire['from_pin'], wire['to_pin']):
            tag = pin.split(':')[0]
            if tag.startswith(('-S', '-H', '-K')) and tag not in known:
                add(tag, CATEGORIES['CONTROL'], 'Control device / auxiliary contact; select from diagram requirements')
                known.add(tag)
    if final and any(item.missing_part_number or item.notes != 'VERIFIED_OEM_CATALOG' for item in items):
        raise ValueError('Final BOM requires verified OEM evidence and assigned parts for every item')
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
    from lv_assist.exporters import _csv_safe

    with open(filepath, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(BOM_HEADERS)
        data_writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        data_writer.writerows([_csv_safe(cell) for cell in row] for row in to_rows(items))
    return filepath


def export_bom_excel(filepath: str, items: List[BomItem]) -> str:
    from lv_assist.exporters import _xl_safe

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
        ws.append([_xl_safe(cell) for cell in row_vals])
        if it.missing_part_number:
            for c_idx in range(1, len(BOM_HEADERS) + 1):
                ws.cell(row=r_idx, column=c_idx).fill = warn_fill

    wb.save(filepath)
    return filepath
