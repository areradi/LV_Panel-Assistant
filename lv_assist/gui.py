
# --- Stubs for removed EPLAN/AutoCAD modules (v0.8 cleanup) ---
class _RemovedExporterStub:
    def __init__(self, *args, **kwargs): pass
    def __getattr__(self, name):
        return lambda *a, **kw: []

EplanExporter = _RemovedExporterStub
EplanMacroGenerator = _RemovedExporterStub
EplanMacroFileExporter = _RemovedExporterStub
EplanFieldTestExporter = _RemovedExporterStub

# -*- coding: utf-8 -*-
"""
LV-PanelAssist v0.7 — برنامه اصلی یکپارچه (ادغام ویزارد گام‌به‌گام در پوسته مینیمال).

ساختار UI/UX: سایدبار ۷ مرحله‌ای (پروژه و ساختار IEC 81346 → فیدرها → ابزار دقیق و
PLC → محاسبات و نتایج → نقشه‌ها → خروجی‌ها → کاتالوگ و قیمت) — بدون نیاز به اکسل
برای شروع؛ اکسل همچنان به‌عنوان ورود گروهی پشتیبانی می‌شود.
"""
import os
import math
import sys
import webbrowser
import zipfile
import tempfile
from datetime import datetime
from typing import Tuple, List, Optional
import tkinter as tk
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk, simpledialog

from lv_assist.paths import get_app_working_dir, config_file_path, get_output_dir
from lv_assist.models import (
    ProjectSpec, FeederInput, EarthingSystem, LoadType, ValidationStatus,
    PanelType, SpecialScenario, ConductorMaterial, InsulationType, InstallationMethod, SpdClass,
    CatalogDevice, DataQuality
)
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine, build_design_verification
from lv_assist.exporters import ExcelExporter, PrintableReportExporter, DesignVerificationExporter
from lv_assist.outputs import SldGenerator, TccGenerator, PdfExporter, EplanExporter, EplanPartsExporter
from lv_assist.control_circuits import ControlCircuitGenerator
from lv_assist.layout import PanelLayoutGenerator
pass  # [v0.8 REMOVED] from lv_assist.eplan_macro import EplanMacroExporter
pass  # [v0.8 REMOVED] from lv_assist.eplan_macro_files import EplanMacroFileExporter, EplanPageMacroExporter
pass  # [v0.8 REMOVED] from lv_assist.eplan_field_test import EplanFieldTestKit
from lv_assist.i18n import tr, i18n
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.field_wizard_engine import (
    AutomationSignalType, FieldInstrumentInput, IndustrialAutomationEngine,
)
from lv_assist import web_catalog
from lv_assist.gui_helpers import (
    AsyncWebSearchManager,
    FieldValidationError,
    parse_cable_length_input,
)

LANG_SEGMENT_TO_CODE = {"FA": "fa", "EN": "en", "DE": "de"}


class LocalizedOptionMenu(ctk.CTkOptionMenu):
    """Display translated labels while keeping stable model values at the UI boundary."""

    def __init__(self, master, *, values, translation_prefix, command=None, **kwargs):
        self._translation_prefix = translation_prefix
        self._raw_values = list(values)
        self._labels = {value: tr(f"{translation_prefix}{value}") for value in values}
        callback = (lambda _label: command(self.get())) if command else None
        super().__init__(master, values=list(self._labels.values()), command=callback, **kwargs)

    def get(self):
        label = super().get()
        return next((value for value, text in self._labels.items() if text == label), label)

    def set(self, value):
        super().set(self._labels.get(value, value))

    def cget(self, attribute_name):
        if attribute_name == "values":
            return self._raw_values.copy()
        return super().cget(attribute_name)

    def configure(self, require_redraw=False, **kwargs):
        if "values" in kwargs:
            self._raw_values = list(kwargs["values"])
            self._labels = {value: tr(f"{self._translation_prefix}{value}") for value in self._raw_values}
            kwargs["values"] = list(self._labels.values())
        return super().configure(require_redraw=require_redraw, **kwargs)

DEVICE_TYPE_OPTIONS = [
    "MCB", "MCCB", "MPCB", "ACB", "RCD", "CONTACTOR", "CAP_CONTACTOR", "BIMETAL",
    "TIMER_YD", "VFD", "SOFT_STARTER", "PSU_24V", "DC_SEL_MOD", "MCB_2P_CTRL",
    "FAN_FILTER", "ENCLOSURE", "SPD", "DETUNED_REACTOR", "CAP_MODULE",
]

# TECH-05: شیت راهنمای سه‌زبانه در قالب اکسل — (field, fa, en, de, allowed, example)
GUIDE_PROJECT_ROWS = [
    ("project_name", "نام پروژه (در عنوان گزارش‌ها و نقشه‌ها نمایش داده می‌شود)",
     "Project name (shown in report and drawing titles)",
     "Projektname (erscheint in Berichts- und Zeichnungstiteln)", "Text", "Pump Station (MDB-PUMP-02)"),
    ("panel_tag", "تگ مکان نصب طبق IEC 81346 (پیشوند +)",
     "Location tag per IEC 81346 (+ prefix)", "Ortskennzeichen nach IEC 81346 (+ Präfix)", "Text", "+MCC1"),
    ("nominal_voltage_v", "ولتاژ نامی شبکه (V)", "Nominal supply voltage (V)", "Netz-Nennspannung (V)", "V (e.g. 400)", "400"),
    ("earthing_system", "سیستم زمین (نوع اتصال شبکه)", "Earthing system (network connection type)",
     "Erdungssystem (Netzanschlussart)", "TN-S | TN-C-S | TT | IT", "TN-S"),
    ("panel_type", "نوع تابلو", "Panel type", "Schaltschranktyp", "MCC | DISTRIBUTION | CONTROL | PUMP_STATION", "MCC"),
    ("special_scenario", "سناریوی ویژه پروژه (پمپ آتش، ATS و ...)", "Special project scenario (fire pump, ATS, ...)",
     "Sonderprojektszenario (Feuerlöschpumpe, ATS, ...)",
     "NONE | FIRE_PUMP | ATS_MAINS_GEN | FIRE_PUMP_BYPASS | ATS_MAINS_MAINS | UPS_CRITICAL | EMERGENCY_LIGHTING", "NONE"),
    ("prospective_ik_ka", "جریان اتصال کوتاه احتمالی در محل نصب (kA)؛ خالی = برآورد از ترانس",
     "Prospective short-circuit current at installation point (kA); empty = estimated from transformer",
     "Prospektiver Kurzschlussstrom am Einbauort (kA); leer = aus Transformator geschätzt", "kA", "22"),
    ("transformer_kva", "توان نامی ترانس تغذیه (kVA)", "Feeding transformer rating (kVA)",
     "Nennleistung des speisenden Transformators (kVA)", "kVA", "1600"),
    ("transformer_uk_pct", "ولتاژ اتصال کوتاه ترانس (%)", "Transformer short-circuit voltage (%)",
     "Kurzschlussspannung des Transformators (%)", "% (1-20)", "6"),
    ("ambient_temp_c", "دمای محیط (°C)", "Ambient temperature (°C)", "Umgebungstemperatur (°C)", "°C", "40"),
    ("max_internal_temp_c", "حداکثر دمای مجاز داخل تابلو (°C)", "Max. allowed temperature inside the panel (°C)",
     "Max. zulässige Innentemperatur (°C)", "°C (35-70)", "50"),
    ("altitude_m", "ارتفاع نصب از سطح دریا (m)", "Installation altitude above sea level (m)",
     "Aufstellungshöhe über NN (m)", "m (0-4000)", "1000"),
    ("target_ip", "درجه حفاظت هدف بدنه تابلو", "Target enclosure ingress protection rating",
     "Angestrebte Schutzart des Gehäuses", "IP54 | IP55 | IP66", "IP54"),
    ("internal_separation_form", "فرم جداسازی داخلی (IEC 61439-2)", "Internal separation form (IEC 61439-2)",
     "Innere Unterteilung (IEC 61439-2)", "Form 1 | Form 2b | Form 3b | Form 4b", "Form 2b"),
    ("simultaneity_factor_ks", "ضریب هم‌زمانی کل بارها", "Overall load simultaneity factor",
     "Gleichzeitigkeitsfaktor der Lasten", "0.1 - 1.0", "0.85"),
    ("spare_factor", "ضریب رزرو برای شینه و کلید اصلی", "Spare capacity factor for busbar and main breaker",
     "Reservefaktor für Sammelschiene und Hauptschalter", "0.0 - 1.0", "0.20"),
    ("plc_hmi_24vdc_power_w", "توان پیوسته PLC/HMI در مدار ۲۴V DC (W)", "Continuous PLC/HMI power on 24V DC circuit (W)",
     "Dauerleistung PLC/HMI am 24-V-DC-Kreis (W)", "W", "55"),
    ("simultaneous_motor_starts", "حداکثر تعداد موتورهای هم‌زمان در حال استارت",
     "Max. number of motors starting simultaneously", "Max. Anzahl gleichzeitig startender Motoren", "1 - 10", "2"),
    ("preferred_manufacturer", "سازنده ترجیحی تجهیزات (ANY = انتخاب آزاد)",
     "Preferred equipment manufacturer (ANY = free choice)",
     "Bevorzugter Gerätehersteller (ANY = freie Wahl)", "Text (e.g. SIEMENS, SCHNEIDER, ANY)", "ANY"),
    ("spd_class", "کلاس برقگیر SPD در ورودی تابلو (IEC 61643-11)",
     "SPD class at panel incoming (IEC 61643-11)",
     "SPD-Klasse am Einspeisepunkt (IEC 61643-11)", "NONE | T1 | T2 | T1_T2", "T2"),
    ("spd_connection_length_m", "طول مسیر اتصال SPD از شینه تا دستگاه (m)",
     "SPD connection lead length from busbar to device (m)",
     "Anschlussleitungslänge von der Schiene zum SPD (m)", "m (≤0.5 recommended, >1.0 not allowed)", "0.5"),
]

GUIDE_FEEDER_ROWS = [
    ("feeder_id", "شناسه یکتای فیدر", "Unique feeder identifier", "Eindeutige Abgangskennung", "Text", "F01"),
    ("func_tag", "تگ عملکرد طبق IEC 81346 (پیشوند =)", "Function tag per IEC 81346 (= prefix)",
     "Funktionskennzeichen nach IEC 81346 (= Präfix)", "Text", "=PUMP1"),
    ("loc_tag", "تگ مکان نصب", "Location tag", "Ortskennzeichen", "Text", "+MCC1"),
    ("description", "شرح مصرف‌کننده", "Load description", "Lastbeschreibung", "Text", "Main pump"),
    ("load_type", "نوع بار", "Load type", "Lastart",
     "MOTOR_DOL | MOTOR_STAR_DELTA | MOTOR_SOFT_STARTER | MOTOR_VFD | SUB_FEEDER | LIGHTING_SOCKET | HEATER_RESISTIVE",
     "MOTOR_DOL"),
    ("power_kw", "توان نامی بار (kW)", "Rated load power (kW)", "Nennleistung der Last (kW)", "kW (>0)", "15"),
    ("phases", "تعداد فاز", "Number of phases", "Phasenzahl", "1 | 2 | 3", "3"),
    ("cos_phi", "ضریب توان بار؛ خالی = پیش‌فرض بر اساس نوع بار",
     "Load power factor; empty = default by load type", "Leistungsfaktor der Last; leer = Standard je Lastart", "0.1 - 1.0", "0.85"),
    ("efficiency", "راندمان؛ خالی = 1.0", "Efficiency; empty = 1.0", "Wirkungsgrad; leer = 1,0", "0.1 - 1.0", "0.91"),
    ("demand_factor_kd", "ضریب تقاضای بار", "Load demand factor", "Bedarfsfaktor der Last", "0.1 - 1.0", "1.0"),
    ("cable_length_m", "طول کابل تا مصرف‌کننده (m)", "Cable length to load (m)", "Kabellänge zur Last (m)", "m", "45"),
    ("cable_section_mm2", "سطح مقطع کابل موجود؛ خالی = انتخاب خودکار", "Existing cable cross-section; empty = auto-select",
     "Vorhandener Kabelquerschnitt; leer = automatische Wahl", "mm² (e.g. 2.5, 4, 6, 10, 16, ...)", ""),
    ("has_socket_outlets", "وجود پریز خروجی در فیدر", "Feeder has socket outlets", "Abgang mit Steckdosen",
     "TRUE | FALSE", "FALSE"),
    ("conductor_material", "جنس هادی کابل", "Cable conductor material", "Kabelleiterwerkstoff", "CU | AL", "CU"),
    ("insulation", "نوع عایق کابل", "Cable insulation type", "Kabelisolierung", "PVC | XLPE", "PVC"),
    ("installation_method", "روش نصب کابل (IEC 60364-5-52)", "Cable installation method (IEC 60364-5-52)",
     "Verlegeart des Kabels (IEC 60364-5-52)", "C | B1 | E | F", "C"),
    ("fire_resistant", "کابل مقاوم در برابر آتش", "Fire-resistant cable", "Feuerbeständiges Kabel", "TRUE | FALSE", "FALSE"),
    ("thdi_pct", "اعوجاج هارمونیکی جریان بار (%)؛ خالی = بدون هارمونیک",
     "Load current harmonic distortion THDi (%); empty = none", "Oberschwingungsgehalt THDi der Last (%); leer = keine",
     "% (0-100)", "40"),
    ("fire_pump_service", "سرویس پمپ آتش‌نشانی (قواعد ویژه)", "Fire pump service (special rules)",
     "Feuerlöschpumpen-Betrieb (Sonderregeln)", "TRUE | FALSE", "FALSE"),
]


class ExcelImportError(Exception):
    """خطای دوستانه ایمپورت اکسل — پیام آماده نمایش در پاپ‌آپ GUI."""


