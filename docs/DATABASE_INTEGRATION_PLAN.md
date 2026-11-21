# Engineering Database Integration Plan

**Phase:** 1 — inspection and planning only
**Status:** Awaiting approval before implementation
**Database:** `data/lv_panel_database.sqlite` (read-only source)

## 1. Purpose and boundaries

This plan describes how the extracted engineering database could be made available to LV_Panel-Assistant without replacing the existing catalog or allowing unverified extraction results into safety calculations. Phase 1 creates this plan only. It does not add a database module, change application behavior, migrate data, or modify the SQLite file.

The extracted database is treated as an independent source with its own schema and quality lifecycle. The current application catalog remains the active source for existing calculations until a later, separately approved phase defines and validates any integration.

## 2. Findings from the current application

- `main.py` starts `LVAssistApp`; application behavior is organized under `lv_assist/`.
- `lv_assist/paths.py` centralizes application data paths. In development, the data directory is under the package; frozen builds use the application data location and seed-file handling.
- `lv_assist/catalog.py` implements the existing catalog repository and its legacy schema. Its initialization can create or migrate database structures and its normal connections are writable. It must not be pointed at the extracted database.
- The local `config.json` contains `database_path: "data/lv_panel_database.sqlite"`, but `config.example.json` does not currently document that key and the application has no current consumer for it. The path setting therefore is not yet an integration contract.
- Existing catalog migration utilities are for the legacy catalog/JSON inputs, not for the extracted database schema.

## 3. Extracted database inspection

The database was opened using SQLite read-only mode and checked without writing to it.

| Table | Rows observed | Notes |
|---|---:|---|
| `components` | 190,457 | Product/component records |
| `component_attributes` | 350,107 | Extracted technical attributes |
| `sources` | 991 | Source references |
| `review_queue` | 56,944 | Items awaiting human review |
| `staging_pdf_tables` | 1,756 | Staged extraction data |
| `change_history` | 0 | No history rows observed |
| `compatibility_relations` | 0 | No relation rows observed |
| `engineering_rules` | 0 | No rule rows observed |
| `normalized_attributes_pilot` | 13 | Small normalization pilot |

`PRAGMA quick_check` returned `ok`; `user_version` is `0`. The database contains no records marked `verified` in either `components` or `component_attributes`: all observed component records are `extracted` or `needs_review`, and attributes have the same two observed statuses. Consequently, the extracted database currently has no data eligible for safety-critical recommendations under the supplied policy.

A read-only inspection of `3RV20111JA10` found an extracted Siemens record and extracted `rated_current` values including a 7–10 A range. Voltage attributes include 690 V and 6 kV. These are unverified source values and require review and unit/meaning validation; this example must not be presented as an approved protective-device selection.

## 4. Proposed architecture

Add an isolated data-access layer in a later approved phase. It should not reuse `CatalogRepository` because that repository can mutate schema and data during initialization.

```text
Application/config
       |
       v
Database path resolver (existing path conventions + configured relative path)
       |
       v
Read-only SQLite connection/context manager
       |
       +--> ComponentRepository
       +--> AttributeRepository
       +--> Source/review lookups as needed
       |
       v
Typed records / domain results
       |
       +--> search and unverified preview
       +--> verified-only safety query (returns no eligible result until verified data exists)
```

### Proposed modules for Phase 2

| Module | Responsibility |
|---|---|
| `lv_assist/database/__init__.py` | Public package surface, kept small |
| `lv_assist/database/connection.py` | Resolve the configured path; open SQLite with read-only URI mode; provide a context manager; set query-only behavior; translate low-level connection errors to domain exceptions |
| `lv_assist/database/models.py` | Typed representations for component, attribute, provenance, and query result; preserve missing data as `None` |
| `lv_assist/database/repositories.py` | `ComponentRepository` and `AttributeRepository`; parameterized SQL only; explicit status filtering |
| `lv_assist/database/queries.py` | Shared query definitions and narrowly scoped lookup functions, including part-number search and candidate discovery |
| `lv_assist/motor_protection.py` | Later proof-of-concept motor-protection search, kept separate from the calculation engine until its data and formula policy are approved |

Connections should be scoped to a request/context rather than shared as a global SQLite connection. If repository instances are shared between UI threads, each operation should obtain a thread-appropriate connection; do not disable SQLite thread checks without a demonstrated need. Repositories should not create tables, run migrations, or write review status.

## 5. Query and data-quality policy

- Use parameterized SQL for all values, including part numbers and filters.
- Preserve source units and source locator alongside normalized values. Do not infer a conversion or choose between conflicting values in the DAL.
- A safety query must require the relevant component and attributes to be `verified`; missing, conflicting, or unverified required fields produce no eligible recommendation and a clear “data unavailable / requires review” result.
- Search and preview may include `extracted` records only when the result is visibly labeled unverified and cannot be mistaken for a validated engineering decision.
- `needs_review`, `raw`, and `deprecated` records must not be used for safety calculations. The meaning and allowed use of any future status must be explicit.
- A missing attribute remains `None`; do not substitute zero, a typical value, or a guessed unit.
- Source provenance should travel with displayed results: source/document reference, locator where available, status, and any review warning.

## 6. Configuration and path strategy

The existing `database_path` entry is currently local configuration, not an application-supported setting. A later implementation should define and document a stable setting in the configuration example and resolve relative paths using an explicit application rule. It should avoid hard-coded machine-specific paths and should report a useful configuration error when the configured database is absent or unreadable.

