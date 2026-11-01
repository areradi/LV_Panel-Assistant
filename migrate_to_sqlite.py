# -*- coding: utf-8 -*-
"""
اسکریپت ایجاد دیتابیس SQLite و مهاجرت خودکار فایل‌های JSON کاتالوگ و قوانین مهندسی.
پوشش یافته‌های ممیزی: F-001, F-003, F-005, F-006, F-007, F-008, F-016, F-017
تک‌پایپلاینی (TECH-02): توسعه‌های داده فاز ۵/۶/۷ از پوشه scripts/ به صورت
خودکار و Idempotent پیش از ساخت دیتابیس اجرا می‌شوند.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = (
    BASE_DIR / "lv_assist" / "data"
    if (BASE_DIR / "lv_assist" / "data").exists()
    else BASE_DIR / "data"
)
DEFAULT_DB_PATH = DATA_DIR / "lv_assist.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ۱. جدول رجیستری استانداردها (رفع F-008 و F-012)
CREATE TABLE IF NOT EXISTS standards_registry (
    standard_id TEXT PRIMARY KEY,
    standard_code TEXT NOT NULL,
    edition TEXT,
    title TEXT,
    category TEXT,
    scope_notes TEXT,
    max_phase_current_a REAL,
    raw_json TEXT NOT NULL
);

-- ۲. جدول منابع دیتاشیت و وضعیت اعتبار داده (رفع F-016)
CREATE TABLE IF NOT EXISTS datasheet_sources (
    source_id TEXT PRIMARY KEY,
    manufacturer TEXT NOT NULL,
    document_ref TEXT NOT NULL,
    revision TEXT,
    data_quality TEXT NOT NULL CHECK (
        data_quality IN ('REAL_VERIFIED', 'ESTIMATED', 'UNVERIFIED')
    )
);

-- ۳. جدول اصلی تجهیزات کاتالوگ (رفع F-002, F-004, F-007, F-016)
CREATE TABLE IF NOT EXISTS catalog_devices (
    device_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    series TEXT NOT NULL,
    model TEXT NOT NULL,
    in_a REAL,
    poles INTEGER,
    icu_ka_400v REAL,
    power_loss_w REAL NOT NULL DEFAULT 0.0,
    derating_40c REAL NOT NULL DEFAULT 1.0,
    derating_50c REAL NOT NULL DEFAULT 1.0,
    ip_rating TEXT,
    ip_numeric INTEGER,
    airflow_m3h REAL,
    kvar_rating REAL,
    width_mm REAL,
    height_mm REAL,
    depth_mm REAL,
    data_quality TEXT NOT NULL CHECK (
        data_quality IN ('REAL_VERIFIED', 'ESTIMATED', 'UNVERIFIED')
    ),
    source_id TEXT REFERENCES datasheet_sources(source_id),
    raw_json TEXT NOT NULL
);

-- ۴. جدول قدرت قطع تجهیزات بر حسب ولتاژ (رفع F-006)
CREATE TABLE IF NOT EXISTS device_breaking_capacities (
    device_id TEXT NOT NULL REFERENCES catalog_devices(device_id) ON DELETE CASCADE,
    voltage_v REAL NOT NULL CHECK (voltage_v > 0),
    icu_ka REAL NOT NULL CHECK (icu_ka > 0),
    ics_ka REAL,
    PRIMARY KEY (device_id, voltage_v)
);

-- ۵. جدول کاهش ظرفیت دمایی تجهیزات بر حسب دما (رفع F-017)
CREATE TABLE IF NOT EXISTS device_thermal_derating (
    device_id TEXT NOT NULL REFERENCES catalog_devices(device_id) ON DELETE CASCADE,
    temp_c REAL NOT NULL CHECK (temp_c BETWEEN 20 AND 80),
    derating_factor REAL NOT NULL CHECK (derating_factor > 0 AND derating_factor <= 1.2),
    PRIMARY KEY (device_id, temp_c)
);

-- ۶. جدول قواعد سلکتیویته تأییدشده سازنده (رفع F-003)
CREATE TABLE IF NOT EXISTS selectivity_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    upstream_series TEXT NOT NULL,
    downstream_series TEXT NOT NULL,
    upstream_in_min_a REAL,
    upstream_in_max_a REAL,
    downstream_in_max_a REAL,
    min_ratio REAL,
    limit_ka REAL,
    selectivity_type TEXT NOT NULL CHECK (
        selectivity_type IN ('VERIFIED_TOTAL', 'VERIFIED_PARTIAL', 'TOTAL', 'PARTIAL')
    ),
    voltage_v REAL NOT NULL DEFAULT 400.0,
    is_verified_manufacturer_rule INTEGER NOT NULL DEFAULT 1 CHECK (is_verified_manufacturer_rule IN (0, 1)),
    raw_json TEXT NOT NULL
);

-- ۷. جدول منحنی‌های قطع تقریبی - صرفاً برای ترسیم TCC و بررسی مقدماتی (رفع F-003)
CREATE TABLE IF NOT EXISTS trip_curves (
    curve_id TEXT PRIMARY KEY,
    curve_name TEXT NOT NULL,
    device_category TEXT,
    inst_min_mult REAL,
    inst_max_mult REAL,
    is_approximate INTEGER NOT NULL DEFAULT 1 CHECK (is_approximate = 1),
    allow_for_verification INTEGER NOT NULL DEFAULT 0 CHECK (allow_for_verification = 0),
    raw_json TEXT NOT NULL
);

-- ۸. جدول مرجع جریان‌دهی پایه کابل‌ها با قابلیت ردیابی استاندارد (رفع F-001 و F-008)
CREATE TABLE IF NOT EXISTS cable_ampacity_reference (
    standard_id TEXT NOT NULL REFERENCES standards_registry(standard_id),
    table_ref TEXT NOT NULL,
    material TEXT NOT NULL CHECK (material IN ('CU', 'AL')),
    insulation TEXT NOT NULL CHECK (insulation IN ('PVC', 'XLPE')),
    installation_method TEXT NOT NULL,
    loaded_conductors INTEGER NOT NULL DEFAULT 3,
    section_mm2 REAL NOT NULL CHECK (section_mm2 > 0),
    iz0_a REAL NOT NULL CHECK (iz0_a > 0),
    r_ohm_per_km REAL,
    x_ohm_per_km REAL,
    PRIMARY KEY (material, insulation, installation_method, loaded_conductors, section_mm2)
);

-- ۹. جدول مقاطع استاندارد هادی حفاظتی PE بدون سقف مصنوعی ۱۲۰ میلی‌متر مربع (رفع F-005)
CREATE TABLE IF NOT EXISTS pe_standard_sections (
    section_mm2 REAL PRIMARY KEY CHECK (section_mm2 > 0)
);

CREATE INDEX IF NOT EXISTS idx_devices_category ON catalog_devices(category);
CREATE INDEX IF NOT EXISTS idx_devices_series ON catalog_devices(series);
CREATE INDEX IF NOT EXISTS idx_selectivity_pair ON selectivity_rules(upstream_series, downstream_series);
"""

