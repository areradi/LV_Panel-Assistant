# -*- coding: utf-8 -*-
"""فاز ۵ (داده): افزودن کتابخانه چندسازنده‌ای + منحنی‌های واقعی + قواعد سلکتیویته سازندگان جدید."""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lv_assist", "data")

# ---------------------------------------------------------------------------
# ۱. دستگاه‌های جدید (ABB / Schneider / Eaton) با ابعاد فیزیکی برای layout
# ---------------------------------------------------------------------------
NEW_DEVICES = [
    # --- ABB ---
    dict(part_number="XT1N160-TMD100-3P", manufacturer="ABB", series="ABB Tmax XT1", device_type="MCCB",
         rated_current_in_a=100.0, icu_ka_400v=36.0, power_loss_w=18.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=76.0, height_mm=130.0, depth_mm=70.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB Tmax XT1N 160 TMD datasheet (1SDA066...)"),
    dict(part_number="XT2N160-TMD160-3P", manufacturer="ABB", series="ABB Tmax XT2", device_type="MCCB",
         rated_current_in_a=160.0, icu_ka_400v=36.0, power_loss_w=25.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=105.0, height_mm=153.0, depth_mm=70.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB Tmax XT2N 160 TMD datasheet"),
    dict(part_number="MS132-6.3", manufacturer="ABB", series="ABB MS132", device_type="MPCB",
         rated_current_in_a=6.3, icu_ka_400v=100.0, power_loss_w=4.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=45.0, height_mm=90.0, depth_mm=81.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB MS132 manual motor starter datasheet"),
    dict(part_number="MS132-16", manufacturer="ABB", series="ABB MS132", device_type="MPCB",
         rated_current_in_a=16.0, icu_ka_400v=100.0, power_loss_w=5.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=45.0, height_mm=90.0, depth_mm=81.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB MS132 manual motor starter datasheet"),
    dict(part_number="MS132-32", manufacturer="ABB", series="ABB MS132", device_type="MPCB",
         rated_current_in_a=32.0, icu_ka_400v=100.0, power_loss_w=8.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=45.0, height_mm=90.0, depth_mm=81.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB MS132 manual motor starter datasheet"),
    dict(part_number="AF09-30-10-13", manufacturer="ABB", series="ABB AF", device_type="CONTACTOR",
         rated_current_in_a=9.0, power_loss_w=1.5, coil_holding_24v_w=5.0, coil_pull_in_24v_w=6.5,
         width_mm=45.0, height_mm=86.0, depth_mm=77.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB AF09 contactor datasheet (24V DC coil)"),
    dict(part_number="AF16-30-10-13", manufacturer="ABB", series="ABB AF", device_type="CONTACTOR",
         rated_current_in_a=16.0, power_loss_w=2.2, coil_holding_24v_w=5.0, coil_pull_in_24v_w=6.5,
         width_mm=45.0, height_mm=86.0, depth_mm=77.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB AF16 contactor datasheet (24V DC coil)"),
    dict(part_number="AF30-30-00-13", manufacturer="ABB", series="ABB AF", device_type="CONTACTOR",
         rated_current_in_a=32.0, power_loss_w=3.0, coil_holding_24v_w=5.0, coil_pull_in_24v_w=6.5,
         width_mm=55.0, height_mm=100.0, depth_mm=107.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB AF30 contactor datasheet (24V DC coil)"),
    dict(part_number="S201-C10", manufacturer="ABB", series="ABB S200", device_type="MCB",
         rated_current_in_a=10.0, icu_ka_400v=6.0, power_loss_w=1.5,
         derating_40c=1.0, derating_50c=0.95, width_mm=17.5, height_mm=88.0, depth_mm=69.0,
         data_quality="REAL_VERIFIED", datasheet_ref="ABB S200 C-curve MCB datasheet"),
    # --- Schneider ---
    dict(part_number="NSX100F-TM80D-3P", manufacturer="Schneider", series="Schneider NSX100", device_type="MCCB",
         rated_current_in_a=80.0, icu_ka_400v=36.0, power_loss_w=18.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=105.0, height_mm=161.0, depth_mm=86.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider Compact NSX100F datasheet (LVPED)"),
    dict(part_number="NSX160F-TM125D-3P", manufacturer="Schneider", series="Schneider NSX160", device_type="MCCB",
         rated_current_in_a=125.0, icu_ka_400v=36.0, power_loss_w=25.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=105.0, height_mm=161.0, depth_mm=86.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider Compact NSX160F datasheet (LVPED)"),
    dict(part_number="GV2ME14", manufacturer="Schneider", series="Schneider GV2ME", device_type="MPCB",
         rated_current_in_a=10.0, icu_ka_400v=100.0, power_loss_w=3.5,
         derating_40c=1.0, derating_50c=0.95, width_mm=45.0, height_mm=89.0, depth_mm=78.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider TeSys GV2ME datasheet"),
    dict(part_number="LC1D09BD", manufacturer="Schneider", series="Schneider TeSys D", device_type="CONTACTOR",
         rated_current_in_a=9.0, power_loss_w=1.8, coil_holding_24v_w=7.0, coil_pull_in_24v_w=8.5,
         width_mm=45.0, height_mm=77.0, depth_mm=86.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider TeSys LC1D09 datasheet (24V DC coil)"),
    dict(part_number="LC1D18BD", manufacturer="Schneider", series="Schneider TeSys D", device_type="CONTACTOR",
         rated_current_in_a=18.0, power_loss_w=2.4, coil_holding_24v_w=7.0, coil_pull_in_24v_w=8.5,
         width_mm=45.0, height_mm=77.0, depth_mm=86.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider TeSys LC1D18 datasheet (24V DC coil)"),
    dict(part_number="LC1D32BD", manufacturer="Schneider", series="Schneider TeSys D", device_type="CONTACTOR",
         rated_current_in_a=32.0, power_loss_w=3.2, coil_holding_24v_w=7.5, coil_pull_in_24v_w=9.0,
         width_mm=45.0, height_mm=85.0, depth_mm=92.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider TeSys LC1D32 datasheet (24V DC coil)"),
    dict(part_number="A9F74110", manufacturer="Schneider", series="Schneider Acti9 iC60", device_type="MCB",
         rated_current_in_a=10.0, icu_ka_400v=6.0, power_loss_w=1.8,
         derating_40c=1.0, derating_50c=0.95, width_mm=18.0, height_mm=85.0, depth_mm=78.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Schneider Acti9 iC60N C-curve datasheet"),
    # --- Eaton ---
    dict(part_number="NZM1-4-XT100", manufacturer="Eaton", series="Eaton NZM1", device_type="MCCB",
         rated_current_in_a=100.0, icu_ka_400v=50.0, power_loss_w=20.0,
         derating_40c=1.0, derating_50c=0.95, width_mm=105.0, height_mm=185.0, depth_mm=110.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Eaton Moeller NZM1 XT datasheet"),
    dict(part_number="FAZ-C10/2", manufacturer="Eaton", series="Eaton FAZ", device_type="MCB",
         rated_current_in_a=10.0, icu_ka_400v=10.0, power_loss_w=1.5,
         derating_40c=1.0, derating_50c=0.95, width_mm=36.0, height_mm=80.0, depth_mm=75.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Eaton Moeller FAZ C-curve datasheet"),
    dict(part_number="PKZM0-10", manufacturer="Eaton", series="Eaton PKZM0", device_type="MPCB",
         rated_current_in_a=10.0, icu_ka_400v=50.0, power_loss_w=3.5,
         derating_40c=1.0, derating_50c=0.95, width_mm=45.0, height_mm=93.0, depth_mm=76.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Eaton Moeller PKZM0 datasheet"),
    dict(part_number="DILM9-10(24VDC)", manufacturer="Eaton", series="Eaton DILM", device_type="CONTACTOR",
         rated_current_in_a=9.0, power_loss_w=1.6, coil_holding_24v_w=4.8, coil_pull_in_24v_w=6.2,
         width_mm=45.0, height_mm=85.0, depth_mm=107.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Eaton Moeller DILM9 datasheet (24V DC coil)"),
    dict(part_number="DILM17-10(24VDC)", manufacturer="Eaton", series="Eaton DILM", device_type="CONTACTOR",
         rated_current_in_a=17.0, power_loss_w=2.2, coil_holding_24v_w=4.8, coil_pull_in_24v_w=6.2,
         width_mm=45.0, height_mm=85.0, depth_mm=107.0,
         data_quality="REAL_VERIFIED", datasheet_ref="Eaton Moeller DILM17 datasheet (24V DC coil)"),
]

# ---------------------------------------------------------------------------
# ۲. منحنی‌های تریپ تیپیکال سری‌های جدید (تقریبی، از دیتاشیت سازنده)
# ---------------------------------------------------------------------------
NEW_CURVES = {
    "ABB Tmax XT1": dict(thermal_k=70.0, alpha=2.0, im_min_mult=6.0, im_max_mult=10.0,
                         ref="ABB XT1 TMD time-current curve (typical)"),
    "ABB Tmax XT2": dict(thermal_k=80.0, alpha=2.0, im_min_mult=5.0, im_max_mult=10.0,
                         ref="ABB XT2 TMD time-current curve (typical)"),
    "ABB MS132": dict(thermal_k=45.0, alpha=2.0, im_min_mult=12.0, im_max_mult=14.0,
                      ref="ABB MS132 trip characteristic (typical)"),
    "ABB S200": dict(thermal_k=100.0, alpha=2.0, im_min_mult=5.0, im_max_mult=10.0,
                     ref="ABB S200 C-curve (typical)"),
    "Schneider NSX100": dict(thermal_k=75.0, alpha=2.0, im_min_mult=7.5, im_max_mult=9.5,
                             ref="Schneider NSX100 TM-D curve (typical)"),
    "Schneider NSX160": dict(thermal_k=75.0, alpha=2.0, im_min_mult=7.5, im_max_mult=9.5,
                             ref="Schneider NSX160 TM-D curve (typical)"),
    "Schneider GV2ME": dict(thermal_k=45.0, alpha=2.0, im_min_mult=12.0, im_max_mult=14.0,
                            ref="Schneider GV2ME trip characteristic (typical)"),
    "Schneider Acti9 iC60": dict(thermal_k=120.0, alpha=2.0, im_min_mult=5.0, im_max_mult=10.0,
                                 ref="Schneider iC60N C-curve (typical)"),
    "Eaton NZM1": dict(thermal_k=85.0, alpha=2.0, im_min_mult=8.0, im_max_mult=12.0,
                       ref="Eaton NZM1 XT time-current curve (typical)"),
    "Eaton FAZ": dict(thermal_k=110.0, alpha=2.0, im_min_mult=5.0, im_max_mult=10.0,
                      ref="Eaton FAZ C-curve (typical)"),
    "Eaton PKZM0": dict(thermal_k=45.0, alpha=2.0, im_min_mult=12.0, im_max_mult=14.0,
                        ref="Eaton PKZM0 trip characteristic (typical)"),
}

# ---------------------------------------------------------------------------
# ۳. قواعد سلکتیویته تأییدشده سازندگان جدید
# ---------------------------------------------------------------------------
NEW_RULES = [
    dict(upstream_series="ABB Tmax XT2", upstream_min_in_a=160.0,
         downstream_series="ABB MS132", downstream_max_in_a=16.0,
         selectivity_limit_is_ka=30.0, is_total_up_to_icu=True,
         catalog_reference="ABB Tmax XT2 / MS132 selectivity tables (Tech. paper QT1)"),
    dict(upstream_series="ABB Tmax XT1", upstream_min_in_a=100.0,
         downstream_series="ABB S200", downstream_max_in_a=63.0,
         selectivity_limit_is_ka=6.0, is_total_up_to_icu=True,
         catalog_reference="ABB XT1 / S200 coordination tables"),
    dict(upstream_series="Schneider NSX160", upstream_min_in_a=125.0,
         downstream_series="Schneider GV2ME", downstream_max_in_a=32.0,
         selectivity_limit_is_ka=36.0, is_total_up_to_icu=True,
         catalog_reference="Schneider Selectivity & Cascading Guide (LVPED310004)"),
    dict(upstream_series="Schneider NSX100", upstream_min_in_a=80.0,
         downstream_series="Schneider Acti9 iC60", downstream_max_in_a=63.0,
         selectivity_limit_is_ka=6.0, is_total_up_to_icu=True,
         catalog_reference="Schneider NSX / Acti9 iC60 coordination tables"),
    dict(upstream_series="Eaton NZM1", upstream_min_in_a=100.0,
         downstream_series="Eaton FAZ", downstream_max_in_a=63.0,
         selectivity_limit_is_ka=10.0, is_total_up_to_icu=True,
         catalog_reference="Eaton Moeller NZM / FAZ selectivity tables"),
]

# ابعاد فیلترفن‌های موجود (برای layout کامل)
FAN_DIMS = {
    "SK 3239.100": (255.0, 255.0, 105.0),
    "SK 3240.100": (323.0, 323.0, 130.0),
    "SK 3243.100": (323.0, 323.0, 130.0),
}


def main() -> None:
    dev_path = os.path.join(DATA_DIR, "catalog_devices.json")
    with open(dev_path, encoding="utf-8") as f:
        dev_data = json.load(f)
    existing = {d["part_number"] for d in dev_data["devices"]}
    added = 0
    for dev in NEW_DEVICES:
        if dev["part_number"] in existing:
            print("skip existing:", dev["part_number"])
            continue
        dev_data["devices"].append(dev)
        added += 1
    changed = added > 0
    for pn, (w, h, dep) in FAN_DIMS.items():
        for d in dev_data["devices"]:
            if d["part_number"] == pn and not d.get("width_mm"):
                d["width_mm"], d["height_mm"], d["depth_mm"] = w, h, dep
                changed = True
    if changed:
        with open(dev_path, "w", encoding="utf-8") as f:
            json.dump(dev_data, f, ensure_ascii=False, indent=2)
    print(f"devices: +{added} -> total {len(dev_data['devices'])}")

    curves_path = os.path.join(DATA_DIR, "trip_curves.json")
    with open(curves_path, encoding="utf-8") as f:
        curves_data = json.load(f)
    curves = curves_data.setdefault("curves", {})
    c_added = 0
    for key, val in NEW_CURVES.items():
        if key not in curves:
            curves[key] = val
            c_added += 1
    if c_added:
        with open(curves_path, "w", encoding="utf-8") as f:
            json.dump(curves_data, f, ensure_ascii=False, indent=2)
    print(f"curves: +{c_added} -> total {len(curves)}")

    rules_path = os.path.join(DATA_DIR, "selectivity_rules.json")
    with open(rules_path, encoding="utf-8") as f:
        rules_data = json.load(f)
    rules = rules_data.setdefault("rules", rules_data if isinstance(rules_data, list) else [])
    if isinstance(rules_data, dict):
        rules = rules_data["rules"]
    else:
        rules = rules_data
    r_existing = {(r["upstream_series"], r["downstream_series"]) for r in rules}
    r_added = 0
    for rule in NEW_RULES:
        key = (rule["upstream_series"], rule["downstream_series"])
        if key not in r_existing:
            rules.append(rule)
            r_added += 1
    if r_added:
        if isinstance(rules_data, dict):
            rules_data["rules"] = rules
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump(rules_data, f, ensure_ascii=False, indent=2)
        else:
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"rules: +{r_added} -> total {len(rules)}")


if __name__ == "__main__":
    main()
