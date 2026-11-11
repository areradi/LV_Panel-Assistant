import csv
from types import SimpleNamespace

from lv_assist.exporters import _csv_safe, _xl_safe


def test_xl_safe_blocks_classic_prefixes():
    payloads = [
        "=cmd|'/c calc'!A0",
        '=HYPERLINK("http://evil.com","x")',
        "+cmd",
        "-1+1",
        "@SUM(1+1)",
    ]
    for payload in payloads:
        assert _xl_safe(payload).startswith("'"), f"Should neutralize: {payload!r}"


def test_xl_safe_blocks_control_chars_before_prefix():
    for payload in ("\t=cmd", "\n=cmd", "\r=cmd", "  =cmd"):
        assert _xl_safe(payload).startswith("'"), f"Should neutralize: {payload!r}"


def test_xl_safe_passes_safe_values():
    assert _xl_safe("hello") == "hello"
    assert _xl_safe("PWR1") == "PWR1"
    assert _xl_safe("") == ""
    assert _xl_safe(None) is None
    assert _xl_safe(42) == 42


def test_csv_safe_uses_tab_prefix():
    for payload in ("=cmd", "+cmd", "-1+1", "@SUM(1+1)"):
        result = _csv_safe(payload)
        assert result.startswith("\t")
        assert result[1:] == payload


def test_csv_safe_passes_safe_values():
    assert _csv_safe("hello") == "hello"
    assert _csv_safe(None) is None


def _bom_item(**overrides):
    from lv_assist.bom import BomItem

    values = {
        "item_no": 1,
        "tag": "=INCOMING",
        "category": "Control",
        "description": "@evil",
        "manufacturer": "ACME",
        "part_number": "=cmd",
        "tech_spec": "+details",
        "qty": 1,
        "unit": "pcs",
        "panel": "MCC",
        "func_loc": "=INCOMING+MCC1",
    }
    values.update(overrides)
    return BomItem(**values)


def test_bom_excel_neutralizes_formula(tmp_path):
    from openpyxl import load_workbook
    from lv_assist.bom import export_bom_excel

    out = tmp_path / "bom.xlsx"
    export_bom_excel(str(out), [_bom_item()])
    ws = load_workbook(out)["04_BOM"]
    assert ws.cell(row=2, column=6).value == "'=cmd"
    assert ws.cell(row=2, column=4).value == "'@evil"


def test_bom_csv_neutralizes_formula(tmp_path):
    from lv_assist.bom import export_bom_csv

    out = tmp_path / "bom.csv"
    export_bom_csv(str(out), [_bom_item()])
    with open(out, encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.reader(fp))
    assert rows[1][5] == "\t=cmd"
    assert rows[1][3] == "\t@evil"


def test_connections_csv_neutralizes_formula(tmp_path, monkeypatch):
    import lv_assist.control_circuits as control_module
    from lv_assist.control_circuits import ControlCircuitGenerator

    wire = SimpleNamespace(
        wire_no="W01-01",
        from_dev="=evil",
        from_term="1",
        to_dev="@cmd",
        to_term="2",
        cross_section_mm2=1.5,
        color="BU",
        remark="safe remark",
    )
    monkeypatch.setattr(control_module, "require_current_calculation", lambda *args: None)
    monkeypatch.setattr(
        ControlCircuitGenerator,
        "build_all_wires",
        classmethod(lambda cls, *args: [wire]),
    )
    out = tmp_path / "connections.csv"
    ControlCircuitGenerator.export_connections_csv(str(out), None, [], None)
    with open(out, encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.reader(fp))
    assert rows[1][1] == "\t=evil"
    assert rows[1][3] == "\t@cmd"


def test_main_xlsx_safe_helper_regression():
    assert _xl_safe("=HYPERLINK()") == "'=HYPERLINK()"
    assert _xl_safe("hello") == "hello"
