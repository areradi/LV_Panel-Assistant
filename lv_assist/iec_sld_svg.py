# -*- coding: utf-8 -*-
"""
LV-PanelAssist Dynamic IEC 60617 Single-Line Diagram (SLD) SVG Generator
100% Data-Driven from ProjectSpec, PanelSummaryOutput, and List[FeederCalcOutput].
No hardcoded project or feeder values.
"""

import html
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class SLDFeederDTO(BaseModel):
    feeder_id: str
    func_tag: str
    loc_tag: str
    description: str
    load_type: str
    power_kw: float
    design_current_ib_a: float
    protection_tag: str
    protection_part: str
    protection_in_a: float
    protection_icu_ka: float
    switching_tag: str = ""
    switching_part: str = ""
    overload_tag: str = ""
    overload_part: str = ""
    overload_range: str = ""
    cable_designation: str
    cable_length_m: float
    voltage_drop_pct: float
    selectivity_status: str


class SLDPanelDTO(BaseModel):
    project_name: str
    panel_tag: str
    standard_ref: str
    nominal_voltage_v: float
    frequency_hz: float
    earthing_system: str
    prospective_ik_ka: float
    main_breaker_tag: str = "-Q0"
    main_breaker_part: str
    main_breaker_in_a: float
    main_breaker_icu_ka: float
    design_main_current_a: float
    busbar_spec: str
    pe_busbar_spec: str
    incoming_cable_spec: str
    psu_tag: str = "-G1"
    psu_part: str = ""
    psu_rating_str: str = ""
    spd_part: str = ""
    feeders: List[SLDFeederDTO]