class ExcelInputManager:
    @staticmethod
    def create_input_template(filepath: str) -> None:
        wb = openpyxl.Workbook()
        header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, name="Calibri", size=11)

        ws_proj = wb.active; ws_proj.title = "Project_Spec"
        ws_proj.append([tr("xl_h_key"), tr("xl_h_value"), tr("xl_h_guide")])
        for row in [
            ("project_name", tr("template_project_name"), tr("xl_g_project_name")),
            ("panel_tag", "+MCC1", tr("xl_g_panel_tag")),
            ("nominal_voltage_v", 400.0, tr("xl_g_voltage")),
            ("earthing_system", "TN-S", tr("xl_g_earthing")),
            ("panel_type", "MCC", tr("xl_g_panel_type")),
            ("special_scenario", "NONE", tr("xl_g_scenario")),
            ("prospective_ik_ka", 22.0, tr("xl_g_ik")),
            ("transformer_kva", 1600.0, tr("xl_g_trafo")),
            ("transformer_uk_pct", 6.0, tr("xl_g_uk_pct")),
            ("ambient_temp_c", 40.0, tr("xl_g_ambient")),
            ("max_internal_temp_c", 50.0, tr("xl_g_internal")),
            ("altitude_m", 1000.0, tr("xl_g_altitude")),
            ("target_ip", "IP54", tr("xl_g_ip")),
            ("internal_separation_form", "Form 2b", tr("xl_g_form")),
            ("simultaneity_factor_ks", 0.85, tr("xl_g_ks")),
            ("spare_factor", 0.20, tr("xl_g_spare")),
            ("plc_hmi_24vdc_power_w", 55.0, tr("xl_g_plc")),
            ("simultaneous_motor_starts", 2, tr("xl_g_starts")),
            ("preferred_manufacturer", "ANY", tr("xl_g_mfg")),
            ("spd_class", "T2", tr("xl_g_spd")),
            ("spd_connection_length_m", 0.5, tr("xl_g_spd_inst")),
        ]: ws_proj.append(list(row))

        ws_feed = wb.create_sheet("Feeders_List")
        ws_feed.append([tr("xl_h_fid"), tr("xl_h_func"), tr("xl_h_loc"), tr("xl_h_desc"), tr("xl_h_lt"),
                        tr("xl_h_kw"), tr("xl_h_ph"), tr("xl_h_cos"), tr("xl_h_eff"), tr("xl_h_kd"),
                        tr("xl_h_len"), tr("xl_h_sec"), tr("xl_h_socket"), tr("xl_h_conductor"),
                        tr("xl_h_insulation"), tr("xl_h_method"), tr("xl_h_fr"), tr("xl_h_thdi"),
                        tr("xl_h_fire_pump")])
        for f in [
            ("F01", "=PUMP1", "+MCC1", tr("xl_d_f01"), "MOTOR_DOL", 15.0, 3, 0.85, 0.91, 1.0, 45.0, None, False, "CU", "PVC", "C", False, None, False),
            ("F02", "=COMP1", "+MCC1", tr("xl_d_f02"), "MOTOR_STAR_DELTA", 30.0, 3, 0.86, 0.93, 1.0, 55.0, None, False, "CU", "PVC", "C", False, None, False),
            ("F03", "=PUMP2", "+MCC1", tr("xl_d_f03"), "MOTOR_VFD", 18.5, 3, 0.95, 0.90, 1.0, 40.0, None, False, "CU", "XLPE", "E", False, 40.0, False),
            ("F04", "=LGT1", "+MCC1", tr("xl_d_f04"), "LIGHTING_SOCKET", 12.0, 3, 0.90, 1.0, 0.8, 60.0, None, True, "CU", "PVC", "C", False, None, False),
        ]: ws_feed.append(list(f))

        # TECH-05: شیت راهنمای سه‌زبانه
        ws_guide = wb.create_sheet("Guide_&_Definitions")
        ws_guide.append(["Field", "Description (FA)", "Description (EN)", "Description (DE)", "Allowed values / Unit", "Example"])
        for row in GUIDE_PROJECT_ROWS + GUIDE_FEEDER_ROWS:
            ws_guide.append(list(row))
        ws_guide.freeze_panes = "A2"

        # TECH-05: لیست‌های کشویی برای ستون‌های Enum و بولی
        def _dv(sheet, values, cell_range):
            dv = DataValidation(type="list", formula1='"' + values + '"', allow_blank=True, showDropDown=False)
            dv.error = tr("xl_dv_error")
            dv.errorTitle = tr("xl_dv_error_title")
            sheet.add_data_validation(dv)
            dv.add(cell_range)

        def _proj_row(key):
            for r in range(2, ws_proj.max_row + 1):
                if ws_proj.cell(row=r, column=1).value == key:
                    return r
            return 2

        for key, values in [
            ("earthing_system", "TN-S,TN-C-S,TT,IT"),
            ("panel_type", "MCC,DISTRIBUTION,CONTROL,PUMP_STATION"),
            ("special_scenario", "NONE,FIRE_PUMP,ATS_MAINS_GEN,FIRE_PUMP_BYPASS,ATS_MAINS_MAINS,UPS_CRITICAL,EMERGENCY_LIGHTING"),
            ("target_ip", "IP54,IP55,IP66"),
            ("internal_separation_form", "Form 1,Form 2b,Form 3b,Form 4b"),
            ("spd_class", "NONE,T1,T2,T1_T2"),
        ]:
            _dv(ws_proj, values, f"B{_proj_row(key)}")

        for col, values in [
            ("E", "MOTOR_DOL,MOTOR_STAR_DELTA,MOTOR_SOFT_STARTER,MOTOR_VFD,SUB_FEEDER,LIGHTING_SOCKET,HEATER_RESISTIVE"),
            ("G", "1,2,3"),
            ("M", "TRUE,FALSE"),
            ("N", "CU,AL"),
            ("O", "PVC,XLPE"),
            ("P", "A1,A2,B1,B2,C,E,F,D"),
            ("Q", "TRUE,FALSE"),
            ("S", "TRUE,FALSE"),
        ]:
            _dv(ws_feed, values, f"{col}2:{col}2000")

        for ws in wb.worksheets:
            for cell in ws[1]: cell.fill = header_fill; cell.font = header_font; cell.alignment = Alignment(horizontal="center")
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 25
        for col_letter, width in zip("ABCDEF", (24, 55, 55, 55, 45, 22)):
            ws_guide.column_dimensions[col_letter].width = width
        wb.save(filepath)

    @staticmethod
    def _parse_bool(val) -> bool:
        if val is None or val == "": return False
        if isinstance(val, bool): return val
        if isinstance(val, (int, float)): return bool(val)
        return str(val).strip().lower() in ("true", "1", "yes", "y")

    @staticmethod
    def load_from_excel(filepath: str):
        """بارگذاری قالب اکسل — همه خطاهای رایج به ExcelImportError با پیام راهنما تبدیل می‌شوند."""
        try:
            wb = openpyxl.load_workbook(filepath, data_only=True)
        except Exception:
            raise ExcelImportError(tr("err_excel_invalid"))
        for sheet in ("Project_Spec", "Feeders_List"):
            if sheet not in wb.sheetnames:
                raise ExcelImportError(tr("err_excel_sheets", sheet=sheet))
        try:
            ws_proj = wb["Project_Spec"]
            proj_dict = {str(row[0]).strip(): row[1] for row in ws_proj.iter_rows(min_row=2, values_only=True) if row[0]}
            errors: List[str] = []

            def _f(key, default):
                val = proj_dict.get(key)
                return float(val) if val not in (None, "") else default

            def _f_opt(key):
                val = proj_dict.get(key)
                return float(val) if val not in (None, "") else None

            def _enum(cls, key, default):
                # F-013: مقدار نامعتبر Enum نباید بی‌صدا جایگزین شود
                val = proj_dict.get(key)
                if val in (None, ""):
                    return default
                try:
                    return cls(str(val).strip())
                except Exception:
                    allowed = ", ".join(e.value for e in cls)
                    errors.append(tr("err_enum_proj", sheet="Project_Spec", field=key, value=str(val), allowed=allowed))
                    return default

            project = ProjectSpec(
                project_name=str(proj_dict.get("project_name", "Project")),
                standard_ref=str(proj_dict.get("standard_ref") or "IEC 61439-2 / IEC 60204-1"),
                panel_tag=str(proj_dict.get("panel_tag", "+MCC1")),
                nominal_voltage_v=_f("nominal_voltage_v", 400.0),
                earthing_system=_enum(EarthingSystem, "earthing_system", EarthingSystem.TN_S),
                panel_type=_enum(PanelType, "panel_type", PanelType.MCC),
                special_scenario=_enum(SpecialScenario, "special_scenario", SpecialScenario.NONE),
                prospective_ik_ka=_f_opt("prospective_ik_ka"),
                transformer_kva=_f_opt("transformer_kva"),
                transformer_uk_pct=_f("transformer_uk_pct", 6.0),
                ambient_temp_c=_f("ambient_temp_c", 40.0),
                max_internal_temp_c=_f("max_internal_temp_c", 50.0),
                altitude_m=_f("altitude_m", 1000.0),
                target_ip=str(proj_dict.get("target_ip", "IP54")),
                internal_separation_form=str(proj_dict.get("internal_separation_form", "Form 2b")),
                simultaneity_factor_ks=_f("simultaneity_factor_ks", 0.85),
                spare_factor=_f("spare_factor", 0.20),
                plc_hmi_24vdc_power_w=_f("plc_hmi_24vdc_power_w", 55.0),
                simultaneous_motor_starts=int(_f("simultaneous_motor_starts", 2)),
                preferred_manufacturer=str(proj_dict.get("preferred_manufacturer", "ANY")).strip() or "ANY",
                spd_class=_enum(SpdClass, "spd_class", SpdClass.T2),
                spd_connection_length_m=_f("spd_connection_length_m", 0.5),
            )

            ws_feed = wb["Feeders_List"]
            headers = [str(c.value) if c.value else "" for c in ws_feed[1]]
            feeders = []
            for row_no, row in enumerate(ws_feed.iter_rows(min_row=2, values_only=True), start=2):
                if not row or row[0] is None: continue
                row = list(row) + [None] * 19

                def _cell(i, default=None):
                    return row[i] if row[i] not in (None, "") else default

                def _num(i, key_label="", default=None):
                    """تبدیل عددی ایمن — مقدار خراب به‌جای کرش، خطای ردیفی دوستانه تولید می‌کند."""
                    val = _cell(i)
                    if val is None:
                        return default
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        errors.append(tr("err_excel_row_value", row=row_no,
                                         col=headers[i] or f"Col{i + 1}", value=str(val)))
                        return default

                def _cell_enum(cls, i, default):
                    # F-013: خطای Enum با آدرس دقیق سلول (شیت/سطر/ستون) ثبت می‌شود
                    val = _cell(i, default.value)
                    try: return cls(str(val).strip())
                    except Exception:
                        allowed = ", ".join(e.value for e in cls)
                        errors.append(tr("err_enum_feed", sheet="Feeders_List", row=row_no,
                                         col=headers[i] or f"Col{i + 1}", value=str(val), allowed=allowed))
                        return default

                power_kw = _num(5, "power_kw")
                if not power_kw or power_kw <= 0:
                    errors.append(tr("err_excel_row_power", row=row_no, id=str(row[0]).strip()))
                    continue

                cos_phi = _num(7)
                eff = _num(8)
                cable_len = _num(10)
                cable_sec = _num(11)
                thdi = _num(17)

                feeders.append(FeederInput(
                    feeder_id=str(row[0]).strip(), func_tag=str(_cell(1, "=PWR")), loc_tag=str(_cell(2, project.panel_tag)),
                    description=str(_cell(3, "")), load_type=_cell_enum(LoadType, 4, LoadType.SUB_FEEDER), power_kw=float(power_kw),
                    phases=int(_num(6, "phases", 3) or 3), cos_phi=cos_phi,
                    efficiency=eff, demand_factor_kd=_num(9, "demand", 1.0) or 1.0,
                    cable_length_m=cable_len, cable_section_mm2=cable_sec,
                    has_socket_outlets=ExcelInputManager._parse_bool(_cell(12)),
                    conductor_material=_cell_enum(ConductorMaterial, 13, ConductorMaterial.CU),
                    insulation=_cell_enum(InsulationType, 14, InsulationType.PVC),
                    installation_method=_cell_enum(InstallationMethod, 15, InstallationMethod.C),
                    fire_resistant=ExcelInputManager._parse_bool(_cell(16)),
                    thdi_pct=thdi,
                    fire_pump_service=ExcelInputManager._parse_bool(_cell(18)),
                ))
            if not feeders and not errors:
                raise ExcelImportError(tr("err_excel_generic"))
            return project, feeders, errors
        except ExcelImportError:
            raise
        except (KeyError, IndexError, TypeError) as ex:
            raise ExcelImportError(tr("err_excel_generic")) from ex


class ToolTip:
    """UI/UX #8: راهنمای هاور ساده روی دکمه‌های کلیدی."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tip: return
        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#FFFFE0",
                 foreground="#1C2833", relief="solid", borderwidth=1,
                 font=("Tahoma", 9), padx=6, pady=3).pack()

    def _hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def build_demo_project() -> Tuple[ProjectSpec, List[FeederInput]]:
    """UI/UX #2: پروژه نمونه استاندارد بدون نیاز به فایل اکسل."""
    project = ProjectSpec(
        project_name=tr("demo_name"), panel_tag="+MCC1", nominal_voltage_v=400.0,
        earthing_system=EarthingSystem.TN_S, panel_type=PanelType.MCC,
        special_scenario=SpecialScenario.NONE, prospective_ik_ka=22.0,
        transformer_kva=1600.0, ambient_temp_c=40.0, max_internal_temp_c=50.0,
        altitude_m=1000.0, target_ip="IP54", internal_separation_form="Form 2b",
        simultaneity_factor_ks=0.85, spare_factor=0.20, plc_hmi_24vdc_power_w=55.0,
        simultaneous_motor_starts=2, preferred_manufacturer="ANY",
    )
    feeders = [
        FeederInput(feeder_id="F01", func_tag="=PUMP1", loc_tag="+MCC1", description=tr("xl_d_f01"),
                    load_type=LoadType.MOTOR_DOL, power_kw=15.0, cos_phi=0.85, efficiency=0.91,
                    demand_factor_kd=1.0, cable_length_m=45.0),
        FeederInput(feeder_id="F02", func_tag="=COMP1", loc_tag="+MCC1", description=tr("xl_d_f02"),
                    load_type=LoadType.MOTOR_STAR_DELTA, power_kw=30.0, cos_phi=0.86, efficiency=0.93,
                    demand_factor_kd=1.0, cable_length_m=55.0),
        FeederInput(feeder_id="F03", func_tag="=PUMP2", loc_tag="+MCC1", description=tr("xl_d_f03"),
                    load_type=LoadType.MOTOR_VFD, power_kw=18.5, cos_phi=0.95, efficiency=0.90,
                    demand_factor_kd=1.0, cable_length_m=40.0, thdi_pct=40.0,
                    insulation=InsulationType.XLPE, installation_method=InstallationMethod.E),
        FeederInput(feeder_id="F04", func_tag="=LGT1", loc_tag="+MCC1", description=tr("xl_d_f04"),
                    load_type=LoadType.LIGHTING_SOCKET, power_kw=12.0, cos_phi=0.90, efficiency=1.0,
                    demand_factor_kd=0.8, cable_length_m=60.0, has_socket_outlets=True),
    ]
    return project, feeders


