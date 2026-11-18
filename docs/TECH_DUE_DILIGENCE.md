# Technical Due Diligence — Customer Questions and Evidence

## 1. How to read these answers

Each answer is marked **Confirmed**, **Limited**, **Planned**, or **Decision needed**. “Confirmed” means the repository contains implementation or tests for the described scope; it does not imply certification or validation for every installation. Evidence links point to code, tests, or project records. Unresolved visual and security matters remain explicit.

## 2. Customer questions

### Calculations and standards

**Q1. Does the product perform LV cable sizing and voltage-drop checks?**
**Confirmed —** The engine selects supported cable sizes and calculates voltage drop. See `lv_assist/engine.py`, `tools/oracle_cable.py`, and `tests/test_oracle_cable.py`. Scope and inputs must be reviewed for each project.

**Q2. Is the output an IEC 61439 compliance certificate?**
**Confirmed — no.** Reports explicitly state that results are preliminary and require qualified-engineer review; see the report exporters and disclaimer tests. The software does not certify an assembly.

**Q3. How are missing short-circuit or breaker data handled?**
**Confirmed —** Main-breaker Icu/Ik logic returns unknown or failure for covered missing/invalid/insufficient cases instead of treating missing data as a pass. See `lv_assist/engine.py` and `tests/test_main_breaker_icu.py`.

**Q4. Is the independent oracle equivalent to the full calculation engine?**
**Limited —** F-031a independently checks pure cable selection and cross-checks demo cases. It does not yet include the engine's fault-energy compatibility layer; see `docs/ORACLE_FINDINGS.md`. F-031b remains planned.

**Q5. Can every catalog device be treated as manufacturer-verified?**
**Limited —** Device data quality and available ratings vary. The engine distinguishes verified and estimated evidence; missing ratings do not establish suitability. Review the selected manufacturer's documentation for the installation.

### Outputs and integration

**Q6. Which report formats can be generated?**
**Confirmed —** The repository implements Excel and HTML reports, browser-based PDF export, SVG drawings, BOM exports, and commercial quotation output. See `lv_assist/exporters.py`, `outputs.py`, `bom.py`, `commercial.py`, and their focused tests.

**Q7. Can BOM data be imported into an ERP?**
**Limited —** BOM CSV is available, but no stable customer-specific ERP schema or supported integration API is documented. Field mapping and consumer testing would be needed for each integration.

**Q8. Is EPLAN or DXF export available?**
**Limited —** EPLAN/DXF GUI actions are disabled and are not a supported workflow. See `lv_assist/gui.py`, `lv_assist/outputs.py`, and `docs/ARCHITECTURE.md`.

**Q9. Does each report retain calculation provenance and reject stale inputs?**
**Confirmed for covered exporters —** Input fingerprints and provenance metadata are implemented, with current-calculation guards in report/export paths. See `lv_assist/calculation_state.py`, `lv_assist/drawing_status.py`, and provenance tests. This is not a signed audit record.

**Q10. Is printed PDF/SVG output visually verified in all languages?**
**Limited —** PDF depends on browser rendering. Persian/Latin BiDi and clipping remain unresolved in `docs/TECH_DEBT.md`; automated markup tests do not prove visual correctness.

### Data and deployment

**Q11. Where is project/catalog data stored?**
**Confirmed —** The application is a desktop program and uses local SQLite/catalog data; see `docs/ARCHITECTURE.md` and `lv_assist/catalog.py`. This alone does not establish that every feature is network-free.

**Q12. Is cloud synchronization or multi-user project storage available?**
**Planned / not established —** The architecture describes a single desktop application. No implemented shared cloud project store is identified in the reviewed product architecture.

**Q13. Can customers import feeder data from Excel or paste it from a spreadsheet?**
**Confirmed for supported formats —** Header-aware XLSX import and clipboard parsing are implemented. See `lv_assist/excel_clipboard.py`, `lv_assist/gui.py`, `tests/test_excel_import.py`, and `tests/test_excel_clipboard_parser.py`. Unsupported headers need mapping or correction.

**Q14. Is backup, restore, and retention managed centrally?**
**Decision needed —** The repository documents local mutable data but does not establish a centrally managed enterprise backup/retention service. Agree the operating procedure before deployment.

### Security and audit

**Q15. Are CSV formula-injection risks addressed?**
**Limited —** CSV-safe handling is implemented and tested for covered exporters, including EPLAN CSV paths; see `lv_assist/outputs.py` and `tests/test_eplan_csv_safety.py`. This is a security baseline, not a complete security assessment.

**Q16. Has the application completed a security audit?**
**Limited —** T-034 changes include a Pydantic version floor and CSV safeguards. These are baseline controls; they do not amount to penetration testing, a threat model, or a comprehensive dependency/security review.

**Q17. Are role-based permissions and an audit log available?**
**Planned / not established —** No implemented B2B identity, role model, or centralized audit trail is evidenced in the reviewed architecture. These require product and deployment decisions.

### Operations

**Q18. Does a 50-feeder project complete within three seconds?**
**Limited — reported result:** “Performance: 50 feeders in ~47 ms (benchmark on Windows 11, Python 3.12, i7-class CPU) — well within B2B target of <3 seconds.” R-16b (`0ee56452e73cd8018d877a8e0fb96dfb4d1cd341`) implements scope-local catalog caching and tests cache behavior in `tests/test_process_project_catalog_cache.py`. The commit does not contain a reproducible benchmark script or recorded timing artifact; treat 47 ms as a supplied measurement, not an independently verified product guarantee.

