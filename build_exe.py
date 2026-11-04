# -*- coding: utf-8 -*-
"""
build_exe.py
اسکریپت ساخت خودکار فایل اجرایی تک‌فایلی ویندوز (LV-PanelAssist.exe) با PyInstaller.
دیتابیس تمیز از بذرهای پروژه ساخته می‌شود؛ داده‌های محلی کاربر وارد بسته انتشار نمی‌شوند.
"""
import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from lv_assist.distribution import prepare_release_data

ROOT = Path(__file__).resolve().parent
APP_NAME = "PanelCalc-Pro"
ENTRY_SCRIPT = ROOT / "main.py"


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print("[OK] PyInstaller نصب است.")
    except ImportError:
        print("[INFO] در حال نصب PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build():
    ensure_pyinstaller()
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-data-', dir=ROOT / 'build') as temporary:
        release_files = prepare_release_data(ROOT / 'lv_assist' / 'data', Path(temporary))
        _build_with_data(release_files)


def _build_with_data(release_files):
    sep = ";" if os.name == "nt" else ":"
    data_args = [f'--add-data={path}{sep}lv_assist/data' for path in release_files]
    data_args += [f"--add-data={ROOT / 'lv_assist' / 'translations' / (lang + '.json')}{sep}lv_assist/translations"
                  for lang in ('fa', 'en', 'de')]

    template_xlsx = ROOT / "templates" / "Input_Load_List_Template.xlsx"
    if template_xlsx.exists():
        data_args.append(f"--add-data={template_xlsx}{sep}templates")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        f"--name={APP_NAME}",
        f"--specpath={ROOT / 'build' / 'spec'}",
        "--hidden-import=openpyxl",
        "--hidden-import=pydantic",
        "--hidden-import=defusedxml",
        "--hidden-import=sqlite3",
        "--hidden-import=customtkinter",
        "--collect-data=customtkinter",
        "--collect-all=rapidfuzz",
        *data_args,
        str(ENTRY_SCRIPT),
    ]

    print("\n[BUILDING] در حال کامپایل و ساخت فایل اجرایی تک‌فایلی...")
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))

    dist_dir = ROOT / "dist"
    exe_file = dist_dir / (f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME)

    # کپی پوشه data و قالب اکسل در کنار فایل exe برای پایداری تغییرات دیتابیس کاربر
    target_data = dist_dir / "data"
    target_data.mkdir(parents=True, exist_ok=True)
    for item in release_files:
        if not (target_data / item.name).exists():
            shutil.copy2(item, target_data / item.name)

    if template_xlsx.exists():
        target_templates = dist_dir / "templates"
        target_templates.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_xlsx, target_templates / template_xlsx.name)

    release_zip = dist_dir / f'{APP_NAME}-release.zip'
    with zipfile.ZipFile(release_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(exe_file, exe_file.name)
        for item in release_files:
            archive.write(item, f'data/{item.name}')
        if template_xlsx.exists():
            archive.write(template_xlsx, f'templates/{template_xlsx.name}')

    print("\n" + "=" * 68)
    print(f"[SUCCESS] فایل اجرایی با موفقیت ساخته شد:")
    print(f"  -> {exe_file}")
    print(f"  -> Clean release archive: {release_zip}")
    print(f"  -> دیتابیس قابل ویرایش کنار فایل اجرایی: {target_data / 'lv_assist.db'}")
    print("=" * 68)


if __name__ == "__main__":
    build()
