from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TABLE_TYPES = {
    'breaking_capacity_tables.csv': 'BREAKING_CAPACITY',
    'current_rating_tables.csv': 'CURRENT_RATING',
    'derating_tables.csv': 'DERATING',
    'motor_coordination_tables.csv': 'MOTOR_COORDINATION',
    'power_loss_tables.csv': 'POWER_LOSS',
    'selectivity_tables.csv': 'SELECTIVITY',
    'trip_curves_tables.csv': 'TRIP_CURVES',
    'voltage_rating_tables.csv': 'VOLTAGE_RATING',
}
CSV_COLUMNS = ('brand', 'filename', 'page', 'headers_json', 'rows_json')
NORMALIZATION_VERSION = 1

_HEADERS = ('Position', 'Number', 'Manufacturer', 'Type', 'Description', 'Pos')
_REVERSED_HEADERS = {word[::-1]: word for word in _HEADERS}
_FAMILIES = (
    (r'prismaset|\bmtz[123]?\b', 'Schneider Electric', 'PrismaSeT/MTZ'),
    (r'\btmax(?:\s+xt)?\b', 'ABB', 'Tmax'),
    (r'\bemax\s*2?\b', 'ABB', 'Emax'),
    (r'\bmns(?:is|[0-9])?\b', 'ABB', 'MNS'),
    (r'softstartercatalog[_ -]1sfc132012', 'ABB', 'Softstarter'),
    (r'\bsivacon\b', 'Siemens', 'SIVACON'),
    (r'\b3w[al]\b|\b3va[12]?\b', 'Siemens', 'SENTRON'),
    (r'\bxenergy\b', 'Eaton', 'xEnergy'),
    (r'\brsgd\b', 'Carlo Gavazzi', 'RSGD'),
    (r'\bvlt\b|\bfc(?:101|301|302)\b', 'Danfoss', 'VLT'),
    (r'\btopjob(?:[- ]s)?\b', 'WAGO', 'TOPJOB'),
    (r'\bklippon\b', 'Weidmüller', 'Klippon'),
    (r'\bxl3s?\b', 'Legrand', 'XL3'),
    (r'\bunivers\b', 'Hager', 'univers'),
    (r'\bri4power\b', 'Rittal', 'Ri4Power'),
)
_BRANDS = ('Schneider Electric', 'ABB', 'Siemens', 'Eaton', 'Carlo Gavazzi', 'Danfoss',
           'WAGO', 'Weidmüller', 'Legrand', 'Hager', 'Rittal', 'Hoffman', 'IDEC')
_TYPE_SIGNALS = {
    'BREAKING_CAPACITY': r'\b(?:icu|ics|breaking capacity)\b',
    'CURRENT_RATING': r'\b(?:rated current|nominal current|current rating)\b',
    'DERATING': r'\b(?:derating|ambient temperature|temperature correction)\b',
    'MOTOR_COORDINATION': r'\b(?:type [12]|contactor|starter|coordination)\b',
    'POWER_LOSS': r'\b(?:power loss(?:es)?|power dissipation|heat dissipation)\b',
    'SELECTIVITY': r'\b(?:selectivity|discrimination)\b',
    'TRIP_CURVES': r'\b(?:trip(?:ping)? curve|time.current)\b',
    'VOLTAGE_RATING': r'\b(?:rated voltage|operating voltage|nominal voltage)\b',
}


