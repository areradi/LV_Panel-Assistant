# LV Panel Assistant

Python desktop application for preliminary low-voltage panel design, electrical calculations and engineering documentation. The interface supports Persian, English and German.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

The catalog seed data and workbook template are included. Local settings, generated reports, build artifacts and historical repair tools are excluded from Git.

## Development

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

The focused regression checks pass, but the full suite still contains legacy failures for removed exports and older output expectations. Results support preliminary engineering work and require engineering review. DXF export and the EPLAN import package are disabled.

## Build

```powershell
.\.venv\Scripts\python.exe build_exe.py
```

Builds produce files under `dist/`. The existing local executable is not part of this source repository.

## License

No project license has been selected yet.

## راهنمای فارسی

سامانه هوشمند طراحی مقدماتی، محاسبات الکتریکی و تولید مدارک مهندسی تابلوهای فشار ضعیف —
خروجی‌های جاری شامل مدارک Excel، گزارش HTML و PDF و نقشه‌های SVG است.

## شروع سریع (بدون اکسل)

```bash
pip install -r requirements.txt
python main.py        # یا: python wizard_app.py (همان برنامه یکپارچه)
```

برنامه با یک **ویزارد ۶ مرحله‌ای در سایدبار** باز می‌شود:

| گام | عنوان | توضیح |
|----|-------|-------|
| ۱ | پروژه و ساختار | مشخصات پایه + کدگذاری IEC 81346 (`==` / `++` / `+`) و سازنده ترجیحی |
| ۲ | فیدرها | افزودن تعاملی موتورها و بارها (بدون اکسل؛ cos φ خالی = IE3) |
| ۳ | ابزار دقیق و PLC | سنسورهای DI/AI و عملگرها → سایز خودکار کارت PLC، رله واسط و بار ۲۴V |
| ۴ | محاسبات و نتایج | انتخاب تجهیزات، سلکتیویته، صحت‌سنجی IEC 61439-1 و لاگ قواعد استاندارد |
| ۵ | نقشه‌ها و خروجی‌ها | پیش‌نمایش SLD و مدار فرمان (IEC SVG)، جدول سیم‌کشی From-To، گزارش‌ها و بسته مدارک |
| ۶ | کاتالوگ و قیمت | CRUD روی SQLite، قیمت‌گذاری و جستجوی آنلاین قطعه |

## خروجی‌های حذف‌شده

خروجی DXF و بسته ایمپورت EPLAN حذف شده‌اند و در رابط برنامه ارائه نمی‌شوند.
نقشه‌های SVG و بسته ZIP مدارک مهندسی همچنان در بخش نقشه‌ها و خروجی‌ها در دسترس هستند.

## جستجوی آنلاین تجهیزات

در گام ۶ دکمه «جستجوی آنلاین قطعه»: با مشخصات کلی (نوع، In، Icu، پل، ولتاژ) عبارت
مهندسی ساخته می‌شود؛ جستجوی زنده وب انجام و لینک مستقیم پورتال‌ها باز می‌شود
(EPLAN Data Portal، Siemens Industry Mall، Schneider، ABB، Eaton، Rittal، Phoenix).
قطعه یافته‌شده با برچسب کیفیت داده `ESTIMATED` به کاتالوگ SQLite اضافه و از همان لحظه
در انتخاب خودکار موتور لحاظ می‌شود.

## معماری

```
lv_assist/
  engine.py        موتور محاسبات (کابل، حفاظت، موتور، IEC 60909، هارمونیک، SPD)
  busbar.py        شینه مسی طبق DIN 43671 / IEC 60865-1
  tcc_analyzer.py  تقاطع ریاضی منحنی‌های قطع (دیتاشیت t-I) برای سلکتیویته
  catalog.py       مخزن SQLite + CRUD + قیمت‌ها + حفاظت داده کاربر
  web_catalog.py   جستجوی آنلاین تجهیزات
  field_wizard_engine.py  ابزار دقیق، PLC، IEC 81346
  iec_sld_svg.py / iec_ladder_svg.py  نقشه‌های برداری IEC
  gui.py           پوسته یکپارچه ۶ مرحله‌ای (CustomTkinter)
  paths.py         مدیریت مسیر سازگار با PyInstaller (frozen)
tests/             تست‌های خودکار (pytest)
scripts/           توسعه‌های داده کاتالوگ و ابزار همگام‌سازی Git
templates/         قالب ورودی Excel
outputs/reports/   گزارش‌های تولیدشده برنامه
outputs/previews/  پیش‌نمایش نقشه‌ها
archive/           ابزارهای قدیمی، فقط برای مراجعه
dist/              فایل اجرایی موجود و داده‌های همراه آن
```

گزارش‌ها و پیش‌نمایش‌های خودکار در پوشه `outputs/` ذخیره می‌شوند.
قالب ورودی در `templates/Input_Load_List_Template.xlsx` قرار دارد؛ ساخت قالب جدید از داخل برنامه نیز در دسترس است.
ابزارهای قدیمی در `archive/legacy-tools/` بخشی از اجرای برنامه نیستند و نباید روی نسخه جاری اجرا شوند.
اسکریپت‌های توسعه کاتالوگ در `scripts/` برای مهاجرت دیتابیس لازم‌اند.

ساخت فایل اجرایی از ریشه پروژه: `python build_exe.py`.
ابزار همگام‌سازی Git به `scripts/git_sync.bat` منتقل شده است و هنگام اجرا همچنان از ریشه پروژه کار می‌کند.

## اجرای تست‌ها

```bash
pip install -r requirements-dev.txt
pytest -q
```