**Q19. What availability SLA and support response time are offered?**
**Decision needed —** No contracted SLA or support commitment is established in the reviewed repository. Do not promise one before operational ownership and terms are approved.

### Language and use

**Q20. Which interface languages are supported?**
**Confirmed —** FA, EN, and DE translation files are present. SVG/PDF BiDi and print rendering still have open issues; see `docs/TECH_DEBT.md`. Language availability should not be presented as proof that every generated artifact is visually correct.

## 3. Evidence matrix

| Question | Short answer | File/test evidence | Limitation | Next action |
|---|---|---|---|---|
| Q1 | Cable sizing and voltage drop are implemented for supported cases. | `lv_assist/engine.py`; `tools/oracle_cable.py`; `tests/test_oracle_cable.py` | Oracle scope differs from full engine. | Complete F-031b and expand representative validation. |
| Q2 | Not a conformity certificate. | `lv_assist/exporters.py`; disclaimer tests | Review remains necessary. | Preserve disclaimer in customer deliverables. |
| Q3 | Missing/invalid Icu or Ik is conservative in covered cases. | `lv_assist/engine.py`; `tests/test_main_breaker_icu.py` | Depends on input/catalog evidence. | Review project-specific ratings. |
| Q4 | Independent oracle is partial. | `tools/oracle_cable.py`; `docs/ORACLE_FINDINGS.md` | F-031b absent. | Implement and cross-check fault-energy layer. |
| Q5 | Catalog verification varies. | `lv_assist/catalog.py`; `lv_assist/models.py` | Not all device/rating combinations have evidence. | Confirm OEM documents for selected equipment. |
| Q6 | Multiple report/export formats exist. | exporters, outputs, BOM and commercial modules | PDF has browser/rendering dependencies. | Run visual QA on target environment. |
| Q7 | CSV exists; ERP contract/API is not established. | `lv_assist/bom.py` | Customer schema mapping is not supplied. | Define and test an integration contract. |
| Q8 | EPLAN/DXF is disabled. | `lv_assist/gui.py`; `lv_assist/outputs.py`; architecture doc | No supported export workflow. | Keep disabled until validated. |
| Q9 | Provenance/stale guards exist in covered paths. | `calculation_state.py`; `drawing_status.py`; provenance tests | Not a signed audit log. | Define audit requirements if needed. |
| Q10 | Print and SVG rendering have open issues. | `docs/TECH_DEBT.md` | Automated tests do not establish visual fidelity. | Close visual QA items and test target browsers. |
| Q11 | Desktop/local SQLite architecture. | `docs/ARCHITECTURE.md`; `lv_assist/catalog.py` | Network behavior varies by feature. | Map outbound data flows before locality claims. |
| Q12 | No shared cloud store established. | `docs/ARCHITECTURE.md` | No multi-user architecture. | Decide deployment and collaboration model. |
| Q13 | XLSX and clipboard imports support known headers. | `excel_clipboard.py`; `tests/test_excel_import.py`; parser tests | Not arbitrary workbook ingestion. | Validate customer templates in pilot. |
| Q14 | Enterprise backup/retention is not established. | `docs/ARCHITECTURE.md` | Operational process remains undecided. | Document owner, schedule, and restore drill. |
| Q15 | CSV safety baseline exists for covered exporters. | `outputs.py`; `tests/test_eplan_csv_safety.py` | Not comprehensive security proof. | Extend review to all import/export surfaces. |
| Q16 | T-034 is a baseline, not a complete audit. | `requirements.txt`; `tests/test_eplan_csv_safety.py` | No penetration-test evidence. | Plan threat model and independent review. |
| Q17 | RBAC/audit log not established. | `docs/ARCHITECTURE.md` | B2B access control is a product gap. | Define roles and audit events. |
| Q18 | 47 ms reported; not reproducible from R-16b artifacts. | R-16b commit; `tests/test_process_project_catalog_cache.py` | Cache tests are not timing benchmarks. | Check in fixture, script, repetitions, and raw results. |
| Q19 | No SLA commitment established. | No SLA evidence identified in reviewed docs/code | Contract and operations are undecided. | Define support ownership and service terms. |
| Q20 | FA/EN/DE resources exist; BiDi issues remain. | translation files; `docs/TECH_DEBT.md` | Artifact rendering differs from UI translation coverage. | Complete visual localization QA. |

## 4. Claims not to sell as commitments

- IEC 61439 certification, type testing, or automatic regulatory approval.
- Complete equivalence between F-031a and the full engine before F-031b is complete.
- Universal suitability of catalog devices or availability of verified OEM ratings.
- EPLAN/DXF export, ERP API integration, cloud synchronization, or multi-user access.
- Completed security audit, comprehensive threat coverage, or role-based access control.
- A guaranteed 47 ms runtime or a formal <3-second SLA without a reproducible benchmark protocol and customer-scale measurements.
- Visually correct Persian BiDi and print layout in every browser/PDF environment while the related `docs/TECH_DEBT.md` items remain open.
- Contracted uptime, response times, support hours, backup, or data-retention service until approved and operationally supported.
