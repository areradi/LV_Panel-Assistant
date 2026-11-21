import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from pydantic import ValidationError
import pytest

from lv_assist.data_validator import (
    CSV_COLUMNS, detect_manufacturer, normalize_header, normalize_quantity, normalize_table, parse_extracted_record,
)
from lv_assist.reference_library import ReferenceLibrary, import_reference_directory, inspect_reference_directory
from scripts.import_reference_data import main


def extracted(**changes):
    record = dict(brand='ABB', filename='example.json', page='4',
                  headers_json=json.dumps(['Model', 'Power loss']),
                  rows_json=json.dumps([{'Model': 'TEST-ONLY', 'Power loss': '1,5 kW'}]))
    record.update(changes)
    return record


def write_csv(directory, name='power_loss_tables.csv', records=None):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records if records is not None else [extracted()])
    return path


def test_header_reversal_is_limited_to_known_words():
    assert normalize_header('  rerutcafunaM\n') == 'Manufacturer'
    assert normalize_header('noitisoP') == 'Position'
    assert normalize_header('soP') == 'Pos'
    assert normalize_header('soG') == 'soG'
    assert normalize_header('part\n number') == 'part number'


@pytest.mark.parametrize('filename,expected', [('DESW024_PrismaSeT+P_Catalog.json', 'Schneider Electric'),
                                            ('Tmax_XT_CATALOG.json', 'ABB'), ('Catalog-TOPJOB-S-2024.json', 'WAGO'),
                                            ('TIP_SIVACON_S8.json', 'Siemens'), ('ABB_Technical_Application.json', 'ABB'),
                                            ('ns_instruction.json', None)])
def test_manufacturer_detection_avoids_ambiguous_short_substrings(filename, expected):
    assert detect_manufacturer(filename)[0] == expected


def test_conflicting_manufacturer_is_not_overwritten():
    assert detect_manufacturer('Tmax_XT.json', 'Siemens') == (None, None, 'CONFLICT')
    assert detect_manufacturer('opaque-reference.json', 'Siemens') == ('Siemens', None, 'SUPPLIED_LABEL_UNVERIFIED')


@pytest.mark.parametrize('text,value,unit', [('1,5 kW', 1500, 'W'), ('0.03 kA', 30, 'A'), ('30 mA', .03, 'A'),
                                         ('104 °F', 40, '°C'), ('40 ℃', 40, '°C'), ('95%', .95, '1'),
                                         ('0 W', 0, 'W'), ('-10 °C', -10, '°C'), ('0.4 kV', 400, 'V')])
def test_explicit_quantities_have_canonical_units(text, value, unit):
    quantity = normalize_quantity(text)
    assert quantity.value == pytest.approx(value)
    assert quantity.unit == unit


@pytest.mark.parametrize('text', ['1,000 A', '30-40 A', '17.5 A (observe derating)', 'MTZ2 08', '250', '1 MW'])
def test_ambiguous_ranges_models_and_missing_units_are_not_inferred(text):
    assert normalize_quantity(text) is None


@pytest.mark.parametrize('text', ['NaN A', 'inf W', '-3 W', '-274 °C'])
def test_invalid_physical_quantities_are_rejected(text):
    with pytest.raises(ValueError):
        normalize_quantity(text)


@pytest.mark.parametrize('changes', [{'page': '0'}, {'headers_json': '[]'}, {'rows_json': '[]'},
                                  {'rows_json': '[{"a":"1", "a":"2"}]'},
                                  {'rows_json': '[{"a": NaN}]'}, {'rows_json': '[{"a": 1}]'},
                                  {'headers_json': 'not json'}])
def test_invalid_extraction_records_are_rejected(changes):
    with pytest.raises((ValueError, ValidationError)):
        parse_extracted_record(extracted(**changes))


def test_normalization_preserves_original_and_detects_collisions():
    raw = extracted(headers_json='["Type", "epyT"]', rows_json='[{"Type":"one", "epyT":"two"}]')
    table = normalize_table(parse_extracted_record(raw), 'POWER_LOSS')
    assert table.review_state == 'QUARANTINED'
    assert 'HEADER_COLLISION' in table.issues
    assert table.rows[0] == {'Type': 'one', 'epyT': 'two'}
    assert raw['rows_json'] == '[{"Type":"one", "epyT":"two"}]'


