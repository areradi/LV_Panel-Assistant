import csv
from types import SimpleNamespace


def test_eplan_csv_sanitizes_data_without_changing_headers(tmp_path, monkeypatch):
    import lv_assist.outputs as outputs

    device = SimpleNamespace(
        part_number="=cmd|'/c calc'!A0",
        series="+HYPERLINK(\"https://example.invalid\")",
        device_type="MCCB",
        manufacturer="@SUM(1+1)",
        data_quality=SimpleNamespace(value="VERIFIED_OEM_CATALOG"),
        rated_current_in_a=16.0,
        icu_ka_400v=25.0,
        power_loss_w=1.2,
        width_mm=45.0,
        height_mm=100.0,
        depth_mm=80.0,
    )
    entries = [("=FUNC", "", "-B1", "+category", device, "", 1)]
    monkeypatch.setattr(outputs, "require_current_calculation", lambda *args: None)
    monkeypatch.setattr(outputs, "_bom_entries", lambda *args: entries)

    path = tmp_path / "eplan.csv"
    outputs.EplanExporter.export_csv(str(path), object(), [], object())

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == outputs.EplanExporter.HEADERS
    assert rows[1][0].startswith("\t=")
    assert rows[1][1].startswith("\t+")
    assert rows[1][2].startswith("\t@")
    assert rows[1][4].startswith("\t=")
    assert rows[1][5].startswith("\t+")


def test_eplan_parts_csv_sanitizes_data_without_changing_headers(tmp_path, monkeypatch):
    import lv_assist.outputs as outputs

    device = SimpleNamespace(
        part_number="=cmd|'/c calc'!A0",
        series="+HYPERLINK(\"https://example.invalid\")",
        device_type="MCCB",
        manufacturer="@SUM(1+1)",
        rated_current_in_a=16.0,
        icu_ka_400v=25.0,
        power_loss_w=1.2,
        width_mm=45.0,
        height_mm=100.0,
        depth_mm=80.0,
    )
    entries = [("", "", "", "", device, "", 1)]
    monkeypatch.setattr(outputs, "require_current_calculation", lambda *args: None)
    monkeypatch.setattr(outputs, "_bom_entries", lambda *args: entries)

    path = tmp_path / "eplan-parts.csv"
    outputs.EplanPartsExporter.export_csv(str(path), object(), [], object())

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == outputs.EplanPartsExporter.HEADERS
    assert rows[1][0].startswith("\t=")
    assert rows[1][1].startswith("\t=")
    assert rows[1][3].startswith("\t@")
    assert rows[1][4].startswith("\t+")


def test_pydantic_dependency_floor_excludes_advisory_affected_versions():
    from pathlib import Path

    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    pydantic_line = next(
        line.strip()
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip().lower().startswith("pydantic")
    )
    assert pydantic_line == "pydantic>=2.14.2,<3.0"