# داده‌های مرجع پایه کابل بر اساس IEC 60364-5-52 (روش مرجع C، ۳ هادی باردار مس، PVC در ۳۰ درجه - جدول B.52.3)
REFERENCE_CABLE_IZ0_3PH_CU_PVC_METHOD_C: dict[float, tuple[float, float, float]] = {
    1.5: (17.5, 12.1, 0.08),
    2.5: (24.0, 7.41, 0.08),
    4.0: (32.0, 4.61, 0.08),
    6.0: (41.0, 3.08, 0.08),
    10.0: (57.0, 1.83, 0.08),
    16.0: (76.0, 1.15, 0.08),
    25.0: (96.0, 0.727, 0.08),
    35.0: (119.0, 0.524, 0.08),
    50.0: (144.0, 0.387, 0.08),
    70.0: (184.0, 0.268, 0.08),
    95.0: (223.0, 0.193, 0.08),
    120.0: (259.0, 0.153, 0.08),
    150.0: (299.0, 0.124, 0.08),
    185.0: (341.0, 0.0991, 0.08),
    240.0: (403.0, 0.0754, 0.08),
    300.0: (464.0, 0.0601, 0.08),
}

STANDARD_PE_SECTIONS_MM2: list[float] = [
    1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0, 35.0,
    50.0, 70.0, 95.0, 120.0, 150.0, 185.0, 240.0, 300.0, 400.0
]


