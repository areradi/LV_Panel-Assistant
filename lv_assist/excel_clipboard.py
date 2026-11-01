from dataclasses import dataclass, field
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
                if power_kw <= 0 or power_kw > 2000:
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
                    if length_m <= 0 or length_m > 5000:
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
                    if not (0.1 <= cos_phi <= 1.0):
                        result.errors.append(
                            RowValidationError(human_row, "cos_phi", raw_cos, "ضریب توان باید بین 0.1 و 1.0 باشد.")
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
                    if not (0.1 <= efficiency <= 1.0):
                        result.errors.append(
                            RowValidationError(human_row, "efficiency", raw_eff, "بازده باید بین 0.1 و 1.0 باشد.")
                        )
                        continue
                except ValueError:
                    result.errors.append(
                        RowValidationError(human_row, "efficiency", raw_eff, "فرمت عدد بازده نامعتبر است.")
                    )
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
                )
            )

        return result
