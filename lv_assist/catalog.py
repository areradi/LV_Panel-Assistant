# -*- coding: utf-8 -*-
"""
مدیریت کاتالوگ تجهیزات، قواعد سلکتیویته، منحنی‌های قطع و جداول استاندارد مبتنی بر SQLite.
رفع یافته‌های ممیزی: F-001, F-003, F-005, F-006, F-007, F-008, F-016, F-017.
منبع حقیقت: lv_assist/data/lv_assist.db که توسط migrate_to_sqlite.py از فایل‌های JSON ساخته می‌شود.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from lv_assist.models import CatalogDevice, SelectivityRuleRecord, SelectivityEvalState, DataQuality
from lv_assist.i18n import tr, i18n
from lv_assist import paths

DATA_DIR = paths.get_data_dir()
DB_PATH = DATA_DIR / "lv_assist.db"


USER_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS device_prices (
    device_id TEXT PRIMARY KEY REFERENCES catalog_devices(device_id) ON DELETE CASCADE,
    unit_price REAL CHECK (unit_price IS NULL OR unit_price >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR',
    price_source TEXT NOT NULL DEFAULT 'MANUAL',
    updated_at TEXT
);
"""


def _ensure_user_tables(db_path: Path) -> None:
    """مهاجرت سبک و Idempotent: جدول قیمت‌ها + ستون is_user_entry برای ردیف‌های کاربر."""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.executescript(USER_TABLES_SQL)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(catalog_devices)").fetchall()]
            if "is_user_entry" not in cols:
                conn.execute("ALTER TABLE catalog_devices ADD COLUMN is_user_entry INTEGER NOT NULL DEFAULT 0")
            conn.commit()
    except sqlite3.Error:
        pass


def _backup_user_data(db_path: Path):
    """پشتیبان‌گیری ردیف‌های واردشده توسط کاربر و قیمت‌ها قبل از بازسازی از JSON."""
    user_rows, price_rows = [], []
    if not db_path.exists():
        return user_rows, price_rows
    try:
        with sqlite3.connect(db_path) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(catalog_devices)").fetchall()]
            if "is_user_entry" in cols:
                user_rows = conn.execute(
                    "SELECT raw_json, data_quality FROM catalog_devices WHERE is_user_entry = 1"
                ).fetchall()
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "device_prices" in tables:
                price_rows = conn.execute(
                    "SELECT device_id, unit_price, currency, price_source FROM device_prices"
                ).fetchall()
    except sqlite3.Error:
        pass
    return user_rows, price_rows


def _restore_user_data(db_path: Path, user_rows, price_rows) -> None:
    """بازگردانی ردیف‌های کاربر و قیمت‌ها پس از بازسازی دیتابیس از JSON."""
    if not user_rows and not price_rows:
        return
    try:
        with sqlite3.connect(db_path) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(catalog_devices)").fetchall()]
            for raw_json, quality in user_rows:
                try:
                    payload = json.loads(raw_json)
                except (TypeError, ValueError):
                    continue
                device_id = payload.get("part_number")
                if not device_id:
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM catalog_devices WHERE device_id = ?", (device_id,)).fetchone()
                if exists:
                    continue
                if "is_user_entry" not in cols:
                    conn.execute(
                        "ALTER TABLE catalog_devices ADD COLUMN is_user_entry INTEGER NOT NULL DEFAULT 0")
                    cols.append("is_user_entry")
                conn.execute(
                    "INSERT INTO catalog_devices (device_id, category, manufacturer, series, model,"
                    " data_quality, raw_json, is_user_entry) VALUES (?,?,?,?,?,?,?,1)",
                    (device_id, payload.get("device_type", "DEVICE"), payload.get("manufacturer", "?"),
                     payload.get("series", ""), device_id, quality or "ESTIMATED", raw_json))
            conn.executescript(USER_TABLES_SQL)
            for device_id, price, currency, source in price_rows:
                conn.execute(
                    "INSERT OR REPLACE INTO device_prices (device_id, unit_price, currency, price_source, updated_at)"
                    " VALUES (?,?,?,?,datetime('now'))",
                    (device_id, price, currency or "EUR", source or "MANUAL"))
            conn.commit()
    except sqlite3.Error:
        pass


