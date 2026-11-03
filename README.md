# LV Panel Assistant / PanelCalc Pro

Desktop application for preliminary low-voltage electrical panel calculations and engineering documentation. Built with Python, CustomTkinter, Pydantic and SQLite, with Persian, English and German interfaces.

## Run from source — Windows

Python 3.12 is the tested interpreter.

```powershell
git clone https://github.com/areradi/LV_Panel-Assistant.git
cd LV_Panel-Assistant
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B main.py
```

Alternatively, run `Run-PanelCalc.cmd` after installing dependencies. It launches a locally built EXE when present, otherwise the virtual environment or system Python.

The SQLite catalog is created automatically from the included JSON seed files. Local databases and preferences are not committed. `config.example.json` documents the optional language/theme settings; copy it to `config.json` to use it.

## Current functionality

- Project inputs, feeders, instruments and PLC sizing.
- Preliminary cable, protection, busbar, thermal and special-scenario checks.
- Floor-standing, wall-mounted, console and rack enclosure options.
- Separate Equipment and Busbars results, with stale-result guards.
- Actual main-device rated current distinguished from design current; unknown device fields remain unknown.
- Local catalog editing and technical search, plus asynchronous web search.
- Excel, HTML, SVG and document ZIP outputs. PDF uses an installed Edge or Chrome browser.
- Persian RTL layout, Latin calculation digits, EN/DE translations and light/dark appearance.

DXF and the EPLAN import/macro packages remain disabled. The panel wireframe is a contextual preview, not a fabrication drawing. Results require engineering review and do not establish assembly certification.

## Repository layout

```text
lv_assist/       Application modules, translation files and catalog seed data
scripts/         Catalog extension scripts used by database migration
templates/       Input workbook template
tests/           Engine, integration, import/export and UI regression tests
docs/            Architecture, scenario scope and verification summary
.codex/skills/   Existing project-specific Anti Slop rules and licenses
main.py          Desktop entry point
wizard_app.py    Alternate entry point to the same application
migrate_to_sqlite.py  Seed-to-SQLite migration
build_exe.py     Windows executable build
```

See [architecture](docs/ARCHITECTURE.md), [scenario scope](docs/SPECIAL_SCENARIOS.md) and [merge verification](docs/MERGE_REPORT.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B -m pytest -q
```

The merged version passed **359 tests**, excluding one browser-dependent PDF roundtrip. That PDF test was also attempted separately, but the installed browsers crashed in the restricted test environment. After the final text-rendering correction, **70 integration/UI regression tests** passed again. PDF conversion remains unverified in that environment.

To run independently of browser availability:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -k "not test_html_to_pdf_roundtrip"
```

Historical tests for removed EPLAN functionality and raw local build/test logs are retained in the local recovery backup, not in the published source tree. Active regression tests check that disabled export modules stay absent.

## Build a Windows executable

```powershell
.\.venv\Scripts\python.exe build_exe.py
```

The build script installs PyInstaller if missing. Output is `dist/PanelCalc-Pro.exe`, with editable data under `dist/data/` and the workbook under `dist/templates/`. Keep those files together when distributing a portable copy. Intermediate files are generated under `build/`.

RapidFuzz accelerates matching when installed; the stdlib fallback is also tested. No local language model is required.

## License

No project license has been selected. Third-party skill license notices are retained with their files.

## راهنمای فارسی

این برنامه برای طراحی و محاسبات مقدماتی تابلو برق است. برای اجرا از سورس، مراحل بخش Windows را انجام دهید؛ یا پس از نصب وابستگی‌ها فایل `Run-PanelCalc.cmd` را باز کنید.

رابط فارسی راست‌چین است و نتایج محاسبات با ارقام لاتین نمایش داده می‌شوند. امکانات سناریوهای ویژه، نوع نصب محفظه، فیدرها، PLC، نتایج تجهیزات و شینه و خروجی‌های Excel/HTML/SVG در همین برنامه قرار دارند.

دیتابیس از داده‌های همراه پروژه ساخته می‌شود. پوشه‌های ساخت، تنظیمات شخصی، دیتابیس محلی و لاگ‌ها وارد Git نمی‌شوند. خروجی PDF به مرورگر نصب‌شده وابسته است و موفقیت آن در محیط محدود تست تأیید نشده است. محدودیت‌های مهندسی در مستندات سناریوها آمده‌اند.