class FeederEditDialog(ctk.CTkToplevel):
    """UI/UX #1: ویرایش سریع فیدر داخل برنامه + محاسبه مجدد."""

    def __init__(self, master, feeder: FeederInput, on_save):
        super().__init__(master)
        self.feeder = feeder
        self.on_save = on_save
        self.title(tr("edt_title", a=feeder.feeder_id))
        self.geometry("420x500")
        self.resizable(False, False)
        self.grab_set()
        font = ctk.CTkFont(family=i18n.font_family(), size=12)
        self._entries = {}

        def row(key, attr, caster):
            fr = ctk.CTkFrame(self); fr.pack(fill="x", padx=14, pady=5)
            ctk.CTkLabel(fr, text=tr(key), width=150, anchor="w", font=font).pack(side="left", padx=6)
            entry = ctk.CTkEntry(fr, width=190, font=font)
            entry.insert(0, str(getattr(feeder, attr) if getattr(feeder, attr) is not None else ""))
            entry.pack(side="right", padx=6)
            self._entries[attr] = (entry, caster)

        def _opt_float(v):
            v = (v or "").strip()
            return None if v in ("", "None") else float(v)

        row("edt_desc", "description", str)
        row("edt_power", "power_kw", float)
        row("edt_cos", "cos_phi", _opt_float)
        row("edt_eff", "efficiency", _opt_float)
        row("edt_kd", "demand_factor_kd", float)
        row("edt_length", "cable_length_m", _opt_float)

        self.geometry("440x590")
        type_row = ctk.CTkFrame(self); type_row.pack(fill="x", padx=14, pady=5)
        ctk.CTkLabel(type_row, text=tr("edt_type"), width=150, anchor="w", font=font).pack(side="left", padx=6)
        self._type_menu = LocalizedOptionMenu(type_row, values=[e.value for e in LoadType],
                                               translation_prefix="lt_", width=190, font=font)
        self._type_menu.set(feeder.load_type.value)
        self._type_menu.pack(side="right", padx=6)

        meth_row = ctk.CTkFrame(self); meth_row.pack(fill="x", padx=14, pady=5)
        ctk.CTkLabel(meth_row, text=tr("xl_h_method"), width=150, anchor="w", font=font).pack(side="left", padx=6)
        self._method_menu = ctk.CTkOptionMenu(meth_row, values=[m.value for m in InstallationMethod], width=190, font=font)
        self._method_menu.set(feeder.installation_method.value)
        self._method_menu.pack(side="right", padx=6)

        ins_row = ctk.CTkFrame(self); ins_row.pack(fill="x", padx=14, pady=5)
        ctk.CTkLabel(ins_row, text=tr("xl_h_insulation"), width=150, anchor="w", font=font).pack(side="left", padx=6)
        self._ins_menu = ctk.CTkOptionMenu(ins_row, values=[ins.value for ins in InsulationType], width=190, font=font)
        self._ins_menu.set(feeder.insulation.value)
        self._ins_menu.pack(side="right", padx=6)

        btn_row = ctk.CTkFrame(self); btn_row.pack(fill="x", padx=14, pady=(16, 8))
        ctk.CTkButton(btn_row, text=tr("dlg_save"), fg_color="#1E8449", font=font,
                      command=self._save).pack(side="left", padx=8, expand=True)
        ctk.CTkButton(btn_row, text=tr("dlg_cancel"), fg_color="#566573", font=font,
                      command=self.destroy).pack(side="left", padx=8, expand=True)

    def _save(self):
        f = self.feeder
        try:
            updated = FeederInput(
                feeder_id=f.feeder_id, func_tag=f.func_tag, loc_tag=f.loc_tag,
                description=self._entries["description"][0].get().strip() or f.description,
                load_type=LoadType(self._type_menu.get()),
                power_kw=self._entries["power_kw"][1](self._entries["power_kw"][0].get()),
                phases=f.phases,
                cos_phi=self._entries["cos_phi"][1](self._entries["cos_phi"][0].get()),
                efficiency=self._entries["efficiency"][1](self._entries["efficiency"][0].get()),
                demand_factor_kd=self._entries["demand_factor_kd"][1](self._entries["demand_factor_kd"][0].get()),
                cable_length_m=self._entries["cable_length_m"][1](self._entries["cable_length_m"][0].get()),
                cable_section_mm2=f.cable_section_mm2, has_socket_outlets=f.has_socket_outlets,
                conductor_material=f.conductor_material, insulation=InsulationType(self._ins_menu.get()),
                installation_method=InstallationMethod(self._method_menu.get()), fire_resistant=f.fire_resistant,
                thdi_pct=f.thdi_pct, fire_pump_service=f.fire_pump_service,
            )
        except Exception as ex:
            messagebox.showerror(tr("msg_error"), str(ex), parent=self)
            return
        self.on_save(updated)
        self.destroy()


