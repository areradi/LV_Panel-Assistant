# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
import tempfile
from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH)
sys.path.insert(0, str(root))
from lv_assist.distribution import prepare_release_data
(root / 'build').mkdir(exist_ok=True)
release_temp = tempfile.TemporaryDirectory(prefix='release-data-', dir=root / 'build')
release_files = prepare_release_data(root / 'lv_assist/data', Path(release_temp.name))
extra_data, extra_binaries, extra_imports = collect_all('rapidfuzz')
a = Analysis(
    [str(root / 'main.py')], pathex=[str(root)], binaries=extra_binaries,
    datas=[(str(path), 'lv_assist/data') for path in release_files]
          + [(str(root / 'lv_assist/translations' / (lang + '.json')), 'lv_assist/translations') for lang in ('fa', 'en', 'de')]
          + [(str(root / 'templates/Input_Load_List_Template.xlsx'), 'templates')]
          + collect_data_files('customtkinter') + extra_data,
    hiddenimports=['openpyxl', 'pydantic', 'defusedxml', 'sqlite3', 'customtkinter'] + extra_imports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='PanelCalc-Pro',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          upx_exclude=[], runtime_tmpdir=None, console=False,
          disable_windowed_traceback=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file=None)
release_temp.cleanup()
