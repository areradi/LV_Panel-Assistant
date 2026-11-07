# Attached audit remediation

The supplied `1.docx` is an assessment based on archive listings, not an executed source review. Its backlog is tracked here against source and runtime evidence. Missing `.pyc` files are not evidence of missing integration: this project deliberately runs Python with `-B`.

## Stage 1: input validation (BKL-P0-02)

Rejected two-phase inputs and nonfinite clipboard power/cable lengths. Input edits now receive the same Pydantic validation as construction. Electrical loads use electrical input kW without a motor-efficiency divisor; motor shaft power retains that divisor. Omitted model and clipboard defaults are exposed as `assumed_fields` rather than being indistinguishable from explicit inputs.

Validation: 375 passed, 1 browser-dependent PDF check deselected, using Python 3.12 and the virtual X display. The PDF roundtrip was attempted during environment preparation and timed out after 120 seconds; it is not a passing check.

## Stage 2: enforce calculation state at export boundaries (BKL-P0-06)

The engine records a SHA-256 signature of all project and feeder inputs. Direct Excel/HTML/SVG, layout, wiring, BOM, commercial, and bridge calls reject changed inputs and feeder outputs from another calculation before writing files. Serialized calculations retain their input snapshot for verification. Live references also detect edits, additions, and replacements in the original feeder list. GUI form edits continue to use the existing stale guard until recalculation.

Validation: the existing 375-test baseline passed with these guards; 22 targeted remediation tests passed, including stale direct exports, recovery after recalculation, mixed result rejection, and serialized snapshot mutation. A result signature establishes input consistency, not engineering approval.

| Audit ID | Initial source assessment (superseded by the stages below) |
| --- | --- |
| P0-01 | Baseline 359 tests passed; `.pyc` inference rejected. Need measured coverage and integration review. |
| P0-02 | Stage 1 fixes validated; expose assumptions in deliverables. |
| P0-03 | Fault-profile helper exists but is not used for all feeder safety checks. |
| P0-04 | Post-selection phase/PE thermal and overload checks need review. |
| P0-05 | Busbar selection exists; peak-factor assumptions and temperature/mechanical scope need review. |
| P0-06 | GUI stale guards exist; direct export boundaries need input signatures. |
| P1-01 | Runtime queries already use SQLite; JSON files are migration seeds. Review provenance claims. |
| P1-02 | Require real manufacturer coordination evidence; do not fabricate Type 2 tables. |
| P1-03 | Existing enclosure thermal estimate needs scope/verification review. |
| P1-04 | Distinguish mandatory constraints from engineering estimates and manufacturer evidence. |
| P1-05 | Wire/terminal schedules already exist. Review BOM model/tag integration and output guards. |
| P2-01 | `wizard_app.py` already wraps the same application; stepper exists. |
| P2-02 | Existing FA/EN/DE GUI tests pass; review translation key parity and technical direction. |
| P3-01 | Build data currently includes mutable development files; restrict distribution inputs. Windows executable acceptance requires Windows. |

No source change or test result constitutes IEC certification or substitutes for manufacturer data and engineering sign-off. The report's exact OEM/DIN/IEC reference tables and Windows clean-machine acceptance cannot be invented from the audit text.

## Stage 3: feeder electrical safety (BKL-P0-03/04, P1-02)

Removed the unsupported 50% reduction of PE fault current. PE sizing now uses the actual conductor/insulation k-factor and refuses unsupported combinations or times outside the adiabatic domain. Automatic phase sizing includes thermal withstand and the second overload condition. Clearing-time estimates use the upper instantaneous pickup tolerance; a legacy policy flag can no longer silently cap a long trip at five seconds.

