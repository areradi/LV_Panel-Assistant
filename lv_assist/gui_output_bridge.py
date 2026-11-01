# -*- coding: utf-8 -*-
"""
LV-PanelAssist GUI-to-IEC SVG Output Bridge (lv_assist/gui_output_bridge.py)
Transforms live calculation outputs from gui.py / engine.py into:
  1. Dynamic IEC 60617 Single-Line Diagram SVG (via lv_assist/iec_sld_svg.py)
  2. Dynamic Per-Feeder IEC Ladder / Multi-Line Control Schematics (via lv_assist/iec_ladder_svg.py)
  3. Dynamic Wire Ferrule Schedule & Terminal/Cable Schedule
  4. Automatic HTML Engineering Report Injection (Zero Hardcoding, Zero Calc Engine Modification)
"""

import os
import html
from typing import List, Dict, Any, Optional, Tuple

from lv_assist.iec_sld_svg import (
    SLDPanelDTO,
    SLDFeederDTO,
    IECSldSvgGenerator,
)
from lv_assist.iec_ladder_svg import (
    FeederLadderDTO,
    IECLadderSvgGenerator,
)


class GuiOutputBridge:
    """
    پل ارتباطی استاندارد بین داده‌های زنده gui.py و موتورهای ترسیم iec_sld_svg.py و iec_ladder_svg.py
    بدون تغییر منطق محاسباتی و بدون هیچ داده Hard-code شده.
    """

    @staticmethod
    def _val_str(val: Any) -> str:
        if val is None:
            return ""
        return str(getattr(val, "value", val))

    @classmethod
    def to_sld_dto(cls, project: Any, feeders_out: List[Any], summary: Any) -> SLDPanelDTO:
        """تبدیل مدل‌های زنده پروژه و فیدرها به ساختار ورودی iec_sld_svg.py"""
        sld_feeders: List[SLDFeederDTO] = []

        for idx, f in enumerate(feeders_out, start=1):
            prot = getattr(f, "selected_protection", None)
            cont_main = getattr(f, "selected_contactor_main", None) or getattr(f, "selected_contactor", None)
            cont_delta = getattr(f, "selected_contactor_delta", None)
            cont_star = getattr(f, "selected_contactor_star", None)
            bimetal = getattr(f, "selected_bimetal", None) or getattr(f, "selected_overload", None)
            vfd = getattr(f, "selected_vfd", None) or getattr(f, "selected_soft_starter", None)
            rcd = getattr(f, "selected_rcd", None)
            ltype = cls._val_str(getattr(f, "load_type", "SUB_FEEDER"))

            sw_tag, sw_part = "", ""
            if ltype == "MOTOR_STAR_DELTA" and cont_main:
                sw_tag = f"-K{idx}M/-K{idx}D/-K{idx}Y"
                ky_p = getattr(cont_star, "part_number", "")
                sw_part = f"2x{cont_main.part_number} + {ky_p}"
            elif vfd:
                sw_tag = f"-U{idx}"
                sw_part = getattr(vfd, "part_number", "")
            elif cont_main:
                sw_tag = f"-K{idx}M"
                sw_part = getattr(cont_main, "part_number", "")
            elif rcd:
                sw_tag = f"-F{idx}R"
                sw_part = getattr(rcd, "part_number", "")

            ol_tag, ol_part, ol_range = "", "", ""
            if bimetal:
                ol_tag = f"-F{idx}"
                ol_part = getattr(bimetal, "part_number", "")
                s_min = getattr(bimetal, "setting_min_a", 0.0)
                s_max = getattr(bimetal, "setting_max_a", 0.0)
                ol_range = f"{s_min:g}-{s_max:g}A" if s_max > 0 else ""

            sel_state = cls._val_str(getattr(f, "selectivity_state", ""))
            is_ka = getattr(f, "selectivity_limit_is_ka", None)
            sel_str = f"{sel_state} (Is={is_ka}kA)" if is_ka else sel_state

            sld_feeders.append(SLDFeederDTO(
                feeder_id=str(getattr(f, "feeder_id", f"F{idx:02d}")),
                func_tag=str(getattr(f, "func_tag", "=PWR")),
                loc_tag=str(getattr(f, "loc_tag", getattr(project, "panel_tag", "+MCC1"))),
                description=str(getattr(f, "description", "")),
                load_type=ltype,
                power_kw=float(getattr(f, "power_kw", 0.0)),
                design_current_ib_a=float(getattr(f, "design_current_ib_a", 0.0)),
                protection_tag=f"-Q{idx}",
                protection_part=str(getattr(prot, "part_number", "UNSELECTED")),
                protection_in_a=float(getattr(prot, "rated_current_in_a", 0.0)),
                protection_icu_ka=float(getattr(prot, "icu_ka_400v", 0.0)),
                switching_tag=sw_tag,
                switching_part=sw_part,
                overload_tag=ol_tag,
                overload_part=ol_part,
                overload_range=ol_range,
                cable_designation=str(getattr(f, "cable_designation_str", "")),
                cable_length_m=float(getattr(f, "cable_length_m", 0.0) or 0.0),
                voltage_drop_pct=float(getattr(f, "voltage_drop_percent", 0.0) or 0.0),
                selectivity_status=sel_str
            ))

        main_brk = getattr(summary, "main_breaker", None)
        psu = getattr(summary, "selected_psu_24v", None)
        busbar_obj = getattr(summary, "busbar", None)
        bus_spec = getattr(summary, "recommended_busbar_spec", None) or getattr(busbar_obj, "spec", "Cu Busbar")
        pe_spec = getattr(summary, "recommended_pe_busbar_spec", "PE Cu Bar")
        inc_cable = getattr(summary, "recommended_incoming_cable_str", "Incoming 3P+N+PE")

        psu_w = getattr(summary, "ctrl_24v_total_continuous_w", 0.0)
        psu_a = getattr(summary, "ctrl_24v_design_current_with_spare_a", 0.0)
        psu_str = f"24VDC Load = {psu_w}W ({psu_a}A w/Spare)" if psu_w else "24VDC Control Circuit"

        ik_val = getattr(summary, "ik_total_ka", None) or getattr(project, "prospective_ik_ka", 25.0) or 25.0

        return SLDPanelDTO(
            project_name=str(getattr(project, "project_name", "LV Switchboard")),
            panel_tag=str(getattr(project, "panel_tag", "+MCC1")),
            standard_ref=str(getattr(project, "standard_ref", "IEC 61439-2")),
            nominal_voltage_v=float(getattr(project, "nominal_voltage_v", 400.0)),
            frequency_hz=float(getattr(project, "frequency_hz", 50.0)),
            earthing_system=cls._val_str(getattr(project, "earthing_system", "TN-S")),
            prospective_ik_ka=float(ik_val),
            main_breaker_tag="-Q0",
            main_breaker_part=str(getattr(main_brk, "part_number", "Main Breaker")),
            main_breaker_in_a=float(getattr(main_brk, "rated_current_in_a", 0.0)),
            main_breaker_icu_ka=float(getattr(main_brk, "icu_ka_400v", 0.0)),
            design_main_current_a=float(getattr(summary, "design_main_current_a", 0.0)),
            busbar_spec=str(bus_spec),
            pe_busbar_spec=str(pe_spec),
            incoming_cable_spec=str(inc_cable),
            psu_tag="-G1",
            psu_part=str(getattr(psu, "part_number", "SITOP 24VDC")),
            psu_rating_str=psu_str,
            feeders=sld_feeders
        )

    @classmethod
    def to_feeder_ladder_dto(
        cls, project: Any, feeder_out: Any, summary: Any, feeder_index: int = 1
    ) -> FeederLadderDTO:
        """تبدیل اطلاعات یک فیدر محاسبه‌شده به ورودی iec_ladder_svg.py"""
        prot = getattr(feeder_out, "selected_protection", None)
        km = getattr(feeder_out, "selected_contactor_main", None) or getattr(feeder_out, "selected_contactor", None)
        kd = getattr(feeder_out, "selected_contactor_delta", None)
        ky = getattr(feeder_out, "selected_contactor_star", None)
        bm = getattr(feeder_out, "selected_bimetal", None) or getattr(feeder_out, "selected_overload", None)
        tmr = getattr(feeder_out, "selected_timer_yd", None)
        vfd = getattr(feeder_out, "selected_vfd", None) or getattr(feeder_out, "selected_soft_starter", None)
        psu = getattr(summary, "selected_psu_24v", None)

        idx = feeder_index
        return FeederLadderDTO(
            feeder_index=idx,
            sheet_no=10 + idx,
            project_name=str(getattr(project, "project_name", "LV Switchboard")),
            panel_tag=str(getattr(project, "panel_tag", "+MCC1")),
            feeder_id=str(getattr(feeder_out, "feeder_id", f"F{idx:02d}")),
            func_tag=str(getattr(feeder_out, "func_tag", f"=F{idx}")),
            loc_tag=str(getattr(feeder_out, "loc_tag", getattr(project, "panel_tag", "+MCC1"))),
            description=str(getattr(feeder_out, "description", "")),
            load_type=cls._val_str(getattr(feeder_out, "load_type", "MOTOR_DOL")),
            power_kw=float(getattr(feeder_out, "power_kw", 0.0)),
            ib_a=float(getattr(feeder_out, "design_current_ib_a", 0.0)),
            delta_current_a=float(getattr(feeder_out, "delta_loop_current_a", 0.0) or 0.0),
            star_current_a=float(getattr(feeder_out, "star_current_a", 0.0) or 0.0),
            prot_tag=f"-Q{idx}",
            prot_part=str(getattr(prot, "part_number", "NONE")),
            prot_in_a=float(getattr(prot, "rated_current_in_a", 0.0)),
            km_tag=f"-K{idx}M" if km else "",
            km_part=str(getattr(km, "part_number", "")) if km else "",
            kd_tag=f"-K{idx}D" if kd else "",
            kd_part=str(getattr(kd, "part_number", "")) if kd else "",
            ky_tag=f"-K{idx}Y" if ky else "",
            ky_part=str(getattr(ky, "part_number", "")) if ky else "",
            bimetal_tag=f"-F{idx}" if bm else "",
            bimetal_part=str(getattr(bm, "part_number", "")) if bm else "",
            timer_tag=f"-K{idx}T" if tmr else "",
            timer_part=str(getattr(tmr, "part_number", "")) if tmr else "",
            vfd_tag=f"-U{idx}" if vfd else "",
            vfd_part=str(getattr(vfd, "part_number", "")) if vfd else "",
            power_cable_str=str(getattr(feeder_out, "cable_designation_str", "")),
            psu_part=str(getattr(psu, "part_number", "SITOP 24VDC"))
        )

    @classmethod
    def generate_sld_svg(cls, project: Any, feeders_out: List[Any], summary: Any) -> str:
        """تولید کد برداری SVG نقشه تک‌خطی کل تابلو"""
        dto = cls.to_sld_dto(project, feeders_out, summary)
        return IECSldSvgGenerator.render_sld_svg(dto)

    @classmethod
    def generate_feeder_ladder_svg(
        cls, project: Any, feeder_out: Any, summary: Any, feeder_index: int = 1
    ) -> str:
        """تولید کد برداری SVG نقشه مدار فرمان برای یک فیدر مشخص"""
        dto = cls.to_feeder_ladder_dto(project, feeder_out, summary, feeder_index=feeder_index)
        return IECLadderSvgGenerator.render_feeder_ladder_svg(dto)

    @classmethod
    def generate_all_ladder_svgs(
        cls, project: Any, feeders_out: List[Any], summary: Any
    ) -> Dict[str, str]:
        """تولید دیکشنری کامل مدار فرمان تمام فیدرهای پروژه {feeder_id: svg_str}"""
        result: Dict[str, str] = {}
        for idx, f in enumerate(feeders_out, start=1):
            fid = str(getattr(f, "feeder_id", f"F{idx:02d}"))
            result[fid] = cls.generate_feeder_ladder_svg(project, f, summary, feeder_index=idx)
        return result

    @classmethod
    def generate_all_wire_and_terminal_schedules(
        cls, project: Any, feeders_out: List[Any], summary: Any
    ) -> Tuple[List[dict], List[dict]]:
        """تولید جدول یکپارچه وایرشو (From-To Wires) و ترمینال‌بندی برای کل فیدرهای پروژه"""
        all_wires: List[dict] = []
        all_terminals: List[dict] = []
        for idx, f in enumerate(feeders_out, start=1):
            dto = cls.to_feeder_ladder_dto(project, f, summary, feeder_index=idx)
            sched = IECLadderSvgGenerator.build_feeder_wires_and_terminals(dto)
            all_wires.extend(sched["wires"])
            all_terminals.extend(sched["terminals"])
        return all_wires, all_terminals

    @classmethod
    def export_all_svgs_to_folder(
        cls, folder_path: str, project: Any, feeders_out: List[Any], summary: Any
    ) -> List[str]:
        """ذخیره فایل‌های مستقل .svg برای نقشه تک‌خطی و مدار فرمان تمام فیدرها"""
        os.makedirs(folder_path, exist_ok=True)
        saved_files: List[str] = []

        sld_path = os.path.join(folder_path, "01_IEC_Single_Line_Diagram.svg")
        with open(sld_path, "w", encoding="utf-8") as fp:
            fp.write(cls.generate_sld_svg(project, feeders_out, summary))
        saved_files.append(sld_path)

        for idx, f in enumerate(feeders_out, start=1):
            fid = str(getattr(f, "feeder_id", f"F{idx:02d}"))
            lad_path = os.path.join(folder_path, f"{idx + 1:02d}_IEC_Control_Ladder_{fid}.svg")
            with open(lad_path, "w", encoding="utf-8") as fp:
                fp.write(cls.generate_feeder_ladder_svg(project, f, summary, feeder_index=idx))
            saved_files.append(lad_path)

        return saved_files

    @classmethod
    def inject_schematics_into_html_report(
        cls, html_filepath: str, project: Any, feeders_out: List[Any], summary: Any
    ) -> None:
        """
        تزریق خودکار نقشه تک‌خطی (SLD)، نقشه‌های مدار فرمان تمام فیدرها و جداول سیم‌کشی/ترمینال
        به درون فایل گزارش چاپی HTML
        """
        if not os.path.exists(html_filepath):
            return

        sld_svg = cls.generate_sld_svg(project, feeders_out, summary)
        ladder_map = cls.generate_all_ladder_svgs(project, feeders_out, summary)
        wires, terminals = cls.generate_all_wire_and_terminal_schedules(project, feeders_out, summary)

        esc = lambda s: html.escape(str(s or ""))

        ladder_sections_html = []
        for idx, f in enumerate(feeders_out, start=1):
            fid = str(getattr(f, "feeder_id", f"F{idx:02d}"))
            fdesc = str(getattr(f, "description", ""))
            svg_code = ladder_map.get(fid, "")
            ladder_sections_html.append(f"""
            <div style="page-break-before: always; margin-top: 18px;">
                <h2>نقشه اجرایی مدار فرمان و قدرت فیدر {esc(fid)} — {esc(fdesc)} (IEC 60617 / EPLAN Multi-Line)</h2>
                {svg_code}
            </div>
            """)

        wire_rows_html = "".join(
            f"<tr><td dir='ltr'><b>{esc(w['wire_no'])}</b></td>"
            f"<td dir='ltr'><b>{esc(w['feeder_id'])}</b></td>"
            f"<td>{esc(w['potential_role'])}</td>"
            f"<td dir='ltr'><b>{esc(w['from_pin'])}</b></td>"
            f"<td dir='ltr'><b>{esc(w['to_pin'])}</b></td>"
            f"<td dir='ltr'>{esc(w['wire_spec'])}</td></tr>"
            for w in wires
        )

        term_rows_html = "".join(
            f"<tr><td dir='ltr'><b>{esc(t['feeder_id'])}</b></td>"
            f"<td dir='ltr'><b>{esc(t['terminal_strip'])}{esc(t['terminal_pin'])}</b></td>"
            f"<td dir='ltr'>{esc(t['internal_wire_no'])} ({esc(t['internal_target'])})</td>"
            f"<td dir='ltr'><b>{esc(t['cable_tag'])} ({esc(t['cable_core'])})</b></td>"
            f"<td dir='ltr'>{esc(t['cable_spec'])}</td>"
            f"<td dir='ltr'><b>{esc(t['external_location'])} / {esc(t['external_target'])}</b></td></tr>"
            for t in terminals
        )

        injected_block = f"""
        <div style="page-break-before: always; margin-top: 18px;">
            <h2>نقشه تک‌خطی مهندسی تابلو (IEC 60617 Single-Line Diagram — Dynamic SLD)</h2>
            {sld_svg}
        </div>
        {"".join(ladder_sections_html)}
        <div style="page-break-before: always; margin-top: 18px;">
            <h2>جدول جامع شماره‌گذاری سیم‌ها و وایرشو (From-To Wire Ferrule Schedule)</h2>
            <table>
                <thead>
                    <tr>
                        <th>شماره سیم (در بیضی آبی)</th><th>فیدر</th><th>نقش پتانسیل</th>
                        <th>مبدأ اتصال (From Device:Pin)</th><th>مقصد اتصال (To Device:Pin)</th><th>مشخصات سیم</th>
                    </tr>
                </thead>
                <tbody>{wire_rows_html}</tbody>
            </table>

            <h2>جدول سرسیم‌بندی ریل‌های ترمینال (-X) و کابل‌های فرمان سایت (-W)</h2>
            <table>
                <thead>
                    <tr>
                        <th>فیدر</th><th>ترمینال تابلو</th><th>سیم و اتصال داخلی</th>
                        <th>تگ کابل و شماره رشته</th><th>مشخصات کابل</th><th>محل نصب و تجهیز بیرونی</th>
                    </tr>
                </thead>
                <tbody>{term_rows_html}</tbody>
            </table>
        </div>
        """

        with open(html_filepath, "r", encoding="utf-8") as fp:
            content = fp.read()

        if '<div class="disclaimer">' in content:
            content = content.replace('<div class="disclaimer">', injected_block + '\n<div class="disclaimer">', 1)
        elif "</body>" in content:
            content = content.replace("</body>", injected_block + "\n</body>", 1)
        else:
            content += injected_block

        with open(html_filepath, "w", encoding="utf-8") as fp:
            fp.write(content)

    @classmethod
    def export_sld_svg_to_folder(cls, folder_path: str, project, feeders_out, summary):
        """ذخیره مستقل فقط نقشه تک‌خطی (بدون هیچ فایل مدار فرمان)."""
        os.makedirs(folder_path, exist_ok=True)
        sld_path = os.path.join(folder_path, "Single_Line_Diagram.svg")
        with open(sld_path, "w", encoding="utf-8") as fp:
            fp.write(cls.generate_sld_svg(project, feeders_out, summary))
        return [sld_path]

    @classmethod
    def export_control_svgs_to_folder(cls, folder_path: str, project, feeders_out, summary):
        """ذخیره مستقل فقط نقشه‌های مدار فرمان (بدون هیچ فایل SLD)."""
        os.makedirs(folder_path, exist_ok=True)
        saved = []
        for idx, f in enumerate(feeders_out, start=1):
            fid = str(getattr(f, "feeder_id", f"F{idx:02d}"))
            p = os.path.join(folder_path, f"Control_Ladder_{fid}.svg")
            with open(p, "w", encoding="utf-8") as fp:
                fp.write(cls.generate_feeder_ladder_svg(project, f, summary, feeder_index=idx))
            saved.append(p)
        return saved

