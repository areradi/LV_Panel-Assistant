from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec, SpdClass


def _run_spd_provisional_case(spd_class=SpdClass.T2, has_external_lps=None):
    project = ProjectSpec(
        project_name="SPD provisional status",
        prospective_ik_ka=22.0,
        spd_class=spd_class,
        has_external_lps=has_external_lps,
    )
    assert "has_external_lps" in project.model_dump()
    feeder = FeederInput(
        feeder_id="F01",
        description="Test feeder",
        load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
        cos_phi=0.9,
        efficiency=1.0,
    )
    _, _, validations = EngineeringEngine([]).process_project(project, [feeder])
    return validations


def test_spd_provisional_warning_when_lps_unknown():
    validations = _run_spd_provisional_case(has_external_lps=None)

    rule = next(item for item in validations if item.rule_id == "RULE-SPD-PROVISIONAL")
    assert rule.status.value == "WARNING"


def test_no_provisional_warning_when_lps_known_false():
    validations = _run_spd_provisional_case(has_external_lps=False)

    assert not any(item.rule_id == "RULE-SPD-PROVISIONAL" for item in validations)


def test_no_provisional_warning_when_lps_known_true():
    validations = _run_spd_provisional_case(has_external_lps=True)

    assert not any(item.rule_id == "RULE-SPD-PROVISIONAL" for item in validations)


def test_no_provisional_warning_when_spd_class_none():
    validations = _run_spd_provisional_case(spd_class=SpdClass.NONE)

    assert not any(item.rule_id == "RULE-SPD-PROVISIONAL" for item in validations)
