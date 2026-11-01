# -*- coding: utf-8 -*-
"""
LV-PanelAssist Information-Rich Engineering Schematic Generator (v0.7.0)
Generates EPLAN-grade schematics matching industrial multi-line standards:
  1. Sheet Type A: Motorized Breaker / Feeder Power + Control Schematic
  2. Sheet Type B: Remote / VFD / PLC Control Interface Schematic
  3. Automatic From-To Wire List & Terminal/Cable Schedule
"""

from typing import Dict, List
from pydantic import BaseModel


class WireConnectionRecord(BaseModel):
    wire_number: str
    potential_type: str
    from_device_pin: str
    to_device_pin: str
    wire_size_mm2: str = "1.5 mm²"
    wire_color: str = "Red (AC) / Dark Blue (24VDC)"


class TerminalCableRecord(BaseModel):
    terminal_strip: str
    terminal_pin: str
    internal_wire_no: str
    internal_target: str
    cable_tag: str
    cable_spec: str
    cable_core_no: str
    external_location: str
    external_device_pin: str


class IndustrialSchematicGenerator:
    """
    تولیدکننده نقشه‌های اجرایی کارگاهی (دارای شماره سیم، شماره پایه، ترمینال، کابل چندرشته و آینه کنتاکت‌ها)
    """

    @staticmethod
    def generate_sheet_type_a_motorized_breaker_svg(
        feeder_index: int = 2,
        page_no: int = 11,
        q_tag: str = "-Q2",
        f_tag: str = "-F36",
        power_spec: str = "3VA2 / NSX 160A"
    ) -> str:
        idx = feeder_index
        return f"""
        <svg viewBox="0 0 1280 860" width="100%" height="780" style="background:#FAFAFA; border:2px solid #1F4E78; font-family:Consolas,Calibri,sans-serif;">
            <rect x="0" y="0" width="1280" height="24" fill="#1F4E78"/>
            <text x="40" y="16" fill="#FFF" font-size="11" font-weight="bold">SHEET {page_no} | POWER &amp; MOTORIZED BREAKER CONTROL ({q_tag} - {power_spec})</text>
            <text x="600" y="16" fill="#AED6F1" font-size="11">1          2          3          4          5          6          7          8          9          10</text>

            <text x="22" y="42" fill="#1E8449" font-size="10">{page_no}.1:D</text>
            <text x="25" y="54" fill="#1F618D" font-size="12" font-weight="bold">N</text>
            <line x1="28" y1="60" x2="28" y2="810" stroke="#1F618D" stroke-width="1.8"/>
            <text x="22" y="828" fill="#1F618D" font-size="12" font-weight="bold">N</text>

            <text x="65" y="42" fill="#1E8449" font-size="10">{page_no}.1:D</text>
            <text x="65" y="54" fill="#1F4E78" font-size="11" font-weight="bold">-1L1</text>
            <line x1="75" y1="60" x2="75" y2="450" stroke="#E74C3C" stroke-width="2"/>
            <line x1="75" y1="530" x2="75" y2="810" stroke="#E74C3C" stroke-width="2"/>

            <text x="98" y="42" fill="#1E8449" font-size="10">{page_no}.1:D</text>
            <text x="98" y="54" fill="#1F4E78" font-size="11" font-weight="bold">-1L2</text>
            <line x1="105" y1="60" x2="105" y2="450" stroke="#E74C3C" stroke-width="2"/>
            <line x1="105" y1="530" x2="105" y2="810" stroke="#E74C3C" stroke-width="2"/>

            <text x="130" y="42" fill="#1E8449" font-size="10">{page_no}.1:D</text>
            <text x="130" y="54" fill="#1F4E78" font-size="11" font-weight="bold">-1L3</text>
            <line x1="135" y1="60" x2="135" y2="450" stroke="#E74C3C" stroke-width="2"/>
            <line x1="135" y1="530" x2="135" y2="810" stroke="#E74C3C" stroke-width="2"/>

            <line x1="135" y1="120" x2="1180" y2="120" stroke="#E74C3C" stroke-width="1.8"/>
            <ellipse cx="165" cy="112" rx="18" ry="10" fill="#FFF" stroke="#1F4E78" stroke-width="1.5"/>
            <text x="165" y="116" fill="#000" font-size="11" font-weight="bold" text-anchor="middle">-89</text>

            <rect x="200" y="112" width="36" height="16" fill="#FFF" stroke="#1F4E78" stroke-width="1.5"/>
            <text x="218" y="105" fill="#1F4E78" font-size="11" font-weight="bold" text-anchor="middle">{f_tag}</text>

            <ellipse cx="290" cy="112" rx="18" ry="10" fill="#FFF" stroke="#1F4E78" stroke-width="1.5"/>
            <text x="290" y="116" fill="#000" font-size="11" font-weight="bold" text-anchor="middle">-36</text>

            <line x1="28" y1="720" x2="1180" y2="720" stroke="#E74C3C" stroke-width="1.8"/>

            <rect x="50" y="435" width="635" height="135" fill="none" stroke="#34568B" stroke-width="1.4" stroke-dasharray="6,4"/>
            <text x="32" y="452" fill="#1F4E78" font-size="12" font-weight="bold">{q_tag}</text>

            <line x1="75" y1="450" x2="63" y2="515" stroke="#1F4E78" stroke-width="2"/>
            <line x1="105" y1="450" x2="93" y2="515" stroke="#1F4E78" stroke-width="2"/>
            <line x1="135" y1="450" x2="123" y2="515" stroke="#1F4E78" stroke-width="2"/>

            <text x="235" y="494" fill="#1F4E78" font-size="11" font-weight="bold">OFF</text>
            <text x="320" y="494" fill="#1F4E78" font-size="11" font-weight="bold">SDE</text>
        </svg>
        """.strip()

    @staticmethod
    def generate_sheet_type_b_remote_terminal_cable_svg(
        ext_loc_tag: str = "+1NW",
        terminal_strip: str = "-X5",
        cable_tag: str = "-W101",
        cable_spec: str = "PP00 14 x 1.5 mm²"
    ) -> str:
        return f"""
        <svg viewBox="0 0 980 680" width="100%" height="620" style="background:#FAFAFA; border:2px solid #8E244D; font-family:Consolas,Calibri,sans-serif;">
            <rect x="0" y="0" width="980" height="24" fill="#8E244D"/>
            <text x="30" y="16" fill="#FFF" font-size="11" font-weight="bold">SHEET 07 | REMOTE FIELD INTERFACE, TERMINAL STRIP ({terminal_strip}) &amp; CONTROL CABLE ({cable_tag})</text>

            <line x1="420" y1="35" x2="920" y2="35" stroke="#C2185B" stroke-width="2"/>
            <line x1="120" y1="155" x2="740" y2="155" stroke="#C2185B" stroke-width="2"/>
            
            <circle cx="320" cy="180" r="4" fill="#FFF" stroke="#8E244D" stroke-width="1.8"/>
            <text x="308" y="176" fill="#8E244D" font-size="10" font-weight="bold" text-anchor="end">{terminal_strip}</text>
            <text x="330" y="176" fill="#8E244D" font-size="10">:01</text>
            <text x="255" y="377" fill="#8E244D" font-size="12" font-weight="bold" text-anchor="middle">{cable_tag}</text>
            <text x="255" y="395" fill="#8E244D" font-size="10" font-weight="bold" text-anchor="middle">{cable_spec}</text>
        </svg>
        """.strip()

    @staticmethod
    def get_wire_and_terminal_schedules(feeder_idx: int = 2) -> Dict[str, List[dict]]:
        i = feeder_idx
        wires = [
            WireConnectionRecord(wire_number="-89", potential_type="L3 Control Tap", from_device_pin=f"-Q{i}:5 (-1L3)", to_device_pin=f"-F36:1"),
            WireConnectionRecord(wire_number="-36", potential_type="Fused Control Phase", from_device_pin="-F36:2", to_device_pin=f"-Q{i}:SDE(81)"),
            WireConnectionRecord(wire_number="-46", potential_type="ON Lamp Feed", from_device_pin=f"-KOFF{i}:24", to_device_pin=f"-ON{i}:X1"),
        ]
        terminals = [
            TerminalCableRecord(
                terminal_strip="-X5", terminal_pin=":01", internal_wire_no="W_KA1.2_14",
                internal_target="-KA1.2:14", cable_tag="-W101", cable_spec="PP00 14 x 1.5 mm²",
                cable_core_no="Core 1", external_location="+1NW", external_device_pin="-KC01:11 (62.1)"
            ),
        ]
        return {
            "wires": [w.model_dump() for w in wires],
            "terminals": [t.model_dump() for t in terminals],
        }