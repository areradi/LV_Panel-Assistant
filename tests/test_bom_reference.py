from lv_assist.bom import build_bom
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec, SpdClass, feeder_reference_tag


def _make_project_with_feeders(n, with_spd=True):
    project = ProjectSpec(
        project_name=f"Test {n} feeders",
        prospective_ik_ka=25.0,
        spd_class=SpdClass.T2 if with_spd else SpdClass.NONE,
    )
    feeders = [
        FeederInput(
            feeder_id=f"F{i + 1:02d}",
            description=f"Feeder {i + 1}",
            load_type=LoadType.MOTOR_DOL,
            power_kw=5.0,
        )
        for i in range(n)
    ]
    return project, feeders


def _build_bom(project, feeders):
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders)
    return build_bom(project, outputs, summary)


def test_spd_tag_is_f_spd_not_f9():
    project, feeders = _make_project_with_feeders(1)
    bom = _build_bom(project, feeders)
    spd_items = [it for it in bom if it.device and it.device.spd_class]
    assert spd_items, "SPD not found in BOM"
    assert all(it.tag == "-F-SPD" for it in spd_items)


def test_no_duplicate_tags_9_feeders_with_spd():
    project, feeders = _make_project_with_feeders(9)
    bom = _build_bom(project, feeders)
    tags = [it.tag for it in bom if it.tag]
    duplicates = [tag for tag in set(tags) if tags.count(tag) > 1]
    assert not duplicates, f"Duplicate tags: {duplicates}"


def test_no_duplicate_tags_10_feeders_with_spd():
    project, feeders = _make_project_with_feeders(10)
    bom = _build_bom(project, feeders)
    tags = [it.tag for it in bom if it.tag]
    duplicates = [tag for tag in set(tags) if tags.count(tag) > 1]
    assert not duplicates, f"Duplicate tags: {duplicates}"


def test_feeders_1_to_8_reference_tags_unchanged():
    assert [feeder_reference_tag(i, "overload") for i in range(1, 9)] == [
        f"-F{i}" for i in range(1, 9)
    ]


def test_feeder_9_bimetal_tag_remains_f9():
    assert feeder_reference_tag(9, "overload") == "-F9"


def test_bom_excel_exports_with_new_tags(tmp_path):
    from lv_assist.bom import export_bom_excel

    project, feeders = _make_project_with_feeders(3)
    bom = _build_bom(project, feeders)
    out = tmp_path / "bom.xlsx"
    export_bom_excel(str(out), bom)
    assert out.exists()


def test_spd_fuse_tag_is_f_spdf():
    project, feeders = _make_project_with_feeders(1)
    bom = _build_bom(project, feeders)
    fuse_items = [it for it in bom if it.tag == "-F-SPDF"]
    assert fuse_items, "SPD fuse BOM item should use -F-SPDF"
