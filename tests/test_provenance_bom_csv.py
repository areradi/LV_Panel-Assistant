import json
from pathlib import Path

from openpyxl import load_workbook

from lv_assist.bom import build_bom, export_bom_csv, export_bom_excel
from lv_assist.catalog import CatalogRepository
from lv_assist.control_circuits import ControlCircuitGenerator
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec


def _make_project(**overrides):
    values = {
        "project_name": "BOM provenance test",
        "prospective_ik_ka": 25.0,
        "transformer_kva": 630.0,
    }
    values.update(overrides)
    return ProjectSpec(**values)


def _make_feeder(**overrides):
    values = {
        "feeder_id": "F01",
        "description": "Feeder",
        "load_type": LoadType.MOTOR_DOL,
        "power_kw": 5.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _run(project, feeders=None):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    return engine.process_project(project, feeders or [_make_feeder()])


def test_bom_excel_without_provenance_unchanged(tmp_path):
    project = _make_project()
    outputs, summary, _ = _run(project)
    bom = build_bom(project, outputs, summary)
    out = tmp_path / "bom.xlsx"
    export_bom_excel(str(out), bom)
    wb = load_workbook(out)
    assert "04_BOM" in wb.sheetnames
    assert "Provenance" not in wb.sheetnames


def test_bom_excel_with_provenance_adds_sheet(tmp_path):
    project = _make_project()
    outputs, summary, _ = _run(project)
    bom = build_bom(project, outputs, summary)
    provenance = {"Input Hash": "abc123", "Engine Version": "1.0.0"}
    out = tmp_path / "bom.xlsx"
    export_bom_excel(str(out), bom, provenance=provenance)
    wb = load_workbook(out)
    assert "Provenance" in wb.sheetnames
    ws = wb["Provenance"]
    values = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value]
    assert any("Input Hash" in value for value in values)
    assert any("abc123" in value for value in values)


def test_bom_csv_with_provenance_creates_sidecar(tmp_path):
    project = _make_project()
    outputs, summary, _ = _run(project)
    bom = build_bom(project, outputs, summary)
    provenance = {"Input Hash": "def456", "Engine Version": "2.0.0"}
    out = tmp_path / "bom.csv"
    export_bom_csv(str(out), bom, provenance=provenance)
    sidecar = Path(str(out) + ".provenance.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["Input Hash"] == "def456"
    assert data["Engine Version"] == "2.0.0"


def test_connections_csv_creates_sidecar(tmp_path):
    project = _make_project()
    outputs, summary, _ = _run(project)
    out = tmp_path / "connections.csv"
    ControlCircuitGenerator.export_connections_csv(str(out), project, outputs, summary)
    sidecar = Path(str(out) + ".provenance.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "Input Hash" in data
    assert data["Input Hash"] in (summary.verified_input_hash, "not recorded")


def test_connections_csv_rows_unchanged(tmp_path):
    project = _make_project()
    outputs, summary, _ = _run(project)
    out = tmp_path / "connections.csv"
    ControlCircuitGenerator.export_connections_csv(str(out), project, outputs, summary)
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert len(lines) > 1
    assert lines[0].count(",") >= 7