def _compute_file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_ip_numeric(ip_str: str | None) -> int | None:
    """استخراج عدد دو رقمی IP (مثلاً 'IP54' -> 54) برای مقایسه شرطی."""
    if not ip_str:
        return None
    digits = "".join(ch for ch in str(ip_str) if ch.isdigit())
    return int(digits[:2]) if len(digits) >= 2 else None


def _load_json_safe(path: Path) -> Any:
    if not path.exists():
        logger.warning("فایل داده یافت نشد: %s", path)
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


PHASE_EXTENSION_SCRIPTS = (
    "extend_catalog_phase5",
    "extend_catalog_phase6",
    "extend_catalog_phase7",
    "extend_catalog_phase13",
)


def _run_phase_extensions() -> None:
    """اجرای Idempotent توسعه‌های داده فاز ۵/۶/۷ پیش از محاسبه هش و مهاجرت (TECH-02)."""
    scripts_dir = BASE_DIR / "scripts"
    if not scripts_dir.is_dir():
        return
    sys.path.insert(0, str(scripts_dir))
    try:
        for name in PHASE_EXTENSION_SCRIPTS:
            script_path = scripts_dir / f"{name}.py"
            spec = importlib.util.spec_from_file_location(name, script_path)
            if spec is None or spec.loader is None:
                logger.warning("اسکریپت توسعه داده اجرا نشد: %s", script_path)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if callable(getattr(module, "main", None)):
                module.main()
    finally:
        sys.path.remove(str(scripts_dir))


def migrate_standards(conn: sqlite3.Connection, data_dir: Path) -> None:
    std_path = data_dir / "standards_registry.json"
    raw_data = _load_json_safe(std_path)

    records: list[dict[str, Any]] = []
    if isinstance(raw_data, list):
        records = raw_data
    elif isinstance(raw_data, dict):
        if "standards" in raw_data and isinstance(raw_data["standards"], list):
            records = raw_data["standards"]
        else:
            for k, v in raw_data.items():
                if isinstance(v, dict):
                    item = dict(v)
                    item.setdefault("id", k)
                    records.append(item)

    for idx, item in enumerate(records, start=1):
        std_id = str(item.get("id") or item.get("code") or item.get("standard") or f"STD-{idx:03d}")
        std_code = str(item.get("code") or item.get("standard") or std_id)
        edition = str(item.get("edition") or item.get("year") or "")
        title = str(item.get("title") or item.get("name") or item.get("description") or "")
        category = str(item.get("category") or item.get("domain") or "GENERAL")
        scope_notes = str(item.get("scope") or item.get("notes") or "")

        # اعمال محدودیت دامنه جریان برای استانداردهای هارمونیک (رفع F-012)
        max_curr = item.get("max_phase_current_a")
        if "61000-3-2" in std_code and max_curr is None:
            max_curr = 16.0
            scope_notes = (scope_notes + " | محدود به تجهیزات با جریان ورودی <= 16A در هر فاز").strip(" |")
        elif "61000-3-12" in std_code and max_curr is None:
            max_curr = 75.0

        conn.execute(
            """
            INSERT OR REPLACE INTO standards_registry
            (standard_id, standard_code, edition, title, category, scope_notes, max_phase_current_a, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (std_id, std_code, edition, title, category, scope_notes, max_curr, json.dumps(item, ensure_ascii=False)),
        )

    # اطمینان از وجود استاندارد مرجع کابل IEC 60364-5-52
    conn.execute(
        """
        INSERT OR IGNORE INTO standards_registry
        (standard_id, standard_code, edition, title, category, scope_notes, max_phase_current_a, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "IEC-60364-5-52",
            "IEC 60364-5-52",
            "2009",
            "Selection and erection of electrical equipment - Wiring systems",
            "CABLE_SIZING",
            "Reference ampacity tables for LV cables",
            None,
            json.dumps({"code": "IEC 60364-5-52", "edition": "2009"}),
        ),
    )


