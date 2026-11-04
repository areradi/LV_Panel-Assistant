# -*- coding: utf-8 -*-
from lv_assist.drawing_status import preliminary_drawing
from lv_assist.calculation_state import require_current_calculation
import csv
import math
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from lv_assist.models import (
    ProjectSpec, FeederCalcOutput, PanelSummaryOutput, CatalogDevice, LoadType
)
from lv_assist.catalog import TripCurveRepository
from lv_assist.i18n import tr


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class SldGenerator:
    """تولید دیاگرام تک‌خطی (Single-Line Diagram) به صورت SVG مستقل."""

    LINE_W_BUSBAR = 3.5     # سلسله‌مراتب ضخامت خطوط نقشه صنعتی
    LINE_W_POWER = 1.8
    LINE_W_CONTROL = 1.0
    TITLE_BLOCK_H = 92.0
    ROW_H = 255.0

    @staticmethod
    def _breaker(x: float, y: float, tag: str, part: str, color: str) -> List[str]:
        pn = _esc(part) if part else ""
        return [
            f'<rect x="{x - 20}" y="{y}" width="40" height="30" rx="4" fill="{color}" stroke="#1F4E78" stroke-width="1.5"/>',
            f'<text x="{x}" y="{y + 19}" text-anchor="middle" font-size="10" fill="white" font-weight="bold">{_esc(tag)}</text>',
            f'<text x="{x}" y="{y + 42}" text-anchor="middle" font-size="9" fill="#566573" dir="ltr">{pn}</text>',
        ]

    @staticmethod
    def _title_block(project: ProjectSpec, summary: PanelSummaryOutput, w: float, tb_y: float) -> List[str]:
        require_current_calculation(project, summary)
        parts: List[str] = []
        parts.append(f'<rect x="10" y="{tb_y}" width="{w - 20}" height="{SldGenerator.TITLE_BLOCK_H - 10}" fill="#F4F6F7" stroke="#1F4E78" stroke-width="1.5"/>')
        parts.append(f'<text x="24" y="{tb_y + 20}" font-size="13" font-weight="bold" fill="#1F4E78">{_esc(project.project_name)} ({_esc(project.panel_tag)})</text>')
        parts.append(f'<text x="24" y="{tb_y + 36}" font-size="9" fill="#566573">{_esc(project.standard_ref)}</text>')
        legend_x = w - 232.0
        cell_w = (legend_x - 34.0) / 6.0
        labels = [
            (tr("sld_dwg"), f"SLD-{project.panel_tag}"),
            (tr("sld_voltage"), f"{project.nominal_voltage_v:g} V / {project.frequency_hz:g} Hz"),
            (tr("sld_bus_in"), f"{summary.design_main_current_a} A"),
            (tr("sld_earth"), project.earthing_system.value),
            (tr("sld_date"), datetime.now().strftime("%Y-%m-%d")),
            (tr("sld_drawn"), project.designer_name or "-"),
        ]
        for i, (lbl, val) in enumerate(labels):
            cx = 24.0 + i * cell_w
            parts.append(f'<text x="{cx}" y="{tb_y + 54}" font-size="8" fill="#566573">{_esc(lbl)}</text>')
            parts.append(f'<text x="{cx}" y="{tb_y + 70}" font-size="9.5" font-weight="bold" fill="#1C2833" dir="ltr">{_esc(val)}</text>')
        parts.append(f'<text x="{legend_x}" y="{tb_y + 20}" font-size="9" font-weight="bold" fill="#1F4E78">{_esc(tr("sld_legend"))}</text>')
        for i, (wd, lbl) in enumerate([(SldGenerator.LINE_W_BUSBAR, tr("sld_lw_busbar")),
                                       (SldGenerator.LINE_W_POWER, tr("sld_lw_power")),
                                       (SldGenerator.LINE_W_CONTROL, tr("sld_lw_control"))]):
            ly = tb_y + 34.0 + i * 16.0
            parts.append(f'<line x1="{legend_x}" y1="{ly}" x2="{legend_x + 28}" y2="{ly}" stroke="#1F4E78" stroke-width="{wd}"/>')
            parts.append(f'<text x="{legend_x + 34}" y="{ly + 4}" font-size="8.5" fill="#1C2833">{_esc(lbl)}</text>')
        return parts

    @staticmethod
    def _load_symbol(x: float, y: float, f: FeederCalcOutput) -> List[str]:
        lt = f.load_type
        if lt in (LoadType.MOTOR_DOL, LoadType.MOTOR_STAR_DELTA, LoadType.MOTOR_SOFT_STARTER):
            return [f'<circle cx="{x}" cy="{y}" r="16" fill="#EBF5FB" stroke="#1F4E78" stroke-width="2"/>',
                    f'<text x="{x}" y="{y + 5}" text-anchor="middle" font-size="13" font-weight="bold" fill="#1F4E78">M</text>',
                    f'<text x="{x}" y="{y + 28}" text-anchor="middle" font-size="9" fill="#566573">{_esc(tr("lt_" + lt.value))}</text>']
        if lt == LoadType.MOTOR_VFD:
            return [f'<rect x="{x - 20}" y="{y - 14}" width="40" height="28" rx="4" fill="#EBF5FB" stroke="#1F4E78" stroke-width="2"/>',
                    f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="10" font-weight="bold" fill="#1F4E78">VFD</text>']
        if lt == LoadType.HEATER_RESISTIVE:
            return [f'<rect x="{x - 20}" y="{y - 14}" width="40" height="28" rx="4" fill="#FDEDEC" stroke="#C0392B" stroke-width="2"/>',
                    f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="10" font-weight="bold" fill="#C0392B">R</text>']
        if lt == LoadType.LIGHTING_SOCKET:
            return [f'<rect x="{x - 20}" y="{y - 14}" width="40" height="28" rx="4" fill="#FEF9E7" stroke="#B7950B" stroke-width="2"/>',
                    f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="10" font-weight="bold" fill="#B7950B">L</text>']
        return [f'<path d="M {x} {y - 14} L {x + 12} {y + 10} L {x - 12} {y + 10} Z" fill="#E8F8F5" stroke="#117A65" stroke-width="2"/>',
                f'<text x="{x}" y="{y + 30}" text-anchor="middle" font-size="9" fill="#117A65">{_esc(tr("lt_SUB_FEEDER"))}</text>']

    @staticmethod
    def _spd_branch(inc_x: float, bus_y: float, summary: PanelSummaryOutput) -> List[str]:
        if summary.selected_spd is None:
            return []
        x = inc_x + 40.0
        base = bus_y + 120.0
        pn = _esc(summary.selected_spd.part_number or "")
        cls = summary.selected_spd.spd_class or ""
        return [
            f'<line x1="{inc_x}" y1="{bus_y}" x2="{inc_x}" y2="{bus_y + 12}" stroke="#1E8449" stroke-width="1.8"/>',
            f'<line x1="{inc_x}" y1="{bus_y + 12}" x2="{x}" y2="{bus_y + 12}" stroke="#1E8449" stroke-width="1.8"/>',
            f'<line x1="{x}" y1="{bus_y + 12}" x2="{x}" y2="{base}" stroke="#1E8449" stroke-width="1.8"/>',
            f'<rect x="{x - 20}" y="{base}" width="40" height="30" rx="4" fill="#1E8449" stroke="#1F4E78" stroke-width="1.5"/>',
            f'<text x="{x}" y="{base + 19}" text-anchor="middle" font-size="10" fill="white" font-weight="bold">-F9</text>',
            f'<text x="{x}" y="{base + 42}" text-anchor="middle" font-size="8" font-weight="bold" fill="#1E8449" dir="ltr">{pn[:26]}</text>',
            f'<text x="{x}" y="{base + 54}" text-anchor="middle" font-size="8" fill="#566573">{_esc(tr("sld_spd"))} {_esc(cls)}</text>',
        ]

    @staticmethod
    def _cap_branch(x: float, bus_y: float, summary: PanelSummaryOutput) -> List[str]:
        parts: List[str] = []
        base = bus_y + 60.0
        parts.append(f'<line x1="{x}" y1="{bus_y}" x2="{x}" y2="{base}" stroke="#7D3C98" stroke-width="1.8"/>')
        pn = summary.cap_bank_protection.part_number if summary.cap_bank_protection else summary.cap_bank_suggested_str[:24]
        parts += SldGenerator._breaker(x, base, "-Qcap", pn, "#7D3C98")
        y_cur = base + 56
        if summary.cap_bank_contactor:
            parts.append(f'<line x1="{x}" y1="{y_cur - 4}" x2="{x}" y2="{y_cur}" stroke="#7D3C98" stroke-width="1.5"/>')
            parts.append(f'<rect x="{x - 20}" y="{y_cur}" width="40" height="22" rx="3" fill="#F4ECF7" stroke="#7D3C98" stroke-width="1.5"/>')
            parts.append(f'<text x="{x}" y="{y_cur + 15}" text-anchor="middle" font-size="8" fill="#7D3C98" font-weight="bold">-Kcap</text>')
            y_cur += 40
        if summary.cap_bank_reactor_dev:
            parts.append(f'<line x1="{x}" y1="{y_cur - 4}" x2="{x}" y2="{y_cur}" stroke="#7D3C98" stroke-width="1.5"/>')
            parts.append(f'<rect x="{x - 20}" y="{y_cur}" width="40" height="22" rx="3" fill="#F4ECF7" stroke="#7D3C98" stroke-width="1.5"/>')
            parts.append(f'<text x="{x}" y="{y_cur + 15}" text-anchor="middle" font-size="8" fill="#7D3C98" font-weight="bold">-Lcap</text>')
            y_cur += 40
        parts.append(f'<line x1="{x}" y1="{y_cur - 4}" x2="{x}" y2="{y_cur + 4}" stroke="#7D3C98" stroke-width="1.5"/>')
        parts.append(f'<line x1="{x - 14}" y1="{y_cur + 4}" x2="{x + 14}" y2="{y_cur + 4}" stroke="#7D3C98" stroke-width="2.5"/>')
        parts.append(f'<line x1="{x - 14}" y1="{y_cur + 12}" x2="{x + 14}" y2="{y_cur + 12}" stroke="#7D3C98" stroke-width="2.5"/>')
        steps_txt = " + ".join(f"{s:g}" for s in summary.cap_bank_steps) if summary.cap_bank_steps else f"{summary.cap_bank_installed_kvar:g}"
        detuned_txt = tr("sld_cap_detuned", a=summary.cap_bank_detuned_pct) if summary.cap_bank_detuned_pct > 0 else tr("sld_cap_std")
        parts.append(f'<text x="{x}" y="{y_cur + 32}" text-anchor="middle" font-size="9" font-weight="bold" fill="#7D3C98">{_esc(tr("sld_cap"))} {_esc(steps_txt)} kvar</text>')
        parts.append(f'<text x="{x}" y="{y_cur + 44}" text-anchor="middle" font-size="8" fill="#566573">{_esc(detuned_txt)}</text>')
        return parts

    @staticmethod
    @preliminary_drawing
    def generate_svg(project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> str:
        require_current_calculation(project, summary, feeders)
        n = max(1, len(feeders))
        # فاصله داینامیک ستون‌ها بر اساس طول بلندترین برچسب (جلوگیری از تداخل متن)
        def _label_px(f: FeederCalcOutput) -> float:
            lbl = f"{f.feeder_id} — {f.description[:40]}"
            pn = (f.selected_protection.part_number if f.selected_protection else "")[:26]
            cable = (f.cable_designation_str or "")[:24]
            return max(len(lbl) * 6.8, len(pn) * 5.2, len(cable) * 4.6)
        max_lbl_px = max((_label_px(f) for f in feeders), default=0.0)
        per_row = 5 if max_lbl_px <= 182.0 else (4 if max_lbl_px <= 235.0 else 3)
        rows = math.ceil(n / per_row)
        col_w = max(200.0, max_lbl_px + 30.0)
        w = max(1180.0, 120.0 + per_row * col_w + 40.0)
        h = 330.0 + rows * SldGenerator.ROW_H + SldGenerator.TITLE_BLOCK_H
        bus_y = 120.0
        parts: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="Tahoma, Segoe UI, sans-serif">',
            f'<rect width="{w}" height="{h}" fill="white"/>',
            f'<text x="20" y="28" font-size="17" font-weight="bold" fill="#1F4E78">{_esc(tr("sld_title"))} — {_esc(project.project_name)} ({_esc(project.panel_tag)})</text>',
            f'<text x="20" y="46" font-size="10" fill="#566573">{datetime.now().strftime("%Y-%m-%d %H:%M")} | {_esc(project.standard_ref)} | Ik″={summary.ik_used_ka if summary.ik_used_ka is not None else "?"} kA</text>',
        ]
        sel_colors = {"VERIFIED_TOTAL": "#1E8449", "VERIFIED_PARTIAL": "#B7950B",
                      "PRELIMINARY": "#566573", "PRELIMINARY_RATIO": "#566573", "VIOLATION": "#C0392B"}

        # ---- Incomer (left side) ----
        inc_x = 110.0
        if project.transformer_kva:
            parts.append(f'<circle cx="{inc_x}" cy="42" r="14" fill="none" stroke="#1F4E78" stroke-width="2"/>')
            parts.append(f'<circle cx="{inc_x}" cy="42" r="8" fill="none" stroke="#1F4E78" stroke-width="2"/>')
            parts.append(f'<text x="{inc_x}" y="76" text-anchor="middle" font-size="10" fill="#1F4E78">{_esc(tr("sld_tr"))} {project.transformer_kva:g} kVA</text>')
        else:
            parts.append(f'<path d="M {inc_x} {28} L {inc_x} {56}" stroke="#1F4E78" stroke-width="2"/>')
            parts.append(f'<path d="M {inc_x} {28} L {inc_x - 8} {38} L {inc_x + 8} {38} Z" fill="#1F4E78"/>')
            parts.append(f'<text x="{inc_x}" y="76" text-anchor="middle" font-size="10" fill="#1F4E78">{_esc(tr("sld_mains"))}</text>')
        parts.append(f'<line x1="{inc_x}" y1="56" x2="{inc_x}" y2="86" stroke="#1F4E78" stroke-width="{SldGenerator.LINE_W_POWER}"/>')
        parts += SldGenerator._breaker(inc_x, 86, "-Q0", summary.main_breaker.part_number if summary.main_breaker else summary.suggested_main_breaker_str, "#1F4E78")
        parts.append(f'<line x1="{inc_x}" y1="116" x2="{inc_x}" y2="{bus_y}" stroke="#1F4E78" stroke-width="{SldGenerator.LINE_W_POWER}"/>')

        # ---- Busbar ----
        for i, (name, color) in enumerate([("L1", "#C0392B"), ("L2", "#D35400"), ("L3", "#B7950B"), ("N", "#1F4E78"), ("PE", "#1E8449")]):
            y = bus_y + i * 8
            parts.append(f'<line x1="60" y1="{y}" x2="{w - 40}" y2="{y}" stroke="{color}" stroke-width="{SldGenerator.LINE_W_BUSBAR}"/>')
            parts.append(f'<text x="{w - 30}" y="{y + 4}" text-anchor="middle" font-size="10" font-weight="bold" fill="{color}">{name}</text>')
        parts.append(f'<text x="185" y="{bus_y - 10}" font-size="11" font-weight="bold" fill="#1F4E78">{_esc(tr("sld_busbar"))}: {_esc(summary.recommended_busbar_spec)} | PE: {_esc(summary.recommended_pe_busbar_spec)}</text>')

        # ---- SPD branch (IEC 61643-11) ----
        parts += SldGenerator._spd_branch(inc_x, bus_y, summary)

        # ---- Capacitor bank branch ----
        if summary.cap_bank_installed_kvar > 0.0:
            parts += SldGenerator._cap_branch(90.0, bus_y, summary)

        # ---- Feeders ----
        for idx, f in enumerate(feeders):
            row_i, col_i = divmod(idx, per_row)
            x = 130.0 + col_i * col_w + col_w / 2
            base = bus_y + 60 + row_i * SldGenerator.ROW_H
            color = sel_colors.get(f.selectivity_state.value if hasattr(f.selectivity_state, "value") else str(f.selectivity_state), "#566573")
            parts.append(f'<line x1="{x}" y1="{bus_y + 28}" x2="{x}" y2="{base}" stroke="#566573" stroke-width="{SldGenerator.LINE_W_POWER}"/>')
            parts += SldGenerator._breaker(x, base, f"-Q{idx + 1}", f.selected_protection.part_number if f.selected_protection else f.suggested_spec_str[:24], color)
            y_cur = base + 56
            if f.selected_contactor_main:
                parts.append(f'<line x1="{x}" y1="{y_cur - 4}" x2="{x}" y2="{y_cur}" stroke="#566573" stroke-width="{SldGenerator.LINE_W_CONTROL}"/>')
                parts.append(f'<rect x="{x - 20}" y="{y_cur}" width="40" height="24" rx="3" fill="#EBF5FB" stroke="#1F4E78" stroke-width="1.5"/>')
                parts.append(f'<text x="{x}" y="{y_cur + 16}" text-anchor="middle" font-size="9" fill="#1F4E78" font-weight="bold">-K{idx + 1}M</text>')
                y_cur += 48
            if f.selected_soft_starter or f.selected_vfd:
                dev = f.selected_soft_starter or f.selected_vfd
                parts.append(f'<line x1="{x}" y1="{y_cur - 4}" x2="{x}" y2="{y_cur}" stroke="#566573" stroke-width="{SldGenerator.LINE_W_CONTROL}"/>')
                parts.append(f'<rect x="{x - 24}" y="{y_cur}" width="48" height="24" rx="3" fill="#FEF9E7" stroke="#B7950B" stroke-width="1.5"/>')
                parts.append(f'<text x="{x}" y="{y_cur + 16}" text-anchor="middle" font-size="8" fill="#B7950B" font-weight="bold">{_esc(dev.part_number)}</text>')
                y_cur += 44
            parts.append(f'<line x1="{x}" y1="{y_cur - 4}" x2="{x}" y2="{y_cur + 16}" stroke="#566573" stroke-width="{SldGenerator.LINE_W_CONTROL}"/>')
            parts += SldGenerator._load_symbol(x, y_cur + 32, f)
            parts.append(f'<text x="{x}" y="{y_cur + 72}" text-anchor="middle" font-size="9" font-weight="bold" fill="#1C2833">{_esc(f.feeder_id)} — {_esc(f.description[:40])}</text>')
            cable = (f.cable_designation_str or "-")[:48]
            c1, c2 = cable[:24], cable[24:]
            if c2:
                parts.append(f'<text x="{x}" y="{y_cur + 84}" text-anchor="middle" font-size="8" fill="#566573" dir="ltr">{_esc(c1)}'
                             f'<tspan x="{x}" dy="1.2em">{_esc(c2)}</tspan></text>')
            else:
                parts.append(f'<text x="{x}" y="{y_cur + 84}" text-anchor="middle" font-size="8" fill="#566573" dir="ltr">{_esc(c1)}</text>')

        parts += SldGenerator._title_block(project, summary, w, h - SldGenerator.TITLE_BLOCK_H + 8.0)
        parts.append("</svg>")
        return "\n".join(parts)

    @staticmethod
    def generate_svg_file(filepath: str, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        require_current_calculation(project, summary, feeders)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(SldGenerator.generate_svg(project, feeders, summary))


class TccGenerator:
    """منحنی جریان-زمان (Time-Current Curve) لگاریتمی به صورت SVG."""

    X_MIN, X_MAX = 1.0, 100000.0   # A
    Y_MIN, Y_MAX = 0.01, 1000.0    # s
    X0, X1 = 140.0, 1140.0
    Y0, Y1 = 60.0, 640.0
    PALETTE = ["#1F4E78", "#1E8449", "#B03A2E", "#7D3C98", "#B7950B", "#117A65", "#C0392B", "#5D6D7E", "#D35400", "#2E86C1"]

    @staticmethod
    def _px(i_a: float) -> float:
        return TccGenerator.X0 + (math.log10(max(i_a, 1e-6)) - math.log10(TccGenerator.X_MIN)) / (math.log10(TccGenerator.X_MAX) - math.log10(TccGenerator.X_MIN)) * (TccGenerator.X1 - TccGenerator.X0)

    @staticmethod
    def _py(t_s: float) -> float:
        return TccGenerator.Y1 - (math.log10(max(t_s, 1e-6)) - math.log10(TccGenerator.Y_MIN)) / (math.log10(TccGenerator.Y_MAX) - math.log10(TccGenerator.Y_MIN)) * (TccGenerator.Y1 - TccGenerator.Y0)

    @classmethod
    def _curve_points(cls, dev: CatalogDevice) -> List[Tuple[float, float]]:
        curve = TripCurveRepository.get_curve(dev.series)
        in_a = dev.rated_current_in_a
        im_max_mult = curve.get("im_max_mult", 12.0)
        im = in_a * im_max_mult
        pts = []
        i = in_a * 1.13
        while i <= im:
            t = TripCurveRepository.thermal_time_s(dev.series, i / in_a)
            pts.append((i, t))
            i *= 1.06
        pts.append((im, 0.01))
        return pts

    @classmethod
    def _instantaneous_band(cls, dev: CatalogDevice, color: str) -> str:
        im_min_a, im_max_a = TripCurveRepository.instantaneous_band_a(dev.series, dev.rated_current_in_a)
        x1, x2 = cls._px(im_min_a), cls._px(im_max_a)
        y1, y2 = cls._py(0.02), cls._py(0.01)
        return f'<rect x="{x1:.1f}" y="{y2:.1f}" width="{max(x2 - x1, 2.0):.1f}" height="{max(y1 - y2, 2.0):.1f}" fill="{color}" opacity="0.35"/>'

    @classmethod
    def _polyline(cls, pts: List[Tuple[float, float]], color: str, width: float = 2.2, dash: str = "") -> str:
        coords = " ".join(f"{cls._px(i):.1f},{cls._py(t):.1f}" for i, t in pts)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}"{d}/>'

    @staticmethod
    @preliminary_drawing
    def generate_svg(project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> str:
        require_current_calculation(project, summary, feeders)
        parts: List[str] = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="720" font-family="Tahoma, Segoe UI, sans-serif">',
            '<rect width="1180" height="720" fill="white"/>',
            f'<text x="20" y="30" font-size="17" font-weight="bold" fill="#1F4E78">{_esc(tr("tcc_title"))} — {_esc(project.project_name)}</text>',
        ]
        # Grid
        for i_a in (1, 10, 100, 1000, 10000, 100000):
            x = TccGenerator._px(float(i_a))
            parts.append(f'<line x1="{x:.1f}" y1="{TccGenerator.Y0}" x2="{x:.1f}" y2="{TccGenerator.Y1}" stroke="#E5E8E8" stroke-width="1"/>')
            parts.append(f'<text x="{x:.1f}" y="{TccGenerator.Y1 + 20}" text-anchor="middle" font-size="10" fill="#566573">{i_a:,} A</text>')
        for t_s in (0.01, 0.1, 1, 10, 100, 1000):
            y = TccGenerator._py(float(t_s))
            parts.append(f'<line x1="{TccGenerator.X0}" y1="{y:.1f}" x2="{TccGenerator.X1}" y2="{y:.1f}" stroke="#E5E8E8" stroke-width="1"/>')
            label = "10 ms" if t_s == 0.01 else ("100 ms" if t_s == 0.1 else f"{t_s:g} s")
            parts.append(f'<text x="{TccGenerator.X0 - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#566573">{label}</text>')
        parts.append(f'<rect x="{TccGenerator.X0}" y="{TccGenerator.Y0}" width="{TccGenerator.X1 - TccGenerator.X0}" height="{TccGenerator.Y1 - TccGenerator.Y0}" fill="none" stroke="#BDC3C7" stroke-width="1.5"/>')

        # Ik line
        if summary.ik_used_ka is not None:
            x = TccGenerator._px(summary.ik_used_ka * 1000.0)
            parts.append(f'<line x1="{x:.1f}" y1="{TccGenerator.Y0}" x2="{x:.1f}" y2="{TccGenerator.Y1}" stroke="#C0392B" stroke-width="2" stroke-dasharray="6,4"/>')
            parts.append(f'<text x="{x + 5:.1f}" y="{TccGenerator.Y0 + 14}" font-size="11" font-weight="bold" fill="#C0392B">{_esc(tr("tcc_ik"))} {summary.ik_used_ka} kA</text>')

        legend_y = TccGenerator.Y0 + 6
        def _legend(color: str, text: str):
            nonlocal legend_y
            s = f'<line x1="870" y1="{legend_y}" x2="896" y2="{legend_y}" stroke="{color}" stroke-width="2.5"/>'
            s += f'<text x="902" y="{legend_y + 4}" font-size="10" fill="#1C2833" dir="ltr">{_esc(text)}</text>'
            legend_y += 17
            return s

        # Main breaker curve
        any_estimated = False
        def _est_mark(dev: Optional[CatalogDevice]) -> str:
            return "" if (dev is None or TripCurveRepository.is_datasheet_points(dev.series)) else " ≈"

        if summary.main_breaker:
            mb_mark = _est_mark(summary.main_breaker)
            any_estimated = any_estimated or bool(mb_mark)
            parts.append(TccGenerator._polyline(TccGenerator._curve_points(summary.main_breaker), "#1F4E78", 3.0))
            parts.append(TccGenerator._instantaneous_band(summary.main_breaker, "#1F4E78"))
            parts.append(_legend("#1F4E78", f'{tr("tcc_main")}: {summary.main_breaker.part_number} ({summary.main_breaker.rated_current_in_a:g}A){mb_mark}'))
            if summary.main_breaker.icu_ka_400v > 0:
                x = TccGenerator._px(summary.main_breaker.icu_ka_400v * 1000.0)
                parts.append(f'<line x1="{x:.1f}" y1="{TccGenerator.Y0}" x2="{x:.1f}" y2="{TccGenerator.Y1}" stroke="#7F8C8D" stroke-width="1.5" stroke-dasharray="2,4"/>')

        # Feeder curves
        for i, f in enumerate(feeders):
            dev = f.selected_protection
            if not dev: continue
            f_mark = _est_mark(dev)
            any_estimated = any_estimated or bool(f_mark)
            color = TccGenerator.PALETTE[(i + 1) % len(TccGenerator.PALETTE)]
            parts.append(TccGenerator._polyline(TccGenerator._curve_points(dev), color))
            parts.append(TccGenerator._instantaneous_band(dev, color))
            parts.append(_legend(color, f"{f.feeder_id}: {dev.part_number} ({dev.rated_current_in_a:g}A){f_mark}"))
            if dev.icu_ka_400v > 0:
                x = TccGenerator._px(dev.icu_ka_400v * 1000.0)
                parts.append(f'<line x1="{x:.1f}" y1="{TccGenerator.Y0}" x2="{x:.1f}" y2="{TccGenerator.Y1}" stroke="#BDC3C7" stroke-width="1" stroke-dasharray="2,4"/>')
            if f.selectivity_limit_is_ka:
                x = TccGenerator._px(f.selectivity_limit_is_ka * 1000.0)
                parts.append(f'<line x1="{x:.1f}" y1="{TccGenerator.Y0}" x2="{x:.1f}" y2="{TccGenerator.Y1}" stroke="#B7950B" stroke-width="1.8" stroke-dasharray="8,5"/>')
                parts.append(f'<text x="{x + 5:.1f}" y="{TccGenerator.Y0 + 30}" font-size="9" fill="#B7950B">{_esc(tr("tcc_sel"))} {_esc(f.feeder_id)} = {f.selectivity_limit_is_ka:g} kA</text>')

        # فاز تحلیل TCC: علامت‌گذاری تقاطع ریاضی منحنی کلید اصلی و هر فیدر
        if summary.main_breaker:
            from lv_assist.tcc_analyzer import TccAnalyzer
            inter_y = (TccGenerator.Y0 + TccGenerator.Y1) / 2.0
            for i, f in enumerate(feeders):
                dev = f.selected_protection
                if not dev:
                    continue
                try:
                    inter = TccAnalyzer.find_intersection(summary.main_breaker, dev)
                except Exception:
                    continue
                if not inter.intersection_a or inter.intersection_a <= TccGenerator.X_MIN \
                        or inter.intersection_a >= TccGenerator.X_MAX:
                    continue
                x = TccGenerator._px(inter.intersection_a)
                color = TccGenerator.PALETTE[(i + 1) % len(TccGenerator.PALETTE)]
                parts.append(f'<circle cx="{x:.1f}" cy="{inter_y:.1f}" r="5" fill="none" stroke="{color}" stroke-width="2"/>')
                parts.append(f'<circle cx="{x:.1f}" cy="{inter_y:.1f}" r="1.8" fill="{color}"/>')
                parts.append(f'<text x="{x:.1f}" y="{inter_y - 9:.1f}" text-anchor="middle" font-size="8.5" fill="{color}" dir="ltr">Is = {inter.intersection_a / 1000.0:g} kA</text>')

        # F-003: برچسب بصری واضح برای منحنی‌های تخمینی
        if any_estimated:
            parts.append(f'<text x="{TccGenerator.X1}" y="30" text-anchor="end" font-size="11" font-weight="bold" fill="#B7950B">≈ {_esc(tr("tcc_estimated_note"))}</text>')
            parts.append(f'<text x="{TccGenerator.X1}" y="44" text-anchor="end" font-size="8.5" fill="#854D0E" dir="ltr">{_esc(tr("tcc_estimated_sub"))}</text>')

        # Motor starting points
        for i, f in enumerate(feeders):
            if f.starting_kva <= 0: continue
            i_start_a = f.starting_kva * 1000.0 / (math.sqrt(3) * project.nominal_voltage_v)
            t_start = {LoadType.MOTOR_DOL: 2.0, LoadType.MOTOR_STAR_DELTA: 5.0,
                       LoadType.MOTOR_SOFT_STARTER: 10.0, LoadType.MOTOR_VFD: 2.0}.get(f.load_type, 2.0)
            x, y = TccGenerator._px(i_start_a), TccGenerator._py(t_start)
            color = TccGenerator.PALETTE[(i + 1) % len(TccGenerator.PALETTE)]
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}"/>')
            parts.append(f'<text x="{x + 8:.1f}" y="{y - 5:.1f}" font-size="9" fill="{color}">{_esc(f.feeder_id)} {_esc(tr("tcc_start"))}</text>')

        parts.append(f'<text x="20" y="{TccGenerator.Y1 + 48}" font-size="10" fill="#B7950B">{_esc(tr("tcc_note"))} {_esc(tr("tcc_curve_note"))}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

    @staticmethod
    def generate_svg_file(filepath: str, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        require_current_calculation(project, summary, feeders)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(TccGenerator.generate_svg(project, feeders, summary))


class PdfExporter:
    """تبدیل گزارش HTML به PDF با استفاده از مرورگر نصب‌شده (بدون وابستگی پایتونی)."""

    EDGE_CANDIDATES = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/microsoft-edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]

    @classmethod
    def _find_browser(cls) -> Optional[str]:
        for p in cls.EDGE_CANDIDATES:
            if os.path.exists(p):
                return p
        for name in ("msedge", "chrome", "chromium", "chromium-browser", "microsoft-edge", "google-chrome"):
            found = shutil.which(name)
            if found:
                return found
        return None

    @classmethod
    def export_html_to_pdf(cls, html_path: str, pdf_path: str) -> bool:
        browser = cls._find_browser()
        if not browser:
            return False
        url = Path(os.path.abspath(html_path)).as_uri()
        browsers = [browser] + [p for p in cls.EDGE_CANDIDATES if p != browser and os.path.isfile(p)]
        for candidate in browsers:
            try:
                with tempfile.TemporaryDirectory(prefix='lvassist_pdf_', dir=str(Path(pdf_path).resolve().parent)) as profile_dir:
                    subprocess.run(
                        [candidate, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                         "--no-pdf-header-footer", f"--user-data-dir={profile_dir}",
                         f"--print-to-pdf={os.path.abspath(pdf_path)}", url],
                        check=True, capture_output=True, timeout=120,
                    )
                if os.path.isfile(pdf_path) and Path(pdf_path).read_bytes().startswith(b'%PDF-'):
                    return True
            except (subprocess.SubprocessError, OSError):
                continue
        return False


def _bom_entries(project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> List[tuple]:
    from lv_assist.bom import iter_device_entries
    return iter_device_entries(project, feeders, summary)


class EplanExporter:
    """خروجی CSV قطعات سازگار با EPLAN Electric P8 Parts Management."""

    HEADERS = ["Part number", "Type number", "Manufacturer", "Description 1", "Device tag", "Function", "Qty", "Unit", "Data quality"]

    @staticmethod
    def _tag(func: str, loc: str, bmk: str) -> str:
        return f"{func}{loc}{bmk}"

    @classmethod
    def export_csv(cls, filepath: str, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        require_current_calculation(project, summary, feeders)
        rows: List[list] = []
        for func, loc, bmk, cat, dev, spec, qty in _bom_entries(project, feeders, summary):
            if dev is None:
                rows.append(["", "", "To be purchased", spec, cls._tag(func, loc, bmk), cat, qty, "PCS", "ESTIMATED"])
            else:
                rows.append([dev.part_number, f"{dev.series} {dev.device_type}", dev.manufacturer,
                             f"{dev.series} ({dev.device_type})", cls._tag(func, loc, bmk), cat, qty, "PCS", dev.data_quality.value])

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(cls.HEADERS)
            writer.writerows(rows)


class EplanPartsExporter:
    """CSV ایمپورت به EPLAN Parts Management: هر شماره فنی یک ردیف با مجموع تعداد."""

    HEADERS = ["Part number", "Type number", "Order number", "Manufacturer", "Description 1",
               "Description 2", "Technical data 1", "Technical data 2", "Product group",
               "Quantity unit", "Quantity"]

    GROUP_MAP = {
        "MCCB": "Circuit breakers", "MCB": "Circuit breakers", "MCB_2P_CTRL": "Circuit breakers",
        "MPCB": "Motor-protective circuit breakers", "RCD": "Residual current devices",
        "CONTACTOR": "Contactors", "CAP_CONTACTOR": "Contactors",
        "BIMETAL": "Overload relays", "TIMER_YD": "Timing relays",
        "VFD": "Frequency converters", "SOFT_STARTER": "Soft starters",
        "PSU_24V": "Power supplies", "DC_SEL_MOD": "Electronic modules",
        "FAN_FILTER": "Fans", "ENCLOSURE": "Enclosures",
        "DETUNED_REACTOR": "Reactors", "CAP_MODULE": "Capacitors",
    }

    @classmethod
    def export_csv(cls, filepath: str, project: ProjectSpec, feeders: List[FeederCalcOutput], summary: PanelSummaryOutput) -> None:
        require_current_calculation(project, summary, feeders)
        agg: dict = {}
        for _, _, _, _, dev, _, qty in _bom_entries(project, feeders, summary):
            if dev is None:
                continue
            if dev.part_number in agg:
                agg[dev.part_number][1] += qty
            else:
                agg[dev.part_number] = [dev, qty]

        rows: List[list] = []
        for dev, qty in sorted(agg.values(), key=lambda x: x[0].part_number):
            td1 = f"In={dev.rated_current_in_a:g}A" if dev.rated_current_in_a else ""
            if dev.icu_ka_400v > 0:
                td1 += f" | Icu={dev.icu_ka_400v:g}kA"
            td2 = f"Loss={dev.power_loss_w:g}W"
            dims = " x ".join(f"{d:g}" for d in (dev.width_mm, dev.height_mm, dev.depth_mm) if d)
            if dims:
                td2 += f" | {dims} mm"
            rows.append([dev.part_number, dev.part_number, "", dev.manufacturer,
                         f"{dev.series} ({dev.device_type})", "", td1, td2,
                         cls.GROUP_MAP.get(dev.device_type, "Others"), "PCS", qty])

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(cls.HEADERS)
            writer.writerows(rows)
