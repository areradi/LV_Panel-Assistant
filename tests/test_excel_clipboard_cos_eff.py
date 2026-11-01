# -*- coding: utf-8 -*-
"""P1-A2 tests: cos_phi/efficiency are now parsed and validated."""

from lv_assist.excel_clipboard import ExcelClipboardParser as E


def test_cos_phi_and_efficiency_parsed_when_present():
    raw = (
        "Tag,Desc,Power,Len,Starter,cos_phi,eff\n"
        "F01,Pump,15,50,DOL,0.95,0.99"
    )
    res = E.parse_clipboard_text(raw)
    assert res.errors == []
    r = res.valid_rows[0]
    assert r.cos_phi == 0.95
    assert r.efficiency == 0.99


def test_cos_phi_header_with_space_detected():
    raw = (
        "Tag,Desc,Power,Len,Starter,Cos Phi,Eff\n"
        "F01,Pump,15,50,DOL,0.95,0.99"
    )
    res = E.parse_clipboard_text(raw)
    assert res.errors == []
    assert res.valid_rows[0].cos_phi == 0.95


def test_cos_phi_defaults_when_absent():
    res = E.parse_clipboard_text("F01\tPump\t15\t50\tDOL")
    assert res.errors == []
    assert res.valid_rows[0].cos_phi == 0.85
    assert res.valid_rows[0].efficiency == 0.9


def test_invalid_cos_phi_rejected():
    raw = "Tag,Desc,Power,Len,Starter,cos_phi\nF01,Pump,15,50,DOL,1.5"
    res = E.parse_clipboard_text(raw)
    assert res.valid_rows == []
    assert res.errors[0].column_name == "cos_phi"


def test_invalid_efficiency_rejected():
    raw = "Tag,Desc,Power,Len,Starter,eff\nF01,Pump,15,50,DOL,0"
    res = E.parse_clipboard_text(raw)
    assert res.valid_rows == []
    assert res.errors[0].column_name == "efficiency"
