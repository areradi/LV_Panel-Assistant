from lv_assist.catalog import TripCurveRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import CatalogDevice, FeederInput, LoadType, ProjectSpec


def _unknown_supply_case():
    project = ProjectSpec(
        project_name="Unknown fault current",
        prospective_ik_ka=None,
        transformer_kva=None,
    )
    feeder = FeederInput(
        feeder_id="F01",
        description="Test feeder",
        load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
        cos_phi=0.9,
        efficiency=1.0,
    )
    outputs, _, validations = EngineeringEngine([]).process_project(project, [feeder])
    return outputs[0], validations


def test_no_ik_no_protection_selected_pe_is_none():
    output, _ = _unknown_supply_case()

    assert output.selected_pe_mm2 is None


def test_no_ik_no_protection_clearing_time_is_none():
    output, _ = _unknown_supply_case()

    assert output.clearing_time_s is None


def test_no_ik_pe_basis_str_does_not_crash():
    output, _ = _unknown_supply_case()

    assert "مبنای آدیاباتیک قابل محاسبه نیست" in output.pe_basis_str


def test_no_ik_emits_rule_fault_noik_fallback_001():
    _, validations = _unknown_supply_case()

    rule = next(
        (item for item in validations if item.rule_id == "RULE-FAULT-NOIK-FALLBACK-001"),
        None,
    )
    assert rule is not None
    assert rule.status.value == "INSUFFICIENT_DATA"


def test_candidate_fault_compatible_returns_false_without_ik():
    engine = EngineeringEngine([])
    project = ProjectSpec(
        project_name="Unknown fault current",
        prospective_ik_ka=None,
        transformer_kva=None,
    )
    feeder = FeederInput(
        feeder_id="F01",
        description="Test feeder",
        load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
    )
    protection = CatalogDevice(
        part_number="TEST-1",
        manufacturer="Test",
        series="Test series",
        device_type="MCCB",
    )

    assert engine._candidate_fault_compatible(
        project, feeder, protection, 2.5, None, None, None, None
    ) is False


def test_infinite_clear_time_emits_insufficient_data_rule(monkeypatch):
    monkeypatch.setattr(
        TripCurveRepository,
        "instantaneous_band_a",
        lambda series, rated_current: (1e9, 1e9),
    )
    monkeypatch.setattr(TripCurveRepository, "thermal_time_s", lambda series, mult: None)
    project = ProjectSpec(project_name="Invalid protection curve", prospective_ik_ka=10.0)
    feeder = FeederInput(
        feeder_id="F01",
        description="Test feeder",
        load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
        cos_phi=0.9,
        efficiency=1.0,
    )
    protection = CatalogDevice(
        part_number="TEST-MCB-16",
        manufacturer="Test",
        series="TEST",
        device_type="MCB",
        rated_current_in_a=16.0,
        icu_ka_400v=25.0,
    )

    outputs, _, validations = EngineeringEngine([protection]).process_project(project, [feeder])

    assert outputs[0].clearing_time_s is None
    assert outputs[0].selected_pe_mm2 is None
    rule = next(
        (item for item in validations if item.rule_id == "RULE-FAULT-NOIK-FALLBACK-001"),
        None,
    )
    assert rule is not None
    assert rule.status.value == "INSUFFICIENT_DATA"
