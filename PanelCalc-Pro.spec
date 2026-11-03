# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import customtkinter
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
extra_data, extra_binaries, extra_imports = collect_all('rapidfuzz')
a = Analysis(
    [str(root / 'main.py')], pathex=[str(root)], binaries=extra_binaries,
    datas=[(str(root / 'lv_assist/data'), 'lv_assist/data'),
           (str(root / 'lv_assist/translations'), 'lv_assist/translations'),
           (str(Path(customtkinter.__file__).parent), 'customtkinter'),
           (str(root / 'templates/Input_Load_List_Template.xlsx'), 'templates')] + extra_data,
    hiddenimports=['openpyxl', 'pydantic', 'defusedxml', 'sqlite3', 'customtkinter'] + extra_imports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='PanelCalc-Pro',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          upx_exclude=[], runtime_tmpdir=None, console=False,
          disable_windowed_traceback=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file=None)
