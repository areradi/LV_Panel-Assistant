from __future__ import annotations

from collections import Counter
from contextlib import closing
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3

from lv_assist.data_validator import (
    CSV_COLUMNS, NORMALIZATION_VERSION, TABLE_TYPES, ReferenceTable, canonical_json, content_hash,
    normalize_table, parse_extracted_record,
)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS reference_library_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_source_files (
    file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_tables (
    table_id TEXT PRIMARY KEY,
    table_type TEXT NOT NULL,
    manufacturer TEXT,
    source_file TEXT NOT NULL,
    source_page INTEGER NOT NULL CHECK(source_page > 0),
    review_state TEXT NOT NULL CHECK(review_state IN ('PENDING_REVIEW', 'QUARANTINED')),
    data_quality TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK(data_quality = 'UNVERIFIED'),
    normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_occurrences (
    file_id TEXT NOT NULL REFERENCES reference_source_files(file_id),
    csv_row INTEGER NOT NULL,
    table_id TEXT REFERENCES reference_tables(table_id),
    original_type TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    PRIMARY KEY(file_id, csv_row)
);
CREATE TABLE IF NOT EXISTS reference_documents (
    sha256 TEXT PRIMARY KEY,
    text_content TEXT NOT NULL,
    claimed_standard_code TEXT,
    claimed_edition TEXT,
    data_quality TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK(data_quality = 'UNVERIFIED')
);
CREATE INDEX IF NOT EXISTS idx_reference_tables_lookup ON reference_tables(table_type, manufacturer, review_state);
"""


def _read_source(path: Path, root: Path) -> tuple[dict, bytes]:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Reference sources must stay inside the input directory')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    metadata = dict(file_id=content_hash([path.name, digest]), filename=path.name, sha256=digest,
                    size_bytes=len(data), kind=path.suffix.lower().lstrip('.'))
    return metadata, data


def _document_claims(filename: str) -> tuple[str | None, str | None]:
    code = re.search(r'\b(?:IEC(?: (?:TR|TS))?|VDE|DIN)\s+\d+(?:-\d+)*', filename)
    edition = re.search(r'\b(?:19|20)\d{2}\b', filename)
    return code.group().strip() if code else None, edition.group() if edition else None


def _merge_tables(existing: ReferenceTable, incoming: ReferenceTable) -> ReferenceTable:
    issues = set(existing.issues + incoming.issues)
    if existing.manufacturer != incoming.manufacturer:
        issues.add('MANUFACTURER_CONFLICT')
        existing.manufacturer = None
        existing.manufacturer_basis = 'CONFLICT'
    if existing.table_type != incoming.table_type:
        issues.add('CATEGORY_CONFLICT')
        existing.table_type = 'OTHER'
    existing.issues = sorted(issues)
    if issues - {'CATEGORY_RECLASSIFIED'}:
        existing.review_state = 'QUARANTINED'
    return existing


def _table_statistics(tables) -> dict:
    tables = list(tables)
    return dict(by_type=dict(sorted(Counter(t.table_type for t in tables).items())),
                by_manufacturer=dict(sorted(Counter(t.manufacturer or 'Unknown' for t in tables).items())),
                by_review_state=dict(sorted(Counter(t.review_state for t in tables).items())),
                table_issues=dict(sorted(Counter(issue for t in tables for issue in t.issues).items())))


def inspect_reference_directory(directory: Path) -> dict:
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    sources, occurrences, documents, tables = [], [], {}, {}
    csv_counts, issues = Counter(), Counter()
    supplied_total = None
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {'.csv', '.md'} and path.name != 'summary.json':
            continue
        if not path.is_file():
            continue
        metadata, data = _read_source(path, directory)
        sources.append(metadata)
        if path.name == 'summary.json':
            supplied = json.loads(data.decode('utf-8-sig'))
            if not isinstance(supplied, dict):
                raise ValueError('Expected an object in summary.json')
            supplied_total = supplied.get('total_tables')
            continue
        if path.suffix.lower() == '.md':
            code, edition = _document_claims(path.name)
            documents.setdefault(metadata['sha256'], (data.decode('utf-8-sig'), code, edition))
            continue
        if path.name not in TABLE_TYPES:
            raise ValueError(f'Unsupported extraction file: {path.name}')
        with io.StringIO(data.decode('utf-8-sig'), newline='') as stream:
            reader = csv.DictReader(stream, restkey='__extra_columns__')
            if reader.fieldnames is None or len(reader.fieldnames) != len(CSV_COLUMNS) or set(reader.fieldnames) != set(CSV_COLUMNS):
                raise ValueError(f'Invalid CSV schema: {path.name}')
            for index, raw in enumerate(reader, start=2):
                csv_counts[path.name] += 1
                occurrence = dict(file_id=metadata['file_id'], csv_row=index, original_type=TABLE_TYPES[path.name],
                                  raw_json=canonical_json(raw), table_id=None, issues=[])
                try:
                    record = parse_extracted_record(raw)
                    table = normalize_table(record, TABLE_TYPES[path.name])
                    occurrence['table_id'] = table.table_id
                    occurrence['issues'] = table.issues
                    existing = tables.get(table.table_id)
                    if existing is None:
                        tables[table.table_id] = table
                    else:
                        _merge_tables(existing, table)
                except (ValueError, TypeError, json.JSONDecodeError):
                    occurrence['issues'] = ['INVALID_EXTRACTED_RECORD']
                issues.update(occurrence['issues'])
                occurrences.append(occurrence)
    if not csv_counts:
        raise ValueError('No extraction CSV records found')
    valid = sum(item['table_id'] is not None for item in occurrences)
    summary = dict(normalization_version=NORMALIZATION_VERSION, source_files=sources,
                   csv_tables=dict(sorted(csv_counts.items())), total_extracted_tables=sum(csv_counts.values()),
                   unique_tables=len(tables), duplicate_occurrences=valid - len(tables),
                   invalid_records=len(occurrences) - valid, reference_document_files=sum(s['kind'] == 'md' for s in sources),
                   unique_reference_documents=len(documents),
                   occurrence_issues=dict(sorted(issues.items())),
                   **_table_statistics(tables.values()),
                   supplied_summary_total=supplied_total,
                   supplied_summary_matches=(supplied_total == sum(csv_counts.values())) if supplied_total is not None else None,
                   verified_records=0)
    return dict(summary=summary, tables=tables, documents=documents, occurrences=occurrences)


def import_reference_directory(directory: Path, db_path: Path) -> dict:
    batch = inspect_reference_directory(directory)
    summary = batch['summary']
    db_path = Path(db_path)
    if db_path.resolve().is_relative_to(Path(directory).resolve()):
        raise ValueError('The reference database must be outside its input directory')
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {'reference_library_info', 'reference_source_files', 'reference_tables', 'reference_occurrences', 'reference_documents'}
        if existing - expected:
            raise ValueError('Use a separate reference library database, not the application catalog')
        if existing:
            version = conn.execute("SELECT value FROM reference_library_info WHERE key='normalization_version'").fetchone()
            if version is None or version[0] != str(NORMALIZATION_VERSION):
                raise ValueError('Unsupported reference library normalization version')
        conn.executescript(SCHEMA_SQL)
        with conn:
            for source in summary['source_files']:
                conn.execute('INSERT OR IGNORE INTO reference_source_files VALUES (:file_id, :filename, :sha256, :size_bytes, :kind)', source)
            effective_tables = []
            for table in batch['tables'].values():
                previous = conn.execute('SELECT normalized_json FROM reference_tables WHERE table_id=?', (table.table_id,)).fetchone()
                if previous:
                    table = _merge_tables(ReferenceTable.model_validate_json(previous[0]), table)
                effective_tables.append(table)
                conn.execute('INSERT INTO reference_tables VALUES (?, ?, ?, ?, ?, ?, ?, ?) '
                             'ON CONFLICT(table_id) DO UPDATE SET table_type=excluded.table_type, manufacturer=excluded.manufacturer, '
                             'review_state=excluded.review_state, normalized_json=excluded.normalized_json',
                             (table.table_id, table.table_type, table.manufacturer, table.source_file, table.source_page,
                              table.review_state, table.data_quality, table.model_dump_json()))
            for occurrence in batch['occurrences']:
                conn.execute('INSERT OR REPLACE INTO reference_occurrences VALUES (?, ?, ?, ?, ?, ?)',
                             (occurrence['file_id'], occurrence['csv_row'], occurrence['table_id'], occurrence['original_type'],
                              occurrence['raw_json'], canonical_json(occurrence['issues'])))
            for digest, (content, code, edition) in batch['documents'].items():
                conn.execute('INSERT OR IGNORE INTO reference_documents VALUES (?, ?, ?, ?, ?)',
                             (digest, content, code, edition, 'UNVERIFIED'))
            summary.update(_table_statistics(effective_tables))
            summary['database_totals'] = {
                name: conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for name, table in [('tables', 'reference_tables'), ('occurrences', 'reference_occurrences'),
                                    ('documents', 'reference_documents'), ('source_files', 'reference_source_files')]
            }
            conn.execute('INSERT OR REPLACE INTO reference_library_info VALUES (?, ?)', ('last_import_summary', canonical_json(summary)))
            conn.execute('INSERT OR REPLACE INTO reference_library_info VALUES (?, ?)', ('normalization_version', str(NORMALIZATION_VERSION)))
    return summary


class ReferenceLibrary:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        if not self.db_path.is_file():
            raise FileNotFoundError(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True)

    def find_tables(self, *, table_type: str | None = None, manufacturer: str | None = None,
                    include_quarantined: bool = False, limit: int = 50, offset: int = 0) -> list[ReferenceTable]:
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError('Expected 1 <= limit <= 500 and offset >= 0')
        conditions, parameters = [], []
        for column, value in [('table_type', table_type), ('manufacturer', manufacturer)]:
            if value is not None:
                conditions.append(f'{column} = ?')
                parameters.append(value)
        if not include_quarantined:
            conditions.append("review_state = 'PENDING_REVIEW'")
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with closing(self._connect()) as conn:
            rows = conn.execute('SELECT normalized_json FROM reference_tables' + where + ' ORDER BY table_id LIMIT ? OFFSET ?',
                                [*parameters, limit, offset]).fetchall()
        return [ReferenceTable.model_validate_json(row[0]) for row in rows]

    def get_occurrences(self, table_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute('SELECT s.filename, s.sha256, o.csv_row, o.original_type, o.raw_json, o.issues_json '
                                'FROM reference_occurrences o JOIN reference_source_files s ON s.file_id=o.file_id '
                                'WHERE o.table_id=? ORDER BY s.filename, o.csv_row', (table_id,)).fetchall()
        return [dict(csv_file=name, csv_sha256=digest, csv_row=row, original_type=kind,
                     raw_record=json.loads(raw), issues=json.loads(issues)) for name, digest, row, kind, raw, issues in rows]

    def get_document(self, sha256: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute('SELECT text_content FROM reference_documents WHERE sha256=?', (sha256,)).fetchone()
        return row[0] if row else None