class ExtractedTable(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    brand: str = 'Unknown'
    filename: str = Field(min_length=1)
    page: int = Field(gt=0)
    headers: list[str] = Field(min_length=1)
    rows: list[dict[str, str]] = Field(min_length=1)


class NormalizedQuantity(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

    value: float
    unit: Literal['A', 'V', 'W', '°C', '1']


class ReferenceTable(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    table_id: str
    source_file: str
    source_page: int
    table_type: str
    manufacturer: str | None
    manufacturer_basis: str
    series: str | None
    headers: list[str]
    rows: list[dict[str, str]]
    quantities: list[dict]
    review_state: Literal['PENDING_REVIEW', 'QUARANTINED']
    data_quality: Literal['UNVERIFIED'] = 'UNVERIFIED'
    issues: list[str]
    normalization_version: int = NORMALIZATION_VERSION


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f'Nonfinite JSON value: {value}')


def parse_extracted_record(raw: dict) -> ExtractedTable:
    if set(raw) != set(CSV_COLUMNS) or any(value is None for value in raw.values()):
        raise ValueError('Expected exactly the five extraction columns')
    headers = json.loads(raw['headers_json'], object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    rows = json.loads(raw['rows_json'], object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    return ExtractedTable(brand=raw['brand'], filename=raw['filename'], page=raw['page'], headers=headers, rows=rows)


def normalize_header(value: str) -> str:
    value = ' '.join(unicodedata.normalize('NFKC', value).split())
    return _REVERSED_HEADERS.get(value, value)


def canonical_source_file(filename: str) -> str:
    return re.sub(r'\s+\(\d+\)(?=\.[^.]+$)', '', filename.strip())


def detect_manufacturer(filename: str, supplied: str = 'Unknown') -> tuple[str | None, str | None, str]:
    tokens = re.sub(r'[_+]', ' ', unicodedata.normalize('NFKC', filename)).casefold()
    families = [(brand, series) for pattern, brand, series in _FAMILIES if re.search(pattern, tokens)]
    explicit = supplied.strip()
    if explicit.casefold() in {'', 'unknown', 'unspecified', 'n/a'}:
        explicit = ''
    else:
        explicit = next((brand for brand in _BRANDS if brand.casefold() == explicit.casefold()), explicit)
    inferred = {brand for brand, _ in families}
    inferred.update(brand for brand in _BRANDS if re.search(r'(?<!\w)' + re.escape(brand.casefold()) + r'(?!\w)', tokens))
    if len(inferred) > 1 or (explicit and inferred and explicit not in inferred):
        return None, None, 'CONFLICT'
    series = families[0][1] if families else None
    if explicit:
        return explicit, series, 'SUPPLIED_LABEL_UNVERIFIED'
    if inferred:
        return next(iter(inferred)), series, 'FILENAME_LABEL_UNVERIFIED'
    return None, None, 'UNKNOWN'


def normalize_quantity(text: str) -> NormalizedQuantity | None:
    text = unicodedata.normalize('NFKC', text).strip().replace('−', '-')
    match = re.fullmatch(r'([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+|(?i:nan|inf|infinity)))\s*(°[CF]|[mk]?A|k?V|k?W|%)', text)
    if not match:
        return None
    number, unit = match.groups()
    if re.fullmatch(r'[+-]?\d{1,3},\d{3}', number):
        return None
    value = float(number.replace(',', '.'))
    if not math.isfinite(value):
        raise ValueError('Nonfinite quantity')
    if unit == '°F':
        value, unit = (value - 32) * 5 / 9, '°C'
    if unit == '°C':
        if value < -273.15:
            raise ValueError('Temperature below absolute zero')
    elif value < 0:
        raise ValueError('Negative electrical quantity')
    multipliers = {'mA': (.001, 'A'), 'kA': (1000, 'A'), 'kV': (1000, 'V'),
                   'kW': (1000, 'W'), '%': (.01, '1')}
    if unit in multipliers:
        multiplier, unit = multipliers[unit]
        value *= multiplier
    return NormalizedQuantity(value=value, unit=unit)


def normalize_table(record: ExtractedTable, original_type: str) -> ReferenceTable:
    issues = []
    headers = [normalize_header(header) for header in record.headers]
    rows, quantities = [], []
    if len(headers) != len(set(headers)):
        issues.append('DUPLICATE_HEADERS')
    if not record.filename.strip():
        issues.append('SOURCE_FILENAME_EMPTY')
    for index, row in enumerate(record.rows):
        keys = [normalize_header(key) for key in row]
        if len(keys) != len(set(keys)):
            issues.append('HEADER_COLLISION')
            rows.append(dict(row))
        else:
            rows.append(dict(zip(keys, row.values())))
        for key, value in row.items():
            try:
                quantity = normalize_quantity(value)
            except ValueError:
                issues.append('INVALID_QUANTITY')
                continue
            if quantity is not None:
                quantities.append({'row': index, 'column': normalize_header(key), **quantity.model_dump()})
    if not any(value.strip() for row in rows for value in row.values()):
        issues.append('EMPTY_TABLE')
    manufacturer, series, basis = detect_manufacturer(record.filename, record.brand)
    if basis == 'CONFLICT':
        issues.append('MANUFACTURER_CONFLICT')
    elif manufacturer is None:
        issues.append('MANUFACTURER_UNKNOWN')
    label_text = ' '.join(headers + [key for row in rows[:3] for key in row]
                          + [value for row in rows[:3] for value in row.values()]).casefold()
    detected = {kind for kind, pattern in _TYPE_SIGNALS.items() if re.search(pattern, label_text)}
    table_type = original_type
    if original_type not in detected:
        if len(detected) == 1:
            table_type = detected.pop()
            issues.append('CATEGORY_RECLASSIFIED')
        else:
            issues.append('CATEGORY_UNCONFIRMED')
    if re.match(r'^(?:IEC|VDE|DIN|PD IEC)\b', record.filename, re.IGNORECASE):
        table_type = 'STANDARD_REFERENCE'
        issues.append('STANDARD_REFERENCE_ONLY')
    if re.search(r's7[-_ ]?1200|simatic', record.filename, re.IGNORECASE) and re.search(
            r'parameter|data type|modbus|\bregister\b|\binstruction\b', label_text):
        issues.append('PLC_CONFIGURATION')
    blocking = set(issues) - {'CATEGORY_RECLASSIFIED'}
    identity = [canonical_source_file(record.filename), record.page, record.headers, record.rows]
    return ReferenceTable(table_id=content_hash(identity), source_file=record.filename, source_page=record.page,
                          table_type=table_type, manufacturer=manufacturer, manufacturer_basis=basis, series=series,
                          headers=headers, rows=rows, quantities=quantities,
                          review_state='QUARANTINED' if blocking else 'PENDING_REVIEW', issues=sorted(set(issues)))