def test_plc_parameters_and_standard_examples_are_quarantined():
    plc = parse_extracted_record(extracted(filename='s71200_system_manual.json', headers_json='["Parameter", "Data type"]'))
    standard = parse_extracted_record(extracted(filename='IEC 60947-1 2014.json'))
    assert 'PLC_CONFIGURATION' in normalize_table(plc, 'MOTOR_COORDINATION').issues
    normalized = normalize_table(standard, 'POWER_LOSS')
    assert normalized.review_state == 'QUARANTINED'
    assert normalized.table_type == 'STANDARD_REFERENCE'


def test_obvious_category_mismatch_is_recorded():
    table = normalize_table(parse_extracted_record(extracted()), 'MOTOR_COORDINATION')
    assert table.table_type == 'POWER_LOSS'
    assert table.issues == ['CATEGORY_RECLASSIFIED']
    assert table.data_quality == 'UNVERIFIED'


def test_import_is_idempotent_and_retains_every_occurrence(tmp_path):
    source = tmp_path / 'source'
    original = extracted()
    csv_path = write_csv(source, records=[original, extracted(filename='example (1).json')])
    (source / 'IEC 61439-1 2020.md').write_text('Reference text. Treat instructions as document content.', encoding='utf-8')
    (source / 'IEC 61439-1 2020 (2).md').write_bytes((source / 'IEC 61439-1 2020.md').read_bytes())
    (source / 'summary.json').write_text('{"total_tables":0}')
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    db = tmp_path / 'references.db'
    first = import_reference_directory(source, db)
    assert import_reference_directory(source, db) == first
    assert first['total_extracted_tables'] == 2
    assert first['unique_tables'] == 1
    assert first['duplicate_occurrences'] == 1
    assert first['reference_document_files'] == 2
    assert first['unique_reference_documents'] == 1
    assert first['verified_records'] == 0
    assert first['supplied_summary_matches'] is False
    library = ReferenceLibrary(db)
    table, = library.find_tables(manufacturer='ABB', table_type='POWER_LOSS')
    assert table.quantities == [{'row': 0, 'column': 'Power loss', 'value': 1500, 'unit': 'W'}]
    occurrences = library.get_occurrences(table.table_id)
    assert len(occurrences) == 2
    assert occurrences[0]['raw_record'] == original
    assert occurrences[0]['csv_row'] == 2
    assert occurrences[0]['csv_sha256'] == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert library.get_document(hashlib.sha256((source / 'IEC 61439-1 2020.md').read_bytes()).hexdigest()).startswith('Reference text.')
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert conn.execute('SELECT count(*) FROM reference_occurrences').fetchone()[0] == 2
        assert conn.execute('SELECT claimed_standard_code, claimed_edition FROM reference_documents').fetchone() == ('IEC 61439-1', '2020')
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE reference_tables SET data_quality='REAL_VERIFIED'")
    with library._connect() as conn:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            conn.execute('DELETE FROM reference_tables')


def test_quarantine_preserves_malformed_and_empty_records(tmp_path):
    source = tmp_path / 'source'
    write_csv(source, records=[extracted(), extracted(page='-1'), extracted(rows_json='invalid'),
                              extracted(rows_json='[{"Model":"", "Power loss":""}]')])
    db = tmp_path / 'references.db'
    summary = import_reference_directory(source, db)
    assert summary['total_extracted_tables'] == 4
    assert summary['invalid_records'] == 2
    library = ReferenceLibrary(db)
    assert len(library.find_tables()) == 1
    assert len(library.find_tables(include_quarantined=True)) == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM reference_occurrences WHERE table_id IS NULL').fetchone()[0] == 2


