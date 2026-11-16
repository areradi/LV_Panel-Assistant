from dataclasses import dataclass, field
import math
from typing import List, Dict, Optional, Tuple


@dataclass
class ParsedFeederRow:
    row_index: int
    feeder_tag: str
    description: str
    power_kw: float
    length_m: Optional[float]
    starter_type: str = "DOL"
    cos_phi: float = 0.85
    efficiency: float = 0.90
    assumed_fields: Dict[str, float] = field(default_factory=dict)
    phases: Optional[int] = None
    demand_factor_kd: Optional[float] = None
    cable_section_mm2: Optional[float] = None
    conductor_material: Optional[str] = None
    thdi_pct: Optional[float] = None
    has_socket_outlets: Optional[bool] = None
    fire_resistant: Optional[bool] = None


@dataclass
class RowValidationError:
    row_index: int
    column_name: str
    raw_value: str
    error_message: str


@dataclass
class ClipboardImportResult:
    valid_rows: List[ParsedFeederRow] = field(default_factory=list)
    errors: List[RowValidationError] = field(default_factory=list)
    detected_mapping: Dict[str, int] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return len(self.errors) == 0 and len(self.valid_rows) > 0


class ExcelClipboardParser:
    HEADER_SYNONYMS: Dict[str, List[str]] = {
        "feeder_tag": ["tag", "bmk", "feeder", "code", "کد", "فیدر", "تگ", "kennzeichnung"],
        "description": ["desc", "description", "name", "load", "شرح", "نام مصرف کننده", "توضیحات", "bezeichnung"],
        "power_kw": ["kw", "power", "power_kw", "p_kw", "توان", "توان (kw)", "leistung"],
        "length_m": ["length", "len", "length_m", "l_m", "طول", "طول کابل", "طول (m)", "länge"],
        "starter_type": ["starter", "type", "drive", "راه انداز", "نوع راه انداز", "راه‌انداز", "شروع"],
        "cos_phi": ["cosphi", "cos_phi", "cos phi", "pf", "ضریب توان"],
        "efficiency": ["eff", "efficiency", "eta", "راندمان", "بازده"],
        "phases": ["phases", "phase", "phase_count", "number of phases", "phasen", "anzahl phasen", "فاز", "تعداد فاز", "تعداد فازها"],
        "demand_factor_kd": ["demand_factor_kd", "demand factor", "demand", "kd", "ضریب تقاضا", "ضریب بار", "bedarfsfaktor"],
        "cable_section_mm2": ["cable_section_mm2", "cable section", "cross section", "section", "querschnitt", "مقطع", "سطح مقطع", "مقطع کابل", "mm2", "mm²"],
        "conductor_material": ["conductor_material", "conductor material", "conductor", "material", "leiterwerkstoff", "leitermaterial", "جنس هادی", "جنس کابل", "هادی", "رسانا"],
        "thdi_pct": ["thdi_pct", "thdi", "thd-i", "harmonic distortion", "oberschwingungsgehalt", "اعوجاج هارمونیکی", "اعوجاج هارمونیک", "هارمونیک"],
        "has_socket_outlets": ["has_socket_outlets", "socket outlets", "socket", "steckdosen", "steckdose", "پریز", "سوکت"],
        "fire_resistant": ["fire_resistant", "fire resistant", "fire resistance", "feuerbeständig", "brandschutz", "مقاوم در برابر حریق", "مقاوم حریق", "ضد حریق"],
    }

    VALID_STARTERS = {"DOL", "YD", "STAR-DELTA", "VFD", "SOFTSTARTER", "FEEDER", "RESISTIVE"}

    @classmethod
    def _detect_header_mapping(cls, first_row_cells: List[str]) -> Tuple[bool, Dict[str, int]]:
        mapping: Dict[str, int] = {}
        normalized = [c.strip().lower() for c in first_row_cells]

        for col_idx, cell_text in enumerate(normalized):
            for field_name, synonyms in cls.HEADER_SYNONYMS.items():
                if any(syn == cell_text or syn in cell_text for syn in synonyms):
                    if field_name not in mapping:
                        mapping[field_name] = col_idx

        is_header = "power_kw" in mapping or len(mapping) >= 2
        if not is_header:
            default_order = ["feeder_tag", "description", "power_kw", "length_m", "starter_type", "cos_phi", "efficiency"]
            mapping = {
                field_name: idx
                for idx, field_name in enumerate(default_order)
                if idx < len(first_row_cells)
            }
        return is_header, mapping

    @classmethod
    def parse_clipboard_text(cls, raw_clipboard: str) -> ClipboardImportResult:
        result = ClipboardImportResult()
        lines = [line for line in raw_clipboard.splitlines() if line.strip()]
        if not lines:
            result.errors.append(RowValidationError(0, "CLIPBOARD", "", "متن کپی‌شده خالی است."))
            return result

        delimiter = "\t" if "\t" in lines[0] else (";" if ";" in lines[0] else ",")
        rows_cells = [[cell.strip() for cell in line.split(delimiter)] for line in lines]

        has_header, mapping = cls._detect_header_mapping(rows_cells[0])
        result.detected_mapping = mapping
        start_idx = 1 if has_header else 0

        for idx in range(start_idx, len(rows_cells)):
            human_row = idx + 1
            cells = rows_cells[idx]
            if all(not c for c in cells):
                continue

            def get_cell(field_key: str, default_val: str = "") -> str:
                col_i = mapping.get(field_key)
                if col_i is not None and col_i < len(cells):
                    return cells[col_i]
                return default_val

            tag = get_cell("feeder_tag", f"F{human_row:02d}") or f"F{human_row:02d}"
            desc = get_cell("description", f"Feeder {human_row}")

            raw_kw = get_cell("power_kw", "").replace(",", ".")
            try:
                power_kw = float(raw_kw)
                if not math.isfinite(power_kw) or power_kw <= 0 or power_kw > 2000:
                    result.errors.append(
                        RowValidationError(human_row, "power_kw", raw_kw, "توان فیدر باید عددی مثبت و تا 2000 کیلووات باشد.")
                    )
                    continue
            except ValueError:
                result.errors.append(
                    RowValidationError(human_row, "power_kw", raw_kw, "مقدار توان (kW) نامعتبر یا خالی است.")
                )
                continue

            raw_len = get_cell("length_m", "").replace(",", ".")
            length_m: Optional[float] = None
            if raw_len:
                try:
                    length_m = float(raw_len)
                    if not math.isfinite(length_m) or length_m <= 0 or length_m > 5000:
                        result.errors.append(
                            RowValidationError(human_row, "length_m", raw_len, "طول کابل باید عددی مثبت باشد.")
                        )
                        continue
                except ValueError:
                    result.errors.append(
                        RowValidationError(human_row, "length_m", raw_len, "فرمت عدد طول کابل نامعتبر است.")
                    )
                    continue

            raw_starter = (get_cell("starter_type", "DOL") or "DOL").upper()
            if raw_starter not in cls.VALID_STARTERS:
                result.errors.append(
                    RowValidationError(human_row, "starter_type", raw_starter, f"نوع راه‌انداز '{raw_starter}' نامعتبر است.")
                )
                continue

            raw_cos = get_cell("cos_phi", "").replace(",", ".")
            cos_phi = 0.85
            if raw_cos:
                try:
                    cos_phi = float(raw_cos)
                    if not (0.2 < cos_phi <= 1.0):
                        result.errors.append(
                            RowValidationError(human_row, "cos_phi", raw_cos, "ضریب توان باید بیشتر از 0.2 و حداکثر 1.0 باشد.")
                        )
                        continue
                except ValueError:
                    result.errors.append(
                        RowValidationError(human_row, "cos_phi", raw_cos, "فرمت عدد ضریب توان نامعتبر است.")
                    )
                    continue

            raw_eff = get_cell("efficiency", "").replace(",", ".")
            efficiency = 0.9
            if raw_eff:
                try:
                    efficiency = float(raw_eff)
                    if not (0.1 < efficiency <= 1.0):
                        result.errors.append(
                            RowValidationError(human_row, "efficiency", raw_eff, "بازده باید بین 0.1 و 1.0 باشد.")
                        )
                        continue
                except ValueError:
                    result.errors.append(
                        RowValidationError(human_row, "efficiency", raw_eff, "فرمت عدد بازده نامعتبر است.")
                    )
                    continue

            row_error_count = len(result.errors)

            def optional_number(field_key: str, valid, message: str) -> Optional[float]:
                raw_value = get_cell(field_key, "").replace(",", ".")
                if not raw_value:
                    return None
                try:
                    value = float(raw_value)
                except ValueError:
                    result.errors.append(RowValidationError(
                        human_row, field_key, raw_value, f"مقدار {field_key} نامعتبر است."
                    ))
                    return None
                if not math.isfinite(value) or not valid(value):
                    result.errors.append(RowValidationError(
                        human_row, field_key, raw_value, message
                    ))
                    return None
                return value

            phases_value = optional_number(
                "phases", lambda value: value in (1, 3), "تعداد فاز باید 1 یا 3 باشد."
            )
            if phases_value is not None and not phases_value.is_integer():
                result.errors.append(RowValidationError(
                    human_row, "phases", get_cell("phases"), "تعداد فاز باید عدد صحیح 1 یا 3 باشد."
                ))
                phases_value = None
            phases = int(phases_value) if phases_value is not None else None

            demand_factor_kd = optional_number(
                "demand_factor_kd", lambda value: 0 < value <= 1,
                "ضریب تقاضا باید بزرگ‌تر از 0 و حداکثر 1 باشد."
            )
            cable_section_mm2 = optional_number(
                "cable_section_mm2", lambda value: value > 0,
                "مقطع کابل باید عددی مثبت باشد."
            )
            thdi_pct = optional_number(
                "thdi_pct", lambda value: 0 <= value <= 200,
                "THDi باید بین 0 و 200 درصد باشد."
            )

            raw_material = get_cell("conductor_material", "").strip()
            conductor_material = None
            if raw_material:
                material_aliases = {
                    "cu": "CU", "copper": "CU", "kupfer": "CU", "مس": "CU", "مسی": "CU",
                    "al": "AL", "aluminium": "AL", "aluminum": "AL", "آلومینیوم": "AL",
                    "آلومينيوم": "AL", "آلومینیم": "AL", "آلومينييم": "AL",
                }
                conductor_material = material_aliases.get(raw_material.casefold())
                if conductor_material is None:
                    result.errors.append(RowValidationError(
                        human_row, "conductor_material", raw_material,
                        "جنس هادی باید CU/مس یا AL/آلومینیوم باشد."
                    ))

            def optional_bool(field_key: str) -> Optional[bool]:
                raw_value = get_cell(field_key, "").strip().casefold()
                if not raw_value:
                    return None
                if raw_value in {"true", "yes", "y", "1", "بله", "آری", "اره", "ja"}:
                    return True
                if raw_value in {"false", "no", "n", "0", "خیر", "نه", "nein"}:
                    return False
                result.errors.append(RowValidationError(
                    human_row, field_key, get_cell(field_key),
                    "مقدار بولی باید true/false، yes/no، بله/خیر یا 1/0 باشد."
                ))
                return None

            has_socket_outlets = optional_bool("has_socket_outlets")
            fire_resistant = optional_bool("fire_resistant")
            if len(result.errors) > row_error_count:
                continue

            result.valid_rows.append(
                ParsedFeederRow(
                    row_index=human_row,
                    feeder_tag=tag,
                    description=desc,
                    power_kw=power_kw,
                    length_m=length_m,
                    starter_type=raw_starter,
                    cos_phi=cos_phi,
                    efficiency=efficiency,
                    assumed_fields={key: value for key, value, raw in
                                    (("cos_phi", cos_phi, raw_cos), ("efficiency", efficiency, raw_eff))
                                    if not raw},
                    phases=phases,
                    demand_factor_kd=demand_factor_kd,
                    cable_section_mm2=cable_section_mm2,
                    conductor_material=conductor_material,
                    thdi_pct=thdi_pct,
                    has_socket_outlets=has_socket_outlets,
                    fire_resistant=fire_resistant,
                )
            )

        return result
