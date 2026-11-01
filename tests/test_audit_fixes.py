from lv_assist.core_verification import (
    ValidationStatus,
    estimate_clear_time_s,
    calculate_adiabatic_pe_mm2,
    calculate_network_ik_profile,
    verify_breaking_capacity_icu,
    aggregate_status,
)
from lv_assist.catalog_provenance import evaluate_selectivity_status
from lv_assist.excel_clipboard import ExcelClipboardParser


def test_audit_f1_pe_sizing_rejects_trip_time_above_5s_without_silent_cap():
    def mock_thermal_curve(series: str, mult: float) -> float:
        return 12.5

    est = estimate_clear_time_s("MCCB_GENERIC", 3.2, mock_thermal_curve)
    assert est.time_s == 12.5
    assert est.exceeds_adiabatic_5s_limit is True
    assert est.status == ValidationStatus.ERROR

    pe_mm2, check_res = calculate_adiabatic_pe_mm2(fault_current_a=1200.0, trip_estimate=est)
    assert pe_mm2 is None
    assert check_res.status == ValidationStatus.ERROR
    assert "5.0 s" in (check_res.limit_or_reference or "")


def test_audit_f2_transformer_ik_differs_from_feeder_end_ik():
    profile = calculate_network_ik_profile(
        transformer_kva=1000.0,
        uk_percent=6.0,
        line_voltage_v=400.0,
        incomer_cable_length_m=15.0,
        incomer_cable_mm2=240.0,
        feeder_cable_length_m=85.0,
        feeder_phase_mm2=16.0,
        feeder_pe_mm2=16.0,
    )
    assert profile.scope_status == ValidationStatus.COMPLETED
    assert profile.ik_transformer_3p_ka > profile.ik_main_busbar_3p_ka
    assert profile.ik_main_busbar_3p_ka > profile.ik_feeder_end_max_3p_ka
    assert profile.ik_feeder_end_max_3p_ka > profile.ik_feeder_end_min_1p_ka


def test_audit_f3_missing_ik_never_produces_completed_status():
    icu_check = verify_breaking_capacity_icu(device_icu_ka=36.0, prospective_ik_ka=None)
    assert icu_check.status == ValidationStatus.INSUFFICIENT_DATA
    assert aggregate_status([icu_check]) == ValidationStatus.INSUFFICIENT_DATA


def test_audit_f5_preliminary_selectivity_never_marked_completed():
    res = evaluate_selectivity_status(
        upstream_in_a=250.0,
        downstream_in_a=63.0,
        has_manufacturer_coordination_table=False
    )
    assert res.status == ValidationStatus.WARNING
    assert "PRELIMINARY" in (res.limit_or_reference or "")


def test_audit_ux_excel_multirow_paste_and_validation():
    clipboard_data = (
        "BMK\tشرح مصرف کننده\tتوان (kW)\tطول (m)\tنوع راه انداز\n"
        "-Q1\tپمپ خنک کننده ۱\t15.0\t45\tDOL\n"
        "-Q2\tفن سیرکولاسیون\t37.0\t70\tVFD\n"
        "-Q3\tفیدر با توان منفی\t-5.5\t30\tDOL\n"
    )
    parsed = ExcelClipboardParser.parse_clipboard_text(clipboard_data)
    assert len(parsed.valid_rows) == 2
    assert parsed.valid_rows[0].feeder_tag == "-Q1"
    assert parsed.valid_rows[1].starter_type == "VFD"
    assert len(parsed.errors) == 1
    assert parsed.errors[0].row_index == 4
    assert parsed.errors[0].column_name == "power_kw"
