# -*- coding: utf-8 -*-
"""فاز ۷ (داده): افزودن پله‌های کوچک بانک خازنی (5/10/12.5/15/20 kvar) به کاتالوگ.

یافته F-004 ممیزی: fallback ثابت 25 kvar برای نیازهای کوچک حذف می‌شود؛
برای پوشش کامل، ماژول‌های خازنی و کنتاکتورهای خازنی رده‌بندی کوچک‌تر
به کاتالوگ اضافه می‌شوند (data_quality=ESTIMATED — کد سفارش تیپیکال،
نیازمند تأیید دیتاشیت سازنده پیش از سفارش واقعی).
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lv_assist", "data")

CAP_CONTACTORS = [
    ("3RT2616-1AP00", 5.0, 12.0, 4.0, 45.0, 85.0, 100.0),
    ("3RT2626-1AP00", 10.0, 21.0, 6.0, 45.0, 85.0, 100.0),
    ("3RT2634-1AP00", 15.0, 30.0, 8.0, 45.0, 85.0, 100.0),
    ("3RT2644-1AP00", 20.0, 65.0, 12.0, 55.0, 113.0, 125.0),
]
CAP_MODULES = [
    ("PHC-5-400-EST", 5.0),
    ("PHC-10-400-EST", 10.0),
    ("PHC-12.5-400-EST", 12.5),
    ("PHC-15-400-EST", 15.0),
    ("PHC-20-400-EST", 20.0),
]


def main() -> None:
    path = os.path.join(DATA_DIR, "catalog_devices.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    devs = data if isinstance(data, list) else data.get("devices", [])

    existing = {(d.get("part_number"), d.get("device_type")) for d in devs}
    added = 0
    for pn, kvar, i_a, loss, w, h, d in CAP_CONTACTORS:
        if (pn, "CAP_CONTACTOR") in existing:
            continue
        devs.append({
            "part_number": pn, "manufacturer": "Siemens", "series": "SIRIUS 3RT26",
            "device_type": "CAP_CONTACTOR", "rated_current_in_a": i_a, "cap_kvar_400v": kvar,
            "power_loss_w": loss, "width_mm": w, "height_mm": h, "depth_mm": d,
            "data_quality": "ESTIMATED", "source_ref": "typical catalog code - verify datasheet before order",
        })
        added += 1
    for pn, kvar in CAP_MODULES:
        if (pn, "CAP_MODULE") in existing:
            continue
        devs.append({
            "part_number": pn, "manufacturer": "GENERIC", "series": "PFC-MODULE",
            "device_type": "CAP_MODULE", "cap_kvar_400v": kvar,
            "width_mm": 152.0, "height_mm": 200.0, "depth_mm": 105.0,
            "data_quality": "ESTIMATED", "source_ref": "typical module - verify datasheet before order",
        })
        added += 1

    if isinstance(data, dict):
        data["devices"] = devs
    else:
        data = devs
    if added:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"phase7 cap devices added: +{added} -> total {len(devs)}")


if __name__ == "__main__":
    main()
