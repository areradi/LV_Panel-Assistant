import pytest

from lv_assist.bom import CATEGORIES, BomItem, build_bom
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import CatalogDevice, FeederInput, LoadType, ProjectSpec


def _make_bom_item(**overrides):
    values = {
        "item_no": 1,
        "tag": "-Q1",
        "category": "Breakers",
        "description": "Test",
        "manufacturer": "ACME",
        "part_number": "PART1",
        "tech_spec": "spec",
        "qty": 1,
        "unit": "pcs",
        "panel": "+MCC1",
        "func_loc": "=F1",
        "notes": "VERIFIED_OEM_CATALOG",
        "item_type": "catalog",
    }
    values.update(overrides)
    return BomItem(**values)


def _validate(items):
    from lv_assist import bom

    bom._validate_final_bom(items)


def test_valid_catalog_item_passes():
    item = _make_bom_item(
        device=CatalogDevice(part_number="PART1", manufacturer="ACME", series="S", device_type="MCCB"),
    )
    _validate([item])


def test_catalog_item_without_device_is_rejected():
    item = _make_bom_item(device=None)
    with pytest.raises(ValueError, match="catalog items missing"):
        _validate([item])


def test_catalog_item_without_verified_evidence_is_rejected():
    device = CatalogDevice(part_number="PART1", manufacturer="ACME", series="S", device_type="MCCB")
    item = _make_bom_item(device=device, notes="PRELIMINARY")
    with pytest.raises(ValueError, match="catalog items missing"):
        _validate([item])


def test_material_with_positive_quantity_and_allowed_unit_passes():
    item = _make_bom_item(item_type="material", device=None, qty=10.0, unit="m")
    _validate([item])


def test_material_without_quantity_is_rejected():
    item = _make_bom_item(item_type="material", device=None, qty=None, unit="m")
    with pytest.raises(ValueError, match="material items missing"):
        _validate([item])


def test_material_with_nonpositive_quantity_is_rejected():
    item = _make_bom_item(item_type="material", device=None, qty=0, unit="pcs")
    with pytest.raises(ValueError, match="material items missing"):
        _validate([item])


def test_material_with_unlisted_unit_is_rejected():
    item = _make_bom_item(item_type="material", device=None, qty=1, unit="foo")
    with pytest.raises(ValueError, match="material items missing"):
        _validate([item])


def test_estimate_is_rejected_and_tag_is_reported():
    item = _make_bom_item(item_type="estimate", tag="-SUG1", device=None)
    with pytest.raises(ValueError, match="estimate items must be resolved") as exc_info:
        _validate([item])
    assert "-SUG1" in str(exc_info.value)


def test_validation_error_lists_all_invalid_tags():
    items = [
        _make_bom_item(item_type="estimate", tag="-SUG1", device=None),
        _make_bom_item(item_type="material", tag="-W-IN", device=None, qty=None, unit="m"),
    ]
    with pytest.raises(ValueError) as exc_info:
        _validate(items)
    assert "-SUG1" in str(exc_info.value)
    assert "-W-IN" in str(exc_info.value)


def test_build_bom_classifies_materials_and_final_still_rejects_estimates():
    project = ProjectSpec(
        project_name="Final BOM test",
        prospective_ik_ka=25.0,
        transformer_kva=630.0,
    )
    feeders = [FeederInput(
        feeder_id="F01", description="Motor feeder", load_type=LoadType.MOTOR_DOL, power_kw=5.0
    )]
    engine = EngineeringEngine(CatalogRepository.get_default_catalog())
    outputs, summary, _ = engine.process_project(project, feeders)
    items = build_bom(project, outputs, summary)
    assert next(item for item in items if item.tag == "-BUS-PH").item_type == "material"
    assert next(item for item in items if item.tag == "-W1").item_type == "material"
    terminals = [item for item in items if item.category == CATEGORIES["TERMINALS"]]
    assert all(item.item_type == "material" for item in terminals)
    with pytest.raises(ValueError, match="Final BOM rejected:"):
        build_bom(project, outputs, summary, final=True)
