import json
import sqlite3

import pytest

from lv_assist.catalog import CatalogRepository, SiemensSelectivityRepository
from lv_assist.models import CatalogDevice, SelectivityEvalState, SelectivityRuleRecord
from migrate_to_sqlite import SCHEMA_SQL, migrate_selectivity_and_curves


def pair():
    return (
        CatalogDevice(part_number='TEST-U', manufacturer='TEST OEM', series='UP',
                      device_type='MCCB', rated_current_in_a=100),
        CatalogDevice(part_number='TEST-D', manufacturer='TEST OEM', series='DOWN',
                      device_type='MCB', rated_current_in_a=90),
    )


def reviewed_rule(**changes):
    values = dict(upstream_series='UP', upstream_min_in_a=100, downstream_series='DOWN',
                  downstream_max_in_a=90, selectivity_limit_is_ka=20, catalog_reference='TEST FIXTURE ONLY',
                  manufacturer='TEST OEM', datasheet_revision='TEST REV', source_page=4,
                  table_ref='TEST TABLE', voltage_v=400, upstream_part_numbers=['TEST-U'],
                  downstream_part_numbers=['TEST-D'], data_quality='REAL_VERIFIED',
                  is_verified_manufacturer_rule=True)
    values.update(changes)
    return SelectivityRuleRecord(**values)


def use_rule(monkeypatch, rule):
    monkeypatch.setattr(SiemensSelectivityRepository, 'get_selectivity_rules', classmethod(lambda cls: [rule]))


def test_explicit_oem_table_precedes_rating_ratio(monkeypatch):
    use_rule(monkeypatch, reviewed_rule())
    up, down = pair()
    assert SiemensSelectivityRepository.evaluate_pair(up, down, 15)[:2] == (SelectivityEvalState.VERIFIED_TOTAL, 20)
    assert SiemensSelectivityRepository.evaluate_pair(up, down, 25)[:2] == (SelectivityEvalState.VERIFIED_PARTIAL, 20)


@pytest.mark.parametrize('changes', [
    {'manufacturer': None}, {'datasheet_revision': None}, {'source_page': None}, {'table_ref': None},
    {'voltage_v': None}, {'upstream_part_numbers': []}, {'downstream_part_numbers': []},
    {'catalog_reference': 'Verified Entry'}, {'data_quality': 'UNVERIFIED'},
    {'is_verified_manufacturer_rule': False}, {'upstream_max_in_a': 50},
])
def test_incomplete_evidence_cannot_verify(monkeypatch, changes):
    rule = reviewed_rule(**changes)
    assert not rule.has_verified_source
    use_rule(monkeypatch, rule)
    state, _, _ = SiemensSelectivityRepository.evaluate_pair(*pair(), 15)
    assert state not in (SelectivityEvalState.VERIFIED_TOTAL, SelectivityEvalState.VERIFIED_PARTIAL)


@pytest.mark.parametrize('field,value', [('manufacturer', 'OTHER'), ('part_number', 'OTHER')])
@pytest.mark.parametrize('side', [0, 1])
def test_table_cannot_apply_to_other_manufacturer_or_part(monkeypatch, field, value, side):
    use_rule(monkeypatch, reviewed_rule())
    devices = pair()
    setattr(devices[side], field, value)
    state, _, _ = SiemensSelectivityRepository.evaluate_pair(*devices, 15)
    assert state not in (SelectivityEvalState.VERIFIED_TOTAL, SelectivityEvalState.VERIFIED_PARTIAL)


@pytest.mark.parametrize('fault,voltage', [(15, 415), (float('nan'), 400), (float('inf'), 400),
                                         (0, 400), (-1, 400), (15, float('nan'))])
def test_fault_and_voltage_must_match_table_scope(monkeypatch, fault, voltage):
    use_rule(monkeypatch, reviewed_rule())
    state, _, _ = SiemensSelectivityRepository.evaluate_pair(*pair(), fault, voltage_v=voltage)
    assert state not in (SelectivityEvalState.VERIFIED_TOTAL, SelectivityEvalState.VERIFIED_PARTIAL)


def test_migration_does_not_invent_manufacturer_verification(tmp_path):
    legacy = reviewed_rule().model_dump(mode='json')
    for key in ['manufacturer', 'datasheet_revision', 'source_page', 'table_ref', 'voltage_v',
                'upstream_part_numbers', 'downstream_part_numbers', 'data_quality', 'is_verified_manufacturer_rule']:
        legacy.pop(key)
    (tmp_path / 'selectivity_rules.json').write_text(json.dumps({'rules': [legacy, reviewed_rule(voltage_v=415).model_dump(mode='json')]}))
    db = tmp_path / 'catalog.db'
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA_SQL)
        migrate_selectivity_and_curves(conn, tmp_path)
        rows = conn.execute('SELECT is_verified_manufacturer_rule, voltage_v FROM selectivity_rules ORDER BY rule_id').fetchall()
        assert rows == [(0, 400), (1, 415)]
        conn.commit()
    rules = CatalogRepository(db).selectivity_rules
    assert not rules[0].has_verified_source
    assert rules[1].has_verified_source


def test_legacy_database_flag_alone_is_not_evidence(tmp_path):
    db = tmp_path / 'old.db'
    legacy = dict(upstream_series='UP', upstream_min_in_a=100, downstream_series='DOWN',
                  downstream_max_in_a=90, selectivity_limit_is_ka=55, catalog_reference='Unreviewed legacy text')
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute('INSERT INTO selectivity_rules (upstream_series, downstream_series, selectivity_type, raw_json) VALUES (?, ?, ?, ?)',
                     ('UP', 'DOWN', 'VERIFIED_TOTAL', json.dumps(legacy)))
    assert not CatalogRepository(db).selectivity_rules[0].has_verified_source