def _ensure_database(db_path: Optional[Path] = None) -> Path:
    """ساخت خودکار دیتابیس SQLite و اجرای مهاجرت در اولین بارگذاری.

    حفاظت داده کاربر: اگر بازسازی از JSON لازم شود، ابتدا ردیف‌های کاربر
    (is_user_entry=1) و قیمت‌ها پشتیبان‌گیری و پس از بازسازی بازگردانی می‌شوند.
    """
    db_path = DB_PATH if db_path is None else Path(db_path)
    if not db_path.exists():
        try:
            from migrate_to_sqlite import build_or_migrate_database
        except ImportError:
            import sys
            root_dir = Path(__file__).resolve().parent.parent
            if str(root_dir) not in sys.path:
                sys.path.insert(0, str(root_dir))
            from migrate_to_sqlite import build_or_migrate_database
        user_rows, price_rows = _backup_user_data(db_path)
        build_or_migrate_database(db_path=db_path, data_dir=DATA_DIR)
        _ensure_user_tables(db_path)
        from lv_assist.migrations import run_migrations
        run_migrations(db_path)
        _restore_user_data(db_path, user_rows, price_rows)
    else:
        from lv_assist.migrations import run_migrations
        run_migrations(db_path)
        _ensure_user_tables(db_path)
    return db_path


