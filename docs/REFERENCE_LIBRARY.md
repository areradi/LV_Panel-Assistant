# Imported reference library

The extraction importer creates a separate SQLite library for inspecting source tables. It retains the supplied CSV records, source filenames/pages, file hashes and every duplicate occurrence. It does not add devices, losses, derating factors or coordination rules to the calculation catalog.

## Import and inspect

Unpack the supplied archive into a local working directory. Run these commands from the repository root with the application's Python environment:

```bash
python -B scripts/import_reference_data.py /path/to/cleaned_data
python -B scripts/import_reference_data.py /path/to/cleaned_data --db lv_assist/data/reference_library.db --report work/reference_import_summary.json
```

The first command only inspects the sources. The second imports them and writes a JSON summary. The database and report must be outside the input directory; the report must also be separate from the database. An existing application catalog is rejected as an import target. Unknown library schema versions are rejected. Imports use a transaction, retain earlier source versions and do not modify the input files.

The importer accepts the eight `*_tables.csv` filenames listed in `lv_assist/data_validator.py`. Each record has `brand`, `filename`, `page`, `headers_json` and `rows_json` columns. The two JSON fields contain a header list and a list of string-valued row dictionaries. Malformed records remain in `reference_occurrences` with a null table link and an issue code. Invalid file-level schemas stop the import before database writes. `summary.json` is checked against the measured record count, not used as the count.

## Normalization and review states

- Known reversed header words and header whitespace are normalized. Other words retain their spelling. Header collisions retain the original row and cause quarantine.
- Manufacturer labels are retained with an unverified origin. Distinctive filename families and explicit manufacturer names can supply an unverified label. Short strings such as `NS` do not establish a manufacturer. Conflicting labels cause quarantine.
- Whole-cell scalar quantities with explicit units can be annotated in A, V, W, °C or dimensionless ratio units. Ranges, ambiguous comma grouping, model numbers and bare numbers remain uninterpreted. The original cell text is retained. These annotations do not establish device identity, operating mode or per-pole/per-device losses.
- Type signals can correct an obvious category mismatch. Ambiguous categories, unknown/conflicting manufacturers, duplicate headers, invalid physical quantities and empty tables cause quarantine. PLC configuration tables and standards examples also remain outside equipment candidates.
- A duplicate requires identical parsed table content and extraction page from the same source filename. Numbered copy suffixes such as ` (1)` can be removed when comparing filenames. Every original filename, CSV record and file hash is still retained. Different editions or source names are not merged solely because their tables look similar.

`PENDING_REVIEW` means that the basic extraction checks did not identify a blocking issue. `QUARANTINED` means at least one issue needs resolution. Both states have `UNVERIFIED` quality, enforced by SQLite constraints. The library provides no automatic promotion to verified data.

The summary describes the current input batch after reconciling earlier metadata conflicts. `database_totals` counts the accumulated library, including earlier source versions. Issue counts can overlap. Reimporting identical sources does not create additional occurrences.

## Read API

```python
from pathlib import Path
from lv_assist.reference_library import ReferenceLibrary

library = ReferenceLibrary(Path('lv_assist/data/reference_library.db'))
tables = library.find_tables(table_type='DERATING', manufacturer='Schneider Electric')
for table in tables:
    print(table.source_file, table.source_page, table.data_quality)
    print(library.get_occurrences(table.table_id))
```

Queries use read-only connections. Pagination accepts `limit` up to 500 and `offset`; quarantine is included only with `include_quarantined=True`. `get_document(sha256)` returns an indexed Markdown document as source text. Its content is never executed. Standard codes/editions inferred from filenames are explicitly stored as claims, not inserted into the engine's standards registry. An extraction page is not an independently checked PDF page reference.

The library database is local, ignored by Git and excluded from the explicit release-data list. The checked-in [import summary](data/cleaned_data_import_summary.json) records the source-file hashes and measured counts. It does not contain the full reference texts or replace the original archive.

## Required before calculation use

A reviewer must resolve the exact equipment model, document/revision/table/page and application conditions before mapping a row into a supported calculation schema. Derating needs temperature and rating basis; losses need operating mode/current and per-pole/per-device scope. Motor coordination needs the exact starter/protective-device combination, test type, voltage and fault rating. Standards extracts need an edition/applicability review and checked tables or coefficients.

The current attachments do not establish those conditions for all rows. No Type 2 matrix, complete IEC/TR 60890 solver or verified busbar current table was generated from keyword matches. The existing catalog evidence checks remain in force.

## Sources reviewed on 2026-11-07

The Word attachment supplies a proposed data-library design, illustrative records and suggested patches. Its suggestions were evaluated as reference material alongside the user's remediation request. For example, the proposed short `NS` filename match and `soG` reversal were not copied as reliable rules. The prior audit document called `1.docx` in `REPORT_REMEDIATION.md` belongs to the earlier stages; it is not this new attachment.

| Attachment | SHA-256 |
| --- | --- |
| `New Microsoft Word Document.docx` | `a1a8f6d7dab463f3418e1094ffa4f51bb70b59a5d6d54a0b0683199b1fa2a9c9` |
| `cleaned_data.zip` | `ed0a1b7d17b1190320c05d4de8d6a40a2fc2c764bb1f15eb08afe2e8a4888e81` |