def migrate_catalog_devices(conn: sqlite3.Connection, data_dir: Path) -> None:
    dev_path = data_dir / "catalog_devices.json"
    raw_data = _load_json_safe(dev_path)
    if not raw_data:
        return

    devices: list[dict[str, Any]] = []
    if isinstance(raw_data, list):
        devices = raw_data
    elif isinstance(raw_data, dict):
        if "devices" in raw_data and isinstance(raw_data["devices"], list):
            devices = raw_data["devices"]
        else:
            for k, v in raw_data.items():
                if isinstance(v, list):
                    for entry in v:
                        if isinstance(entry, dict):
                            entry_copy = dict(entry)
                            entry_copy.setdefault("category", k)
                            devices.append(entry_copy)

    # ثبت منابع پایه دیتاشیت (رفع F-016)
    conn.execute(
        """
        INSERT OR REPLACE INTO datasheet_sources
        (source_id, manufacturer, document_ref, revision, data_quality)
        VALUES
        ('SRC-VERIFIED-CAT', 'Manufacturer Official Catalog', 'Verified Entry', '2025/2026', 'REAL_VERIFIED'),
        ('SRC-UNSPECIFIED-JSON', 'Legacy JSON Import (No Datasheet Ref)', 'Unspecified', 'N/A', 'ESTIMATED')
        """
    )

    for idx, dev in enumerate(devices, start=1):
        dev_copy = dict(dev)
        dev_id = str(
            dev_copy.get("id")
            or dev_copy.get("device_id")
            or dev_copy.get("part_number")
            or dev_copy.get("model")
            or f"DEV-{idx:04d}"
        )
        category = str(dev_copy.get("category") or dev_copy.get("device_type") or dev_copy.get("type") or "UNKNOWN")
        manufacturer = str(dev_copy.get("manufacturer") or dev_copy.get("brand") or "Generic")
        series = str(dev_copy.get("series") or dev_copy.get("family") or "Generic")
        model = str(dev_copy.get("model") or dev_copy.get("part_number") or dev_id)

        # رفع F-016: اگر فیلد data_quality به صورت صریح در JSON نبوده، نباید REAL_VERIFIED فرض شود
        explicit_quality = dev_copy.get("data_quality")
        if explicit_quality in ("REAL_VERIFIED", "ESTIMATED", "UNVERIFIED"):
            data_quality = explicit_quality
            source_id = "SRC-VERIFIED-CAT" if data_quality == "REAL_VERIFIED" else "SRC-UNSPECIFIED-JSON"
        else:
            data_quality = "ESTIMATED"
            source_id = "SRC-UNSPECIFIED-JSON"
            dev_copy["data_quality"] = data_quality

        in_a = dev_copy.get("rated_current_in_a") or dev_copy.get("in_a")
        poles = dev_copy.get("poles")
        icu_400 = dev_copy.get("icu_ka_400v") or dev_copy.get("icu_ka")
        power_loss_w = float(dev_copy.get("power_loss_w") or dev_copy.get("loss_w") or 0.0)
        derating_40c = float(dev_copy.get("derating_40c") or 1.0)
        derating_50c = float(dev_copy.get("derating_50c") or 1.0)
        ip_rating = dev_copy.get("ip_rating")
        ip_num = _parse_ip_numeric(ip_rating)
        airflow_m3h = dev_copy.get("airflow_m3h")
        kvar_rating = dev_copy.get("kvar_rating") or dev_copy.get("cap_kvar_400v") or dev_copy.get("kvar")
        width_mm = dev_copy.get("width_mm")
        height_mm = dev_copy.get("height_mm")
        depth_mm = dev_copy.get("depth_mm")

        conn.execute(
            """
            INSERT OR REPLACE INTO catalog_devices (
                device_id, category, manufacturer, series, model,
                in_a, poles, icu_ka_400v, power_loss_w,
                derating_40c, derating_50c, ip_rating, ip_numeric,
                airflow_m3h, kvar_rating, width_mm, height_mm, depth_mm,
                data_quality, source_id, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dev_id, category, manufacturer, series, model,
                in_a, poles, icu_400, power_loss_w,
                derating_40c, derating_50c, ip_rating, ip_num,
                airflow_m3h, kvar_rating, width_mm, height_mm, depth_mm,
                data_quality, source_id, json.dumps(dev_copy, ensure_ascii=False),
            ),
        )

        # پر کردن جدول قدرت قطع بر حسب ولتاژ (رفع F-006)
        if icu_400 is not None and float(icu_400) > 0:
            ics_400 = dev_copy.get("ics_ka_400v") or float(icu_400)
            for v_level in (400.0, 415.0):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO device_breaking_capacities
                    (device_id, voltage_v, icu_ka, ics_ka)
                    VALUES (?, ?, ?, ?)
                    """,
                    (dev_id, v_level, float(icu_400), float(ics_400)),
                )
        if isinstance(dev_copy.get("icu_by_voltage"), dict):
            for v_str, icu_val in dev_copy["icu_by_voltage"].items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO device_breaking_capacities
                    (device_id, voltage_v, icu_ka, ics_ka)
                    VALUES (?, ?, ?, ?)
                    """,
                    (dev_id, float(v_str), float(icu_val), float(icu_val)),
                )

        # پر کردن جدول کاهش ظرفیت دمایی تا ۵۰ درجه (و دماهای بالاتر فقط در صورت وجود در دیتاشیت - رفع F-017)
        conn.execute(
            "INSERT OR REPLACE INTO device_thermal_derating VALUES (?, 40.0, ?)",
            (dev_id, derating_40c),
        )
        conn.execute(
            "INSERT OR REPLACE INTO device_thermal_derating VALUES (?, 50.0, ?)",
            (dev_id, derating_50c),
        )
        if dev_copy.get("derating_60c") is not None:
            conn.execute(
                "INSERT OR REPLACE INTO device_thermal_derating VALUES (?, 60.0, ?)",
                (dev_id, float(dev_copy["derating_60c"])),
            )


def migrate_selectivity_and_curves(conn: sqlite3.Connection, data_dir: Path) -> None:
    # ۱. مهاجرت قواعد سلکتیویته رسمی (selectivity_rules.json)
    sel_path = data_dir / "selectivity_rules.json"
    sel_data = _load_json_safe(sel_path)
    rules: list[dict[str, Any]] = []
    if isinstance(sel_data, list):
        rules = sel_data
    elif isinstance(sel_data, dict):
        rules = sel_data.get("rules") or sel_data.get("selectivity_rules") or []

    conn.execute("DELETE FROM selectivity_rules")
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        up_series = str(rule.get("upstream_series") or rule.get("upstream") or "")
        dn_series = str(rule.get("downstream_series") or rule.get("downstream") or "")
        up_min = rule.get("upstream_min_in_a")
        up_max = rule.get("upstream_max_in_a")
        dn_max = rule.get("downstream_max_in_a")
        min_ratio = rule.get("min_ratio")
        limit_ka = rule.get("selectivity_limit_is_ka")
        sel_type = str(
            rule.get("selectivity_type")
            or ("VERIFIED_TOTAL" if bool(rule.get("is_total_up_to_icu", False)) else "VERIFIED_PARTIAL")
        )
        if sel_type not in ("VERIFIED_TOTAL", "VERIFIED_PARTIAL", "TOTAL", "PARTIAL"):
            sel_type = "VERIFIED_PARTIAL"

        conn.execute(
            """
            INSERT INTO selectivity_rules (
                upstream_series, downstream_series,
                upstream_in_min_a, upstream_in_max_a, downstream_in_max_a,
                min_ratio, limit_ka, selectivity_type, voltage_v,
                is_verified_manufacturer_rule, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 400.0, 1, ?)
            """,
            (
                up_series, dn_series, up_min, up_max, dn_max,
                min_ratio, limit_ka, sel_type, json.dumps(rule, ensure_ascii=False),
            ),
        )

    # ۲. مهاجرت منحنی‌های قطع تقریبی (trip_curves.json) با پرچم عدم مجوز تأیید نهایی (رفع F-003)
    curves_path = data_dir / "trip_curves.json"
    curves_data = _load_json_safe(curves_path)
    if isinstance(curves_data, dict):
        items = curves_data.get("curves", curves_data)
        if isinstance(items, dict):
            for c_key, c_val in items.items():
                if not isinstance(c_val, dict):
                    continue
                inst_min = c_val.get("im_min_mult") or c_val.get("inst_min_mult") or c_val.get("i_inst_min")
                inst_max = c_val.get("im_max_mult") or c_val.get("inst_max_mult") or c_val.get("i_inst_max")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trip_curves (
                        curve_id, curve_name, device_category,
                        inst_min_mult, inst_max_mult,
                        is_approximate, allow_for_verification, raw_json
                    ) VALUES (?, ?, ?, ?, ?, 1, 0, ?)
                    """,
                    (
                        str(c_key),
                        str(c_val.get("name") or c_key),
                        str(c_val.get("category") or "GENERIC"),
                        inst_min,
                        inst_max,
                        json.dumps(c_val, ensure_ascii=False),
                    ),
                )
        elif isinstance(items, list):
            for idx, c_val in enumerate(items, start=1):
                if not isinstance(c_val, dict):
                    continue
                c_key = str(c_val.get("id") or c_val.get("curve") or c_val.get("type") or f"CURVE-{idx}")
                inst_min = c_val.get("im_min_mult") or c_val.get("inst_min_mult")
                inst_max = c_val.get("im_max_mult") or c_val.get("inst_max_mult")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trip_curves (
                        curve_id, curve_name, device_category,
                        inst_min_mult, inst_max_mult,
                        is_approximate, allow_for_verification, raw_json
                    ) VALUES (?, ?, ?, ?, ?, 1, 0, ?)
                    """,
                    (
                        c_key,
                        str(c_val.get("name") or c_key),
                        str(c_val.get("category") or "GENERIC"),
                        inst_min,
                        inst_max,
                        json.dumps(c_val, ensure_ascii=False),
                    ),
                )


def seed_reference_engineering_tables(conn: sqlite3.Connection) -> None:
    """ثبت جداول جریان‌دهی پایه کابل (F-001/F-008) و مقاطع استاندارد PE (F-005)."""
    for section_mm2, (iz0_a, r_ohm, x_ohm) in REFERENCE_CABLE_IZ0_3PH_CU_PVC_METHOD_C.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO cable_ampacity_reference (
                standard_id, table_ref, material, insulation,
                installation_method, loaded_conductors,
                section_mm2, iz0_a, r_ohm_per_km, x_ohm_per_km
            ) VALUES ('IEC-60364-5-52', 'Table B.52.3 (Ref Method C)', 'CU', 'PVC', 'C', 3, ?, ?, ?, ?)
            """,
            (section_mm2, iz0_a, r_ohm, x_ohm),
        )

    for pe_size in STANDARD_PE_SECTIONS_MM2:
        conn.execute(
            "INSERT OR REPLACE INTO pe_standard_sections (section_mm2) VALUES (?)",
            (pe_size,),
        )


