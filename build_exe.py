# -*- coding: utf-8 -*-
"""
build_exe.py
اسکریپت ساخت خودکار فایل اجرایی تک‌فایلی ویندوز (LV-PanelAssist.exe) با PyInstaller.
این اسکریپت به صورت خودکار پوشه‌های data (دیتابیس SQLite و JSONها)، translations و
پکیج customtkinter را درون فایل اجرایی بسته‌بندی می‌کند.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "LV-PanelAssist"
ENTRY_SCRIPT = ROOT / "main.py"


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print("[OK] PyInstaller نصب است.")
    except ImportError:
        print("[INFO] در حال نصب PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def get_customtkinter_path() -> str:
    import customtkinter
    return os.path.dirname(customtkinter.__file__)


def build():
    ensure_pyinstaller()
    ctk_dir = get_customtkinter_path()
    sep = ";" if os.name == "nt" else ":"

    data_args = [
        f"--add-data={ROOT / 'lv_assist' / 'data'}{sep}lv_assist/data",
        f"--add-data={ROOT / 'lv_assist' / 'translations'}{sep}lv_assist/translations",
        f"--add-data={ctk_dir}{sep}customtkinter",
    ]

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
        "--hidden-import=openpyxl",
        "--hidden-import=pydantic",
        "--hidden-import=defusedxml",
        "--hidden-import=sqlite3",
        "--hidden-import=customtkinter",
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
    src_data = ROOT / "lv_assist" / "data"
    for item in src_data.glob("*"):
        if item.is_file():
            shutil.copy2(item, target_data / item.name)

    if template_xlsx.exists():
        target_templates = dist_dir / "templates"
        target_templates.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_xlsx, target_templates / template_xlsx.name)

    print("\n" + "=" * 68)
    print(f"[SUCCESS] فایل اجرایی با موفقیت ساخته شد:")
    print(f"  -> {exe_file}")
    print(f"  -> دیتابیس قابل ویرایش کنار فایل اجرایی: {target_data / 'lv_assist.db'}")
    print("=" * 68)


if __name__ == "__main__":
    build()
