from datetime import datetime

from lv_assist.calculation_state import require_current_calculation
from lv_assist.catalog import CatalogRepository
from lv_assist.engine import EngineeringEngine
from lv_assist.models import FeederInput, LoadType, ProjectSpec, compute_input_hash


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


def test_summary_has_engine_version():
    _, summary, _ = _run(_make_project())
    assert summary.engine_version is None or summary.engine_version.strip()


def test_summary_has_catalog_revision_or_none():
    _, summary, _ = _run(_make_project())
    assert summary.catalog_revision is None or len(summary.catalog_revision) == 64


def test_summary_has_rules_revision_or_none():
    _, summary, _ = _run(_make_project())
    assert summary.rules_revision is None or len(summary.rules_revision) == 64


def test_summary_has_calculated_at_iso():
    _, summary, _ = _run(_make_project())
    assert summary.calculated_at is not None
    calculated_at = datetime.fromisoformat(summary.calculated_at)
    assert calculated_at.tzinfo is not None


def test_input_hash_unchanged_by_metadata():
    project, feeders = _make_project(), [_make_feeder()]
    before = compute_input_hash(project, feeders)
    _, summary, _ = _run(project, feeders)
    summary.engine_version = "different-engine"
    summary.catalog_revision = "a" * 64
    summary.rules_revision = "b" * 64
    summary.calculated_at = "2000-01-01T00:00:00+00:00"
    after = compute_input_hash(project, feeders)
    assert after == before


def test_require_current_calculation_works_with_metadata():
    project = _make_project()
    outputs, summary, _ = _run(project)
    require_current_calculation(project, summary, outputs)


def test_legacy_result_with_none_metadata_still_passes_input_hash():
    project = _make_project()
    _, summary, _ = _run(project)
    summary.engine_version = None
    summary.catalog_revision = None
    summary.rules_revision = None
    summary.calculated_at = None
    require_current_calculation(project, summary)


def test_legacy_result_changed_input_is_rejected():
    project = _make_project()
    _, summary, _ = _run(project)
    project.ambient_temp_c = 45.0
    try:
        require_current_calculation(project, summary)
    except ValueError as exc:
        assert "STALE" in str(exc)
    else:
        raise AssertionError("Changed inputs must be rejected as stale")