The main calculation path now reports feeder-end maximum/minimum fault currents with explicit hot-conductor resistance and source/sequence assumptions. It evaluates TN disconnection, TT RCD/electrode data, VFD RCD compatibility, and phase/PE thermal energy. These approximate-curve checks cannot produce manufacturer-verified completion. The type-2 current-rating check no longer claims tested coordination, and an unavailable protective device is reported as `CATALOG_MATCH_FAILED` instead of substituting a lower-breaking-capacity device.

Validation: 392 passed, 1 PDF test deselected; 45 targeted input/electrical safety tests passed after the final wording/disconnection-limit adjustment. Updated three legacy expectations that encoded the removed half-current assumption, hardcoded copper k-factor, and unqualified fault-model completion. Independent arithmetic checks cover hot-loop impedance, full-current PE sizing, aluminium, phase thermal sizing and fuse I2 overload sizing.

Still requires external evidence: real source positive/negative/zero-sequence impedances, protective-device clearing/let-through curves, OEM starter coordination tables and independent IEC reference cases. The implementation reports these limits; it does not claim a complete IEC 60909/60364 verified design. Automatic resizing currently covers ampacity, voltage drop, phase thermal withstand and I2; an end-of-line ADS failure is reported for redesign rather than automatically changing a user's network/protection design.

## Stage 4: busbar and evidence scope (BKL-P0-05, P1-01/03/04)

Peak factor now uses `1.02 + 0.98 exp(-3 R/X)` when R/X is provided and the conservative upper bound 2 otherwise; fault-current magnitude cannot justify a factor above 2. Busbar selection applies an explicitly preliminary temperature correction. The model exposes force, bending stress and maximum support spacing with explicit spacing/stress inputs. Actual bending stress remains unknown if an actual support span was not supplied; the program no longer invents one. Typical bar data and the lumped enclosure thermal estimate are labelled preliminary rather than verified DIN/IEC results.

Device provenance now requires a specific datasheet reference and revision as well as a verified quality label. Existing `datasheet_ref` metadata is retained. Missing evidence is listed in the calculation checks. Known component temperature limits are checked. Calculation defaults are retained in an explicit assumption snapshot and exported to an Excel worksheet and HTML table. Validation records and exports now distinguish mandatory clauses, informative voltage-drop guidance, OEM rules and engineering practice with an application scope. A suggested selectivity rating ratio cannot override an actual manufacturer table or produce a normative error by itself.

Validation: 397 passed, 1 PDF check deselected after updating the workbook schema expectation for the newly added `Assumed_Defaults` sheet; all new busbar force/span arithmetic, temperature correction, provenance and assumption-export tests passed. Earlier tests that called typical busbar or lumped thermal estimates verified were corrected to expect warnings. Exact DIN current tables, IEC/TR 60890 coefficients and OEM support/material certification remain required external evidence.

## Stage 5: one BOM and consistent deliverables (BKL-P0-01, P1-05)

Moved device enumeration into `bom.py` and made Excel, legacy parts adapters and commercial quotes consume it. The old BOM read obsolete field names (`incoming_breaker`, `selected_breaker`, `selected_contactor`) and omitted real selected devices. It also invented terminal part numbers. The new BOM retains all selected devices, cable quantities and actual derived control terminal/device requirements; unassigned parts remain blank and explicitly estimated. `final=True` refuses an incomplete/unverified BOM. Automatically estimated prices are now labelled estimated, and unassigned parts no longer receive an invented unit price of 35.

Feeder reference tags share a central mapping. Main contactors consistently use `-K<n>M`, and soft starters use `-U<n>`, matching the bridge and drawings. Fixed the missing soft-starter control diagram and prevented phantom DOL controls on nonmotor loads. Direct SVG renderers visibly mark drawings preliminary. Unknown fault level and breaking capacity remain unknown in the SLD instead of becoming 25 kA or a 400 V rating at another voltage.

Excel now includes actual wire/terminal schedules and an uncompleted clause-11 routine inspection checklist; it never invents inspection results. Commercial-sheet errors are no longer silently swallowed. Removed the unreferenced `schematic_generator.py` after a repository-wide reference check; the active IEC SLD/ladder generators remain covered.

