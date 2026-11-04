# Attached audit remediation

The supplied `1.docx` is an assessment based on archive listings, not an executed source review. Its backlog is tracked here against source and runtime evidence. Missing `.pyc` files are not evidence of missing integration: this project deliberately runs Python with `-B`.

## Stage 1: input validation (BKL-P0-02)

Rejected two-phase inputs and nonfinite clipboard power/cable lengths. Input edits now receive the same Pydantic validation as construction. Electrical loads use electrical input kW without a motor-efficiency divisor; motor shaft power retains that divisor. Omitted model and clipboard defaults are exposed as `assumed_fields` rather than being indistinguishable from explicit inputs.

Validation: 375 passed, 1 browser-dependent PDF check deselected, using Python 3.12 and the virtual X display. The PDF roundtrip was attempted during environment preparation and timed out after 120 seconds; it is not a passing check.

## Remaining backlog

## Stage 2: enforce calculation state at export boundaries (BKL-P0-06)

The engine records a SHA-256 signature of all project and feeder inputs. Direct Excel/HTML/SVG, layout, wiring, BOM, commercial, and bridge calls reject changed inputs and feeder outputs from another calculation before writing files. Serialized calculations retain their input snapshot for verification. Live references also detect edits, additions, and replacements in the original feeder list. GUI form edits continue to use the existing stale guard until recalculation.

Validation: the existing 375-test baseline passed with these guards; 22 targeted remediation tests passed, including stale direct exports, recovery after recalculation, mixed result rejection, and serialized snapshot mutation. A result signature establishes input consistency, not engineering approval.

| Audit ID | Source assessment / remaining work |
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