def build_or_migrate_database(
    db_path: Path = DEFAULT_DB_PATH,
    data_dir: Path = DATA_DIR,
    force: bool = False,
) -> Path:
    """ساخت دیتابیس SQLite و مهاجرت خودکار در صورت نبود فایل یا تغییر هش فایل‌های JSON."""
    _run_phase_extensions()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    json_files = [
        data_dir / "catalog_devices.json",
        data_dir / "selectivity_rules.json",
        data_dir / "standards_registry.json",
        data_dir / "trip_curves.json",
    ]
    combined_hash = hashlib.sha256(
        "|".join(_compute_file_sha256(p) for p in json_files).encode("utf-8")
    ).hexdigest()

    if db_path.exists() and not force:
        try:
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM metadata_info WHERE key = 'source_json_hash'"
                ).fetchone()
                if row and row[0] == combined_hash:
                    return db_path
        except sqlite3.Error:
            logger.info("بازسازی دیتابیس به دلیل تغییر ساختار...")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        migrate_standards(conn, data_dir)
        migrate_catalog_devices(conn, data_dir)
        migrate_selectivity_and_curves(conn, data_dir)
        seed_reference_engineering_tables(conn)

        conn.execute(
            "INSERT OR REPLACE INTO metadata_info (key, value) VALUES ('source_json_hash', ?)",
            (combined_hash,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata_info (key, value) VALUES ('migrated_at_utc', ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()

    logger.info("دیتابیس SQLite با موفقیت در مسیر %s ساخته و همگام‌سازی شد.", db_path)
    return db_path


if __name__ == "__main__":
    build_or_migrate_database(force=True)