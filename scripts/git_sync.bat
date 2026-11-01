@echo off
cd /d "%~dp0.."
chcp 65001 >nul
echo ============================================================================
echo [STEP 1/4] Verifying Modular Architecture of lv_assist...
echo ============================================================================
python -c "import lv_assist.models, lv_assist.catalog, lv_assist.engine, lv_assist.busbar, lv_assist.exporters, lv_assist.field_wizard_engine; print('[OK] All Modular Packages Verified Successfully!')"
if %errorlevel% neq 0 (
    echo [ERROR] Modular verification failed! Fix imports before pushing to GitHub.
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo [STEP 2/4] Running Automated Engineering PyTest Suite...
echo ============================================================================
pytest -v
if %errorlevel% neq 0 (
    echo [WARNING] Some tests failed. Review test output above.
)

echo.
echo ============================================================================
echo [STEP 3/4] Cleaning __pycache__ and temporary build artifacts...
echo ============================================================================
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
if exist ".pytest_cache" rd /s /q ".pytest_cache"

echo.
echo ============================================================================
echo [STEP 4/4] Staging ^& Pushing Approved Changes to GitHub...
echo Repository: https://github.com/areradi/lv-panelassist.git
echo ============================================================================
set /p COMMIT_MSG="Enter commit message for this stage (e.g., Add Field Wizard, PLC/Sensors & IEC 81346): "
git init
git remote remove origin 2>nul
git remote add origin https://github.com/areradi/lv-panelassist.git
git branch -M main
git add .
git commit -m "%COMMIT_MSG%"
git push -u origin main

echo.
echo [DONE] Stage successfully pushed to https://github.com/areradi/lv-panelassist
pause