The connection layer should construct a SQLite read-only URI from the resolved absolute path (correctly escaping URI characters) and enable query-only mode. It must never silently fall back to the legacy catalog, create a blank database, or copy/modify the extracted source. Packaging behavior for a separately supplied 294 MB database needs a distribution decision before release.

## 7. Migration and coexistence strategy

1. **Keep the sources separate.** Do not merge extracted tables into the legacy catalog or point legacy initialization/migration code at the new database.
2. **Add a read-only adapter.** Introduce the isolated DAL and test it against a small test database with the same relevant schema. Production database access remains read-only.
3. **Validate schema and quality.** Check expected tables/columns and schema version on open; fail with a clear domain error for incompatible input. Record `user_version` is currently 0, so a versioning contract must be defined before schema evolution.
4. **Build a reviewed mapping.** Map extracted component types, attribute keys, units, ranges, status, and provenance to domain concepts. Keep ambiguous values unavailable rather than forcing a mapping.
5. **Enable preview before safety use.** If approved, expose extracted records as clearly labeled search/preview only. Do not feed them into existing engine calculations.
6. **Gate safety use on verified data.** A future, separate approval should define who verifies records, what evidence is required, how changes are audited, and which rules permit each verified attribute to be used.
7. **Retain rollback.** Feature-flag or otherwise isolate the new lookup path so it can be disabled without changing legacy catalog behavior.

No bulk data migration is recommended at this stage. The current database is an extraction/review store, while the legacy catalog has a different schema and lifecycle. A merge would obscure provenance and could accidentally promote unverified values.

## 8. Motor-protection proof of concept: unresolved acceptance conflict

The requested example uses `I ≈ P(kW) × 2` for a 400 V system and expects `3RV20111JA10` with a 7–10 A range for a 4 kW motor. Numerically this gives approximately 8 A, but the inspected component and attributes are marked `extracted`, not `verified`; therefore it cannot be returned as a safety-eligible recommendation under the required policy. The database currently has zero verified components and attributes, so a verified-only query should return no candidate.

The sample also contains multiple voltage values and requires confirmation of their meaning, units, and compatibility semantics. The current extraction alone is not enough to claim that this product is a suitable MPCB.

Before Phase 3, the owner must choose one of these acceptance interpretations:

- **Safety-only:** the query returns no eligible product until suitable records are verified; the sample acceptance expectation is deferred.
- **Separate preview:** the query may show the sample as an explicitly unverified preview, separate from any safety recommendation; the acceptance test must assert the warning and non-safety status.

The `P × 2` estimate is specified only for 400 V. Supporting other voltages requires an approved formula and assumptions; do not extrapolate it silently.

## 9. Risks and controls

| Risk | Why it matters | Proposed control |
|---|---|---|
| Unverified extraction used as a protection recommendation | Could lead to unsafe device selection | Verified-only safety filter at repository/query boundary and tests proving unverified rows are excluded |
| Mixed or ambiguous units/values | Voltage or current comparisons can be wrong | Preserve raw value/unit/source; normalize only with explicit, tested conversion rules |
| Legacy repository mutates the new database | Could alter source data or schema | Separate package and connection factory; read-only URI; no legacy migration invocation |
| 294 MB database distribution | Installer size, updates, and user data handling | Decide whether database is external/downloaded/provisioned before packaging; never commit it to Git |
| No schema version (`user_version=0`) | Future incompatibility can go unnoticed | Define schema/version compatibility contract before shipping integration |
| Many records require review | Search may return plausible but unsafe entries | Show status and provenance; do not imply completeness or suitability |
| SQLite access from UI threads | Shared connections can fail or block | Use short-lived/request-scoped connections and test concurrent access only if the UI uses it concurrently |
| No verified data today | Safety lookup cannot produce an approved candidate | Treat “no verified result” as the correct current outcome, not a reason to relax filtering |

## 10. Later-phase test plan

For the approved implementation phases, add focused tests using a small temporary SQLite fixture rather than copying the production database:

- Opening a database is read-only; insert/update/schema changes fail.
- Missing path, malformed database, and incompatible schema produce domain-level errors.
- Repository queries use parameters and preserve `None`, source, unit, range, and status.
- `verified` records can enter the safety query; `extracted`, `needs_review`, `raw`, and `deprecated` records cannot.
- Search/preview results are labeled unverified and remain distinct from safety results.
- The motor example obeys the chosen acceptance interpretation and the approved 400 V assumption.
- Existing catalog and calculation tests remain unchanged and pass, apart from documented baseline failures.

## 11. Baseline and approval gates

Before this plan was written, the full test suite was run as a baseline: **727 passed, 8 skipped, 2 failed**. The failures were `tests/test_distribution.py::test_release_archive_uses_only_clean_inputs_and_retains_existing_user_data` (Windows/fake-compiler executable path mismatch, followed by cleanup encountering an open SQLite file) and `tests/test_engine_legacy.py::TestPhase3Pdf::test_html_to_pdf_roundtrip` (PDF/browser integration unavailable in this environment). These are baseline observations, not failures introduced by the database work.

**Phase 1 deliverable:** this plan only.
**Approval required before Phase 2:** confirm the path/configuration contract, schema compatibility policy, whether unverified preview is desired, and the acceptance treatment for the 4 kW / 400 V example. Do not start DAL implementation, modify source data, add dependencies, or wire any UI before approval.

