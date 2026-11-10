from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec, SpdClass, ValidationStatus


def _run_spd_rules(spd_class=SpdClass.T1, has_external_lps=None, backup_fuse=None):
    project = ProjectSpec(
        project_name="SPD rule 033/034 test",
        prospective_ik_ka=22.0,
        spd_class=spd_class,
        has_external_lps=has_external_lps,
    )
    feeders = [FeederInput(
        feeder_id="F01",
        description="Test feeder",
        load_type=LoadType.SUB_FEEDER,
        power_kw=5.0,
        cos_phi=0.90,
        efficiency=1.0,
    )]
    catalog = CatalogRepository.get_default_catalog()
    catalog = [
        device.model_copy(update={"spd_backup_fuse_a": backup_fuse})
        if device.device_type == "SPD" and device.spd_class == spd_class.value
        else device
        for device in catalog
    ]
    _, _, validations = EngineeringEngine(catalog).process_project(project, feeders)
    return {
        item.rule_id: item
        for item in validations
        if item.rule_id in {"RULE-SPD-033", "RULE-SPD-034", "RULE-SPD-035"}
    }


def test_rule_033_insufficient_when_fuse_is_none():
    rules = _run_spd_rules(backup_fuse=None)
    assert rules["RULE-SPD-033"].status == ValidationStatus.INSUFFICIENT_DATA


def test_rule_033_insufficient_when_fuse_is_zero():
    rules = _run_spd_rules(backup_fuse=0.0)
    assert rules["RULE-SPD-033"].status == ValidationStatus.INSUFFICIENT_DATA


def test_rule_033_completed_when_fuse_valid():
    rules = _run_spd_rules(backup_fuse=315.0)
    assert rules["RULE-SPD-033"].status == ValidationStatus.COMPLETED


def test_rule_034_provisional_when_lps_none():
    rules = _run_spd_rules(has_external_lps=None)
    assert rules["RULE-SPD-034"].status == ValidationStatus.WARNING


def test_rule_034_mismatch_when_lps_false():
    rules = _run_spd_rules(has_external_lps=False)
    assert rules["RULE-SPD-034"].status == ValidationStatus.WARNING


def test_rule_034_completed_when_lps_true():
    rules = _run_spd_rules(has_external_lps=True)
    assert rules["RULE-SPD-034"].status == ValidationStatus.COMPLETED


def test_rule_034_not_emitted_for_t2():
    rules = _run_spd_rules(spd_class=SpdClass.T2)
    assert "RULE-SPD-034" not in rules


def test_rule_035_skipped_when_fuse_is_none():
    rules = _run_spd_rules(backup_fuse=None)
    assert "RULE-SPD-035" not in rules
    assert rules["RULE-SPD-033"].status == ValidationStatus.INSUFFICIENT_DATA
