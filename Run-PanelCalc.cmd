@echo off
setlocal
cd /d "%~dp0"
if exist "dist\PanelCalc-Pro.exe" (
    start "" "dist\PanelCalc-Pro.exe"
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -B main.py
) else (
    python -B main.py
)
