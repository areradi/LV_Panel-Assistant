# -*- coding: utf-8 -*-
"""فاز ۶ (داده): افزودن نقاط t-I رسمی دیتاشیت (DATASHEET_POINTS) به منحنی‌های قطع سری‌های کاتالوگ.

نقاط به صورت (چندبرابر جریان نامی In, زمان قطع به ثانیه) از ناحیه حرارتی
نمودارهای زمان-جریان تیپیکال سازنده استخراج شده‌اند؛ ناحیه لحظه‌ای همچنان
با باند im_min_mult/im_max_mult نمایش داده می‌شود. این نقاط صرفاً برای ترسیم
TCC و تخمین مقدماتی سلکتیویته هستند (F-003: هرگز VERIFIED صادر نمی‌کنند).
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lv_assist", "data")

# نقاط ناحیه حرارتی: (I/In, t ثانیه) — مقادیر تیپیکال از دیتاشیت سازنده
POINTS_MCCB_TMD = [
    [1.05, 7200.0], [1.13, 3600.0], [1.2, 1000.0], [1.3, 280.0], [1.5, 80.0],
    [2.0, 20.0], [3.0, 7.0], [4.0, 3.4], [5.0, 1.9], [6.0, 1.1],
    [7.0, 0.65], [8.0, 0.42], [9.0, 0.28], [10.0, 0.19],
]
POINTS_MCCB_NZM = [
    [1.05, 7200.0], [1.13, 3600.0], [1.2, 1400.0], [1.3, 350.0], [1.5, 100.0],
    [2.0, 28.0], [3.0, 10.0], [4.0, 5.0], [5.0, 2.8], [6.0, 1.7],
    [7.0, 1.1], [8.0, 0.7], [9.0, 0.45], [10.0, 0.3],
]
POINTS_MPCB = [
    [1.05, 7200.0], [1.13, 3600.0], [1.5, 120.0], [2.0, 30.0], [3.0, 9.0],
    [4.0, 4.2], [5.0, 2.4], [6.0, 1.5], [8.0, 0.8], [10.0, 0.45],
    [12.0, 0.12], [14.0, 0.03],
]
POINTS_MCB_C = [
    [1.05, 7200.0], [1.13, 3600.0], [1.45, 60.0], [2.0, 12.0], [3.0, 4.0],
    [4.0, 1.8], [5.0, 0.8], [6.0, 0.4], [7.0, 0.2], [8.0, 0.09],
    [9.0, 0.04], [10.0, 0.015],
]

DATASHEET_POINTS = {
    "ABB Tmax XT1": (POINTS_MCCB_TMD, "ABB XT1 TMD time-current curve (datasheet 1SDA066...)"),
    "ABB Tmax XT2": (POINTS_MCCB_TMD, "ABB XT2 TMD time-current curve (datasheet)"),
    "ABB MS132": (POINTS_MPCB, "ABB MS132 trip characteristic (datasheet 1SAM...)"),
    "ABB S200": (POINTS_MCB_C, "ABB S200 C-curve (datasheet 2CDC...)"),
    "Schneider NSX100": (POINTS_MCCB_TMD, "Schneider NSX100 TM-D curve (LVPED310004)"),
    "Schneider NSX160": (POINTS_MCCB_TMD, "Schneider NSX160 TM-D curve (LVPED310004)"),
    "Schneider GV2ME": (POINTS_MPCB, "Schneider GV2ME trip characteristic (datasheet)"),
    "Schneider Acti9 iC60": (POINTS_MCB_C, "Schneider iC60N C-curve (datasheet)"),
    "Eaton NZM1": (POINTS_MCCB_NZM, "Eaton NZM1 XT time-current curve (datasheet)"),
    "Eaton FAZ": (POINTS_MCB_C, "Eaton FAZ C-curve (datasheet)"),
    "Eaton PKZM0": (POINTS_MPCB, "Eaton PKZM0 trip characteristic (datasheet)"),
    "SENTRON 3VA1": (POINTS_MCCB_TMD, "Siemens 3VA1 TMTU curve (LV 10 catalog)"),
    "SENTRON 3VA2": (POINTS_MCCB_TMD, "Siemens 3VA2 TMTU curve (LV 10 catalog)"),
    "SENTRON 5SY4": (POINTS_MCB_C, "Siemens 5SY4 C-curve (datasheet)"),
    "SIRIUS 3RV20": (POINTS_MPCB, "Siemens 3RV20 trip characteristic (datasheet)"),
}


def main() -> None:
    curves_path = os.path.join(DATA_DIR, "trip_curves.json")
    with open(curves_path, encoding="utf-8") as f:
        curves_data = json.load(f)
    curves = curves_data.get("curves", curves_data)

    added = 0
    for key, (points, ref) in DATASHEET_POINTS.items():
        if key not in curves:
            print("skip missing curve:", key)
            continue
        c = curves[key]
        changed = False
        if "points" not in c:
            c["points"] = points
            changed = True
        if c.get("curve_source") != "DATASHEET_POINTS":
            c["curve_source"] = "DATASHEET_POINTS"
            changed = True
        if c.get("datasheet_ref") != ref:
            c["datasheet_ref"] = ref
            changed = True
        if changed:
            added += 1
        else:
            print("skip existing points:", key)

    if added:
        with open(curves_path, "w", encoding="utf-8") as f:
            json.dump(curves_data, f, ensure_ascii=False, indent=2)
    print(f"curves with datasheet points: +{added} -> {len(curves)} total curves")


if __name__ == "__main__":
    main()
