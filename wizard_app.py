# -*- coding: utf-8 -*-
"""راه‌انداز ویزارد — v0.7 به بعد: ویزارد گام‌به‌گام به‌صورت کامل در برنامه اصلی ادغام شده است.

این فایل صرفاً برای سازگاری نام کلاس و اجرای مستقیم حفظ شده است؛ همان پوسته
LVAssistApp (سایدبار ۷ مرحله‌ای: پروژه و ساختار → فیدرها → ابزار دقیق و PLC →
محاسبات و نتایج → نقشه‌ها → خروجی‌ها → کاتالوگ و قیمت) باز می‌شود.
"""

from lv_assist.gui import LVAssistApp


class InteractiveEngineeringWizard(LVAssistApp):
    """سازگاری نسخه‌های قبل: ویزارد مستقل با پوسته یکپارچه یکی شده است."""


if __name__ == "__main__":
    app = InteractiveEngineeringWizard()
    app.mainloop()