Validation: 403 passed, 1 PDF check deselected in the final full run. Also 65 targeted BOM, quote, drawing, schedule and existing export tests passed. Cross-output tests cover DOL, star-delta, soft starter and VFD tags. Manufacturing dimensions, torque values and final component selections still require real OEM/design inputs.

## Stage 6: usable engineering inputs (BKL-P0-02, P2-01/02)

Connected the existing clipboard parser to an atomic GUI import action with a visible button and Ctrl+V on the feeder table. Invalid rows or duplicate identifiers leave the existing loads untouched; successful imports invalidate earlier calculations. Duplicate IDs are also rejected by the engine. Spreadsheet zero demand/phase values and fractional motor-start counts are no longer silently replaced or truncated.

Added source R/X and actual busbar geometry to advanced project inputs and RCD type/sensitivity/electrode resistance to the scrollable feeder editor. Preserved all existing model fields when editing a feeder. Assumption metadata now survives model/GUI/JSON roundtrips and is removed when the corresponding field is explicitly edited. Spreadsheet project defaults are recorded as assumptions. `ui_theme.py` now supplies the existing calculate-button colors without changing the palette; removed its unsupported blanket WCAG claim.

The existing single window, advanced-field toggle and formula drawer already provide the guided/expert workflow. No replacement UI or new design assets were needed. All three language files have the same 1081 keys. The unchanged calculate-button pairing was measured at 5.86:1. Validation: 409 passed, 1 PDF check deselected, including live GUI clipboard import, atomic rejection, RCD editing, preserved drafts and language changes.

## Stage 7: clean distribution inputs and measured coverage (BKL-P3-01, P0-01)

Both PyInstaller routes now package an explicit file list and a fresh database generated from copied seed files, rather than the mutable development database or whole directories. Migration extensions operate on the requested data directory. The build script also creates a clean release ZIP and preserves an existing portable user's database. CustomTkinter data is collected without copying its Python cache/source directory wholesale. Repository `.git` and project skills are not distribution inputs; deleting development instructions was unnecessary.

Validation: 412 passed, 1 PDF check deselected. Distribution tests check SQLite integrity, seed preservation, clean archive membership and preservation of existing portable user data. These tests exercise data/archive preparation with a test compiler; they do not establish a successful PyInstaller compilation or Windows execution.

Measured statement coverage across the five requested core modules is **93.07%** (1154 statements, 80 missed): engine 96%, busbar 96%, core verification 90%, TCC 81%, PE/SPD 61%. The combined 85% threshold passed. Coverage tooling is in `requirements-dev.txt`. Per-module gaps remain visible; the combined percentage is not a claim that each module reached 85%.

Run the measured check with Python 3.12 and an available desktop/X display:

```bash
python -B -m pytest -q -k 'not test_html_to_pdf_roundtrip' --cov=lv_assist.engine --cov=lv_assist.busbar --cov=lv_assist.pe_spd_engine --cov=lv_assist.tcc_analyzer --cov=lv_assist.core_verification --cov-report=term-missing --cov-fail-under=85
```

Windows executable creation/acceptance remains unrun on this Linux worker. The browser PDF failure is a separate recorded runtime limitation, not a passing or skipped-by-default test.

## Stage 8: numerical references, phase imbalance and verification boundaries

Added explicit single-phase allocation. Main current is now based on the busiest phase, with a phasor calculation of fundamental neutral current. Unassigned single-phase loads are conservatively grouped on the worst phase and reported as insufficient data rather than silently balanced. The report's 32/10/12 A example produces approximately 32 A main design current, 21.07 A fundamental neutral current and 77.78% imbalance. Single-phase cable notation now identifies L+N+PE. Phase allocation is editable and preserved in the feeder editor, calculation signatures and exports.

