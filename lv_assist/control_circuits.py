# -*- coding: utf-8 -*-
"""اتوماسیون مدارهای کنترلی: دیاگرام نردبانی SVG، لیست سیم‌ها و خروجی اتصالات سازگار با EPLAN."""
import csv
from datetime import datetime
from typing import List, Optional, Tuple

from lv_assist.models import (
    ProjectSpec, FeederCalcOutput, PanelSummaryOutput, ControlWire, LoadType
)
from lv_assist.i18n import tr


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ControlCircuitGenerator:
    """تولید مدار کنترلی استاندارد ۲۴ ولت DC به ازای هر فیدر موتوری + توزیع تغذیه کنترلی پانل."""

    WIRE_COLOR_LP = "BU"    # +24 V DC طبق IEC 60204-1
    WIRE_COLOR_M = "BU"     # 0 V DC
    WIRE_SECTION = 1.5      # mm²
    RAIL_X_L, RAIL_X_R = 50.0, 950.0
    SVG_W = 1000.0

    # ---------------------------------------------------------------- wire lists
    @staticmethod
    def _w(wire_no: str, from_dev: str, from_term: str, to_dev: str, to_term: str, remark: str) -> ControlWire:
        color = ControlCircuitGenerator.WIRE_COLOR_LP
        if to_term in ("M", "COM", "A2") or from_term in ("M", "COM", "A2"):
            color = ControlCircuitGenerator.WIRE_COLOR_M
        return ControlWire(
            wire_no=wire_no, from_dev=from_dev, from_term=from_term, to_dev=to_dev, to_term=to_term,
            color=color, cross_section_mm2=ControlCircuitGenerator.WIRE_SECTION, remark=remark,
        )

    @classmethod
    def generate_common_wires(cls, project: ProjectSpec, summary: PanelSummaryOutput) -> List[ControlWire]:
        wires: List[ControlWire] = []
        tag = project.panel_tag
        n = 1
        def w(fd, ft, td, tt, remark=""):
            nonlocal n
            wires.append(cls._w(f"W00-{n:02d}", fd, ft, td, tt, remark))
            n += 1
        w("-Q01", "2", "-G1", "L1", tr("ctrl_psu_feed"))
        w("-G1", "N", "-Q01", "4", tr("ctrl_psu_feed"))
        w("-G1", "L+", "-F0", "1", tr("ctrl_psu_feed"))
        w("-F0", "2", "-X1", "1", tr("ctrl_lplus"))
        w("-G1", "M", "-X2", "1", tr("ctrl_m"))
        return wires

    @classmethod
    def generate_wires(cls, project: ProjectSpec, f: FeederCalcOutput, idx: int) -> List[ControlWire]:
        wires: List[ControlWire] = []
        p = f"{idx:02d}"
        n = 1
        def w(fd, ft, td, tt, remark=""):
            nonlocal n
            wires.append(cls._w(f"W{p}-{n:02d}", fd, ft, td, tt, remark))
            n += 1
        x1, x2 = "-X1", "-X2"
        q, k = f"-Q{idx}", f"-K{idx}"
        s0, s1 = f"-S{idx}0", f"-S{idx}1"
        h1, h2 = f"-H{idx}1", f"-H{idx}2"

        if f.load_type == LoadType.MOTOR_DOL:
            w(x1, "1", q, "95", tr("ctrl_mpcb_aux"))
            w(q, "96", s0, "11", tr("ctrl_mpcb_aux"))
            w(s0, "12", s1, "13", tr("ctrl_stop"))
            w(s1, "14", k, "A1", tr("ctrl_start"))
            w(k, "A2", x2, "1", tr("ctrl_m"))
            w(s1, "13", k, "13", tr("ctrl_holding"))
            w(s1, "14", k, "14", tr("ctrl_holding"))
            w(x1, "1", k, "53", tr("ctrl_run_lamp"))
            w(k, "54", h1, "X1", tr("ctrl_run_lamp"))
            w(h1, "X2", x2, "1", tr("ctrl_m"))
        elif f.load_type == LoadType.MOTOR_STAR_DELTA:
            ky, kd, kt = f"-K{idx}Y", f"-K{idx}D", f"-K{idx}T"
            fb = f"-F{idx}"
            w(x1, "1", fb, "95", tr("ctrl_bimetal_aux"))
            w(fb, "96", s0, "11", tr("ctrl_bimetal_aux"))
            w(s0, "12", s1, "13", tr("ctrl_stop"))
            w(s1, "14", ky, "A1", tr("ctrl_star_contactor"))
            w(ky, "A2", x2, "1", tr("ctrl_m"))
            w(s1, "14", kt, "A1", tr("ctrl_timer"))
            w(kt, "A2", x2, "1", tr("ctrl_m"))
            w(s1, "13", ky, "13", tr("ctrl_holding"))
            w(s1, "14", ky, "14", tr("ctrl_holding"))
            w(x1, "1", kt, "15", tr("ctrl_timer"))
            w(kt, "18", ky, "21", tr("ctrl_timer"))
            w(ky, "22", kd, "A1", tr("ctrl_delta_contactor"))
            w(kd, "A2", x2, "1", tr("ctrl_m"))
            w(x1, "1", kd, "53", tr("ctrl_run_lamp"))
            w(kd, "54", h1, "X1", tr("ctrl_run_lamp"))
            w(h1, "X2", x2, "1", tr("ctrl_m"))
            w(x1, "1", fb, "97", tr("ctrl_fault_lamp"))
            w(fb, "98", h2, "X1", tr("ctrl_fault_lamp"))
            w(h2, "X2", x2, "1", tr("ctrl_m"))
        elif f.load_type == LoadType.MOTOR_SOFT_STARTER:
            g = f"-G{idx}"
            w(x1, "1", s0, "11", tr("ctrl_stop"))
            w(s0, "12", s1, "13", tr("ctrl_stop"))
            w(s1, "14", g, "DI1", tr("ctrl_soft_di"))
            w(g, "COM", x2, "1", tr("ctrl_m"))
            w(x1, "1", g, "13", tr("ctrl_run_lamp"))
            w(g, "14", h1, "X1", tr("ctrl_run_lamp"))
            w(h1, "X2", x2, "1", tr("ctrl_m"))
            w(x1, "1", g, "95", tr("ctrl_fault_lamp"))
            w(g, "96", h2, "X1", tr("ctrl_fault_lamp"))
            w(h2, "X2", x2, "1", tr("ctrl_m"))
        elif f.load_type == LoadType.MOTOR_VFD:
            u = f"-U{idx}"
            w(x1, "1", s0, "11", tr("ctrl_stop"))
            w(s0, "12", u, "DI_EN", tr("ctrl_vfd_en"))
            w(x1, "1", s1, "13", tr("ctrl_start"))
            w(s1, "14", u, "DI_RUN", tr("ctrl_vfd_run"))
            w(u, "COM", x2, "1", tr("ctrl_m"))
            w(x1, "1", u, "R1A", tr("ctrl_run_lamp"))
            w(u, "R1C", h1, "X1", tr("ctrl_run_lamp"))
            w(h1, "X2", x2, "1", tr("ctrl_m"))
            w(x1, "1", u, "R2A", tr("ctrl_fault_lamp"))
            w(u, "R2C", h2, "X1", tr("ctrl_fault_lamp"))
            w(h2, "X2", x2, "1", tr("ctrl_m"))
        return wires

    @classmethod
    def build_all_wires(cls, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> List[ControlWire]:
        wires = list(cls.generate_common_wires(project, summary))
        for i, f in enumerate(feeders, start=1):
            if f.load_type in (LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA,
                               LoadType.MOTOR_SOFT_STARTER, LoadType.MOTOR_VFD):
                wires.extend(cls.generate_wires(project, f, i))
        return wires

    # ---------------------------------------------------------------- SVG ladder
    @staticmethod
    def _dev(x: float, y: float, tag: str, terms: str, kind: str, color: str) -> List[str]:
        w, h = 84.0, 34.0
        fill = "#EBF5FB" if kind in ("coil", "io") else ("#FEF9E7" if kind in ("no", "nc") else "#E8F8F5")
        stroke = color
        parts = [
            f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>',
            f'<text x="{x}" y="{y - 2}" text-anchor="middle" font-size="10" font-weight="bold" fill="#1F4E78">{_esc(tag)}</text>',
            f'<text x="{x}" y="{y + 10}" text-anchor="middle" font-size="8" fill="#566573" dir="ltr">{_esc(terms)}</text>',
        ]
        if kind == "no":
            parts.append(f'<text x="{x}" y="{y + h / 2 + 12}" text-anchor="middle" font-size="8" fill="#1E8449">{_esc(tr("ctrl_no"))}</text>')
        elif kind == "nc":
            parts.append(f'<text x="{x}" y="{y + h / 2 + 12}" text-anchor="middle" font-size="8" fill="#C0392B">{_esc(tr("ctrl_nc"))}</text>')
        elif kind == "lamp":
            parts.append(f'<circle cx="{x}" cy="{y + h / 2 + 12}" r="4" fill="none" stroke="#B7950B" stroke-width="1.2"/>')
        elif kind == "coil":
            parts.append(f'<text x="{x}" y="{y + h / 2 + 12}" text-anchor="middle" font-size="8" fill="#1F4E78">{_esc(tr("ctrl_coil_lbl"))}</text>')
        return parts

    @classmethod
    def _rung(cls, y: float, devices: List[Tuple[str, str, str]], wire_no: str, color: str) -> List[str]:
        parts = [f'<line x1="{cls.RAIL_X_L}" y1="{y}" x2="{cls.RAIL_X_R}" y2="{y}" stroke="#BDC3C7" stroke-width="1"/>']
        n = len(devices)
        span = cls.RAIL_X_R - cls.RAIL_X_L - 100.0
        for i, (tag, terms, kind) in enumerate(devices):
            x = cls.RAIL_X_L + 70.0 + span * (i + 0.5) / n
            parts += cls._dev(x, y, tag, terms, kind, color)
        parts.append(f'<text x="{cls.RAIL_X_L + 70}" y="{y - 14}" font-size="8.5" fill="#566573" dir="ltr">{_esc(wire_no)}</text>')
        return parts

    @classmethod
    def rung_specs(cls, project: ProjectSpec, feeders: List[FeederCalcOutput]) -> List[tuple]:
        """ساختار نردبانی مشترک برای SVG و DXF: [(kind, title, wire_no, color, rungs)]"""
        motor_feeders = [f for f in feeders if f.load_type in
                         (LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA,
                          LoadType.MOTOR_SOFT_STARTER, LoadType.MOTOR_VFD)]
        specs: List[tuple] = [(
            "common", tr("ctrl_block_common"), "W00", "#1F4E78",
            [[("-Q01", "1 / 2", "io"), ("-G1", "L1/N  L+/M", "coil"), ("-F0", "1 / 2", "io")],
             [("-X1", tr("ctrl_lplus"), "io"), ("-X2", tr("ctrl_m"), "io")]],
        )]
        for f in motor_feeders:
            idx = feeders.index(f) + 1
            title = tr("ctrl_block_feeder", a=f.feeder_id, b=tr("lt_" + f.load_type.value)) + f" — {f.description[:40]}"
            if f.load_type == LoadType.MOTOR_DOL:
                rungs = [
                    [(f"-Q{idx}", "95 / 96", "nc"), (f"-S{idx}0", "11 / 12", "nc"), (f"-S{idx}1", "13 / 14", "no"), (f"-K{idx}", "A1 / A2", "coil")],
                    [(f"-K{idx}", "13 / 14", "no"), (f"-K{idx}", "53 / 54", "no"), (f"-H{idx}1", "X1 / X2", "lamp")],
                ]
            elif f.load_type == LoadType.MOTOR_STAR_DELTA:
                rungs = [
                    [(f"-F{idx}", "95 / 96", "nc"), (f"-S{idx}0", "11 / 12", "nc"), (f"-S{idx}1", "13 / 14", "no"), (f"-K{idx}Y", "A1 / A2", "coil"), (f"-K{idx}T", "A1 / A2", "coil")],
                    [(f"-K{idx}T", "15 / 18", "no"), (f"-K{idx}Y", "21 / 22", "nc"), (f"-K{idx}D", "A1 / A2", "coil")],
                    [(f"-K{idx}D", "53 / 54", "no"), (f"-H{idx}1", "X1 / X2", "lamp"), (f"-F{idx}", "97 / 98", "no"), (f"-H{idx}2", "X1 / X2", "lamp")],
                ]
            elif f.load_type == LoadType.MOTOR_SOFT_STARTER:
                rungs = [
                    [(f"-S{idx}0", "11 / 12", "nc"), (f"-S{idx}1", "13 / 14", "no"), (f"-G{idx}", "DI1 / COM", "io")],
                    [(f"-G{idx}", "13 / 14", "no"), (f"-H{idx}1", "X1 / X2", "lamp"), (f"-G{idx}", "95 / 96", "nc"), (f"-H{idx}2", "X1 / X2", "lamp")],
                ]
            else:  # MOTOR_VFD
                rungs = [
                    [(f"-S{idx}0", "11 / 12", "nc"), (f"-U{idx}", "DI_EN / COM", "io"), (f"-S{idx}1", "13 / 14", "no"), (f"-U{idx}", "DI_RUN / COM", "io")],
                    [(f"-U{idx}", "R1A / R1C", "no"), (f"-H{idx}1", "X1 / X2", "lamp"), (f"-U{idx}", "R2A / R2C", "no"), (f"-H{idx}2", "X1 / X2", "lamp")],
                ]
            specs.append(("feeder", title, f"W{idx:02d}", "#1F4E78", rungs))
        return specs

    @classmethod
    def generate_svg(cls, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> str:
        wires_all = cls.build_all_wires(project, feeders, summary)
        specs = cls.rung_specs(project, feeders)
        total_h = 194.0 + sum(32.0 + 52.0 * len(rungs) for kind, _, _, _, rungs in specs if kind == "feeder") + 34.0
        y = 64.0
        parts: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{cls.SVG_W}" height="{total_h}" font-family="Tahoma, Segoe UI, sans-serif">',
            f'<rect width="{cls.SVG_W}" height="{total_h}" fill="white"/>',
            f'<text x="20" y="28" font-size="17" font-weight="bold" fill="#1F4E78">{_esc(tr("ctrl_title"))} — {_esc(project.project_name)} ({_esc(project.panel_tag)})</text>',
            f'<text x="20" y="46" font-size="10" fill="#566573">{datetime.now().strftime("%Y-%m-%d %H:%M")} | {_esc(tr("ctrl_subtitle"))}</text>',
        ]

        for kind, title, wno, color, rungs in specs:
            if kind == "common":
                parts.append(f'<rect x="20" y="{y - 16}" width="{cls.SVG_W - 40}" height="130" rx="6" fill="#F4F6F7" stroke="#BDC3C7" stroke-width="1"/>')
                parts.append(f'<text x="32" y="{y}" font-size="12" font-weight="bold" fill="#1F4E78">{_esc(title)}</text>')
                y += 22
                parts += cls._rung(y, rungs[0], wno, color); y += 52
                parts += cls._rung(y, rungs[1], wno, color); y += 56
            else:
                block_h = 52 * len(rungs) + 30
                parts.append(f'<rect x="20" y="{y - 14}" width="{cls.SVG_W - 40}" height="{block_h}" rx="6" fill="#FBFCFC" stroke="#D5DBDB" stroke-width="1"/>')
                parts.append(f'<text x="32" y="{y + 2}" font-size="12" font-weight="bold" fill="{color}">{_esc(title)}</text>')
                y += 20
                for rung in rungs:
                    parts += cls._rung(y, rung, wno, color); y += 52
                y += 12

        parts.append(f'<text x="20" y="{y + 12}" font-size="10" fill="#566573">{_esc(tr("ctrl_note", a=len(wires_all)))}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

    @classmethod
    def generate_svg_file(cls, filepath: str, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(cls.generate_svg(project, feeders, summary))

    # ---------------------------------------------------------------- EPLAN CSV
    CONN_HEADERS = ["Connection", "From device", "From pin", "To device", "To pin",
                    "Cross-section (mm²)", "Color", "Remark"]

    @classmethod
    def export_connections_csv(cls, filepath: str, project: ProjectSpec,
                               feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        rows = []
        for w in cls.build_all_wires(project, feeders, summary):
            rows.append([w.wire_no, w.from_dev, w.from_term, w.to_dev, w.to_term,
                         w.cross_section_mm2, w.color, w.remark])
        with open(filepath, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(cls.CONN_HEADERS)
            writer.writerows(rows)
