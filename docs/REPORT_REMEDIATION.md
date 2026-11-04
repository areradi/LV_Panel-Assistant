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