Transformer-derived maximum fault current applies the declared voltage factor (default cmax=1.1); minimum-voltage factor defaults to .95. Motor contribution is included in the maximum fault model and excluded from the firm minimum source. Source factors are editable advanced inputs. Enforced the supported 110–1000 V panel scope and power-factor range. Nonfinite breaking capacities cannot pass the standalone verifier. PE/SPD preselection now rejects invalid physical inputs and preserves the actual selected SPD type. Analytic TCC crossing tests provide an independent reference.

Automatic cable sizing now rechecks end-of-line disconnection and both phase/PE thermal energy for each candidate after choosing protection. An oversized protective-device regression exercises the additional resizing. Same-manufacturer filtering applies to motor starter components; out-of-range overload relays are no longer selected through a fallback. These checks remain preliminary without actual OEM curves/tables.

The clause-10 checklist no longer claims assembly conformity from assumed clearances, an intended dielectric test voltage, typical busbar data or the mere presence of a PE section. Physical/design-verification evidence is not recorded by this application, so such items remain NOT_VERIFIED and known calculation failures propagate. A numerical calculation passing is distinct from a verified assembly.

### Reconciliation of the attached numerical examples

The DOCX contains equations in Word math nodes as well as ordinary text. Both were extracted for comparison. Some proposed reference numbers are inconsistent with their own inputs: cos(phi_sc)=.25 gives R/X=.2582 and kappa≈1.4725, hence approximately 104.1 kA peak at 50 kA RMS, rather than the document's 100.4 kA. The 50 kA/.1 s/k=115 adiabatic result of 137.49 mm² does agree. The example's 25% largest-motor main-current allowance is an engineering choice, not a universal IEC requirement; it was not hardcoded as one. Likewise, 32 A at 400/sqrt(3) V is about 7.39 kW, not the example's separate 5.3 kW statement. The phase-current reference uses the explicitly stated currents.

Distribution-demand, individual motor-efficiency, hot-loop impedance, full-current phase/PE sizing, peak-factor, busbar bending/span and unbalanced-phase arithmetic have executable reference checks. OEM Type 2 coordination, detailed thermal charts and workshop geometry are not established by those arithmetic tests.

### Cloud GUI runtime correction

A real screenshot review exposed a worker issue that logical GUI tests missed: managed Python 3.12/Tk 9 returned zero width for Persian glyphs. System Python 3.13/Tk 8.6 exposes installed fonts and renders them. A separate GUI environment was installed, real windows/screenshots and startup calculations were checked, and the reusable installation/startup draft was updated. Both interpreters passed the full selected suite. See [cloud development instructions](CLOUD_DEVELOPMENT.md). The saved draft is not an environment publication.

## Final validation and open requirements

Final selected suite: **434 passed, 1 browser PDF test deselected**, on both Python 3.12 and Python 3.13/Tk 8.6. Python 3.12 core statement coverage: **95.65%** (1219 statements, 53 missed); engine 96%, busbar 96%, core verification 91%, PE/SPD 98%, TCC 96%. Each measured module exceeds 85%. The PDF test previously failed after a 120-second Chromium timeout, independently reproduced on minimal local HTML; it is not counted as passed. Real Persian window/editor rendering and the demo event loop were also checked.

