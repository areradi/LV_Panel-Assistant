# MVP Scope — LV Panel Assistant

## 1. Purpose and audience

This document describes the current product boundary for B2B evaluation. It separates implemented workflows from known limitations and product gaps. It is a software capability summary, not a claim of certification, a type-test result, or a promise of service availability.

**Intended readers:** panel builders, electrical design teams, EPC engineering leads, and technical procurement reviewers evaluating a desktop engineering assistant.

**Evidence rule:** capability statements below point to implementation, tests, or project records. A passing test shows that a tested case works; it does not establish universal compliance or field performance.

## 2. MVP scope and capability status

| Capability | Status | Evidence in code/tests | Limits |
|---|---|---|---|
| Project and feeder input models | Implemented | `lv_assist/models.py`; UI and import tests including `tests/test_feeder_fields_ui.py` | Inputs still depend on the completeness and correctness of the data entered. |
| Cable selection and sizing | Implemented for supported cases | `lv_assist/engine.py`; independent pure-selection implementation in `tools/oracle_cable.py`; `tests/test_oracle_cable.py` | F-031a covers pure selection. The independent fault-energy compatibility layer F-031b is planned; see `docs/ORACLE_FINDINGS.md`. |
| Feeder load and motor calculations | Implemented for modeled load types, including resolved power factor/efficiency and running/starting kVA reporting | `lv_assist/models.py`, `lv_assist/engine.py`, `lv_assist/exporters.py`; engine/report tests | Results use supplied plate data or explicit defaults. Starting behavior and special motor duty still need project-specific review. |
| Voltage drop, short-circuit, PE and protection checks | Implemented with explicit unknown/insufficient-data outcomes | `lv_assist/engine.py`, `lv_assist/pe_spd_engine.py`; `tests/test_main_breaker_icu.py` | Results depend on available inputs and catalog data. Some estimates remain preliminary and need engineering review. |
| Busbar and thermal screening | Implemented for supported busbar and temperature inputs | `lv_assist/busbar.py`, `lv_assist/engine.py`, preliminary-report tests | Temperature, grouping, enclosure/airflow and manufacturer-specific conditions can require verified project data. |
| Selectivity and protective-device screening | Implemented for available catalog/trip-curve data | `lv_assist/engine.py`, `lv_assist/catalog.py`; legacy engine and report tests | Coordination is limited by catalog curves and the evidence available for each device pair. |
| Validation findings and design assumptions | Implemented as rule results and report entries | `lv_assist/engine.py`, `lv_assist/scenario_rules.py`, `lv_assist/exporters.py` | A finding is a screening/review aid; it does not establish regulatory approval. |
| TCC, single-line, layout and control diagrams | SVG generators implemented | `lv_assist/outputs.py`, `lv_assist/layout.py`, `lv_assist/control_circuits.py`, `lv_assist/iec_sld_svg.py` | Persian/Latin rendering and print fit have unresolved visual defects; see `docs/TECH_DEBT.md`. |
| Main breaker Icu versus Ik | Implemented with conservative unknown/fail handling | `lv_assist/engine.py`; `tests/test_main_breaker_icu.py` | A result is only as reliable as the rated-voltage and catalog evidence supplied. |
| Catalog-backed device selection | Implemented | `lv_assist/catalog.py`, `lv_assist/engine.py` | Missing or unverified manufacturer data must not be treated as a confirmed product match. |
| Project and feeder forms | Implemented | `lv_assist/gui.py`; `tests/test_project_fields_ui.py`, `tests/test_feeder_fields_ui.py` | Desktop application; no role-based multi-user workflow is established. |
| FA / EN / DE interface translations | Implemented for shipped translation keys | `lv_assist/translations/fa.json`, `en.json`, `de.json`; translation/UI tests | Translation coverage does not guarantee that every technical term or generated drawing is visually correct in all languages. |
| Clipboard feeder import | Implemented | `lv_assist/excel_clipboard.py`; `tests/test_excel_clipboard_parser.py` | Supported headers and values are parser-defined; malformed or unsupported inputs need correction. |
| XLSX feeder import | Implemented with header-based mapping | `lv_assist/gui.py`; `tests/test_excel_import.py` | Import follows recognized headers; this is not a general-purpose spreadsheet integration. |
| Catalog and price management UI | Implemented for local catalog/price workflows | `lv_assist/gui.py`, `lv_assist/catalog.py`; catalog/UI tests | Local data workflow; no central tenant or shared catalog service is established. |
| Engineering Excel and HTML reports | Implemented | `lv_assist/exporters.py`; `tests/test_preliminary_html.py` and report tests | Report values can be preliminary; printed layout has open items in `docs/TECH_DEBT.md`. |
| PDF generation | Implemented through browser-based HTML printing | `lv_assist/outputs.py`, `PdfExporter.export_html_to_pdf` | Depends on an available supported browser and its rendering/fonts. Visual and BiDi issues remain tracked. |
| BOM and commercial quotation | Implemented | `lv_assist/bom.py`, `lv_assist/commercial.py`; BOM and quote tests | Pricing completeness depends on the local catalog/price data; unpriced lines must remain visibly unpriced. |
| BOM, connections and report CSV | Implemented with formula-injection safeguards in covered exporters | `lv_assist/bom.py`, `lv_assist/control_circuits.py`, `lv_assist/outputs.py`; `tests/test_eplan_csv_safety.py`, `tests/test_provenance_bom_csv.py` | CSV is a file interchange format, not a negotiated ERP/API contract. Consumers must preserve provenance sidecars where provided. |
| Independent cable oracle F-031a | Implemented for pure cable selection | `tools/oracle_cable.py`; `tests/test_oracle_cable.py`; `docs/ORACLE_FINDINGS.md` | Does not yet replicate the engine's full fault-energy compatibility check. |
| Stale-result guard and report provenance | Implemented across covered exports | `lv_assist/calculation_state.py`, `lv_assist/drawing_status.py`, report exporters and provenance tests | Metadata records calculation provenance; it is not a digital signature or audit log. |
| Preliminary engineering labels and disclaimers | Implemented in covered reports/exports | `lv_assist/exporters.py`, `lv_assist/bom.py`, `lv_assist/drawing_status.py`; `tests/test_preliminary_html.py`, `tests/test_phase7_disclaimers.py` | A disclaimer does not replace design review, manufacturer evidence, or applicable conformity assessment. |
| Performance: 50-feeder project | Reported result: **“Performance: 50 feeders in ~47 ms (benchmark on Windows 11, Python 3.12, i7-class CPU) — well within B2B target of <3 seconds.”** | R-16b commit `0ee56452e73cd8018d877a8e0fb96dfb4d1cd341` adds scope-local catalog lookup caching and cache tests in `tests/test_process_project_catalog_cache.py`. | The checked-in R-16b change/tests do not contain a benchmark harness or recorded 50-feeder timing. The 47 ms figure and machine details are supplied for this document and should be treated as a reported, not independently reproducible, measurement until a benchmark artifact is recorded. |

