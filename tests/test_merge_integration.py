import sqlite3
import threading
from types import SimpleNamespace

import pytest

from lv_assist.catalog_smart_search import SmartCatalogSearch, normalize_search_text
from lv_assist.gui_helpers import AsyncWebSearchManager, FieldValidationError, parse_cable_length_input
from lv_assist.models import EnclosureMounting, MainBreakerSpec, EnclosureSpec, StepExecState
from lv_assist.summary_workflow import CalculationWorkflowEngine, format_summary_cards


@pytest.mark.parametrize('raw', ['nan', 'NaN', 'inf', '-inf', '0', '-2', 'not a number'])
def test_invalid_cable_length_is_never_a_default(raw):
    with pytest.raises(FieldValidationError):
        parse_cable_length_input(raw, default_if_empty=30)


def test_cable_length_normalizes_persian_decimal():
    assert parse_cable_length_input('۳۰٫۵')[0] == 30.5
    assert parse_cable_length_input('', default_if_empty=30)[0] == 30


def test_summary_retains_actual_in_and_unknown_fields():
    result = format_summary_cards(MainBreakerSpec(in_a=160, part_number='TEST'),
                                  EnclosureSpec(width_mm=800, height_mm=1800, depth_mm=600),
                                  design_current_a=125, na_label='Unknown')
    main = result['main_protection']
    assert '160 A' in main['rated_current_in']
    assert '125 A' in main['design_current']
    assert main['poles'] == main['trip_settings'] == main['breaking_capacity'] == 'Unknown'
    assert '800 mm' in result['enclosure']['width']
    assert not any(c in value for card in result.values() for value in card.values() for c in '\u2066\u2067\u2068\u2069')


def test_workflow_invalidates_upstream_and_downstream_results():
    workflow = CalculationWorkflowEngine()
    for name in workflow.nodes:
        workflow.mark_calculated(name)
    workflow.mark_input_changed('project_inputs')
    assert all(n.exec_state == StepExecState.STALE for n in workflow.nodes.values())


class Scheduler:
    def __init__(self):
        self.owner = threading.get_ident()
        self.pending = []

    def after(self, delay, callback):
        assert threading.get_ident() == self.owner
        self.pending.append(callback)

    def drain(self):
        while self.pending:
            self.pending.pop(0)()


def test_async_results_touch_tk_only_from_main_thread():
    scheduler = Scheduler()
    manager = AsyncWebSearchManager(scheduler, lambda spec: [spec])
    results = []
    manager.start_search('first', lambda: None, results.extend, pytest.fail)
    manager._active_thread.join(timeout=2)
    scheduler.drain()
    assert results == ['first']


def test_new_search_cancels_completed_but_undelivered_result():
    scheduler = Scheduler()
    manager = AsyncWebSearchManager(scheduler, lambda spec: [spec])
    results = []
    manager.start_search('obsolete', lambda: None, results.extend, pytest.fail)
    manager._active_thread.join(timeout=2)
    manager.start_search('current', lambda: None, results.extend, pytest.fail)
    manager._active_thread.join(timeout=2)
    scheduler.drain()
    assert results == ['current']


def test_async_error_survives_worker_exception_scope():
    def fail(spec):
        raise ValueError('network unavailable')
    scheduler = Scheduler()
    manager = AsyncWebSearchManager(scheduler, fail)
    errors = []
    manager.start_search(None, lambda: None, pytest.fail, errors.append)
    manager._active_thread.join(timeout=2)
    scheduler.drain()
    assert errors == ['network unavailable']


def test_search_distinguishes_25a_and_250a():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE catalog_devices (device_id TEXT, manufacturer TEXT, series TEXT, model TEXT, category TEXT, ip_rating TEXT, in_a REAL, poles INTEGER, icu_ka_400v REAL)')
    conn.executemany('INSERT INTO catalog_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     [('Q25', 'Test', 'Series', 'Q25', 'MCCB', '', 25, 3, 25),
                      ('Q250', 'Test', 'Series', 'Q250', 'MCCB', '', 250, 3, 25)])
    search = SmartCatalogSearch(conn)
    ids = lambda q: {r['device_id'] for rows in search.search(q).values() for r in rows}
    assert ids('۲۵a') == {'Q25'}
    assert ids('250a') == {'Q250'}
    assert normalize_search_text('25.0A') == '25 a'
    conn.close()


def test_merged_gui_search_uses_absolute_catalog_path(monkeypatch):
    from lv_assist import gui
    opened = []
    def open_search(path):
        opened.append(path)
        return SimpleNamespace(search=lambda query: {'similar_product': [{'device_id': 'Q25'}]})
    monkeypatch.setattr(gui, 'open_smart_search', open_search)
    assert gui.LVAssistApp._smart_catalog_search_ids(SimpleNamespace(), '25a') == {'Q25'}
    assert opened == [str(gui.DB_PATH)]
    assert gui.DB_PATH.is_absolute()


def test_spd_precheck_retains_unknown_lps_and_unique_rule_ids():
    from lv_assist.gui import build_demo_project
    from lv_assist.engine import EngineeringEngine
    from lv_assist.catalog import CatalogRepository
    project, feeders = build_demo_project()
    project.enclosure_mounting = EnclosureMounting.WALL_MOUNTED
    project.enclosure_width_mm = 1000
    project.enclosure_height_mm = 1800
    project.enclosure_depth_mm = 600
    _, summary, validations = EngineeringEngine(CatalogRepository.get_default_catalog()).process_project(project, feeders)
    precheck = [v for v in validations if v.rule_id == 'RULE-SPD-PRECHECK']
    assert len(precheck) == 1 and 'external_lps' in precheck[0].description
    assert len([v for v in validations if v.rule_id == 'RULE-SPD-035']) == 1
    assert any(v.rule_id == 'SCEN-MOUNTING' for v in validations)
    assert summary.selected_enclosure.enclosure_mounting == project.enclosure_mounting


def test_disabled_export_modules_are_not_reintroduced():
    from importlib.util import find_spec
    for name in ['dxf_export', 'eplan_package', 'eplan_macro', 'eplan_macro_files', 'eplan_field_test']:
        assert find_spec('lv_assist.' + name) is None