| Backlog | Final disposition |
| --- | --- |
| P0-01 | Active integrations tested, unused renderer removed, coverage target met. Browser PDF and Windows acceptance remain separate limitations. |
| P0-02 | Physical input validation, motor/electrical units, atomic clipboard import and persistent assumption tracking implemented. Unconfirmed defaults remain provisional. |
| P0-03 | Maximum/minimum/peak calculations and ADS checks integrated; complete IEC 60909 validation requires real sequence impedances, source data and approved reference cases. |
| P0-04 | I2, phase/PE energy and post-selection resizing implemented. Actual clearing/let-through data and motor-start cable verification require OEM curves and starting power-factor/voltage limits. |
| P0-05 | Peak-factor, thermal correction and mechanical traces corrected; exact DIN/OEM current ratings, material properties and certified supports remain required. |
| P0-06 | Input signatures and direct-export stale/mixed-result guards implemented and tested. |
| P1-01 | SQLite runtime confirmed, provenance fields/gates added, release migration isolated. Missing OEM references/revisions remain unverified; none were invented. |
| P1-02 | Same-brand/range checks and VFD RCD incompatibility checks implemented. Tested Type 1/2 coordination matrices and device-specific RCD requirements remain external inputs. |
| P1-03 | Lumped thermal estimate explicitly preliminary; known component temperature limits checked. A complete IEC/TR 60890 solver/reference validation is not implemented without the required method coefficients, applicability inputs and OEM losses. |
| P1-04 | Rule categories/scopes and assembly-evidence boundary implemented. Formal clause/edition applicability and licensed reference tables still require review. |
| P1-05 | Shared BOM, consistent feeder references, wire/terminal schedules and uncompleted routine checklist implemented. Final manufacture still requires assigned parts, torque values, terminal/cable ratings and workshop geometry. |
| P2-01 | Existing unified shell, advanced fields and formula drawer retained and tested; live clipboard workflow added. |
| P2-02 | All three language files have 1088 matching keys; changed workflows exercised in GUI tests. Worker Persian rendering corrected through the supported Tk runtime. |
| P3-01 | Clean release data/archive preparation tested; actual PyInstaller compilation and clean Windows-machine acceptance are unrun. |

Remaining prerequisites are specific OEM datasets/curves, approved thermal and busbar reference tables, real installation/source data and a Windows acceptance environment. This record does not close those items or claim the application is ready to certify an assembly.

## Stage 9: enforce the source and application scope of selectivity tables (2026-11-07)

Source review found that the legacy migration marked every JSON selectivity rule as a verified manufacturer rule. Those rows did not establish an edition, page, tested part pair or voltage. The runtime also matched by series alone and applied a rating-ratio heuristic before checking a manufacturer table.

Rules now need an explicit reviewed-quality flag, manufacturer, document reference/revision, page/table reference, voltage and exact upstream/downstream part numbers. The migration derives its verification flag from that evidence instead of assigning it unconditionally. Existing databases are guarded at read time too. The engine passes the actual project voltage. A fully scoped table is evaluated before the preliminary ratio heuristic; it cannot apply to another manufacturer, part or voltage. The bundled legacy rules remain available for review but cannot establish verified selectivity.

Validation: **219 passed, 1 PDF test deselected** across the legacy engine suite and the new evidence regressions. Synthetic reviewed rules are explicitly named TEST fixtures; they are not delivered as manufacturer data. The unchanged pre-edit baseline was **434 passed, 1 deselected** with a local X display. The separate PDF roundtrip was attempted and failed: this worker's Chromium aborts because its SUID sandbox helper is not configured. No browser sandbox protection was disabled in application code. Windows acceptance and the external engineering datasets remain open.

### Delivery checks for the changed scope

- PASS, R-26: clipboard import and advanced/edit controls have exercised handlers, with atomic failure and stale-result behavior tested.
- PASS, R-34: existing light/dark and FA/EN/DE preservation regressions pass; no replacement palette was introduced.
- PASS, R-25: the retained primary-button text pairing measures 5.86:1; no blanket accessibility claim is made.
- PASS, R-23/R-37: no design assets were created; the existing desktop layout and identity were retained.
- PASS, R-36: computed/reference values are distinguished from assumptions, OEM verification and actual tests.
- FAIL, complete-release R-35: a full manual click-through of every legacy control and a clean Windows executable acceptance were not performed. Automated changed-workflow tests and real Linux window inspection are the evidence available.
- FAIL, full engineering sign-off: the external evidence and method work listed above remain open.