class CatalogRepository:
    """مخزن داده‌های مهندسی و کاتالوگ تجهیزات مبتنی بر SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = _ensure_database(db_path)
        self._devices_cache: Optional[List[CatalogDevice]] = None
        self._rules_cache: Optional[List[SelectivityRuleRecord]] = None
        self._curves_cache: Optional[Dict[str, dict]] = None
        self._standards_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._iz0_cache: Optional[Dict[float, float]] = None
        self._pe_cache: Optional[List[float]] = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # ۱. تجهیزات کاتالوگ با اعمال صریح کیفیت داده (رفع F-016)
    # ------------------------------------------------------------------
    def load_devices(self) -> List[CatalogDevice]:
        result: List[CatalogDevice] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT raw_json, data_quality FROM catalog_devices").fetchall()
            for row in rows:
                payload = json.loads(row["raw_json"])
                db_quality = row["data_quality"]
                if db_quality in DataQuality.__members__:
                    payload["data_quality"] = DataQuality[db_quality]
                else:
                    payload["data_quality"] = db_quality
                result.append(CatalogDevice(**payload))
        return result

    @property
    def devices(self) -> List[CatalogDevice]:
        if self._devices_cache is None:
            self._devices_cache = self.load_devices()
        return self._devices_cache

    # ------------------------------------------------------------------
    # ۲. قدرت قطع وابسته به ولتاژ پروژه (رفع F-006)
    # ------------------------------------------------------------------
    def get_device_icu_at_voltage(
        self,
        device_id: str,
        nominal_voltage_v: float,
        tolerance_v: float = 20.0,
    ) -> Optional[float]:
        """بازیابی Icu متناسب با ولتاژ نامی؛ در نبود داده دیتاشیت برای آن ولتاژ، None برمی‌گردد."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT icu_ka FROM device_breaking_capacities
                WHERE device_id = ? AND ABS(voltage_v - ?) <= ?
                ORDER BY ABS(voltage_v - ?) ASC
                LIMIT 1
                """,
                (device_id, nominal_voltage_v, tolerance_v, nominal_voltage_v),
            ).fetchone()
            return float(row["icu_ka"]) if row else None

    # ------------------------------------------------------------------
    # ۳. ضریب کاهش ظرفیت دمایی با کنترل سقف دما (رفع F-017)
    # ------------------------------------------------------------------
    def get_device_derating_factor(self, device_id: str, internal_temp_c: float) -> Optional[float]:
        """ضریب derating از جدول دما؛ برای دماهای بالای ۵۰ درجه بدون داده معتبر، None برمی‌گردد."""
        if internal_temp_c <= 40.0:
            target_temp = 40.0
        elif internal_temp_c <= 50.0:
            target_temp = 50.0
        else:
            target_temp = internal_temp_c

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT derating_factor FROM device_thermal_derating
                WHERE device_id = ? AND temp_c >= ?
                ORDER BY temp_c ASC
                LIMIT 1
                """,
                (device_id, target_temp),
            ).fetchone()
            return float(row["derating_factor"]) if row else None

    # ------------------------------------------------------------------
    # ۴. بدنه تابلو با شرط IP هدف (رفع F-007)
    # ------------------------------------------------------------------
    def get_compatible_enclosures(self, target_ip: Optional[str] = None) -> List[CatalogDevice]:
        """بدنه‌هایی که درجه حفاظت IP هدف پروژه را تأمین می‌کنند."""
        enclosures = [d for d in self.devices if d.device_type == "ENCLOSURE"]
        if not target_ip:
            return enclosures

        required = re.match(r'IP([0-6])([0-9])', str(target_ip).strip().upper())
        if required is None:
            return []
        req_solid, req_water = map(int, required.groups())

        compatible = []
        for enc in enclosures:
            for solid, water in re.findall(r'IP([0-6])([0-9])', str(enc.ip_rating).upper()):
                solid, water = int(solid), int(water)
                # Immersion and jet-water ratings need separate evidence.
                water_ok = req_water == 0 or water == req_water or (water <= 6 and req_water <= 6 and water >= req_water)
                if solid >= req_solid and water_ok:
                    compatible.append(enc)
                    break
        return compatible

    # ------------------------------------------------------------------
    # ۵. جداول مرجع کابل و مقاطع استاندارد PE (رفع F-001, F-005, F-008)
    # ------------------------------------------------------------------
    def get_cable_iz0_table_cu_pvc_c(self, loaded_conductors: int = 3) -> Dict[float, float]:
        """جدول کامل جریان‌دهی پایه Cu/PVC/روش C از دیتابیس استاندارد."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT section_mm2, iz0_a FROM cable_ampacity_reference
                WHERE material = 'CU' AND insulation = 'PVC' AND installation_method = 'C'
                  AND loaded_conductors = ?
                """,
                (loaded_conductors,),
            ).fetchall()
            return {float(r["section_mm2"]): float(r["iz0_a"]) for r in rows}

    def get_base_cable_iz0(
        self,
        section_mm2: float,
        material: str = "CU",
        insulation: str = "PVC",
        installation_method: str = "C",
        loaded_conductors: int = 3,
    ) -> Optional[float]:
        """جریان‌دهی پایه یک مقطع خاص؛ برای مقطع غیراستاندارد None برمی‌گردد (هرگز مقدار ساختگی)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT iz0_a FROM cable_ampacity_reference
                WHERE section_mm2 = ?
                  AND UPPER(material) = UPPER(?)
                  AND UPPER(insulation) = UPPER(?)
                  AND UPPER(installation_method) = UPPER(?)
                  AND loaded_conductors = ?
                """,
                (section_mm2, material, insulation, installation_method, loaded_conductors),
            ).fetchone()
            if row:
                return float(row["iz0_a"])
            fallback_row = conn.execute(
                """
                SELECT iz0_a FROM cable_ampacity_reference
                WHERE section_mm2 = ? AND material = 'CU' AND insulation = 'PVC' AND installation_method = 'C'
                """,
                (section_mm2,),
            ).fetchone()
            return float(fallback_row["iz0_a"]) if fallback_row else None

    def get_pe_standard_sections(self) -> List[float]:
        """فهرست مقاطع استاندارد PE از دیتابیس (بدون سقف مصنوعی)."""
        if self._pe_cache is None:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT section_mm2 FROM pe_standard_sections ORDER BY section_mm2 ASC"
                ).fetchall()
                self._pe_cache = [float(r["section_mm2"]) for r in rows]
        return self._pe_cache

    def get_standard_pe_section(self, required_pe_mm2: float) -> Optional[float]:
        """اولین مقطع استاندارد PE بزرگ‌تر یا مساوی مقدار لازم؛ اگر فراتر از جدول باشد None."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT section_mm2 FROM pe_standard_sections
                WHERE section_mm2 >= ?
                ORDER BY section_mm2 ASC
                LIMIT 1
                """,
                (required_pe_mm2,),
            ).fetchone()
            return float(row["section_mm2"]) if row else None

    # ------------------------------------------------------------------
    # ۶. قواعد سلکتیویته، منحنی‌های قطع و رجیستری استانداردها
    # ------------------------------------------------------------------
    def load_selectivity_rules(self) -> List[SelectivityRuleRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT raw_json FROM selectivity_rules WHERE is_verified_manufacturer_rule = 1"
            ).fetchall()
            return [SelectivityRuleRecord(**json.loads(r["raw_json"])) for r in rows]

    @property
    def selectivity_rules(self) -> List[SelectivityRuleRecord]:
        if self._rules_cache is None:
            self._rules_cache = self.load_selectivity_rules()
        return self._rules_cache

    @property
    def trip_curves(self) -> Dict[str, dict]:
        if self._curves_cache is None:
            with self._connect() as conn:
                rows = conn.execute("SELECT curve_id, raw_json FROM trip_curves").fetchall()
                self._curves_cache = {r["curve_id"]: json.loads(r["raw_json"]) for r in rows}
        return self._curves_cache

    @property
    def standards(self) -> Dict[str, Dict[str, Any]]:
        if self._standards_cache is None:
            with self._connect() as conn:
                rows = conn.execute("SELECT standard_id, raw_json FROM standards_registry").fetchall()
                self._standards_cache = {r["standard_id"]: json.loads(r["raw_json"]) for r in rows}
        return self._standards_cache

    # ------------------------------------------------------------------
    # CRUD کاتالوگ و قیمت‌ها — پشتیبان تب «مدیریت کاتالوگ» و ورود از جستجوی وب
    # ------------------------------------------------------------------
    def reload(self) -> None:
        """خالی کردن همه کش‌ها پس از تغییر دیتابیس تا موتور انتخاب داده تازه بخواند."""
        self._devices_cache = None
        self._rules_cache = None
        self._curves_cache = None
        self._standards_cache = None
        self._iz0_cache = None
        self._pe_cache = None

    def _sync_singleton_if_same_db(self) -> None:
        """Invalidate the module repository cache when another instance writes its database."""
        import sys

        module = sys.modules[__name__]
        singleton = getattr(module, "catalog_repo", None)
        if singleton is None or singleton is self:
            return
        if str(singleton.db_path) == str(self.db_path):
            singleton.reload()

    @staticmethod
    def _device_row_values(device: CatalogDevice) -> tuple:
        return (
            device.part_number, device.device_type, device.manufacturer, device.series,
            device.part_number, device.rated_current_in_a or None,
            device.icu_ka_400v if device.icu_ka_400v is not None else None,
            device.power_loss_w, device.derating_40c, device.derating_50c,
            device.ip_rating or None,
        )

    def add_device(self, device: CatalogDevice, unit_price: Optional[float] = None,
                   currency: str = "EUR", price_source: str = "MANUAL") -> None:
        """افزودن تجهیز جدید به کاتالوگ SQLite (ردیف کاربر) + جداول وابسته Icu/derating."""
        payload = device.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO catalog_devices (
                    device_id, category, manufacturer, series, model,
                    in_a, icu_ka_400v, power_loss_w, derating_40c, derating_50c,
                    ip_rating, data_quality, source_id, raw_json, is_user_entry
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (*self._device_row_values(device), device.data_quality.value,
                 f"SRC-USER-{price_source}", json.dumps(payload, ensure_ascii=False)),
            )
            if device.icu_ka_400v is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO device_breaking_capacities (device_id, voltage_v, icu_ka, ics_ka)"
                    " VALUES (?,?,?,?)",
                    (device.part_number, 400.0, float(device.icu_ka_400v), device.ics_ka_400v))
            for temp, factor in ((40.0, device.derating_40c), (50.0, device.derating_50c)):
                conn.execute(
                    "INSERT OR REPLACE INTO device_thermal_derating (device_id, temp_c, derating_factor)"
                    " VALUES (?,?,?)", (device.part_number, temp, float(factor)))
            if unit_price is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO device_prices (device_id, unit_price, currency, price_source, updated_at)"
                    " VALUES (?,?,?,?,datetime('now'))",
                    (device.part_number, float(unit_price), currency, price_source))
            conn.commit()
        self.reload()
        self._sync_singleton_if_same_db()

    def update_device(self, device_id: str, device: CatalogDevice,
                      unit_price: Optional[float] = None, currency: Optional[str] = None) -> None:
        """ویرایش کامل یک تجهیز موجود (raw_json و ستون‌های تایپ‌شده همگام به‌روز می‌شوند)."""
        payload = device.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE catalog_devices SET device_id=?, category=?, manufacturer=?, series=?, model=?,
                    in_a=?, icu_ka_400v=?, power_loss_w=?, derating_40c=?, derating_50c=?,
                    ip_rating=?, data_quality=?, raw_json=?, is_user_entry=1
                WHERE device_id=?
                """,
                (*self._device_row_values(device), device.data_quality.value,
                 json.dumps(payload, ensure_ascii=False), device_id),
            )
            if device.icu_ka_400v is not None:
                conn.execute(
                    "DELETE FROM device_breaking_capacities WHERE device_id IN (?, ?)",
                    (device_id, device.part_number),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO device_breaking_capacities (device_id, voltage_v, icu_ka, ics_ka)"
                    " VALUES (?,?,?,?)",
                    (device.part_number, 400.0, float(device.icu_ka_400v), device.ics_ka_400v))
            for temp, factor in ((40.0, device.derating_40c), (50.0, device.derating_50c)):
                conn.execute(
                    "INSERT OR REPLACE INTO device_thermal_derating (device_id, temp_c, derating_factor)"
                    " VALUES (?,?,?)", (device.part_number, temp, float(factor)))
            if unit_price is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO device_prices (device_id, unit_price, currency, price_source, updated_at)"
                    " VALUES (?,?,COALESCE(?, 'EUR'),'MANUAL',datetime('now'))",
                    (device.part_number, float(unit_price), currency))
            conn.commit()
        self.reload()
        self._sync_singleton_if_same_db()

    def delete_device(self, device_id: str) -> bool:
        """حذف تجهیز از کاتالوگ (قیمت‌ها با FK CASCADE حذف می‌شوند)."""
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.execute("DELETE FROM catalog_devices WHERE device_id = ?", (device_id,))
            conn.execute("DELETE FROM device_prices WHERE device_id = ?", (device_id,))
            conn.commit()
        self.reload()
        self._sync_singleton_if_same_db()
        return cur.rowcount > 0

    def set_device_price(self, device_id: str, unit_price: Optional[float], currency: str = "EUR", source: str = "MANUAL") -> None:
        """ثبت/به‌روزرسانی قیمت واحد یک قطعه برای برآورد بهای BOM."""
        with self._connect() as conn:
            if unit_price is None:
                conn.execute("DELETE FROM device_prices WHERE device_id = ?", (device_id,))
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO device_prices (device_id, unit_price, currency, price_source, updated_at)"
                    " VALUES (?,?,?,?,datetime('now'))",
                    (device_id, float(unit_price), currency, source))
            conn.commit()

    def get_device_price(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT unit_price, currency, price_source FROM device_prices WHERE device_id = ?",
                (device_id,)).fetchone()
            if not row or row["unit_price"] is None:
                return None
            return {"unit_price": float(row["unit_price"]), "currency": row["currency"],
                    "source": row["price_source"]}

    def list_prices(self) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT device_id, unit_price, currency, price_source FROM device_prices"
                " WHERE unit_price IS NOT NULL").fetchall()
            return {r["device_id"]: {"unit_price": float(r["unit_price"]),
                                     "currency": r["currency"], "source": r["price_source"]}
                    for r in rows}

    def get_device_payload(self, device_id: str) -> Optional[CatalogDevice]:
        """بازیابی یک تجهیز به صورت مدل Pydantic برای ویرایش گرافیکی."""
        for dev in self.devices:
            if dev.part_number == device_id:
                return dev
        return None

    def is_user_entry(self, device_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_user_entry FROM catalog_devices WHERE device_id = ?", (device_id,)).fetchone()
            return bool(row and row["is_user_entry"])

    # ------------------------------------------------------------------
    # ۷. API سازگار با سایر ماژول‌ها (static)
    # ------------------------------------------------------------------
    @staticmethod
    def get_default_catalog() -> List[CatalogDevice]:
        return list(catalog_repo.devices)

    @staticmethod
    def get_selectivity_rules() -> List[SelectivityRuleRecord]:
        return list(catalog_repo.selectivity_rules)


# نمونه سراسری (Singleton) برای استفاده موتور و خروجی‌ها
catalog_repo = CatalogRepository()


class TripCurveRepository:
    """پارامترهای منحنی تریپ تیپیکال از دیتابیس (داده تقریبی سازنده، نه مدرک هماهنگی الزام‌آور).

    سری‌هایی که نقاط رسمی دیتاشیت دارند (curve_source=DATASHEET_POINTS) از
    درونیابی لگاریتمی نقاط t-I استفاده می‌کنند؛ بقیه سری‌ها با مدل پارامتری
    k / I^alpha تخمین زده می‌شوند. در هر دو حالت خروجی صرفاً تخمین مقدماتی است (F-003).
    """

    @staticmethod
    def get_curve(series: str) -> dict:
        curves = catalog_repo.trip_curves
        return curves.get(series, curves.get("DEFAULT", {}))

    @classmethod
    def datasheet_points(cls, series: str) -> Optional[List[tuple]]:
        c = cls.get_curve(series)
        pts = c.get("points")
        if not pts or len(pts) < 2:
            return None
        return sorted((float(m), float(t)) for m, t in pts)

    @classmethod
    def is_datasheet_points(cls, series: str) -> bool:
        return cls.get_curve(series).get("curve_source") == "DATASHEET_POINTS"

    @classmethod
    def datasheet_ref(cls, series: str) -> str:
        return str(cls.get_curve(series).get("datasheet_ref") or "")

    @staticmethod
    def _interp_log(pts: List[tuple], current_mult: float) -> float:
        if current_mult <= pts[0][0]:
            return pts[0][1]
        for (m1, t1), (m2, t2) in zip(pts, pts[1:]):
            if m1 <= current_mult <= m2:
                if m1 <= 0.0 or m2 <= 0.0 or t1 <= 0.0 or t2 <= 0.0:
                    return t1
                frac = math.log(current_mult / m1) / math.log(m2 / m1)
                t = 10.0 ** (math.log10(t1) + frac * (math.log10(t2) - math.log10(t1)))
                return min(1000.0, max(0.01, t))
        return pts[-1][1]

    @classmethod
    def thermal_time_s(cls, series: str, current_mult: float) -> float:
        pts = cls.datasheet_points(series)
        if pts:
            return cls._interp_log(pts, current_mult)
        c = cls.get_curve(series)
        k, alpha = c.get("thermal_k", 90.0), c.get("alpha", 2.0)
        return min(1000.0, max(0.01, k / max(current_mult, 1e-3) ** alpha))

    @classmethod
    def instantaneous_band_a(cls, series: str, rated_in_a: float):
        c = cls.get_curve(series)
        return (c.get("im_min_mult", 8.0) * rated_in_a, c.get("im_max_mult", 12.0) * rated_in_a)

    @classmethod
    def current_selectivity_limit_ka(cls, upstream: CatalogDevice, downstream: CatalogDevice) -> float:
        up_min_a, _ = cls.instantaneous_band_a(upstream.series, upstream.rated_current_in_a)
        _, down_max_a = cls.instantaneous_band_a(downstream.series, downstream.rated_current_in_a)
        if down_max_a >= up_min_a:
            return 0.0
        return round(up_min_a / 1000.0, 1)


class StandardsRegistry:
    @staticmethod
    def _entries() -> Dict[str, Dict[str, Any]]:
        with catalog_repo._connect() as conn:
            rows = conn.execute("SELECT standard_id, raw_json FROM standards_registry").fetchall()
        entries: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            payload = json.loads(r["raw_json"])
            if isinstance(payload, dict) and "title" in payload:
                entries[r["standard_id"]] = payload
            elif isinstance(payload, dict):
                for std_id, entry in payload.items():
                    if isinstance(entry, dict) and "title" in entry:
                        entries[std_id] = entry
        return entries

    @classmethod
    def title(cls, standard_id: str) -> str:
        entry = cls._entries().get(standard_id)
        if not entry:
            return standard_id
        titles = entry.get("title", {})
        return titles.get(i18n.get_language()) or titles.get("en") or standard_id

    @classmethod
    def scope(cls, standard_id: str) -> str:
        entry = cls._entries().get(standard_id)
        if not entry:
            return ""
        scopes = entry.get("scope", {})
        return scopes.get(i18n.get_language()) or scopes.get("en") or ""


class SiemensSelectivityRepository:
    """ارزیابی سلکتیویته با تفکیک قواعد تأییدشده سازنده از تخمین منحنی تقریبی (رفع F-003)."""

    @classmethod
    def get_selectivity_rules(cls) -> List[SelectivityRuleRecord]:
        return CatalogRepository.get_selectivity_rules()

    @classmethod
    def evaluate_pair(cls, upstream: CatalogDevice, downstream: CatalogDevice, prospective_ik_ka: float):
        ratio = upstream.rated_current_in_a / max(1.0, downstream.rated_current_in_a)
        if ratio < 1.25:
            return (SelectivityEvalState.VIOLATION, 0.0, tr("sel_ref_violation", up=upstream.rated_current_in_a, down=downstream.rated_current_in_a, ratio=f"{ratio:.2f}"))

        matching_rules = [
            r for r in cls.get_selectivity_rules()
            if r.upstream_series == upstream.series
            and upstream.rated_current_in_a >= r.upstream_min_in_a
            and r.downstream_series == downstream.series
            and downstream.rated_current_in_a <= r.downstream_max_in_a
            and ratio >= 1.6
        ]

        if matching_rules:
            best_rule = max(matching_rules, key=lambda x: x.selectivity_limit_is_ka)
            if best_rule.selectivity_limit_is_ka >= prospective_ik_ka:
                return (SelectivityEvalState.VERIFIED_TOTAL, best_rule.selectivity_limit_is_ka, best_rule.catalog_reference)
            else:
                return (SelectivityEvalState.VERIFIED_PARTIAL, best_rule.selectivity_limit_is_ka, best_rule.catalog_reference)

        if ratio >= 1.6:
            # بازه آنی پایین‌دست تا آستانه آنی بالادست رسیده باشد، تقاطع قطعی از منحنی
            # قابل ادعا نیست → فقط نسبت (رفتار محافظه‌کارانه قبلی حفظ می‌شود)
            up_min_a, _ = TripCurveRepository.instantaneous_band_a(upstream.series, upstream.rated_current_in_a)
            _, down_max_a = TripCurveRepository.instantaneous_band_a(downstream.series, downstream.rated_current_in_a)
            if down_max_a >= up_min_a:
                return (SelectivityEvalState.PRELIMINARY_RATIO_ONLY, None,
                        tr("sel_ref_ratio_only", ratio=f"{ratio:.2f}"))
            # فاز تحلیل TCC: حد سلکتیویته از تقاطع ریاضی منحنی‌های t-I واقعی (دیتاشیت یا مدل)
            from lv_assist.tcc_analyzer import TccAnalyzer
            state_tag, curve_limit_ka, note = TccAnalyzer.evaluate_pair(upstream, downstream, None)
            if curve_limit_ka and curve_limit_ka > 0.0:
                # منحنی تقریبی هرگز VERIFIED صادر نمی‌کند؛ صرفاً تخمین مقدماتی (رفع F-003)
                return (SelectivityEvalState.PRELIMINARY, curve_limit_ka,
                        tr("sel_ref_curve_prelim", a=curve_limit_ka) + " — " + note)
            return (SelectivityEvalState.PRELIMINARY_RATIO_ONLY, None, tr("sel_ref_ratio_only", ratio=f"{ratio:.2f}"))

        return (SelectivityEvalState.VIOLATION, 0.0, tr("sel_ref_violation16", ratio=f"{ratio:.2f}"))
