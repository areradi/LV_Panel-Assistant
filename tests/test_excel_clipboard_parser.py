# -*- coding: utf-8 -*-
"""Core behaviour tests for lv_assist.excel_clipboard (no cos/eff yet)."""

from lv_assist.excel_clipboard import (
    ExcelClipboardParser as E,
    ClipboardImportResult,
)


def test_empty_clipboard_returns_single_error():
    res = E.parse_clipboard_text("")
    assert isinstance(res, ClipboardImportResult)
    assert res.valid_rows == []
    assert len(res.errors) == 1
    assert res.errors[0].column_name == "CLIPBOARD"
    assert res.errors[0].row_index == 0


def test_whitespace_only_clipboard_returns_error():
    res = E.parse_clipboard_text("   \n  \n\t")
    assert res.valid_rows == []
    assert len(res.errors) == 1
    assert res.errors[0].column_name == "CLIPBOARD"


def test_default_order_no_header_tab_delimited():
    raw = "F01\tBooster pump\t15\t80\tDOL\nF02\tID fan\t7.5\t30\tVFD"
    res = E.parse_clipboard_text(raw)
    assert res.errors == []
    assert len(res.valid_rows) == 2
    r0 = res.valid_rows[0]
    assert r0.feeder_tag == "F01"
    assert r0.description == "Booster pump"
    assert r0.power_kw == 15.0
    assert r0.length_m == 80.0
    assert r0.starter_type == "DOL"
    r1 = res.valid_rows[1]
    assert r1.feeder_tag == "F02"
    assert r1.power_kw == 7.5
    assert r1.starter_type == "VFD"
    assert res.detected_mapping.get("power_kw") == 2
    assert res.detected_mapping.get("starter_type") == 4


def test_english_header_detected():
    raw = (
        "Tag,Description,Power kW,Length m,Starter,cos_phi,eff\n"
        "Q1,Lighting circuit,2.5,40,RESISTIVE,0.95,0.99\n"
        "Q2,Compressor,30,70,DOL,0.85,0.92"
    )
    res = E.parse_clipboard_text(raw)
    assert res.errors == []
    assert len(res.valid_rows) == 2
    assert "power_kw" in res.detected_mapping
    assert res.detected_mapping["power_kw"] == 2
    r0 = res.valid_rows[0]
    assert r0.feeder_tag == "Q1"
    assert r0.power_kw == 2.5
    assert r0.starter_type == "RESISTIVE"
    assert r0.length_m == 40.0


def test_persian_header_detected():
    raw = "تگ\tشرح\tتوان\tطول\tراه انداز\nF01\tپمپ بوستر\t15\t80\tDOL"
    res = E.parse_clipboard_text(raw)
    assert res.errors == []
    assert len(res.valid_rows) == 1
    assert "power_kw" in res.detected_mapping
    r0 = res.valid_rows[0]
    assert r0.feeder_tag == "F01"
    assert r0.power_kw == 15.0


def test_semicolon_delimiter():
    res = E.parse_clipboard_text("F01;Pump;11;50;DOL")
    assert res.errors == []
    assert res.valid_rows[0].power_kw == 11.0


def test_comma_decimal_in_power():
    res = E.parse_clipboard_text("F01\tPump\t11,5\t50\tDOL")
    assert res.errors == []
    assert res.valid_rows[0].power_kw == 11.5


def test_invalid_power_zero_rejected():
    res = E.parse_clipboard_text("F01\tPump\t0\t50\tDOL")
    assert res.valid_rows == []
    assert len(res.errors) == 1
    assert res.errors[0].column_name == "power_kw"
    assert res.errors[0].row_index == 1


def test_invalid_power_too_large_rejected():
    res = E.parse_clipboard_text("F01\tPump\t5000\t50\tDOL")
    assert res.valid_rows == []
    assert res.errors[0].column_name == "power_kw"


def test_non_numeric_power_rejected():
    res = E.parse_clipboard_text("F01\tPump\tabc\t50\tDOL")
    assert res.valid_rows == []
    assert res.errors[0].column_name == "power_kw"


def test_missing_power_rejected():
    res = E.parse_clipboard_text("F01\tPump\t\t50\tDOL")
    assert res.valid_rows == []
    assert res.errors[0].column_name == "power_kw"


def test_invalid_length_negative_rejected():
    res = E.parse_clipboard_text("F01\tPump\t15\t-10\tDOL")
    assert res.valid_rows == []
    assert res.errors[0].column_name == "length_m"


def test_non_numeric_length_rejected():
    res = E.parse_clipboard_text("F01\tPump\t15\txx\tDOL")
    assert res.valid_rows == []
    assert res.errors[0].column_name == "length_m"


def test_optional_length_blank_allowed():
    res = E.parse_clipboard_text("F01\tPump\t15\t\tDOL")
    assert res.errors == []
    assert res.valid_rows[0].length_m is None


def test_invalid_starter_rejected():
    res = E.parse_clipboard_text("F01\tPump\t15\t50\tBOGUS")
    assert res.valid_rows == []
    assert res.errors[0].column_name == "starter_type"


def test_starter_case_insensitive_uppercased():
    res = E.parse_clipboard_text("F01\tPump\t15\t50\tdol")
    assert res.errors == []
    assert res.valid_rows[0].starter_type == "DOL"


def test_default_starter_when_missing():
    res = E.parse_clipboard_text("F01\tPump\t15")
    assert res.errors == []
    assert res.valid_rows[0].starter_type == "DOL"
    assert res.valid_rows[0].length_m is None


def test_mixed_valid_and_invalid_rows():
    raw = (
        "F01\tGood pump\t15\t50\tDOL\n"
        "F02\tBad power\t0\t50\tDOL\n"
        "F03\tGood fan\t7.5\t30\tVFD\n"
        "F04\tBad starter\t5\t20\tWAT"
    )
    res = E.parse_clipboard_text(raw)
    assert len(res.valid_rows) == 2
    assert {r.feeder_tag for r in res.valid_rows} == {"F01", "F03"}
    assert len(res.errors) == 2
    assert {e.column_name for e in res.errors} == {"power_kw", "starter_type"}


def test_blank_rows_skipped():
    raw = "F01\tPump\t15\t50\tDOL\n\n   \t  \t\t\t\nF02\tFan\t5\t20\tVFD"
    res = E.parse_clipboard_text(raw)
    assert len(res.valid_rows) == 2