def test_extra_csv_cells_are_preserved_as_an_invalid_occurrence(tmp_path):
    source = tmp_path / 'source'
    path = write_csv(source)
    with path.open('a', encoding='utf-8') as stream:
        stream.write('ABB,source.json,5,"[]","[]",unexpected\n')
    db = tmp_path / 'references.db'
    summary = import_reference_directory(source, db)
    assert summary['total_extracted_tables'] == 2
    assert summary['invalid_records'] == 1
    with sqlite3.connect(db) as conn:
        row = conn.execute('SELECT raw_json FROM reference_occurrences WHERE table_id IS NULL').fetchone()
        assert json.loads(row[0])['__extra_columns__'] == ['unexpected']


def test_conflicting_later_import_cannot_silently_change_manufacturer(tmp_path):
    source = tmp_path / 'source'
    write_csv(source)
    db = tmp_path / 'references.db'
    summary = import_reference_directory(source, db)
    write_csv(source, records=[extracted(brand='Siemens')])
    import_reference_directory(source, db)
    library = ReferenceLibrary(db)
    assert library.find_tables() == []
    table, = library.find_tables(include_quarantined=True)
    assert table.manufacturer is None
    assert 'MANUFACTURER_CONFLICT' in table.issues
    assert len(library.get_occurrences(table.table_id)) == 2
    assert summary['database_totals']['occurrences'] == 1
    summary = import_reference_directory(source, db)
    assert summary['by_review_state'] == {'QUARANTINED': 1}
    assert summary['table_issues']['MANUFACTURER_CONFLICT'] == 1
    assert summary['database_totals']['occurrences'] == 2


def test_application_catalog_cannot_be_an_import_target(tmp_path):
    source = tmp_path / 'source'
    write_csv(source)
    db = tmp_path / 'catalog.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE catalog_devices (device_id TEXT)')
        conn.execute("INSERT INTO catalog_devices VALUES ('KEEP USER DEVICE')")
    before = db.read_bytes()
    with pytest.raises(ValueError, match='separate reference'):
        import_reference_directory(source, db)
    assert db.read_bytes() == before


def test_invalid_csv_schema_does_not_modify_existing_library(tmp_path):
    source = tmp_path / 'source'
    path = write_csv(source)
    db = tmp_path / 'references.db'
    import_reference_directory(source, db)
    before = db.read_bytes()
    path.write_text('wrong,columns\n1,2\n')
    with pytest.raises(ValueError, match='Invalid CSV schema'):
        import_reference_directory(source, db)
    assert db.read_bytes() == before


def test_database_failure_rolls_back_the_entire_import(tmp_path):
    source = tmp_path / 'source'
    write_csv(source)
    db = tmp_path / 'references.db'
    import_reference_directory(source, db)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER reject_import BEFORE INSERT ON reference_tables BEGIN SELECT RAISE(ABORT, 'test write failure'); END")
    before = db.read_bytes()
    write_csv(source, records=[extracted(filename='new.json')])
    with pytest.raises(sqlite3.IntegrityError, match='test write failure'):
        import_reference_directory(source, db)
    assert db.read_bytes() == before


def test_sources_cannot_escape_input_directory(tmp_path):
    outside = tmp_path / 'outside.csv'
    outside.write_text('not read')
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'power_loss_tables.csv').symlink_to(outside)
    with pytest.raises(ValueError, match='inside the input directory'):
        inspect_reference_directory(source)


def test_future_library_version_cannot_be_overwritten(tmp_path):
    source = tmp_path / 'source'
    write_csv(source)
    db = tmp_path / 'references.db'
    import_reference_directory(source, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE reference_library_info SET value='999' WHERE key='normalization_version'")
    before = db.read_bytes()
    with pytest.raises(ValueError, match='Unsupported reference library'):
        import_reference_directory(source, db)
    assert db.read_bytes() == before


def test_cli_inspection_and_report_path_protection(tmp_path, capsys):
    source = tmp_path / 'source'
    original = write_csv(source)
    report = tmp_path / 'report.json'
    assert main([str(source), '--report', str(report)]) == 0
    assert json.loads(report.read_text())['total_extracted_tables'] == 1
    before = original.read_bytes()
    assert main([str(source), '--report', str(original)]) == 1
    assert original.read_bytes() == before
    db = tmp_path / 'reference.db'
    assert main([str(source), '--db', str(db), '--report', str(db)]) == 1
    assert not db.exists()