## 3. Incomplete or limited capabilities

| Item | Current position | Evidence / next dependency |
|---|---|---|
| SVG Persian/Latin BiDi and disclaimer fit | Unresolved; visual rendering and clipping remain open. | `docs/TECH_DEBT.md`, section `T-036-SVG-BiDi`. Existing tests check markup, not visual correctness. |
| F-031b fault-energy oracle | Planned; F-031a does not model the engine's added PE/fault-energy compatibility step. | `docs/ORACLE_FINDINGS.md`; requires implementation and cross-check against engine behavior. |
| EPLAN/DXF export | Disabled in the GUI; not available as a supported customer workflow. | `lv_assist/gui.py`, `lv_assist/outputs.py`, `docs/ARCHITECTURE.md`. |
| T-003b/c derating defaults and IP/airflow | Pending authoritative engineering data/decision. | Listed as pending in the supplied project roadmap; no complete authoritative data source was located in the inspected repository. Keep status `PENDING_DATA` until owner evidence is recorded. |
| PDF print quality | Several page-break, wide-table, footer, and BiDi items remain in the technical-debt register. | `docs/TECH_DEBT.md`. |

## 4. B2B gaps and expected capabilities

These are product gaps or unverified capabilities, not implied commitments:

- User identity, sign-in, and role-based permissions (administrator, engineer, viewer).
- Multi-user collaboration, shared project storage, and cloud synchronization.
- Centralized audit trail for edits, approvals, exports, and catalog changes.
- A supported integration API and stable ERP/EPLAN exchange contract.
- Enterprise deployment controls, managed updates, backup/restore procedures, and retention policy.
- Contracted SLA, support hours, incident response, and release policy.
- Customer-specific regulatory or conformity reports beyond the current engineering outputs.
- Independent security review and documented threat model.

The current architecture describes a single desktop application with local SQLite data (`docs/ARCHITECTURE.md`). Web catalog/search features mean that “local desktop” alone is not enough evidence for a no-network or data-locality commitment; outbound data flows need separate review.

## 5. Assumptions and limits

- The user supplies accurate project, feeder, and environmental inputs.
- Catalog coverage and manufacturer evidence vary by device and voltage rating.
- Estimated or incomplete values remain identified as such; they are not silently promoted to verified selections.
- Engineering outputs support review and documentation. They are not a compliance certificate or substitute for qualified engineering approval.
- The 47 ms performance figure is a reported measurement, not a benchmark currently reproducible from the R-16b commit alone.
- B2B deployment model, supported operating environments, security commitments, and support terms require product-owner decisions.

## 6. MVP acceptance checklist

- [ ] A reviewer can create a project and enter representative feeder data.
- [ ] Clipboard and XLSX imports map supported headers and report missing required fields clearly.
- [ ] A representative project calculates and reports supported checks, including unknown/insufficient-data states.
- [ ] Main breaker Icu/Ik behavior is covered by focused tests for missing, insufficient, and invalid values.
- [ ] Exports reject stale calculation results where guarded and retain provenance where implemented.
- [ ] BOM and quotation distinguish priced from unpriced items.
- [ ] CSV safety tests cover formula-like values in the covered CSV exporters.
- [ ] Preliminary status and engineering-review disclaimers appear in the applicable deliverables.
- [ ] PDF/SVG output receives visual QA in each supported language before customer delivery.
- [ ] A reproducible 1/10/50-feeder benchmark artifact records environment, input fixture, repetitions, and measured results before the 47 ms figure is used as a formal performance commitment.
- [ ] Product owner accepts or explicitly defers the B2B gaps listed above.
