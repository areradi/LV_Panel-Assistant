# Oracle Findings

This file documents **discrepancies** between the independent Oracle
implementations and the main engine. Each finding is a **feature**
(the oracle catching a genuine scope difference), not a bug.

## F-01: F01 cable section (Oracle vs full engine) — 2026-11-16

**Discovered in**: F-031a (Cable Selection Oracle)

### Setup
- Feeder F01, MCC1 demo project
- Ib ≈ 27.99 A, 400V 3-phase, PVC Cu, method C, length=55m
- max_vdrop=3%

### Result
| Layer | Phase section | Reason |
|---|---|---|
| Oracle (pure selection) | **10 mm²** | Iz, ΔU, PE — all pass at 10mm² |
| select_feeder_cable without dditional_check | **10 mm²** | match ✅ |
| Full engine (with dditional_check) | **35 mm²** | PE/fault compatibility forces 35mm² |

### Interpretation
- **Not a bug**: the oracle correctly does pure ampacity + ΔU + PE sizing.
- **Engine adds a constraint**: after selecting a section, it verifies that
  fault-current energy through PE is within adiabatic limits. At 10mm²,
  this constraint fails → engine bumps to 35mm².
- **Oracle's value**: isolates the "pure selection" step, making the extra
  constraint visible and testable independently.

### Architecture implication
- **F-031a** = pure selection (current state, complete).
- **F-031b** = fault-energy compatibility layer (planned).
- F-031a + F-031b should match full engine for all demo feeders.

### Cross-check status
All 4 demo feeders (F01-F04) match between Oracle and
select_feeder_cable(without additional_check) — see
	ests/test_oracle_cable.py::test_cross_check_demo_feeders.

### Next steps
1. F-031b: implement fault-compatibility oracle (I²t check on PE).
2. After F-031b: compare F-031a + F-031b with full engine → should match.
3. Document any remaining discrepancies with root cause.