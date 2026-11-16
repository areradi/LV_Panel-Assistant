from openpyxl import load_workbook

from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.models import FeederInput, LoadType, ProjectSpec


def _make_project(**overrides):
    values = {
        "project_name": "Provenance test",
        "prospective_ik_ka": 25.0,
        "transformer_kva": 630.0,
    }
    values.update(overrides)
    return ProjectSpec(**values)


def _make_feeder(**overrides):
    values = {
        "feeder_id": "F01",
        "description": "Feeder",
        "load_type": LoadType.SUB_FEEDER,
        "power_kw": 5.0,
    }
    values.update(overrides)
    return FeederInput(**values)


def _run(project, feeders=None):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    return engine.process_project(project, feeders or [_make_feeder()])


def test_excel_contains_input_hash_in_summary(tmp_path):
    project = _make_project()
    outputs, summary, validations = _run(project)
    out = tmp_path / "out.xlsx"
    ExcelExporter.export_to_excel(str(out), project, outputs, summary, validations)
    ws = load_workbook(out)["01_Project_Summary"]
    values = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value]
    assert any("Input Hash" in value for value in values)
    assert any(summary.verified_input_hash in value for value in values if summary.verified_input_hash)


def test_excel_contains_version_provenance(tmp_path):
    project = _make_project()
    outputs, summary, validations = _run(project)
    out = tmp_path / "out.xlsx"
    ExcelExporter.export_to_excel(str(out), project, outputs, summary, validations)
    ws = load_workbook(out)["01_Project_Summary"]
    values = [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value]
    assert any("Calculated At" in value for value in values)
    assert any("Report Generated At" in value for value in values)


def test_html_contains_provenance_block(tmp_path):
    project = _make_project()
    outputs, summary, validations = _run(project)
    out = tmp_path / "report.html"
    PrintableReportExporter.generate_html_report(
        str(out), project, outputs, summary, validations
    )
    content = out.read_text(encoding="utf-8")
    assert '<div class="provenance"' in content
    assert "Input Hash" in content
    assert "Calculated At" in content
    if summary.verified_input_hash:
        assert summary.verified_input_hash in content


def test_html_handles_missing_metadata_as_not_recorded(tmp_path):
    project = _make_project()
    outputs, summary, validations = _run(project)
    summary.engine_version = None
    summary.calculated_at = None
    out = tmp_path / "report.html"
    PrintableReportExporter.generate_html_report(
        str(out), project, outputs, summary, validations
    )
    content = out.read_text(encoding="utf-8")
    assert "not recorded" in content
