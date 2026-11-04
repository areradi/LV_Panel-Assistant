import math

import pytest
from pydantic import ValidationError

from lv_assist.engine import EngineeringEngine
from lv_assist.excel_clipboard import ExcelClipboardParser
from lv_assist.models import FeederInput, LoadType, ProjectSpec


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
