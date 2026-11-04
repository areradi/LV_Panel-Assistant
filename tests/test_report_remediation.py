import pytest
from pydantic import ValidationError

from lv_assist.engine import EngineeringEngine
from lv_assist.excel_clipboard import ExcelClipboardParser
from lv_assist.models import FeederInput, LoadType, ProjectSpec
from lv_assist.catalog import CatalogRepository
from lv_assist.calculation_state import StaleCalculationStateError, require_current_calculation
from lv_assist.exporters import ExcelExporter, PrintableReportExporter
from lv_assist.gui_output_bridge import GuiOutputBridge
from lv_assist.outputs import SldGenerator
from lv_assist.bom import build_bom


@pytest.fixture
def calculation():
    project = ProjectSpec(project_name="Audit", prospective_ik_ka=10)
    inputs = [feeder(cable_length_m=20)]
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, checks = engine.process_project(project, inputs)
    return project, inputs, outputs, summary, checks, engine


def feeder(**changes):
    return FeederInput(feeder_id="F01", description="Audit load",
                       load_type=LoadType.HEATER_RESISTIVE, power_kw=10, **changes)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_power_rejected_on_creation_and_edit(value):
    with pytest.raises(ValidationError):
        FeederInput(feeder_id="F", description="Invalid", load_type="SUB_FEEDER", power_kw=value)
    item = feeder()
    with pytest.raises(ValidationError):
        item.power_kw = value
    assert item.power_kw == 10


def test_two_phase_input_is_rejected():
    with pytest.raises(ValidationError):
        feeder(phases=2)


@pytest.mark.parametrize("load_type", [LoadType.HEATER_RESISTIVE, LoadType.SUB_FEEDER, LoadType.LIGHTING_SOCKET])
def test_electrical_load_does_not_apply_motor_efficiency(load_type):
    pf, efficiency = EngineeringEngine._resolve_cos_phi_eff(load_type, 0.8, 0.5)
    assert pf == 0.8
    assert efficiency == 1


def test_motor_efficiency_still_converts_shaft_power():
    _, efficiency = EngineeringEngine._resolve_cos_phi_eff(LoadType.MOTOR_DOL, 0.8, 0.9)
    assert 10 / efficiency == pytest.approx(11.111111)


@pytest.mark.parametrize("column", ["power_kw", "length_m"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_clipboard_rejects_nonfinite_values(column, value):
    kw, length = (value, "20") if column == "power_kw" else ("10", value)
    parsed = ExcelClipboardParser.parse_clipboard_text(f"tag\tkw\tlength\nF01\t{kw}\t{length}")
    assert not parsed.valid_rows
    assert parsed.errors[0].column_name == column


def test_assumptions_record_only_omitted_defaults():
    project = ProjectSpec(project_name="Audit", nominal_voltage_v=400)
    assert project.assumed_fields["transformer_uk_pct"] == 6
    assert "nominal_voltage_v" not in project.assumed_fields
    parsed = ExcelClipboardParser.parse_clipboard_text("tag\tkw\nF01\t10")
    assert parsed.valid_rows[0].assumed_fields == {"cos_phi": 0.85, "efficiency": 0.9}


@pytest.mark.parametrize("change", ["temperature", "length", "replacement", "addition"])
def test_direct_exports_reject_changed_inputs_before_writing(calculation, tmp_path, change):
    project, inputs, outputs, summary, checks, engine = calculation
    if change == "temperature":
        project.ambient_temp_c = 45
    elif change == "length":
        inputs[0].cable_length_m = 200
    elif change == "replacement":
        inputs[0] = feeder(cable_length_m=200)
    else:
        inputs.append(FeederInput(
            feeder_id="F02", description="Added", power_kw=1, load_type="SUB_FEEDER"))
    path = tmp_path / "report.xlsx"
    operations = [
        lambda: ExcelExporter.export_to_excel(str(path), project, outputs, summary, checks),
        lambda: PrintableReportExporter.generate_html_report(str(path), project, outputs, summary, checks),
        lambda: GuiOutputBridge.generate_sld_svg(project, outputs, summary),
        lambda: SldGenerator.generate_svg(project, outputs, summary),
        lambda: build_bom(project, outputs, summary),
    ]
    for operation in operations:
        with pytest.raises(StaleCalculationStateError):
            operation()
    assert not path.exists()
    fresh, new_summary, _ = engine.process_project(project, inputs)
    require_current_calculation(project, new_summary, fresh)


def test_mixed_calculation_results_are_rejected(calculation):
    project, inputs, outputs, summary, _, engine = calculation
    inputs[0].cable_length_m = 21
    fresh, new_summary, _ = engine.process_project(project, inputs)
    with pytest.raises(StaleCalculationStateError):
        require_current_calculation(project, new_summary, outputs)
    require_current_calculation(project, new_summary, fresh)


def test_serialized_calculation_remains_verifiable(calculation):
    project, _, outputs, summary, _, _ = calculation
    restored = type(summary).model_validate_json(summary.model_dump_json())
    require_current_calculation(project, restored, outputs)
    restored.calculation_inputs[0].cable_length_m = 200
    with pytest.raises(StaleCalculationStateError):
        require_current_calculation(project, restored, outputs)