# نگاشت مشخصه‌های اصلی هر تجهیز (فقط فیلدهای مرتبط با همان تجهیز نمایش داده می‌شوند)
DEVICE_SPECS_BY_TYPE = {
    "MCB": [("dlg_in", "rated_current_in_a"), ("dlg_icu", "icu_ka_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "MCCB": [("dlg_in", "rated_current_in_a"), ("dlg_icu", "icu_ka_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "MPCB": [("dlg_in", "rated_current_in_a"), ("dlg_icu", "icu_ka_400v"), ("dlg_kw", "motor_kw_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "ACB": [("dlg_in", "rated_current_in_a"), ("dlg_icu", "icu_ka_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "RCD": [("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "CONTACTOR": [("dlg_in", "rated_current_in_a"), ("dlg_kw", "motor_kw_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "BIMETAL": [("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "TIMER_YD": [("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "VFD": [("dlg_kw", "motor_kw_400v"), ("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "SOFT_STARTER": [("dlg_kw", "motor_kw_400v"), ("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "PSU_24V": [("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "DC_SEL_MOD": [("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "MCB_2P_CTRL": [("dlg_in", "rated_current_in_a"), ("dlg_icu", "icu_ka_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "FAN_FILTER": [("dlg_airflow", "airflow_m3h"), ("dlg_loss", "power_loss_w"), ("dlg_ip", "ip_rating"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "ENCLOSURE": [("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm"), ("dlg_ip", "ip_rating")],
    "SPD": [("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "CAP_CONTACTOR": [("dlg_kvar", "cap_kvar_400v"), ("dlg_in", "rated_current_in_a"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "DETUNED_REACTOR": [("dlg_kvar", "cap_kvar_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
    "CAP_MODULE": [("dlg_kvar", "cap_kvar_400v"), ("dlg_loss", "power_loss_w"), ("dlg_width", "width_mm"), ("dlg_height", "height_mm"), ("dlg_depth", "depth_mm")],
}

WEB_SPECS_BY_TYPE = {
    "ENCLOSURE": [("dlg_width", "width_mm", "عرض تابلو - mm"), ("dlg_height", "height_mm", "ارتفاع تابلو - mm"), ("dlg_ip", "ip_rating", "درجه حفاظت IP")],
    "VFD": [("dlg_kw", "motor_kw", "توان موتور - kW"), ("dlg_in", "rated_current_in_a", "جریان نامی - A"), ("wiz_voltage", "voltage_v", "ولتاژ نامی - V")],
    "SOFT_STARTER": [("dlg_kw", "motor_kw", "توان موتور - kW"), ("dlg_in", "rated_current_in_a", "جریان نامی - A"), ("wiz_voltage", "voltage_v", "ولتاژ نامی - V")],
    "CONTACTOR": [("dlg_in", "rated_current_in_a", "جریان نامی AC-3 - A"), ("dlg_kw", "motor_kw", "توان موتور - kW"), ("wiz_voltage", "voltage_v", "ولتاژ بوبین/مدار - V")],
    "BIMETAL": [("dlg_in", "rated_current_in_a", "رنج جریانی - A"), ("dlg_kw", "motor_kw", "توان موتور - kW")],
    "TIMER_YD": [("wiz_voltage", "voltage_v", "ولتاژ تغذیه - V")],
    "FAN_FILTER": [("dlg_airflow", "airflow_m3h", "دبی هوادهی - m3/h"), ("dlg_ip", "ip_rating", "درجه حفاظت IP")],
    "PSU_24V": [("dlg_in", "rated_current_in_a", "جریان خروجی 24VDC - A"), ("wiz_voltage", "voltage_v", "ولتاژ ورودی - V")],
    "DC_SEL_MOD": [("dlg_in", "rated_current_in_a", "جریان نامی - A")],
    "RCD": [("dlg_in", "rated_current_in_a", "جریان نامی - A"), ("wiz_voltage", "voltage_v", "ولتاژ نامی - V")],
    "SPD": [("wiz_voltage", "voltage_v", "ولتاژ نامی شبکه - V")],
    "CAP_MODULE": [("dlg_kvar", "cap_kvar", "توان خازنی - kvar"), ("wiz_voltage", "voltage_v", "ولتاژ نامی - V")],
    "CAP_CONTACTOR": [("dlg_kvar", "cap_kvar", "توان خازنی - kvar"), ("dlg_in", "rated_current_in_a", "جریان نامی - A")],
    "DETUNED_REACTOR": [("dlg_kvar", "cap_kvar", "توان خازنی - kvar"), ("wiz_voltage", "voltage_v", "ولتاژ نامی - V")],
    "DEFAULT_BREAKER": [("dlg_in", "rated_current_in_a", "جریان نامی In - A"), ("dlg_icu", "breaking_capacity_ka", "قدرت قطع Icu - kA"), ("wiz_voltage", "voltage_v", "ولتاژ نامی - V")],
}


class DeviceEditDialog(ctk.CTkToplevel):
    """فرم افزودن/ویرایش قطعه کاتالوگ با تغییر پویا و هوشمند فیلدها بر اساس نوع تجهیز."""

    ALL_SPEC_ATTRS = (
        "rated_current_in_a", "icu_ka_400v", "motor_kw_400v", "cap_kvar_400v",
        "power_loss_w", "width_mm", "height_mm", "depth_mm", "airflow_m3h", "ip_rating"
    )

    def __init__(self, master, device: Optional[CatalogDevice], on_save):
        super().__init__(master)
        self.device = device
        self.on_save = on_save
        self.title(tr("dlg_edit_title", pn=device.part_number) if device else tr("dlg_add_title"))
        self.geometry("490x620")
        self.resizable(False, False)
        self.grab_set()
        self.font = ctk.CTkFont(family=i18n.font_family(), size=12)
        self._entries: dict = {}

        body = ctk.CTkScrollableFrame(self, height=450)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        self.body = body

        def static_row(key, attr):
            fr = ctk.CTkFrame(body, fg_color="transparent")
            fr.pack(fill="x", pady=3)
            ctk.CTkLabel(fr, text=tr(key), width=180, anchor="w", font=self.font).pack(side="left", padx=4)
            entry = ctk.CTkEntry(fr, width=210, font=self.font)
            value = getattr(device, attr, "") if device else ""
            entry.insert(0, str(value if value is not None else ""))
            entry.pack(side="right", padx=4)
            self._entries[attr] = entry

        static_row("dlg_part", "part_number")
        static_row("dlg_mfg", "manufacturer")
        static_row("dlg_series", "series")

        type_fr = ctk.CTkFrame(body, fg_color="transparent")
        type_fr.pack(fill="x", pady=3)
        ctk.CTkLabel(type_fr, text=tr("dlg_type"), width=180, anchor="w", font=self.font).pack(side="left", padx=4)
        self._type_menu = ctk.CTkOptionMenu(
            type_fr, values=DEVICE_TYPE_OPTIONS, width=210, font=self.font,
            command=self._on_type_changed
        )
        init_type = device.device_type if device else "MCCB"
        self._type_menu.set(init_type)
        self._type_menu.pack(side="right", padx=4)

        self.dynamic_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.dynamic_frame.pack(fill="x", pady=4)

        q_fr = ctk.CTkFrame(body, fg_color="transparent")
        q_fr.pack(fill="x", pady=3)
        ctk.CTkLabel(q_fr, text=tr("dlg_quality"), width=180, anchor="w", font=self.font).pack(side="left", padx=4)
        self._quality_menu = LocalizedOptionMenu(q_fr, values=[q.value for q in DataQuality],
                                                  translation_prefix="quality_", width=210, font=self.font)
        self._quality_menu.set(device.data_quality.value if device else DataQuality.ESTIMATED.value)
        self._quality_menu.pack(side="right", padx=4)

        price_fr = ctk.CTkFrame(body, fg_color="transparent")
        price_fr.pack(fill="x", pady=3)
        ctk.CTkLabel(price_fr, text=tr("dlg_price"), width=180, anchor="w", font=self.font).pack(side="left", padx=4)
        self._price_entry = ctk.CTkEntry(price_fr, width=140, font=self.font)
        try:
            pr = CatalogRepository().get_device_price(device.part_number) if device else None
        except Exception:
            pr = None
        if pr:
            self._price_entry.insert(0, f"{pr['unit_price']:g}")
        self._price_entry.pack(side="right", padx=4)
        self._currency_entry = ctk.CTkEntry(price_fr, width=60, font=self.font, placeholder_text="EUR")
        if pr:
            self._currency_entry.insert(0, pr["currency"])
        self._currency_entry.pack(side="right", padx=2)
        ctk.CTkLabel(price_fr, text=tr("dlg_currency"), font=self.font).pack(side="right")

        btn_row = ctk.CTkFrame(self)
        btn_row.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(btn_row, text=tr("dlg_save"), fg_color="#1E8449", font=self.font,
                      command=self._save).pack(side="left", padx=8, expand=True)
        ctk.CTkButton(btn_row, text=tr("dlg_cancel"), fg_color="#566573", font=self.font,
                      command=self.destroy).pack(side="left", padx=8, expand=True)

        self._on_type_changed(init_type)

    def _on_type_changed(self, dtype: str):
        for w in self.dynamic_frame.winfo_children():
            w.destroy()
        for attr in self.ALL_SPEC_ATTRS:
            self._entries.pop(attr, None)

        spec_list = DEVICE_SPECS_BY_TYPE.get(dtype, DEVICE_SPECS_BY_TYPE["MCCB"])
        for key, attr in spec_list:
            fr = ctk.CTkFrame(self.dynamic_frame, fg_color="transparent")
            fr.pack(fill="x", pady=3)
            lbl_txt = tr(key)
            ctk.CTkLabel(fr, text=lbl_txt, width=180, anchor="w", font=self.font).pack(side="left", padx=4)
            entry = ctk.CTkEntry(fr, width=210, font=self.font)
            val = getattr(self.device, attr, "") if self.device else ""
            entry.insert(0, str(val if val not in (None, 0.0, 0) else ""))
            entry.pack(side="right", padx=4)
            self._entries[attr] = entry

    def _save(self):
        def _num(attr, default=0.0):
            ent = self._entries.get(attr)
            if ent is None:
                return default
            raw = (ent.get() or "").strip()
            return float(raw) if raw else default

        pn = self._entries["part_number"].get().strip()
        mfg = self._entries["manufacturer"].get().strip()
        if not pn or not mfg:
            messagebox.showwarning(tr("msg_warn"), tr("cat_err_fields"), parent=self)
            return
        ip_ent = self._entries.get("ip_rating")
        ip_val = ip_ent.get().strip() if ip_ent and ip_ent.get().strip() else ("IP55" if self._type_menu.get() == "ENCLOSURE" else "IP20")
        try:
            device = CatalogDevice(
                part_number=pn,
                manufacturer=mfg,
                series=self._entries["series"].get().strip() or "GENERIC",
                device_type=self._type_menu.get(),
                rated_current_in_a=_num("rated_current_in_a"),
                icu_ka_400v=_num("icu_ka_400v"),
                motor_kw_400v=_num("motor_kw_400v"),
                cap_kvar_400v=_num("cap_kvar_400v"),
                power_loss_w=_num("power_loss_w"),
                width_mm=_num("width_mm"),
                height_mm=_num("height_mm"),
                depth_mm=_num("depth_mm"),
                airflow_m3h=_num("airflow_m3h"),
                ip_rating=ip_val,
                data_quality=DataQuality(self._quality_menu.get()),
            )
            price_raw = (self._price_entry.get() or "").strip()
            unit_price = float(price_raw) if price_raw else None
            currency = (self._currency_entry.get() or "EUR").strip() or "EUR"
        except (TypeError, ValueError) as ex:
            messagebox.showwarning(tr("msg_warn"), tr("cat_err_fields") + f"\n{ex}", parent=self)
            return
        self.on_save(device, unit_price, currency)
        self.destroy()


class WebSearchDialog(ctk.CTkToplevel):
    """جستجوی آنلاین قطعه با تغییر پویا و هوشمند فیلدهای مشخصات فنی بر اساس نوع تجهیز."""

    def __init__(self, master, on_added):
        super().__init__(master)
        self.on_added = on_added
        self.title(tr("web_title"))
        self.geometry("1000x700")
        self.grab_set()
        self.font = ctk.CTkFont(family=i18n.font_family(), size=12)

        hint = ctk.CTkLabel(self, text=tr("web_hint"), font=self.font, wraplength=940, justify="right", anchor="e")
        hint.pack(fill="x", padx=14, pady=8)

        spec_bar = ctk.CTkFrame(self)
        spec_bar.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(spec_bar, text=tr("dlg_type"), font=self.font).pack(side="right", padx=6, pady=6)
        self.cmb_type = ctk.CTkOptionMenu(
            spec_bar, values=DEVICE_TYPE_OPTIONS, width=170, font=self.font,
            command=self._on_type_change
        )
        self.cmb_type.set("MCCB")
        self.cmb_type.pack(side="right", padx=6, pady=6)

        self.spec_entries = {}
        for key, width in (("web_mfg", 140), ("web_series", 150), ("web_part", 160)):
            ctk.CTkLabel(spec_bar, text=tr(key), font=self.font).pack(side="right", padx=4)
            ent = ctk.CTkEntry(spec_bar, width=width, font=self.font)
            ent.pack(side="right", padx=4)
            self.spec_entries[key] = ent

        self.num_bar = ctk.CTkFrame(self)
        self.num_bar.pack(fill="x", padx=12, pady=4)
        self.dynamic_spec_frame = ctk.CTkFrame(self.num_bar, fg_color="transparent")
        self.dynamic_spec_frame.pack(side="right", fill="x", padx=4, pady=4)

        ctk.CTkButton(self.num_bar, text=tr("web_run"), fg_color="#1F618D", font=self.font,
                      command=self._run_search).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(self.num_bar, text=tr("web_open_sources"), fg_color="#5D6D7E", font=self.font,
                      command=self._open_sources).pack(side="left", padx=6, pady=6)

        self.num_entries = {}

        ctk.CTkLabel(self, text=tr("web_results"), font=self.font, anchor="e").pack(fill="x", padx=14, pady=(8, 2))
        self.tree_results = ttk.Treeview(self, columns=("title", "url", "snippet"), show="headings", height=9)
        for col, key, w in (("title", "web_col_title", 320), ("url", "web_col_url", 380), ("snippet", "web_col_snippet", 240)):
            self.tree_results.heading(col, text=tr(key))
            self.tree_results.column(col, width=w, anchor="w")
        self.tree_results.pack(fill="both", expand=True, padx=12, pady=4)
        self.tree_results.bind("<Double-1>", self._open_selected)
        self._results: List[web_catalog.WebResult] = []

        self.add_bar = ctk.CTkFrame(self)
        self.add_bar.pack(fill="x", padx=12, pady=8)
        self.ent_part = ctk.CTkEntry(self.add_bar, width=165, font=self.font, placeholder_text=tr("web_part"))
        self.ent_part.pack(side="right", padx=4, pady=6)
        self.ent_series = ctk.CTkEntry(self.add_bar, width=130, font=self.font, placeholder_text=tr("web_series"))
        self.ent_series.pack(side="right", padx=4, pady=6)
        self.ent_mfg = ctk.CTkEntry(self.add_bar, width=130, font=self.font, placeholder_text=tr("web_mfg"))
        self.ent_mfg.pack(side="right", padx=4, pady=6)

        self.add_dynamic_frame = ctk.CTkFrame(self.add_bar, fg_color="transparent")
        self.add_dynamic_frame.pack(side="right", padx=4)
        self.add_dyn_entries = {}

        ctk.CTkButton(self.add_bar, text=tr("web_add_to_catalog"), fg_color="#1E8449", font=self.font,
                      command=self._add_to_catalog).pack(side="left", padx=6, pady=6)

        self._on_type_change("MCCB")

    def _on_type_change(self, dtype: str):
        for w in self.dynamic_spec_frame.winfo_children():
            w.destroy()
        self.num_entries.clear()

        fields = WEB_SPECS_BY_TYPE.get(dtype, WEB_SPECS_BY_TYPE["DEFAULT_BREAKER"])
        for _key, attr_name, label_fa in fields:
            label = label_fa if i18n.get_language() == "fa" else tr(_key)
            ctk.CTkLabel(self.dynamic_spec_frame, text=label, font=self.font).pack(side="right", padx=4)
            ent = ctk.CTkEntry(self.dynamic_spec_frame, width=85, font=self.font)
            ent.pack(side="right", padx=4)
            self.num_entries[attr_name] = ent

        for w in self.add_dynamic_frame.winfo_children():
            w.destroy()
        self.add_dyn_entries.clear()
        for _key, attr_name, label_fa in fields[:2]:
            label = label_fa if i18n.get_language() == "fa" else tr(_key)
            ent = ctk.CTkEntry(self.add_dynamic_frame, width=110, font=self.font, placeholder_text=label)
            ent.pack(side="right", padx=3, pady=6)
            self.add_dyn_entries[attr_name] = ent

    def _build_spec(self) -> web_catalog.DeviceSearchSpec:
        def _opt(name):
            ent = self.num_entries.get(name)
            if ent is None:
                return None
            raw = (ent.get() or "").strip()
            try:
                return float(raw) if raw else None
            except ValueError:
                return None

        extra_kw = []
        if kw := (self.spec_entries["web_series"].get() or "").strip():
            extra_kw.append(kw)
        if pn_kw := (self.spec_entries["web_part"].get() or "").strip():
            extra_kw.append(pn_kw)
        for k_attr, unit in (("width_mm", "mm"), ("height_mm", "mm"), ("airflow_m3h", "m3/h"), ("cap_kvar", "kvar")):
            val = _opt(k_attr)
            if val:
                extra_kw.append(f"{val:g}{unit}")
        ip_ent = self.num_entries.get("ip_rating")
        if ip_ent and ip_ent.get().strip():
            extra_kw.append(ip_ent.get().strip())

        return web_catalog.DeviceSearchSpec(
            device_type=self.cmb_type.get(),
            rated_current_in_a=_opt("rated_current_in_a"),
            breaking_capacity_ka=_opt("breaking_capacity_ka"),
            motor_kw=_opt("motor_kw"),
            voltage_v=_opt("voltage_v"),
            manufacturer=(self.spec_entries["web_mfg"].get() or "").strip() or None,
            keywords=extra_kw,
        )

    def _run_search(self):
        spec = self._build_spec()
        for item in self.tree_results.get_children():
            self.tree_results.delete(item)

        def _on_success(results):
            self._results = results or []
            if not self._results:
                messagebox.showinfo(tr("msg_warn"), tr("web_no_results"), parent=self)
                return
            for r in self._results:
                self.tree_results.insert("", "end", values=(r.title[:90], r.url, r.snippet[:120]))
            if not self.ent_part.get().strip():
                tokens = [t for t in self._results[0].title.replace("-", " ").split() if any(ch.isdigit() for ch in t)]
                if tokens:
                    self.ent_part.insert(0, tokens[0][:24])

        def _on_error(msg):
            messagebox.showerror(tr("msg_warn"), msg, parent=self)

        if not hasattr(self, "_web_search_mgr"):
            self._web_search_mgr = AsyncWebSearchManager(self, web_catalog.fetch_web_results)
        self._web_search_mgr.start_search(
            spec,
            on_start_ui=lambda: None,
            on_success_ui=_on_success,
            on_error_ui=_on_error,
        )

    def _open_sources(self):
        for name, url in web_catalog.source_urls(self._build_spec())[:4]:
            webbrowser.open(url)

    def _open_selected(self, _event=None):
        sel = self.tree_results.selection()
        if not sel:
            return
        idx = self.tree_results.index(sel[0])
        if 0 <= idx < len(self._results):
            webbrowser.open(self._results[idx].url)

    def _add_to_catalog(self):
        pn = (self.ent_part.get() or "").strip() or (self.spec_entries["web_part"].get() or "").strip()
        mfg = (self.ent_mfg.get() or "").strip() or (self.spec_entries["web_mfg"].get() or "").strip()
        if not pn or not mfg:
            messagebox.showwarning(tr("msg_warn"), tr("cat_err_fields"), parent=self)
            return
        spec = self._build_spec()

        def _get_val(attr_name, default=0.0):
            for source_dict in (self.add_dyn_entries, self.num_entries):
                ent = source_dict.get(attr_name)
                if ent and (ent.get() or "").strip():
                    try:
                        return float(ent.get().strip())
                    except ValueError:
                        pass
            return default

        sel_url = ""
        sel = self.tree_results.selection()
        if sel:
            idx = self.tree_results.index(sel[0])
            if 0 <= idx < len(self._results):
                sel_url = self._results[idx].url

        device = web_catalog.device_from_search(
            spec,
            part_number=pn,
            series=(self.ent_series.get() or "").strip() or (self.spec_entries["web_series"].get() or "").strip(),
            manufacturer=mfg,
            rated_in_a=_get_val("rated_current_in_a"),
            icu_ka=_get_val("breaking_capacity_ka"),
            source_url=sel_url,
        )
        device.motor_kw_400v = _get_val("motor_kw")
        device.width_mm = _get_val("width_mm")
        device.height_mm = _get_val("height_mm")
        device.airflow_m3h = _get_val("airflow_m3h")
        device.cap_kvar_400v = _get_val("cap_kvar")
        ip_ent = self.add_dyn_entries.get("ip_rating") or self.num_entries.get("ip_rating")
        if ip_ent and ip_ent.get().strip():
            device.ip_rating = ip_ent.get().strip()

        try:
            CatalogRepository().add_device(device, price_source="WEB_IMPORT")
        except Exception as ex:
            messagebox.showerror(tr("msg_error"), str(ex), parent=self)
            return
        self.on_added()
        messagebox.showinfo(tr("msg_success"), tr("web_added"), parent=self)
        self.destroy()


class LVAssistApp(ctk.CTk):
    NAV_KEYS = ("nav_step1", "nav_step2", "nav_step3", "nav_step4", "nav_step5_merged", "nav_step7")

    def __init__(self):
        super().__init__()
        i18n.set_config_path(config_file_path())
        self.geometry("1400x820")
        ctk.set_default_color_theme("blue")
        ctk.set_appearance_mode(i18n.get_theme())
        self.catalog = CatalogRepository.get_default_catalog()
        self.engine = EngineeringEngine(self.catalog)
        self.current_project, self.current_feeders, self.last_results = None, None, None
        self._stale = False
        self._project_form_loading = False
        self._project_form_values = {}
        self._project_input_data = {}
        self._demo_text = {}
        self._last_calculation_project = None
        self._last_calculation_feeders = []
        self._last_calc_time = None
        self._export_buttons: List = []
        self._status_lbl = None
        self.instruments_list: List[FieldInstrumentInput] = []
        self.last_auto_results = None
        self._build_ui()
        self._load_default_demo()

    # ================================================================= ناوبری
    def _build_ui(self):
        for w in self.winfo_children(): w.destroy()
        self.title(tr("app_title"))
        font_family = i18n.font_family()
        rtl = i18n.direction() == "rtl"
        self._nav_side = "right" if rtl else "left"

        header = ctk.CTkFrame(self, height=54, corner_radius=8)
        header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text=tr("app_title"),
                     font=ctk.CTkFont(family=font_family, size=16, weight="bold")).pack(side="left", padx=14)
        self.lbl_project_title = ctk.CTkLabel(header, text="-",
                                              font=ctk.CTkFont(family=font_family, size=12, weight="bold"))
        self.lbl_project_title.pack(side="left", padx=12)
        theme_switch = ctk.CTkSwitch(header, text=tr("lbl_theme"),
                                     font=ctk.CTkFont(family=font_family, size=12), onvalue="light",
                                     offvalue="dark", command=self._on_theme_change)
        theme_switch.pack(side="right", padx=8)
        if i18n.get_theme() == "light": theme_switch.select()
        lang_seg = ctk.CTkSegmentedButton(header, values=["FA", "EN", "DE"],
                                          font=ctk.CTkFont(family=font_family, size=12),
                                          command=self._on_language_change)
        lang_seg.set(i18n.get_language().upper())
        lang_seg.pack(side="right", padx=8)

        self._status_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(family=font_family, size=12, weight="bold"))
        self._status_lbl.pack(fill="x", padx=18, pady=(0, 2))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(2, 10))
        nav = ctk.CTkFrame(body, width=190, corner_radius=8)
        nav.pack(side=self._nav_side, fill="y", padx=(0, 6) if rtl else (0, 0), pady=0)
        self._nav_buttons = []
        for idx, key in enumerate(self.NAV_KEYS):
            btn = ctk.CTkButton(nav, text=tr(key), height=42, anchor="w",
                                font=ctk.CTkFont(family=font_family, size=12),
                                fg_color="#1F4E78", hover_color="#2E86C1",
                                command=lambda i=idx: self._switch_view(i))
            btn.pack(fill="x", padx=8, pady=4)
            self._nav_buttons.append(btn)

        self.views = [ctk.CTkFrame(body, corner_radius=8) for _ in range(6)]
        self._build_view_project(self.views[0])
        self._build_view_feeders(self.views[1])
        self._build_view_instruments(self.views[2])
        self._build_view_results(self.views[3])
        self._build_view_exports(self.views[4])
        self._build_view_catalog(self.views[5])
        self._apply_tree_style(font_family)
        self._switch_view(0)
        self._apply_status()

    def _switch_view(self, idx: int):
        for i, view in enumerate(self.views):
            view.pack_forget()
        self.views[idx].pack(fill="both", expand=True)
        for i, btn in enumerate(self._nav_buttons):
            btn.configure(fg_color="#1F4E78" if i == idx else "#34495E")
        if idx == 4 and self.last_results and not self._stale:
            self.action_refresh_schematic_preview()
        if idx == 5:
            self._refresh_catalog_tree()

    # ================================================================= گام ۱: پروژه
    def _build_view_project(self, parent):
        font_family = i18n.font_family()
        font = ctk.CTkFont(family=font_family, size=12)
        rtl = i18n.direction() == "rtl"
        ctk.CTkLabel(parent, text=tr("wiz_s1_hint"), font=font, wraplength=1050,
                     justify="right" if rtl else "left", text_color=("#244A66", "#AED6F1")).pack(
                         anchor="e" if rtl else "w", padx=14, pady=(10, 4))

        form = ctk.CTkFrame(parent, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=14, pady=6)
        self.wiz_entries = {}
        fields = [
            ("wiz_project_name", "entry", tr("default_project_name")),
            ("wiz_std_regime", "combo", ["IEC 61439-2 / IEC 60204-1", "DIN EN 61439-2 (VDE 0660-600-2) / VDE 0100"]),
            ("wiz_higher_func", "entry", "==PROCESS"),
            ("wiz_install_site", "entry", "++EL_ROOM1"),
            ("wiz_panel_tag", "entry", "+MCC1"),
            ("wiz_voltage", "entry", "400"),
            ("wiz_trafo", "entry", "1600"),
            ("wiz_ik", "entry", "22"),
            ("wiz_ambient", "entry", "40"),
            ("wiz_internal", "entry", "50"),
            ("wiz_earthing", "combo", ["TN-S", "TN-C-S", "TT", "IT"]),
            ("wiz_panel_type", "combo", [t.value for t in PanelType]),
            ("wiz_scenario", "combo", [s.value for s in SpecialScenario]),
            ("wiz_ip", "combo", ["IP54", "IP55", "IP66"]),
            ("wiz_spare", "entry", "0.20"),
            ("wiz_ks", "entry", "0.85"),
            ("wiz_plc_base", "entry", "55"),
        ]
        for i, (key, kind, default) in enumerate(fields):
            r, c = divmod(i, 2)
            label_column = c * 2 + (1 if rtl else 0)
            input_column = c * 2 + (0 if rtl else 1)
            lbl = ctk.CTkLabel(form, text=tr(key), font=font, anchor="e" if rtl else "w")
            lbl.grid(row=r, column=label_column, padx=(12, 8), pady=6, sticky="ew")
            if kind == "entry":
                variable = ctk.StringVar(value=default)
                ent = ctk.CTkEntry(form, width=210, font=font, textvariable=variable)
                variable.trace_add("write", self._on_project_input_change)
                ent.grid(row=r, column=input_column, padx=(8, 16), pady=6, sticky="ew")
                self.wiz_entries[key] = ent
            else:
                prefix = {"wiz_panel_type": "panel_", "wiz_scenario": "scenario_"}.get(key)
                menu_class = LocalizedOptionMenu if prefix else ctk.CTkOptionMenu
                localized = {"translation_prefix": prefix} if prefix else {}
                menu = menu_class(form, values=default, width=210, font=font, dynamic_resizing=False,
                                  command=self._on_project_input_change, **localized)
                menu.set(default[0])
                menu.grid(row=r, column=input_column, padx=(8, 16), pady=6, sticky="ew")
                self.wiz_entries[key] = menu
        for cidx in range(4):
            is_input = cidx % 2 == (0 if rtl else 1)
            form.grid_columnconfigure(cidx, weight=1 if is_input else 0,
                                      uniform="project_inputs" if is_input else "project_labels")

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.grid(row=(len(fields) + 1) // 2 + 1, column=0, columnspan=4, pady=8, sticky="ew")
        self.mfg_values = ["ANY"] + sorted({d.manufacturer for d in self.catalog})
        self.mfg_display = [tr("gui_mfg_any")] + self.mfg_values[1:]
        self.mfg_menu = ctk.CTkOptionMenu(row2, values=self.mfg_display, width=170, font=font,
                                          command=self._on_mfg_change)
        self.mfg_menu.pack(side="right", padx=6)
        self.mfg_menu.set(self.mfg_display[0])
        ToolTip(self.mfg_menu, tr("tip_mfg"))
        self.spd_values = [c.value for c in SpdClass]
        self.spd_display = [tr("gui_spd_" + v.lower()) for v in self.spd_values]
        self.spd_menu = ctk.CTkOptionMenu(row2, values=self.spd_display, width=130, font=font,
                                          command=self._on_spd_change)
        self.spd_menu.pack(side="right", padx=6)
        self.spd_menu.set(self.spd_display[self.spd_values.index(SpdClass.T2.value)])
        ToolTip(self.spd_menu, tr("tip_spd"))

        btn_bar = ctk.CTkFrame(parent, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(btn_bar, text=tr("wiz_to_feeders"), fg_color="#1E8449", height=40, font=font,
                      command=lambda: self._switch_view(1)).pack(side="left", padx=8)
        ctk.CTkButton(btn_bar, text=tr("btn_import"), fg_color="#385723", font=font,
                      command=self.action_import_excel).pack(side="left", padx=8)
        ctk.CTkButton(btn_bar, text=tr("btn_template"), fg_color="#2E75B6", font=font,
                      command=self.action_generate_template).pack(side="left", padx=8)
        ctk.CTkButton(btn_bar, text=tr("btn_demo"), fg_color="#C55A11", font=font,
                      command=self.action_load_demo).pack(side="left", padx=8)

    def _fill_project_form(self, project: ProjectSpec):
        self._project_form_loading = True
        try:
            self._set_project_form(project)
            self._project_form_values = {key: widget.get() for key, widget in self.wiz_entries.items()}
            self._project_input_data = project.model_dump()
        finally:
            self._project_form_loading = False

    def _on_project_input_change(self, *_args):
        if not self._project_form_loading:
            self._mark_stale()

    def _set_project_form(self, project: ProjectSpec):
        values = {
            "wiz_project_name": project.project_name,
            "wiz_std_regime": project.standard_ref,
            "wiz_panel_tag": project.panel_tag,
            "wiz_earthing": project.earthing_system.value,
            "wiz_panel_type": project.panel_type.value,
            "wiz_scenario": project.special_scenario.value,
            "wiz_voltage": f"{project.nominal_voltage_v:g}",
            "wiz_trafo": "" if project.transformer_kva is None else str(project.transformer_kva),
            "wiz_ik": "" if project.prospective_ik_ka is None else str(project.prospective_ik_ka),
            "wiz_ambient": f"{project.ambient_temp_c:g}",
            "wiz_internal": f"{project.max_internal_temp_c:g}",
            "wiz_ip": project.target_ip,
            "wiz_spare": f"{project.spare_factor:g}",
            "wiz_ks": f"{project.simultaneity_factor_ks:g}",
            "wiz_plc_base": f"{project.plc_hmi_24vdc_power_w:g}",
        }
        for key, val in values.items():
            widget = self.wiz_entries.get(key)
            if widget is None:
                continue
            if isinstance(widget, ctk.CTkEntry):
                widget.delete(0, "end")
                widget.insert(0, str(val))
            elif isinstance(widget, ctk.CTkOptionMenu):
                if str(val) not in widget.cget("values"):
                    widget.configure(values=[*widget.cget("values"), str(val)])
                widget.set(str(val))
        self.mfg_values = ["ANY"] + sorted({d.manufacturer for d in self.catalog})
        self.mfg_display = [tr("gui_mfg_any")] + self.mfg_values[1:]
        if project.preferred_manufacturer not in self.mfg_values:
            self.mfg_values.append(project.preferred_manufacturer)
            self.mfg_display.append(project.preferred_manufacturer)
        self.mfg_menu.configure(values=self.mfg_display)
        if project.preferred_manufacturer in self.mfg_values:
            self.mfg_menu.set(self.mfg_display[self.mfg_values.index(project.preferred_manufacturer)])
        if project.spd_class.value in self.spd_values:
            self.spd_menu.set(self.spd_display[self.spd_values.index(project.spd_class.value)])

    def _project_from_form(self) -> ProjectSpec:
        def _f(key, optional=False):
            raw = (self.wiz_entries[key].get() or "").strip()
            if not raw and optional:
                return None
            try:
                value = float(raw)
            except ValueError:
                raise ValueError(tr("err_project_number", field=tr(key))) from None
            if not math.isfinite(value):
                raise ValueError(tr("err_project_number", field=tr(key)))
            return value

        data = (self._project_input_data.copy() if self._project_input_data
                else self.current_project.model_dump() if self.current_project else {})
        numeric_fields = {
            "wiz_voltage": "nominal_voltage_v", "wiz_ik": "prospective_ik_ka",
            "wiz_trafo": "transformer_kva", "wiz_ambient": "ambient_temp_c",
            "wiz_internal": "max_internal_temp_c", "wiz_ks": "simultaneity_factor_ks",
            "wiz_spare": "spare_factor", "wiz_plc_base": "plc_hmi_24vdc_power_w",
        }
        text_fields = {
            "wiz_project_name": "project_name", "wiz_std_regime": "standard_ref",
            "wiz_panel_tag": "panel_tag", "wiz_earthing": "earthing_system",
            "wiz_panel_type": "panel_type", "wiz_scenario": "special_scenario",
            "wiz_ip": "target_ip",
        }
        for key, field in numeric_fields.items():
            value = _f(key, optional=key in ("wiz_ik", "wiz_trafo"))
            if (not self.current_project
                    or self.wiz_entries[key].get() != self._project_form_values.get(key)):
                data[field] = value
        for key, field in text_fields.items():
            if (not self.current_project
                    or self.wiz_entries[key].get() != self._project_form_values.get(key)):
                data[field] = self.wiz_entries[key].get().strip()
        data["preferred_manufacturer"] = self.mfg_values[self.mfg_display.index(self.mfg_menu.get())]
        data["spd_class"] = self.spd_values[self.spd_display.index(self.spd_menu.get())]
        return ProjectSpec.model_validate(data)

    # ================================================================= گام ۲: فیدرها
    def _build_view_feeders(self, parent):
        font = ctk.CTkFont(family=i18n.font_family(), size=12)
        ctk.CTkLabel(parent, text=tr("wiz_s2_hint"), font=font, wraplength=1050,
                     justify="right", text_color="#A9DFBF").pack(anchor="e", padx=14, pady=(10, 4))
        bar = ctk.CTkFrame(parent)
        bar.pack(fill="x", padx=12, pady=4)
        self.f_entries = {}
        for key, width in (("wiz_f_id", 80), ("wiz_f_func", 110), ("wiz_f_desc", 180),
                           ("wiz_f_kw", 80), ("wiz_f_len", 80)):
            ctk.CTkLabel(bar, text=tr(key), font=font).pack(side="right", padx=3)
            ent = ctk.CTkEntry(bar, width=width, font=font)
            ent.pack(side="right", padx=3)
            self.f_entries[key] = ent
        self.cmb_f_type = LocalizedOptionMenu(bar, values=[t.value for t in LoadType],
                                                translation_prefix="lt_", width=155, font=font)
        self.cmb_f_type.set("MOTOR_DOL")
        self.cmb_f_type.pack(side="right", padx=3)
        self.cmb_f_method = ctk.CTkOptionMenu(bar, values=[m.value for m in InstallationMethod], width=75, font=font)
        self.cmb_f_method.set("C")
        self.cmb_f_method.pack(side="right", padx=3)
        ctk.CTkButton(bar, text=tr("wiz_add_feeder"), fg_color="#2E86C1", font=font,
                      command=self.action_add_feeder_interactively).pack(side="left", padx=6)
        ctk.CTkButton(bar, text=tr("wiz_remove_selected"), fg_color="#C0392B", font=font,
                      command=self.action_remove_selected_feeder).pack(side="left", padx=6)

        self.tree_feeders = ttk.Treeview(parent, columns=("id", "desc", "type", "kw", "len", "note"), show="headings")
        for col, key, w in [("id", "wiz_f_id", 70), ("desc", "wiz_f_desc", 240), ("type", "wiz_i_type", 160),
                            ("kw", "wiz_f_kw", 90), ("len", "wiz_f_len", 100), ("note", "wiz_f_note", 220)]:
            self.tree_feeders.heading(col, text=tr(key))
            self.tree_feeders.column(col, width=w, anchor="center")
        self.tree_feeders.pack(fill="both", expand=True, padx=12, pady=6)
        ctk.CTkLabel(parent, text=tr("edt_dbl_hint"), font=ctk.CTkFont(family=i18n.font_family(), size=11),
                     text_color="#A6A6A6").pack(side="bottom", pady=(0, 8))
        self.tree_feeders.bind("<Double-1>", self._open_feeder_editor)

    def action_add_feeder_interactively(self):
        f_id = (self.f_entries["wiz_f_id"].get() or "").strip() or f"F{len(self.current_feeders or []) + 1:02d}"
        func = (self.f_entries["wiz_f_func"].get() or "").strip() or f"=M{len(self.current_feeders or []) + 1}"
        if not func.startswith("="):
            func = "=" + func
        panel_tag = (self.wiz_entries["wiz_panel_tag"].get() or "").strip() or "+MCC1"
        desc = (self.f_entries["wiz_f_desc"].get() or "").strip() or f"Feeder {f_id}"
        ltype = LoadType(self.cmb_f_type.get())

        kw_raw = (self.f_entries["wiz_f_kw"].get() or "").strip()
        if not kw_raw:
            kw_raw = simpledialog.askstring("kW", tr("wiz_f_kw"), parent=self)
            if not kw_raw:
                return
        try:
            power_kw = float(kw_raw)
        except ValueError:
            messagebox.showwarning(tr("msg_warn"), tr("cat_err_fields"))
            return
        len_raw = (self.f_entries["wiz_f_len"].get() or "").strip()
        try:
            cable_len, _len_warn = parse_cable_length_input(
                len_raw,
                field_key="feeder_cable_length_m",
                default_if_empty=30.0,
            )
        except FieldValidationError as exc:
            messagebox.showwarning(tr("msg_warn"), exc.message, parent=self)
            return
        # UX مینیمال: هیچ پاپ‌آپ مسدودکننده‌ای برای افزودن فیدر باز نمی‌شود؛
        # cos φ خالی = پیش‌فرض IEC 60034 IE3 (در ستون «ملاحظات» نمایش داده می‌شود).
        cos_phi_raw = None
        inst_m = InstallationMethod(self.cmb_f_method.get()) if hasattr(self, 'cmb_f_method') else InstallationMethod.C
        feeder = FeederInput(feeder_id=f_id, func_tag=func, loc_tag=panel_tag, description=desc,
                             load_type=ltype, power_kw=power_kw, cos_phi=cos_phi_raw,
                             cable_length_m=cable_len, installation_method=inst_m)
        self.current_feeders = list(self.current_feeders or []) + [feeder]
        self._refresh_feeder_tree()
        self._mark_stale()
        for key in ("wiz_f_id", "wiz_f_desc", "wiz_f_kw"):
            self.f_entries[key].delete(0, "end")

    def action_remove_selected_feeder(self):
        sel = self.tree_feeders.selection()
        if not sel:
            return
        idx = self.tree_feeders.index(sel[0])
        self.tree_feeders.delete(sel[0])
        if self.current_feeders and 0 <= idx < len(self.current_feeders):
            self.current_feeders.pop(idx)
            self._refresh_feeder_tree()
            self._mark_stale()

    def _refresh_feeder_tree(self):
        if not hasattr(self, "tree_feeders"):
            return
        for item in self.tree_feeders.get_children():
            self.tree_feeders.delete(item)
        for f in self.current_feeders or []:
            note = (f"cos φ={f.cos_phi:g}" if f.cos_phi else "IE3") + f" | {f.installation_method.value}/{f.insulation.value}"
            self.tree_feeders.insert("", "end", values=(
                f.feeder_id, f.description, tr(f"lt_{f.load_type.value}"),
                f"{f.power_kw:g}", f"{f.cable_length_m or 0:g}", note))

    # ================================================================= گام ۳: ابزار دقیق
    def _build_view_instruments(self, parent):
        font = ctk.CTkFont(family=i18n.font_family(), size=12)
        ctk.CTkLabel(parent, text=tr("wiz_s3_hint"), font=font, wraplength=1050,
                     justify="right", text_color="#F9E79F").pack(anchor="e", padx=14, pady=(10, 4))
        bar = ctk.CTkFrame(parent)
        bar.pack(fill="x", padx=12, pady=4)
        self.i_entries = {}
        for key, width in (("wiz_i_tag", 130), ("wiz_i_desc", 210), ("wiz_i_len", 90)):
            ctk.CTkLabel(bar, text=tr(key), font=font).pack(side="right", padx=3)
            ent = ctk.CTkEntry(bar, width=width, font=font)
            ent.pack(side="right", padx=3)
            self.i_entries[key] = ent
        self.cmb_i_type = LocalizedOptionMenu(bar, values=[s.value for s in AutomationSignalType],
                                                translation_prefix="signal_", width=200, font=font)
        self.cmb_i_type.set("SENSOR_AI_4_20MA")
        self.cmb_i_type.pack(side="right", padx=3)
        ctk.CTkButton(bar, text=tr("wiz_add_inst"), fg_color="#8E44AD", font=font,
                      command=self.action_add_instrument).pack(side="left", padx=6)

        cols = ("tag", "desc", "sig", "len")
        self.tree_inst = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        for c, t, w in (("tag", "wiz_i_tag", 150), ("desc", "wiz_i_desc", 320),
                        ("sig", "wiz_i_type", 230), ("len", "wiz_i_len", 130)):
            self.tree_inst.heading(c, text=tr(t))
            self.tree_inst.column(c, width=w, anchor="center")
        self.tree_inst.pack(fill="both", expand=True, padx=12, pady=6)

        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=8)
        self.lbl_plc_summary = ctk.CTkLabel(bottom, text="-", font=font, justify="right", text_color="#AED6F1")
        self.lbl_plc_summary.pack(side="right", padx=8)
        ctk.CTkButton(bottom, text=tr("wiz_run_calc"), fg_color="#1E8449", height=40, font=font,
                      command=self.action_recalculate).pack(side="left", padx=8)

    def action_add_instrument(self):
        tag = (self.i_entries["wiz_i_tag"].get() or "").strip() or f"INST-{len(self.instruments_list) + 1:02d}"
        desc = (self.i_entries["wiz_i_desc"].get() or "").strip() or f"Instrument {tag}"
        sig = AutomationSignalType(self.cmb_i_type.get())
        try:
            c_len, _ = parse_cable_length_input(
                (self.i_entries["wiz_i_len"].get() or "").strip(),
                field_key="instrument_cable_length_m",
                default_if_empty=35.0,
            )
        except FieldValidationError as exc:
            messagebox.showwarning(tr("msg_warn"), exc.message, parent=self)
            return
        inst = FieldInstrumentInput(
            tag_id=tag,
            higher_func=(self.wiz_entries["wiz_higher_func"].get() or "").strip() or "==PROCESS",
            func_group="=INST", install_site="++FIELD_AREA", mounting_loc="+FIELD",
            description=desc, signal_type=sig, cable_length_m=c_len)
        self.instruments_list.append(inst)
        if hasattr(self, "tree_inst"):
            self.tree_inst.insert("", "end", values=(inst.tag_id, inst.description,
                                                     tr(f"signal_{inst.signal_type.value}"), inst.cable_length_m))
        self.i_entries["wiz_i_tag"].delete(0, "end")
        self.i_entries["wiz_i_desc"].delete(0, "end")
        self._mark_stale()

    # ================================================================= گام ۴: نتایج
    def _build_view_results(self, parent):
        font_family = i18n.font_family()
        font = ctk.CTkFont(family=font_family, size=12)
        anchor = "e" if i18n.direction() == "rtl" else "center"
        kpi_frame = ctk.CTkFrame(parent, height=118, corner_radius=8)
        kpi_frame.pack(fill="x", padx=10, pady=(10, 4))
        self.kpi_labels = {}
        for key in ("main_current", "busbar", "psu_24v", "thermal", "cooling", "enclosure", "cap_bank", "val_summary"):
            card = ctk.CTkFrame(kpi_frame, corner_radius=6)
            card.pack(side="left", expand=True, fill="both", padx=4, pady=6)
            ctk.CTkLabel(card, text=tr(f"kpi_{key}"), font=ctk.CTkFont(family=font_family, size=11),
                         text_color="#A6A6A6").pack(pady=(4, 0))
            val_lbl = ctk.CTkLabel(card, text="-", font=ctk.CTkFont(family=font_family, size=12, weight="bold"))
            val_lbl.pack(pady=(2, 6))
            self.kpi_labels[key] = val_lbl

        tabs = ctk.CTkTabview(parent, corner_radius=8)
        tabs.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        tab_out = tabs.add(tr("tab_feeders"))
        tab_rules = tabs.add(tr("tab_rules"))

        self.tree_results_tbl = ttk.Treeview(tab_out, columns=("id", "desc", "type", "ib", "cable", "vd", "prot", "contactors", "bimetal_vfd", "sel"), show="headings")
        for col, key, w in [("id", "col_id", 45), ("desc", "col_desc", 175), ("type", "col_type", 115), ("ib", "col_ib", 65), ("cable", "col_cable", 230), ("vd", "col_vd", 60), ("prot", "col_prot", 130), ("contactors", "col_contactors", 190), ("bimetal_vfd", "col_bimetal_vfd", 145), ("sel", "col_sel", 140)]:
            self.tree_results_tbl.heading(col, text=tr(key))
            self.tree_results_tbl.column(col, width=w, anchor=anchor)
        self.tree_results_tbl.pack(fill="both", expand=True, padx=6, pady=6)

        self.tree_rules = ttk.Treeview(tab_rules, columns=("status", "rule_id", "target", "std", "desc", "evidence", "action"), show="headings")
        for col, key, w in [("status", "col_status", 125), ("rule_id", "col_rule", 115), ("target", "col_target", 75), ("std", "col_std", 155), ("desc", "col_desc2", 250), ("evidence", "col_evidence", 250), ("action", "col_action", 230)]:
            self.tree_rules.heading(col, text=tr(key))
            self.tree_rules.column(col, width=w, anchor=anchor)
        self._apply_tree_tags(self.tree_rules)
        self.tree_rules.pack(fill="both", expand=True, padx=6, pady=6)

    # ================================================================= گام ۵: نقشه‌ها و خروجی‌ها (ادغام‌شده)
    def _build_view_drawings(self, parent):
        self._build_schematics_preview_tab(parent)

    def _build_view_exports(self, parent):
        font = ctk.CTkFont(family=i18n.font_family(), size=12)
        out_frame = ctk.CTkFrame(parent, corner_radius=8)
        out_frame.pack(fill="x", padx=10, pady=(8, 4))
        self._export_buttons = []

        def _add_btn(parent_f, text, color, cmd, tip_key=None):
            b = ctk.CTkButton(parent_f, text=text, fg_color=color, font=font, height=34, command=cmd)
            b.pack(side="left", padx=4, pady=3)
            if tip_key:
                ToolTip(b, tr(tip_key))
            self._export_buttons.append(b)
            return b

        def _group(grp_key, buttons, extra_right_btn=None):
            row = ctk.CTkFrame(out_frame)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(
                row, text=tr(grp_key), width=220, anchor="w",
                font=ctk.CTkFont(family=i18n.font_family(), size=12, weight="bold"),
                text_color="#A6A6A6"
            ).pack(side="left", padx=6, pady=3)
            for text, color, cmd in buttons:
                _add_btn(row, text, color, cmd)
            if extra_right_btn:
                txt, col, cmd, tip = extra_right_btn
                b_all = _add_btn(row, txt, col, cmd, tip)
                b_all.pack(side="right", padx=8, pady=3)

        # گروه ۱: دفترچه محاسبات و مدارک
        _group("grp_docs", [
            (tr("btn_export"), "#C55A11", self.action_export_report),
            (tr("btn_report"), "#6C3483", self.action_open_printable_report),
            (tr("btn_pdf"), "#B03A2E", self.action_export_pdf),
            (tr("btn_dv"), "#1F618D", self.action_export_dv),
            (tr("btn_quote"), "#0E6655", self.action_open_commercial_quote),
        ])

        # گروه ۲: فقط منحنی TCC و چیدمان پانل SVG (+ دکمه خروجی کامل ZIP در سمت چپ/راست)
        _group(
            "grp_drawings",
            [
                (tr("btn_tcc"), "#7D3C98", self.action_export_tcc),
                (tr("btn_layout"), "#8E44AD", self.action_export_layout),
            ],
            extra_right_btn=(tr("btn_export_all"), "#1E8449", self.action_export_all, "tip_export_all"),
        )

        # بخش ادغام‌شده نقشه‌ها (پیش‌نمایش و خروجی SLD و مدار فرمان + جدول سیم‌ها)
        schem_container = ctk.CTkFrame(parent, corner_radius=8)
        schem_container.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        self._build_schematics_preview_tab(schem_container)

    # ================================================================= گام ۷: کاتالوگ
    def _build_view_catalog(self, parent):
        font = ctk.CTkFont(family=i18n.font_family(), size=12)
        ctk.CTkLabel(parent, text=tr("cat_title"), font=ctk.CTkFont(family=i18n.font_family(), size=14, weight="bold")).pack(anchor="e", padx=14, pady=(10, 4))

        bar = ctk.CTkFrame(parent)
        bar.pack(fill="x", padx=12, pady=4)
        self.ent_cat_search = ctk.CTkEntry(bar, width=260, font=font, placeholder_text=tr("cat_search"))
        self.ent_cat_search.pack(side="right", padx=6)
        self.ent_cat_search.bind("<KeyRelease>", lambda _e: self._refresh_catalog_tree())
        ctk.CTkButton(bar, text=tr("cat_refresh"), fg_color="#566573", font=font,
                      command=self._refresh_catalog_tree).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=tr("cat_delete"), fg_color="#C0392B", font=font,
                      command=self.action_catalog_delete).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=tr("cat_edit"), fg_color="#B7950B", font=font,
                      command=self.action_catalog_edit).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=tr("cat_add"), fg_color="#1E8449", font=font,
                      command=self.action_catalog_add).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=tr("cat_web"), fg_color="#1F618D", font=font,
                      command=self.action_catalog_web_search).pack(side="left", padx=4)

        cols = ("part", "mfg", "series", "type", "in_a", "icu", "kw", "loss", "price", "quality")
        self.tree_catalog = ttk.Treeview(parent, columns=cols, show="headings")
        for c, key, w in (("part", "cat_col_part", 170), ("mfg", "cat_col_mfg", 110),
                          ("series", "cat_col_series", 150), ("type", "cat_col_type", 115),
                          ("in_a", "cat_col_in", 75), ("icu", "cat_col_icu", 75),
                          ("kw", "cat_col_kw", 85), ("loss", "cat_col_loss", 85),
                          ("price", "cat_col_price", 95), ("quality", "cat_col_quality", 110)):
            self.tree_catalog.heading(c, text=tr(key))
            self.tree_catalog.column(c, width=w, anchor="center")
        self.tree_catalog.pack(fill="both", expand=True, padx=12, pady=6)
        self._prices_cache = CatalogRepository().list_prices()

    def _refresh_catalog_tree(self):
        if not hasattr(self, "tree_catalog"):
            return
        query = (self.ent_cat_search.get() or "").strip().lower() if hasattr(self, "ent_cat_search") else ""
        for item in self.tree_catalog.get_children():
            self.tree_catalog.delete(item)
        self._prices_cache = CatalogRepository().list_prices()
        for d in self.catalog_repo_devices():
            if query and query not in d.part_number.lower() and query not in d.series.lower() \
                    and query not in d.manufacturer.lower():
                continue
            price = self._prices_cache.get(d.part_number)
            price_txt = f"{price['unit_price']:g} {price['currency']}" if price else "-"
            self.tree_catalog.insert("", "end", values=(
                d.part_number, d.manufacturer, d.series, d.device_type,
                d.rated_current_in_a, d.icu_ka_400v, d.motor_kw_400v, d.power_loss_w,
                price_txt, tr(f"quality_{d.data_quality.value}")))

    def catalog_repo_devices(self) -> List[CatalogDevice]:
        return CatalogRepository.get_default_catalog()

    def action_catalog_add(self):
        def _save(device, price, currency):
            try:
                CatalogRepository().add_device(device, unit_price=price, currency=currency)
            except Exception as ex:
                messagebox.showerror(tr("msg_error"), tr("cat_err_part_exists") + f"\n{ex}")
                return
            self._reload_engine_catalog()
            self._refresh_catalog_tree()
            messagebox.showinfo(tr("msg_success"), tr("cat_saved"))
        DeviceEditDialog(self, None, _save)

    def action_catalog_edit(self):
        sel = self.tree_catalog.selection()
        if not sel:
            return
        pn = self.tree_catalog.item(sel[0], "values")[0]
        device = CatalogRepository().get_device_payload(pn)
        if not device:
            return

        def _save(updated, price, currency):
            try:
                CatalogRepository().update_device(pn, updated, unit_price=price, currency=currency)
            except Exception as ex:
                messagebox.showerror(tr("msg_error"), str(ex))
                return
            self._reload_engine_catalog()
            self._refresh_catalog_tree()
            messagebox.showinfo(tr("msg_success"), tr("cat_saved"))
        DeviceEditDialog(self, device, _save)

    def action_catalog_delete(self):
        sel = self.tree_catalog.selection()
        if not sel:
            return
        pn = self.tree_catalog.item(sel[0], "values")[0]
        if not messagebox.askyesno(tr("msg_warn"), tr("cat_confirm_delete", pn=pn)):
            return
        CatalogRepository().delete_device(pn)
        self._reload_engine_catalog()
        self._refresh_catalog_tree()
        messagebox.showinfo(tr("msg_success"), tr("cat_deleted"))

    def action_catalog_web_search(self):
        WebSearchDialog(self, on_added=lambda: (self._reload_engine_catalog(), self._refresh_catalog_tree()))

    def _reload_engine_catalog(self):
        self.catalog = CatalogRepository.get_default_catalog()
        self.engine = EngineeringEngine(self.catalog)

    # ================================================================= محاسبات
    def _load_default_demo(self):
        self.current_project, self.current_feeders = build_demo_project()
        self._track_demo_text()
        self._fill_project_form(self.current_project)
        self._refresh_feeder_tree()
        self._run_calculations_and_refresh()

    def _track_demo_text(self):
        self._demo_text = {
            "project_name": self.current_project.project_name,
            "feeders": {feeder.feeder_id: (feeder.description, f"xl_d_f{index:02d}")
                        for index, feeder in enumerate(self.current_feeders, start=1)},
        }

    def _localize_demo_text(self):
        old_name = self._demo_text.get("project_name")
        if old_name is None:
            return
        new_name = tr("demo_name")
        for project in (self.current_project, self._last_calculation_project):
            if project is not None and project.project_name == old_name:
                project.project_name = new_name
        if self._project_input_data.get("project_name") == old_name:
            self._project_input_data["project_name"] = new_name
        if self._project_form_values.get("wiz_project_name") == old_name:
            self._project_form_values["wiz_project_name"] = new_name
        widget = self.wiz_entries["wiz_project_name"]
        if widget.get() == old_name:
            self._project_form_loading = True
            try:
                widget.delete(0, "end")
                widget.insert(0, new_name)
            finally:
                self._project_form_loading = False
        self._demo_text["project_name"] = new_name
        for feeder_id, (old_description, key) in list(self._demo_text["feeders"].items()):
            translated = tr(key)
            for feeder in [*(self.current_feeders or []), *self._last_calculation_feeders]:
                if feeder.feeder_id == feeder_id and feeder.description == old_description:
                    feeder.description = translated
            self._demo_text["feeders"][feeder_id] = (translated, key)

    def _refresh_instrument_tree(self):
        for item in self.tree_inst.get_children():
            self.tree_inst.delete(item)
        for instrument in self.instruments_list:
            self.tree_inst.insert("", "end", values=(
                instrument.tag_id, instrument.description, tr(f"signal_{instrument.signal_type.value}"),
                instrument.cable_length_m))
        if self.last_auto_results:
            _, summary = self.last_auto_results
            self.lbl_plc_summary.configure(text=tr(
                "wiz_plc_summary", di=summary.required_di_with_spare, do=summary.required_do_with_spare,
                ai=summary.required_ai_with_spare, ao=summary.required_ao_with_spare,
                cpu=summary.selected_cpu_part))

    def _run_calculations_and_refresh(self):
        self._mark_stale()
        try:
            project = self._project_from_form()
        except Exception as ex:
            messagebox.showerror(tr("msg_error"), tr("err_calc_generic", detail=str(ex)))
            return
        try:
            input_data = project.model_dump()
            # سایز PLC و بار ۲۴V ابزار دقیق (ادغام ویزارد فیلد)
            if self.instruments_list:
                dol = sum(1 for f in self.current_feeders or [] if f.load_type == LoadType.MOTOR_DOL)
                yd = sum(1 for f in self.current_feeders or [] if f.load_type == LoadType.MOTOR_STAR_DELTA)
                vfd = sum(1 for f in self.current_feeders or [] if f.load_type == LoadType.MOTOR_VFD)
                inst_outs, plc_sum = IndustrialAutomationEngine.process_automation_and_plc(
                    panel_tag=project.panel_tag, motor_dol_count=dol, motor_yd_count=yd,
                    motor_vfd_count=vfd, instruments=self.instruments_list,
                    spare_io_factor=project.spare_factor)
                self.last_auto_results = (inst_outs, plc_sum)
                project.plc_hmi_24vdc_power_w = round(project.plc_hmi_24vdc_power_w + plc_sum.total_instrumentation_24v_w, 1)
                if hasattr(self, "lbl_plc_summary"):
                    self.lbl_plc_summary.configure(text=tr("wiz_plc_summary", di=plc_sum.required_di_with_spare,
                                                            do=plc_sum.required_do_with_spare,
                                                            ai=plc_sum.required_ai_with_spare,
                                                            ao=plc_sum.required_ao_with_spare,
                                                            cpu=plc_sum.selected_cpu_part))
            f_outs, summary, validations = self.engine.process_project(project, self.current_feeders or [])
        except Exception as ex:
            messagebox.showerror(tr("msg_error"), tr("err_calc_generic", detail=str(ex)))
            return
        self.current_project = project
        self._last_calculation_project = project.model_copy(deep=True)
        self._last_calculation_feeders = [feeder.model_copy(deep=True) for feeder in self.current_feeders or []]
        self._project_input_data = input_data
        self._project_form_values = {key: widget.get() for key, widget in self.wiz_entries.items()}
        self.last_results = (f_outs, summary, validations)
        self.lbl_project_title.configure(text=tr("lbl_project", name=project.project_name, tag=project.panel_tag))
        self._refresh_results_views(f_outs, summary, validations)
        self._stale = False
        self._last_calc_time = datetime.now().strftime("%H:%M:%S")
        self._apply_status()
        return True

    def _refresh_results_views(self, f_outs, summary, validations):
        self.kpi_labels["main_current"].configure(text=f"{summary.design_main_current_a}A\n{summary.main_breaker.part_number if summary.main_breaker else '-'}")
        bus_txt = f"{summary.recommended_busbar_spec}\n{tr('kpi_bus_icw', a=summary.busbar_icw_1s_ka, b=summary.busbar_required_supports)}\nΔU={summary.busbar_du_v}V ({summary.busbar_du_pct}%)"
        if summary.motor_contribution_ka is not None:
            bus_txt += f" | I''kM={summary.motor_contribution_ka}kA"
        bus_txt += "\n" + (tr("kpi_spd", a=summary.selected_spd.spd_class, b=summary.selected_spd.part_number) if summary.selected_spd else tr("kpi_spd_none"))
        self.kpi_labels["busbar"].configure(text=bus_txt)
        self.kpi_labels["psu_24v"].configure(text=f"{summary.selected_psu_24v.series if summary.selected_psu_24v else 'N/A'}\n({summary.ctrl_24v_total_continuous_w}W)")
        tint = summary.estimated_internal_temp_c
        tint_text = f"{summary.total_power_loss_w}W / {summary.enclosure_natural_dissipation_w}W\n{tint}°C"
        if tint is not None and tint > 50.0:
            tint_text += f"\n{tr('kpi_tint_50_warn')}"
            self.kpi_labels["thermal"].configure(text=tint_text, text_color="#E74C3C")
        else:
            from customtkinter import ThemeManager
            base_colors = ThemeManager.theme["CTkLabel"]["text_color"]
            default_text = base_colors[1] if ctk.get_appearance_mode() == "Dark" else base_colors[0]
            self.kpi_labels["thermal"].configure(text=tint_text, text_color=default_text)
        self.kpi_labels["cooling"].configure(text=f"{summary.selected_fan.part_number if summary.selected_fan else tr('fan_natural')}")
        self.kpi_labels["enclosure"].configure(text=f"{summary.selected_enclosure.part_number}\n({int(summary.estimated_panel_width_mm)}x{int(summary.estimated_panel_height_mm)})")
        if summary.cap_bank_installed_kvar > 0:
            detuned = f" p={summary.cap_bank_detuned_pct:g}%" if summary.cap_bank_detuned_pct > 0 else ""
            self.kpi_labels["cap_bank"].configure(text=f"{summary.cap_bank_installed_kvar:g} kvar{detuned}")
        else:
            self.kpi_labels["cap_bank"].configure(text=tr("rpt_cap_none"))
        err = sum(1 for v in validations if v.status == ValidationStatus.ERROR)
        warn = sum(1 for v in validations if v.status == ValidationStatus.WARNING)
        self.kpi_labels["val_summary"].configure(text=tr("kpi_errors", err=err, warn=warn))

        for item in self.tree_results_tbl.get_children():
            self.tree_results_tbl.delete(item)
        for f in f_outs:
            cont = f.selected_contactor_main.part_number if f.selected_contactor_main else "-"
            aux = f.selected_bimetal.part_number if f.selected_bimetal else (f.selected_soft_starter.part_number if f.selected_soft_starter else (f.selected_vfd.part_number if f.selected_vfd else "-"))
            self.tree_results_tbl.insert("", "end", values=(f.feeder_id, f.description, tr(f"lt_{f.load_type.value}"), f.design_current_ib_a, f.cable_designation_str, f"{f.voltage_drop_percent}%", f.selected_protection.part_number if f.selected_protection else tr("scenario_NONE"), cont, aux, tr(f"selectivity_{f.selectivity_state.value}")))
        for item in self.tree_rules.get_children():
            self.tree_rules.delete(item)
        for v in validations:
            self.tree_rules.insert("", "end", tags=(v.status.value,), values=(tr(f"status_{v.status.value}"), v.rule_id, v.feeder_id, v.standard_ref, v.description, v.supporting_evidence, v.recommended_action))

    # ================================================================= اکشن‌ها
    def action_generate_template(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="Input_Load_List_Template.xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            ExcelInputManager.create_input_template(path)
            messagebox.showinfo(tr("msg_success"), tr("msg_template_created"))

    def action_import_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            self.current_project, self.current_feeders, errors = ExcelInputManager.load_from_excel(path)
            self._demo_text = {}
        except ExcelImportError as ex:
            messagebox.showwarning(tr("msg_warn"), str(ex))
            return
        except Exception:
            messagebox.showerror(tr("msg_error"), tr("err_excel_generic"))
            return
        self._fill_project_form(self.current_project)
        self._refresh_feeder_tree()
        self._mark_stale()
        if errors:
            messagebox.showwarning(tr("msg_warn"), tr("msg_load_with_errors", n=len(errors)) + "\n\n" + "\n".join(errors[:15]) + "\n\n" + tr("msg_load_stale_hint"))
        else:
            messagebox.showinfo(tr("msg_success"), tr("msg_load_stale_hint"))

    def _mark_stale(self):
        self._stale = True
        self._apply_status()

    def _apply_status(self):
        if self._status_lbl is None: return
        if self.current_project is None:
            self._status_lbl.configure(text="")
            return
        if self._stale:
            self._status_lbl.configure(text=tr("lbl_stale"), text_color="#B7950B")
        else:
            self._status_lbl.configure(text=tr("lbl_up_to_date", a=self._last_calc_time or "-"), text_color="#1E8449")
        state = "disabled" if (self._stale or not self.last_results) else "normal"
        for b in self._export_buttons:
            try: b.configure(state=state)
            except Exception: pass

    def action_load_demo(self):
        self.current_project, self.current_feeders = build_demo_project()
        self._track_demo_text()
        self._fill_project_form(self.current_project)
        self._refresh_feeder_tree()
        self._run_calculations_and_refresh()
        messagebox.showinfo(tr("msg_success"), tr("msg_demo_done"))

    def action_recalculate(self):
        if not self.current_feeders:
            messagebox.showwarning(tr("msg_warning"), tr("wiz_no_feeder"))
            return
        if self._run_calculations_and_refresh():
            f_outs, summary, _ = self.last_results
            messagebox.showinfo(tr("msg_success"), tr("wiz_calc_done", main=summary.design_main_current_a,
                                                       breaker=summary.main_breaker.part_number if summary.main_breaker else "-",
                                                       psu_w=summary.ctrl_24v_total_continuous_w))

    def _open_feeder_editor(self, event=None):
        if not self.current_feeders:
            return
        sel = self.tree_feeders.selection()
        if not sel: return
        idx = self.tree_feeders.index(sel[0])
        if idx >= len(self.current_feeders): return
        FeederEditDialog(self, self.current_feeders[idx], self._on_feeder_saved)

    def _on_feeder_saved(self, updated: FeederInput):
        for i, f in enumerate(self.current_feeders):
            if f.feeder_id == updated.feeder_id:
                self.current_feeders[i] = updated
                break
        self._refresh_feeder_tree()
        self._mark_stale()

    def action_export_all(self):
        if not self._get_results():
            return
        path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile="LV_Panel_Design_Bundle.zip", filetypes=[("ZIP", "*.zip")])
        if not path: return
        f_outs, summary, validations = self.last_results
        try:
            n = LVAssistApp.build_document_bundle(path, self.current_project, f_outs, summary, validations)
            messagebox.showinfo(tr("msg_success"), tr("msg_export_all_done", n=n))
        except Exception as ex:
            messagebox.showerror(tr("msg_error"), str(ex))

    @staticmethod
    def build_document_bundle(zip_path: str, project: ProjectSpec, f_outs, summary, validations, include_pdf: bool = True) -> int:
        """بسته کامل مدارک مهندسی پروژه در یک فایل ZIP (بدون فایل‌های EPLAN و DXF)."""
        dv_report = build_design_verification(project, f_outs, summary, validations)
        files = {
            "01_Design_Output.xlsx": lambda p: ExcelExporter.export_to_excel(p, project, f_outs, summary, validations),
            "02_Engineering_Report.html": lambda p: PrintableReportExporter.generate_html_report(p, project, f_outs, summary, validations),
            "02_Design_Verification_Report.html": lambda p: DesignVerificationExporter.generate_html(p, project, summary, dv_report),
            "07_Commercial_Quotation.html": lambda p: __import__("lv_assist.commercial", fromlist=["CommercialEngine"]).CommercialEngine.export_quote_html(p, project, f_outs, summary),
            "03_Single_Line_Diagram.svg": lambda p: SldGenerator.generate_svg_file(p, project, f_outs, summary),
            "04_Time_Current_Curves.svg": lambda p: TccGenerator.generate_svg_file(p, project, f_outs, summary),
            "05_Control_Circuits.svg": lambda p: ControlCircuitGenerator.generate_svg_file(p, project, f_outs, summary),
            "06_Panel_Layout.svg": lambda p: PanelLayoutGenerator.generate_svg_file(p, project, f_outs, summary),
        }
        count = 0
        with tempfile.TemporaryDirectory(prefix="lvassist_bundle_") as tmp:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, fn in files.items():
                    p = os.path.join(tmp, name)
                    fn(p)
                    zf.write(p, arcname=name)
                    count += 1
                if include_pdf:
                    pdf_path = os.path.join(tmp, "02_Engineering_Report.pdf")
                    if PdfExporter.export_html_to_pdf(os.path.join(tmp, "02_Engineering_Report.html"), pdf_path):
                        zf.write(pdf_path, arcname="02_Engineering_Report.pdf")
                        count += 1
        return count

    def action_export_report(self):
        if not self._get_results(): return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="LV_Panel_Design_Output.xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            f_outs, summary, validations = self.last_results
            ExcelExporter.export_to_excel(path, self.current_project, f_outs, summary, validations)
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_open_printable_report(self):
        if not self._get_results(): return
        f_outs, summary, validations = self.last_results
        path = str(get_output_dir("reports") / "LV_Panel_Engineering_Report.html")
        PrintableReportExporter.generate_html_report(path, self.current_project, f_outs, summary, validations)
        webbrowser.open(f"file://{path}")

    def action_open_commercial_quote(self):
        if not self._get_results():
            return
        from lv_assist.commercial import CommercialEngine
        f_outs, summary, _ = self.last_results
        path = str(get_output_dir("reports") / "LV_Panel_Commercial_Quotation.html")
        CommercialEngine.export_quote_html(path, self.current_project, f_outs, summary)
        webbrowser.open(f"file://{path}")

    def action_export_dv(self):
        if not self._get_results(): return
        f_outs, summary, validations = self.last_results
        path = filedialog.asksaveasfilename(defaultextension=".html",
                                            initialfile="Design_Verification_Report.html",
                                            filetypes=[("HTML", "*.html")])
        if not path: return
        report = build_design_verification(self.current_project, f_outs, summary, validations)
        DesignVerificationExporter.generate_html(path, self.current_project, summary, report)
        webbrowser.open(f"file://{path}")
        messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def _get_results(self):
        if self._stale:
            messagebox.showwarning(tr("msg_warning"), tr("lbl_stale"))
            return None
        if not self.last_results: return None
        f_outs, summary, validations = self.last_results
        return f_outs, summary, validations

    def action_export_sld(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".svg", initialfile="Single_Line_Diagram.svg", filetypes=[("SVG", "*.svg")])
        if path:
            SldGenerator.generate_svg_file(path, self.current_project, res[0], res[1])
            webbrowser.open(f"file://{path}")
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_tcc(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".svg", initialfile="Time_Current_Curves.svg", filetypes=[("SVG", "*.svg")])
        if path:
            TccGenerator.generate_svg_file(path, self.current_project, res[0], res[1])
            webbrowser.open(f"file://{path}")
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_pdf(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile="LV_Panel_Engineering_Report.pdf", filetypes=[("PDF", "*.pdf")])
        if path:
            tmp_html = os.path.join(os.environ.get("TEMP", get_app_working_dir()), "lvassist_report_temp.html")
            PrintableReportExporter.generate_html_report(tmp_html, self.current_project, res[0], res[1], res[2])
            if PdfExporter.export_html_to_pdf(tmp_html, path):
                messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))
            else:
                messagebox.showwarning(tr("msg_warning"), tr("msg_pdf_fail"))

    def action_export_eplan(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="EPLAN_Parts_Import.csv", filetypes=[("CSV", "*.csv")])
        if path:
            EplanExporter.export_csv(path, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_eplan_script(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".cs", initialfile="EPLAN_Generate_Pages.cs", filetypes=[("C# Script", "*.cs")])
        if path:
            EplanMacroExporter.export_file(path, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_eplan_macros(self):
        res = self._get_results()
        if not res: return
        folder = filedialog.askdirectory(title=tr("btn_eplan_macros"))
        if folder:
            out_dir = os.path.join(folder, "EPLAN_Macros")
            written = EplanMacroFileExporter.export_library(out_dir, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_macros_done", n=len(written)))

    def action_export_eplan_page_macros(self):
        res = self._get_results()
        if not res: return
        folder = filedialog.askdirectory(title=tr("btn_eplan_page_macros"))
        if folder:
            out_dir = os.path.join(folder, "EPLAN_Page_Macros")
            written = EplanPageMacroExporter.export_library(out_dir, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_page_macros_done", n=len(written)))

    def action_export_eplan_test_kit(self):
        res = self._get_results()
        if not res: return
        folder = filedialog.askdirectory(title=tr("btn_eplan_test_kit"))
        if folder:
            out_dir = os.path.join(folder, "EPLAN_FieldTest")
            written = EplanFieldTestKit.export_kit(out_dir, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_test_kit_done", n=len(written)))

    def _on_mfg_change(self, display_value: str):
        if self.current_project is None: return
        idx = self.mfg_display.index(display_value) if display_value in self.mfg_display else 0
        self.current_project.preferred_manufacturer = self.mfg_values[idx]
        if self.last_results:
            self._run_calculations_and_refresh()

    def _on_spd_change(self, display_value: str):
        if self.current_project is None: return
        idx = self.spd_display.index(display_value) if display_value in self.spd_display else 0
        self.current_project.spd_class = SpdClass(self.spd_values[idx])
        self._mark_stale()

    def action_export_ctrl_svg(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".svg", initialfile="Control_Circuits.svg", filetypes=[("SVG", "*.svg")])
        if path:
            ControlCircuitGenerator.generate_svg_file(path, self.current_project, res[0], res[1])
            webbrowser.open(f"file://{path}")
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_connections(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="Control_Connections_EPLAN.csv", filetypes=[("CSV", "*.csv")])
        if path:
            ControlCircuitGenerator.export_connections_csv(path, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_layout(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".svg", initialfile="Panel_Layout.svg", filetypes=[("SVG", "*.svg")])
        if path:
            PanelLayoutGenerator.generate_svg_file(path, self.current_project, res[0], res[1])
            webbrowser.open(f"file://{path}")
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_export_parts(self):
        res = self._get_results()
        if not res: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="EPLAN_Parts_Management.csv", filetypes=[("CSV", "*.csv")])
        if path:
            EplanPartsExporter.export_csv(path, self.current_project, res[0], res[1])
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    # --- پیش‌نمایش نقشه‌ها (IEC SVG bridge) ---
    def _build_schematics_preview_tab(self, parent):
        ctrl_bar = ctk.CTkFrame(parent, height=55)
        ctrl_bar.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(ctrl_bar, text=tr("schem_pick"), font=ctk.CTkFont(size=12, weight="bold")).pack(side="right", padx=8)
        self.cmb_sheet_selector = ctk.CTkComboBox(
            ctrl_bar, values=[tr("schem_sld")], width=320,
            command=lambda _: self.action_refresh_schematic_preview()
        )
        self.cmb_sheet_selector.pack(side="right", padx=8, pady=8)

        for key, color, command in (
            ("schem_preview", "#1F618D", self.action_preview_selected_svg_in_browser),
            ("schem_save_one", "#1E8449", self.action_save_single_svg),
            ("schem_save_all", "#B7950B", self.action_save_all_svgs_folder),
        ):
            button = ctk.CTkButton(ctrl_bar, text=tr(key), fg_color=color, command=command)
            button.pack(side="left", padx=6, pady=8)
            self._export_buttons.append(button)

        lbl_w = ctk.CTkLabel(parent, text=tr("schem_wire_table"), font=ctk.CTkFont(size=12))
        lbl_w.pack(anchor="e", padx=10, pady=(4, 2))

        self.tree_wires_preview = ttk.Treeview(
            parent, columns=("wire", "feeder", "role", "from_pin", "to_pin", "spec"), show="headings", height=8
        )
        for col, txt_key, w in [("wire", "schem_w_wire", 130), ("feeder", "schem_w_feeder", 75),
                                ("role", "schem_w_role", 250), ("from_pin", "schem_w_from", 230),
                                ("to_pin", "schem_w_to", 260), ("spec", "schem_w_spec", 180)]:
            self.tree_wires_preview.heading(col, text=tr(txt_key))
            self.tree_wires_preview.column(col, width=w, anchor="center")
        self.tree_wires_preview.pack(fill="x", padx=8, pady=4)

        self.txt_svg_inspector = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11), height=180)
        self.txt_svg_inspector.pack(fill="both", expand=True, padx=8, pady=6)

    def _populate_sheet_selector(self, f_outs, preserve_selection: bool = True):
        if not hasattr(self, "cmb_sheet_selector"):
            return
        prev = self.cmb_sheet_selector.get() if preserve_selection else ""
        sld_item = f"SLD — {tr('schem_sld')}"
        values = [sld_item] + [f"[{f.feeder_id}] {tr('schem_ladder')} — {f.description[:28]}" for f in f_outs]
        self.cmb_sheet_selector.configure(values=values)
        matched = None
        if prev:
            if prev in values:
                matched = prev
            else:
                for f in f_outs:
                    if f"[{f.feeder_id}]" in prev or f" {f.feeder_id} " in prev:
                        matched = next((v for v in values if f"[{f.feeder_id}]" in v), None)
                        break
        self.cmb_sheet_selector.set(matched if matched else values[0])

    def _get_selected_svg_and_name(self) -> Tuple[str, str]:
        if not self._get_results():
            return "", "empty.svg"
        f_outs, summary, _ = self.last_results
        choice = self.cmb_sheet_selector.get() or ""

        for idx, f in enumerate(f_outs, start=1):
            if f"[{f.feeder_id}]" in choice or f" {f.feeder_id} " in choice or choice.endswith(f.feeder_id):
                svg_str = GuiOutputBridge.generate_feeder_ladder_svg(self.current_project, f, summary, feeder_index=idx)
                return svg_str, f"Control_Ladder_{f.feeder_id}.svg"

        svg_str = GuiOutputBridge.generate_sld_svg(self.current_project, f_outs, summary)
        return svg_str, f"SLD_{self.current_project.panel_tag.strip('+')}.svg"

    def action_refresh_schematic_preview(self):
        if not self.last_results or self._stale:
            return
        f_outs, summary, _ = self.last_results
        self._populate_sheet_selector(f_outs, preserve_selection=True)
        svg_str, fname = self._get_selected_svg_and_name()

        wires, _ = GuiOutputBridge.generate_all_wire_and_terminal_schedules(self.current_project, f_outs, summary)
        choice = self.cmb_sheet_selector.get() or ""
        is_sld = choice.startswith("SLD")

        for item in self.tree_wires_preview.get_children():
            self.tree_wires_preview.delete(item)
        for w in wires:
            fid = w["feeder_id"]
            if is_sld or f"[{fid}]" in choice or f" {fid} " in choice:
                self.tree_wires_preview.insert("", "end", values=(
                    w["wire_no"], fid, w["potential_role"], w["from_pin"], w["to_pin"], w["wire_spec"]
                ))

        self.txt_svg_inspector.delete("1.0", "end")
        self.txt_svg_inspector.insert(
            "1.0",
            f"/* {fname} — LV-PanelAssist GuiOutputBridge */\n{svg_str}"
        )

    def action_preview_selected_svg_in_browser(self):
        svg_str, fname = self._get_selected_svg_and_name()
        if not svg_str:
            return
        preview_path = str(get_output_dir("previews") / f"_preview_{fname}.html")
        with open(preview_path, "w", encoding="utf-8") as fp:
            fp.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{fname}</title></head>"
                     f"<body style='margin:20px;background:#F1F5F9;'>{svg_str}</body></html>")
        webbrowser.open(f"file://{preview_path}")

    def action_save_single_svg(self):
        svg_str, fname = self._get_selected_svg_and_name()
        if not svg_str:
            return
        path = filedialog.asksaveasfilename(defaultextension=".svg", initialfile=fname, filetypes=[("SVG Vector", "*.svg")])
        if path:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(svg_str)
            messagebox.showinfo(tr("msg_success"), tr("msg_export_saved"))

    def action_save_all_svgs_folder(self):
        if not self._get_results():
            return
        folder = filedialog.askdirectory(title=tr("schem_save_all"))
        if folder:
            f_outs, summary, _ = self.last_results
            files = GuiOutputBridge.export_all_svgs_to_folder(folder, self.current_project, f_outs, summary)
            messagebox.showinfo(tr("msg_success"), tr("schem_saved_n", n=len(files), folder=folder))

    # ================================================================= زبان و تم
    def _on_language_change(self, value: str):
        code = LANG_SEGMENT_TO_CODE.get(value, "fa")
        if code == i18n.get_language(): return
        i18n.set_language(code)
        self._localize_demo_text()
        if self._last_calculation_project is not None:
            self.last_results = self.engine.process_project(
                self._last_calculation_project.model_copy(deep=True),
                [feeder.model_copy(deep=True) for feeder in self._last_calculation_feeders])
        self._rebuild_preserving_project_form()

    def _on_theme_change(self):
        new_mode = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        i18n.set_theme(new_mode)
        ctk.set_appearance_mode(new_mode)
        self._apply_tree_style(i18n.font_family())
        self._apply_tree_tags(self.tree_rules)
        if self.last_results:
            self._refresh_results_views(*self.last_results)
        self._apply_status()

    def _rebuild_preserving_project_form(self):
        values = {key: widget.get() for key, widget in self.wiz_entries.items()}
        baseline = self._project_form_values.copy()
        input_data = self._project_input_data.copy()
        self._build_ui()
        if self.current_project is not None:
            self._fill_project_form(self.current_project)
            self._refresh_feeder_tree()
            self._refresh_instrument_tree()
            if self.last_results:
                self._refresh_results_views(*self.last_results)
            self.lbl_project_title.configure(text=tr("lbl_project", name=self.current_project.project_name,
                                                      tag=self.current_project.panel_tag))
        self._project_form_loading = True
        try:
            for key, value in values.items():
                widget = self.wiz_entries[key]
                if isinstance(widget, ctk.CTkEntry):
                    widget.delete(0, "end")
                    widget.insert(0, value)
                else:
                    widget.set(value)
            self._project_form_values = baseline
            self._project_input_data = input_data
        finally:
            self._project_form_loading = False
        self._apply_status()

    def _apply_tree_style(self, font_family: str):
        style = ttk.Style(); style.theme_use("default")
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg, field = ("#2B2B2B", "white", "#2B2B2B") if dark else ("#FFFFFF", "#1C2833", "#FFFFFF")
        style.configure("Treeview", background=bg, foreground=fg, rowheight=28, fieldbackground=field, font=(font_family, 10))
        style.configure("Treeview.Heading", background="#1F4E78", foreground="white", font=(font_family, 10, "bold"))

    def _apply_tree_tags(self, tree):
        dark = ctk.get_appearance_mode() == "Dark"
        tags = {
            "COMPLETED": ("#1E3A2F", "#A9DFBF") if dark else ("#E2EFDA", "#1E8449"),
            "WARNING": ("#4A3B12", "#F9E79F") if dark else ("#FFF2CC", "#7D6608"),
            "ERROR": ("#511E1E", "#F5B7B1") if dark else ("#FCE4D6", "#C0392B"),
        }
        for status, (bg, fg) in tags.items():
            tree.tag_configure(status, background=bg, foreground=fg)