class IECSldSvgGenerator:
    """تولیدکننده پویا نقشه تک‌خطی (SLD) بر اساس نمادهای استاندارد IEC 60617"""

    @classmethod
    def render_sld_svg(cls, data: SLDPanelDTO) -> str:
        n_feeders = max(1, len(data.feeders))
        col_pitch = 175
        left_margin = 130
        right_margin = 120
        svg_w = max(1050, left_margin + n_feeders * col_pitch + right_margin)
        svg_h = 760
        bus_x1 = left_margin - 30
        bus_x2 = left_margin + (n_feeders - 1) * col_pitch + 60
        main_x = (bus_x1 + bus_x2) // 2

        esc = lambda s: html.escape(str(s or ""))

        feeder_columns_svg = []
        for idx, f in enumerate(data.feeders):
            fx = left_margin + idx * col_pitch
            feeder_columns_svg.append(cls._render_single_feeder_column(fx, f, esc))

        return f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="100%" height="680"
             style="background:#FFFFFF; border:2px solid #1E3A5F; font-family:Calibri,Consolas,sans-serif;">
            <!-- Top Title Header Bar -->
            <rect x="0" y="0" width="{svg_w}" height="32" fill="#1E3A5F"/>
            <text x="20" y="21" fill="#FFFFFF" font-size="13" font-weight="bold">
                IEC 60617 SINGLE-LINE DIAGRAM (SLD) | {esc(data.project_name)} ({esc(data.panel_tag)})
            </text>
            <text x="{svg_w - 20}" y="21" fill="#AED6F1" font-size="11" text-anchor="end">
                {esc(data.nominal_voltage_v)}V {esc(data.frequency_hz)}Hz | {esc(data.earthing_system)} | Ik'' = {esc(data.prospective_ik_ka)} kA
            </text>

            <!-- Incoming Supply & Cable -->
            <circle cx="{main_x}" cy="58" r="10" fill="none" stroke="#1E3A5F" stroke-width="2"/>
            <line x1="{main_x}" y1="68" x2="{main_x}" y2="115" stroke="#1E3A5F" stroke-width="2.5"/>
            <line x1="{main_x - 8}" y1="88" x2="{main_x + 8}" y2="78" stroke="#1E3A5F" stroke-width="1.8"/>
            <text x="{main_x + 14}" y="70" fill="#1E3A5F" font-size="11" font-weight="bold">
                INCOMING SUPPLY ({esc(data.nominal_voltage_v)}V 3P+N+PE)
            </text>
            <text x="{main_x + 14}" y="86" fill="#4B5563" font-size="10">
                Cable: {esc(data.incoming_cable_spec)} | Design InA = {esc(data.design_main_current_a)} A
            </text>

            <!-- Main Incoming Circuit Breaker (-Q0) IEC 60617 Symbol -->
            <text x="{main_x - 18}" y="128" fill="#C0392B" font-size="12" font-weight="bold" text-anchor="end">
                {esc(data.panel_tag)}{esc(data.main_breaker_tag)}
            </text>
            <text x="{main_x + 16}" y="128" fill="#1F2937" font-size="11" font-weight="bold">
                {esc(data.main_breaker_part)}
            </text>
            <text x="{main_x + 16}" y="143" fill="#4B5563" font-size="10">
                In = {esc(data.main_breaker_in_a)} A | Icu = {esc(data.main_breaker_icu_ka)} kA
            </text>
            <!-- X symbol + contacts for Main Breaker -->
            <line x1="{main_x - 5}" y1="112" x2="{main_x + 5}" y2="122" stroke="#C0392B" stroke-width="2"/>
            <line x1="{main_x + 5}" y1="112" x2="{main_x - 5}" y2="122" stroke="#C0392B" stroke-width="2"/>
            <line x1="{main_x}" y1="117" x2="{main_x - 12}" y2="148" stroke="#C0392B" stroke-width="2.5"/>
            <circle cx="{main_x}" cy="150" r="3" fill="#C0392B"/>
            <line x1="{main_x}" y1="150" x2="{main_x}" y2="195" stroke="#1E3A5F" stroke-width="2.5"/>

            <!-- Main Phase Busbar (3P+N) & PE Busbar -->
            <line x1="{bus_x1}" y1="195" x2="{bus_x2}" y2="195" stroke="#C0392B" stroke-width="5"/>
            <line x1="{bus_x1}" y1="205" x2="{bus_x2}" y2="205" stroke="#16A085" stroke-width="2.5" stroke-dasharray="8,4"/>
            <text x="{bus_x1}" y="185" fill="#C0392B" font-size="11" font-weight="bold">
                MAIN BUSBAR: {esc(data.busbar_spec)} | {esc(data.pe_busbar_spec)}
            </text>

            <!-- Dynamic Feeder Columns -->
            {"".join(feeder_columns_svg)}

            <!-- Bottom ISO 7200 / IEC 61082 Engineering Title Block -->
            <rect x="15" y="{svg_h - 65}" width="{svg_w - 30}" height="52" fill="#F8FAFC" stroke="#1E3A5F" stroke-width="1.5"/>
            <line x1="340" y1="{svg_h - 65}" x2="340" y2="{svg_h - 13}" stroke="#1E3A5F" stroke-width="1"/>
            <line x1="680" y1="{svg_h - 65}" x2="680" y2="{svg_h - 13}" stroke="#1E3A5F" stroke-width="1"/>
            <text x="28" y="{svg_h - 44}" fill="#1E3A5F" font-size="11" font-weight="bold">PROJECT: {esc(data.project_name)}</text>
            <text x="28" y="{svg_h - 24}" fill="#4B5563" font-size="10">LOCATION: {esc(data.panel_tag)} | STD: {esc(data.standard_ref)}</text>
            <text x="355" y="{svg_h - 44}" fill="#1E3A5F" font-size="11" font-weight="bold">24VDC CONTROL SUPPLY ({esc(data.psu_tag)}): {esc(data.psu_part)}</text>
            <text x="355" y="{svg_h - 24}" fill="#4B5563" font-size="10">{esc(data.psu_rating_str)}</text>
            <text x="695" y="{svg_h - 44}" fill="#1E3A5F" font-size="11" font-weight="bold">DRAWING: SINGLE-LINE DIAGRAM (SLD - SHEET 01)</text>
            <text x="695" y="{svg_h - 24}" fill="#4B5563" font-size="10">GENERATED BY: LV-PanelAssist Dynamic Bridge (Zero-Hardcode)</text>
        </svg>
        """.strip()

    @classmethod
    def _render_single_feeder_column(cls, fx: int, f: SLDFeederDTO, esc) -> str:
        parts = []
        # 1. Tap from Main Busbar (Y=195 to Y=245)
        parts.append(f'<circle cx="{fx}" cy="195" r="4" fill="#C0392B"/>')
        parts.append(f'<line x1="{fx}" y1="195" x2="{fx}" y2="245" stroke="#1E3A5F" stroke-width="2"/>')

        # 2. Feeder Protection Device (-Q) at Y=245..285
        parts.append(f'<line x1="{fx - 4}" y1="242" x2="{fx + 4}" y2="250" stroke="#1E3A5F" stroke-width="1.8"/>')
        parts.append(f'<line x1="{fx + 4}" y1="242" x2="{fx - 4}" y2="250" stroke="#1E3A5F" stroke-width="1.8"/>')
        parts.append(f'<line x1="{fx}" y1="246" x2="{fx - 10}" y2="278" stroke="#1E3A5F" stroke-width="2"/>')
        parts.append(f'<rect x="{fx - 14}" y="255" width="8" height="14" fill="none" stroke="#1E3A5F" stroke-width="1.2"/>')
        parts.append(f'<circle cx="{fx}" cy="280" r="2.5" fill="#1E3A5F"/>')
        parts.append(f'<text x="{fx + 10}" y="254" fill="#1E3A5F" font-size="10" font-weight="bold">{esc(f.protection_tag)}</text>')
        parts.append(f'<text x="{fx + 10}" y="267" fill="#1F2937" font-size="9.5">{esc(f.protection_part)}</text>')
        parts.append(f'<text x="{fx + 10}" y="279" fill="#4B5563" font-size="9">In={esc(f.protection_in_a)}A | {esc(f.protection_icu_ka)}kA</text>')
        parts.append(f'<line x1="{fx}" y1="280" x2="{fx}" y2="330" stroke="#1E3A5F" stroke-width="1.8"/>')

        # 3. Switching Device (Contactor -K / Star-Delta / VFD -U / RCD -F) at Y=330..380
        if f.load_type == "MOTOR_VFD":
            parts.append(f'<rect x="{fx - 22}" y="330" width="44" height="44" fill="#EFF6FF" stroke="#1D4ED8" stroke-width="1.8"/>')
            parts.append(f'<line x1="{fx - 22}" y1="374" x2="{fx + 22}" y2="330" stroke="#1D4ED8" stroke-width="1.2"/>')
            parts.append(f'<text x="{fx - 12}" y="346" fill="#1D4ED8" font-size="9" font-weight="bold">~</text>')
            parts.append(f'<text x="{fx + 6}" y="368" fill="#1D4ED8" font-size="9" font-weight="bold">~</text>')
            parts.append(f'<text x="{fx + 26}" y="346" fill="#1D4ED8" font-size="10" font-weight="bold">{esc(f.switching_tag)}</text>')
            parts.append(f'<text x="{fx + 26}" y="360" fill="#1F2937" font-size="9">{esc(f.switching_part)}</text>')
            parts.append(f'<line x1="{fx}" y1="374" x2="{fx}" y2="435" stroke="#1E3A5F" stroke-width="1.8"/>')
        elif f.switching_part:
            # Contactor symbol
            parts.append(f'<line x1="{fx}" y1="330" x2="{fx - 10}" y2="360" stroke="#047857" stroke-width="2"/>')
            parts.append(f'<circle cx="{fx}" cy="362" r="2.5" fill="#047857"/>')
            parts.append(f'<text x="{fx + 10}" y="342" fill="#047857" font-size="10" font-weight="bold">{esc(f.switching_tag)}</text>')
            parts.append(f'<text x="{fx + 10}" y="355" fill="#1F2937" font-size="9">{esc(f.switching_part)}</text>')
            parts.append(f'<line x1="{fx}" y1="362" x2="{fx}" y2="395" stroke="#1E3A5F" stroke-width="1.8"/>')
            if f.overload_part:
                # Thermal Overload (Bimetal -F)
                parts.append(f'<rect x="{fx - 10}" y="395" width="20" height="24" fill="#FEF3C7" stroke="#B45309" stroke-width="1.5"/>')
                parts.append(f'<path d="M {fx} 398 L {fx - 5} 405 L {fx + 5} 410 L {fx} 417" fill="none" stroke="#B45309" stroke-width="1.4"/>')
                parts.append(f'<text x="{fx + 14}" y="406" fill="#B45309" font-size="9.5" font-weight="bold">{esc(f.overload_tag)}</text>')
                parts.append(f'<text x="{fx + 14}" y="418" fill="#1F2937" font-size="8.5">{esc(f.overload_part)} ({esc(f.overload_range)})</text>')
                parts.append(f'<line x1="{fx}" y1="419" x2="{fx}" y2="435" stroke="#1E3A5F" stroke-width="1.8"/>')
            else:
                parts.append(f'<line x1="{fx}" y1="395" x2="{fx}" y2="435" stroke="#1E3A5F" stroke-width="1.8"/>')
        else:
            parts.append(f'<line x1="{fx}" y1="330" x2="{fx}" y2="435" stroke="#1E3A5F" stroke-width="1.8"/>')

        # 4. Outgoing Terminal (-X) & Power Cable Section (Y=435..540)
        parts.append(f'<circle cx="{fx}" cy="435" r="3.5" fill="#FFFFFF" stroke="#1E3A5F" stroke-width="1.8"/>')
        parts.append(f'<text x="{fx - 8}" y="438" fill="#4B5563" font-size="8.5" text-anchor="end">-X1:{esc(f.feeder_id)}</text>')
        parts.append(f'<line x1="{fx}" y1="439" x2="{fx}" y2="540" stroke="#1E3A5F" stroke-width="1.8"/>')
        # Cable 3-phase slash
        parts.append(f'<line x1="{fx - 7}" y1="485" x2="{fx + 7}" y2="475" stroke="#16A085" stroke-width="1.8"/>')
        parts.append(f'<text x="{fx + 9}" y="476" fill="#0F766E" font-size="9" font-weight="bold">{esc(f.cable_designation)}</text>')
        parts.append(f'<text x="{fx + 9}" y="489" fill="#4B5563" font-size="8.5">L={esc(f.cable_length_m)}m | dU={esc(f.voltage_drop_pct)}%</text>')
        parts.append(f'<text x="{fx + 9}" y="502" fill="#6B7280" font-size="8">Sel: {esc(f.selectivity_status)}</text>')

        # 5. Load Symbol (Motor M 3~ or Distribution Feeder Arrow) at Y=562
        if "MOTOR" in f.load_type:
            parts.append(f'<circle cx="{fx}" cy="564" r="24" fill="#F0FDF4" stroke="#15803D" stroke-width="2"/>')
            parts.append(f'<text x="{fx}" y="562" fill="#15803D" font-size="12" font-weight="bold" text-anchor="middle">M</text>')
            parts.append(f'<text x="{fx}" y="576" fill="#15803D" font-size="10" font-weight="bold" text-anchor="middle">3~</text>')
        else:
            parts.append(f'<polygon points="{fx},582 {fx - 12},552 {fx + 12},552" fill="#EFF6FF" stroke="#1D4ED8" stroke-width="2"/>')

        # 6. Bottom Feeder Data Tag Box (Y=600..675)
        parts.append(f'<rect x="{fx - 78}" y="598" width="156" height="76" rx="4" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.2"/>')
        parts.append(f'<text x="{fx}" y="614" fill="#1E3A5F" font-size="10.5" font-weight="bold" text-anchor="middle">{esc(f.feeder_id)} ({esc(f.func_tag)}{esc(f.loc_tag)})</text>')
        desc_short = f.description[:24] + ("…" if len(f.description) > 24 else "")
        parts.append(f'<text x="{fx}" y="630" fill="#334155" font-size="9.5" text-anchor="middle">{esc(desc_short)}</text>')
        parts.append(f'<text x="{fx}" y="646" fill="#0F172A" font-size="9.5" font-weight="bold" text-anchor="middle">P = {esc(f.power_kw)} kW | Ib = {esc(f.design_current_ib_a)} A</text>')
        parts.append(f'<text x="{fx}" y="662" fill="#64748B" font-size="8.5" text-anchor="middle">Type: {esc(f.load_type)}</text>')

        return "\n".join(parts)


def generate_sld_svg(panel_dto: SLDPanelDTO) -> str:
    """تابع استاندارد ورودی برای فراخوانی مستقیم از gui_output_bridge.py"""
    return IECSldSvgGenerator.render_sld_svg(panel_dto)