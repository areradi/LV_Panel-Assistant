# -*- coding: utf-8 -*-
"""مرکز یکپارچه مدیریت مسیرها — سازگار با اجرای توسعه، اجرای ماژولی و بسته PyInstaller.

قاعده: همه دسترسی‌های فایل در سراسر پکیج lv_assist باید از توابع این ماژول استفاده کنند
تا در حالت فایل اجرایی تک‌فایلی (.exe) مسیر دیتابیس، قالب اکسل و ترجمه‌ها درست پیدا شود.

- get_app_working_dir(): پوشه قابل نوشتن (کنار .exe در حالت frozen / ریشه پروژه در توسعه)
- get_bundle_dir(): پوشه منابع فقط-خواندنی داخلی بسته (_MEIPASS در PyInstaller)
- get_data_dir(): پوشه داده SQLite — در حالت frozen داخل پوشه «data» کنار .exe ساخته می‌شود
- resource_path(): مسیر یک منبع بسته‌شده (ترجمه/قالب) در هر دو حالت
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True یعنی برنامه به صورت فایل اجرایی PyInstaller (onefile/onedir) اجرا می‌شود."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_dir() -> Optional[str]:
    """پوشه موقت استخراج منابع PyInstaller (sys._MEIPASS) یا None در اجرای عادی."""
    return getattr(sys, "_MEIPASS", None)


def get_app_working_dir() -> str:
    """پوشه کاری قابل نوشتن: کنار فایل .exe در حالت بسته، ریشه پروژه در حالت توسعه."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return str(PACKAGE_DIR.parent)


def get_data_dir() -> Path:
    """پوشه داده‌های کاربر (دیتابیس SQLite و فایل‌های بذر JSON).

    توسعه: همان lv_assist/data داخل پکیج (سازگار با ساختار فعلی مخزن).
    حالت بسته‌شده: «data» کنار .exe ساخته می‌شود تا دیتابیس کاربر پایدار بماند؛
    اگر دیتابیس همراه بسته موجود باشد، یک‌بار در اولین اجرا کپی می‌شود.
    """
    if not is_frozen():
        return PACKAGE_DIR / "data"
    work_dir = Path(get_app_working_dir())
    data_dir = work_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _copy_bundled_seed_files(data_dir)
    return data_dir


def _copy_bundled_seed_files(data_dir: Path) -> None:
    """کپی یک‌باره دیتابیس/JSONهای بذر از منابع بسته به پوشه داده کاربر (فقط موارد غایب)."""
    candidates = [
        PACKAGE_DIR / "data",                # onedir: کنار پکیج
        Path(get_bundle_dir() or "") / "lv_assist" / "data",  # onefile: _MEIPASS
    ]
    for seed_dir in candidates:
        if not seed_dir.is_dir():
            continue
        for name in ("lv_assist.db", "catalog_devices.json", "selectivity_rules.json",
                     "standards_registry.json", "trip_curves.json"):
            target = data_dir / name
            src = seed_dir / name
            if not target.exists() and src.exists():
                try:
                    shutil.copy2(src, target)
                except OSError:
                    pass


def get_translations_dir() -> Path:
    """پوشه فایل‌های ترجمه — در هر دو حالت توسعه و بسته‌شده در کنار پکیج است."""
    for base in (PACKAGE_DIR, Path(get_bundle_dir() or "") / "lv_assist"):
        candidate = base / "translations"
        if candidate.is_dir():
            return candidate
    return PACKAGE_DIR / "translations"


def resource_path(relative: str) -> str:
    """مسیر یک منبع بسته‌شده (مثل قالب اکسل) — اول پوشه کاری، بعد منابع داخلی بسته."""
    work_candidate = Path(get_app_working_dir()) / relative
    if work_candidate.exists():
        return str(work_candidate)
    bundle_candidate = Path(get_bundle_dir() or PACKAGE_DIR.parent) / relative
    return str(bundle_candidate)


def config_file_path() -> str:
    """مسیر config.json در پوشه کاری قابل نوشتن."""
    return os.path.join(get_app_working_dir(), "config.json")


def get_output_dir(category: str) -> Path:
    """Keep automatically generated reports and previews outside the project root."""
    if category not in ("reports", "previews"):
        raise ValueError(f"Unknown output category: {category}")
    directory = Path(get_app_working_dir()) / "outputs" / category
    directory.mkdir(parents=True, exist_ok=True)
    return directory
