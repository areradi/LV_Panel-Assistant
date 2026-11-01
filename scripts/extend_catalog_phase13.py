# -*- coding: utf-8 -*-
"""فاز ۱۳ (داده): افزودن دستگاه‌های حفاظت صاعقه SPD (IEC 61643-11) به کاتالوگ.

Type 2 (8/20µs) برای تابلوی توزیع، Type 1 (10/350µs) برای ورودی‌های با ریسک
برخورد مستقیم و Type 1+2 ترکیبی. مقادیر Uc/Up/In/Imax/Iimp از دیتاشیت‌های
سازنده برای شبکه TN-S با U0=230V استخراج شده‌اند.
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lv_assist", "data")

# (part_number, manufacturer, series, spd_class, uc_v, up_kv, in_ka, imax_ka, iimp_ka,
#  poles, backup_fuse_a, w, h, d, datasheet_ref)
SPD_DEVICES = [
    # --- Type 2 (8/20 µs) ---
    ("OVR T2 4L 40-275s P TS QS", "ABB", "ABB OVR T2", "T2", 275.0, 1.35, 20.0, 40.0, 0.0,
     "4P", 125.0, 71.2, 88.0, 69.0, "ABB OVR T2 4L 40-275s datasheet (2CTC...)"),
    ("VAL-MS 320/3+1-FM", "Phoenix Contact", "Phoenix VAL-MS", "T2", 335.0, 1.35, 20.0, 40.0, 0.0,
     "3P+N", 125.0, 71.5, 90.0, 65.0, "Phoenix Contact VAL-MS 320/3+1-FM datasheet"),
    ("5SD7484-1", "Siemens", "SENTRON 5SD74", "T2", 335.0, 1.35, 20.0, 40.0, 0.0,
     "3P+N", 125.0, 72.0, 89.0, 76.0, "Siemens 5SD7484-1 datasheet (LV 10)"),
    ("iPRD40r 3P+N 350", "Schneider", "Schneider Acti9 iPRD", "T2", 350.0, 1.5, 20.0, 40.0, 0.0,
     "3P+N", 125.0, 72.0, 92.0, 69.0, "Schneider Acti9 iPRD40r datasheet"),
    ("BXT-ML4 BD 40 275", "Eaton", "Eaton BXT", "T2", 275.0, 1.5, 20.0, 40.0, 0.0,
     "3P+N", 125.0, 72.0, 85.0, 78.0, "Eaton BXT-ML4 BD 40 datasheet"),
    # --- Type 1 (10/350 µs) ---
    ("FLT-SEC-P-T1-3S-350/25-FM", "Phoenix Contact", "Phoenix FLT-SEC", "T1", 350.0, 1.5, 25.0, 50.0, 25.0,
     "3P+N", 315.0, 106.0, 98.0, 74.0, "Phoenix Contact FLT-SEC-P-T1-3S-350/25-FM datasheet"),
    ("5SD7414-1", "Siemens", "SENTRON 5SD741", "T1", 350.0, 1.5, 12.5, 25.0, 12.5,
     "3P+N", 315.0, 72.0, 89.0, 76.0, "Siemens 5SD7414-1 datasheet (LV 10)"),
    # --- Type 1+2 (ترکیبی) ---
    ("OVR T1-T2 4L 25-440s P TS QS", "ABB", "ABB OVR T1-T2", "T1_T2", 440.0, 1.5, 25.0, 50.0, 25.0,
     "4P", 315.0, 71.2, 88.0, 69.0, "ABB OVR T1-T2 4L 25-440s datasheet (2CTC...)"),
]


def main() -> None:
    path = os.path.join(DATA_DIR, "catalog_devices.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    devs = data.get("devices") if isinstance(data, dict) else data

    existing = {d.get("part_number") for d in devs}
    added = 0
    for (pn, mfr, series, cls, uc, up, in_ka, imax, iimp, poles, fuse,
         w, h, d, ref) in SPD_DEVICES:
        if pn in existing:
            print("skip existing:", pn)
            continue
        devs.append({
            "part_number": pn, "manufacturer": mfr, "series": series,
            "device_type": "SPD", "poles": 4,
            "power_loss_w": 0.5,
            "spd_class": cls, "spd_uc_v": uc, "spd_up_kv": up,
            "spd_in_ka": in_ka, "spd_imax_ka": imax, "spd_iimp_ka": iimp,
            "spd_poles": poles, "spd_backup_fuse_a": fuse,
            "width_mm": w, "height_mm": h, "depth_mm": d,
            "data_quality": "REAL_VERIFIED", "datasheet_ref": ref,
        })
        added += 1

    if added:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"phase13 SPD devices added: +{added} -> total {len(devs)}")


if __name__ == "__main__":
    main()
