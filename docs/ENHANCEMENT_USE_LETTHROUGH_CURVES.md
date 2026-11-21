# Enhancement: Use Manufacturer Let-Through Curves in Fault Energy Check

**Ticket ID:** ENH-2026-001  
**Status:** IN REVIEW
**Priority:** Medium  
**Branch:** feat/use-letthrough-curves  
**Author:** [Your Name]  
**Date:** 2026-11-21  

---

## Current Behavior

The engine loads only `VERIFIED` points from `tools/i2t_curves.csv`. When a
matching point or in-range interpolation is unavailable, the existing PE
fallback remains `S_PE = sqrt(Ik^2 * t_clearing) / k`.


Example F01:
- Ik = 22.404 kA, t = 0.02 s, k = 115
- I2t = 22404^2 * 0.02 = 10,038,784 A2s
- S_PE = sqrt(10,038,784) / 115 = 27.6 mm2 -> 35 mm2 selected

---

## Problem

Fallback is conservative (safe) but inefficient:
- Verified 3RV2021-4EA let-through point at 22.404 kA and 400 V: 80,300 A2s
- Adiabatic area from the curve: sqrt(80,300) / 115 = 2.46 mm2; the tabular PE
  minimum for a 10 mm2 phase conductor remains 10 mm2
- Engine F01 phase and PE sections changed from 35 mm2 to 10 mm2. Thermal
  ampacity governs phase selection; voltage drop is 1.27% against a 5% limit.

---

## Implemented Behavior

The engine maps the selected 3RV2021-4EA10 MPCB to its verified curve row,
queries at the bus prospective Ik, and uses the returned I²t in phase/PE
fault-energy checks. A single-point curve is accepted only within ±2% of its
recorded Ik. Multi-point curves use log-log interpolation between points;
outside-range queries return `None`. Missing or empty curve files therefore
leave the RMS fallback active.

---

## Implementation Plan

### 1. Loader

- `tools/i2t_curve_loader.py` provides `I2tCurveLoader(csv_path)` and
  `get_letthrough_i2t(device_type, rated_a, ik_ka)`.
- Only rows marked `VERIFIED` are accepted. Interpolation is log-log and
  extrapolation is disabled.

### 2. Engine PE/fault-energy path

The selected curve energy is used for phase-section and PE adiabatic sizing,
the bus portion of the fault-compatibility callback, and the associated
validation evidence. The feeder-end fault point continues to use its existing
estimated clearing-time fallback because no verified curve point is available
there.

### 3. PE basis display

When fallback:
- "S_PE >= (I_ef * sqrt(t)) / k = (22.4 kA * 1000 * sqrt(0.02)) / 115 = 27.6 mm2 -> 35 mm2"

When curve:
- `let-through curve 3RV2021-4EA10 @ 22.404 kA: I2t=80,300 A2s -> S=2.46 mm2 (IEC 60364-5-54)`

---

## Expected Impact

| Feeder | Current (fallback) | Proposed (curve) | Savings |
|--------|-------------------|-----------------|---------|
| F01 | 35 mm2 | 10 mm2 phase / 10 mm2 PE | ~71% section reduction |
| Other feeders | TBD | TBD | TBD |

---

## Testing

1. Loader tests cover verified-only loading, single-point tolerance,
   log-log interpolation, no extrapolation, and missing/empty files.
2. Engine tests verify F01 uses the curve and retains the 35 mm2 fallback
   when the active curve file is empty.
3. The F-031b standalone oracle remains on its formula-level fallback; this
   integration connects the loader to the engine only.
4. `ORACLE_FINDINGS.md` records the changed engine behavior and constraint.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wrong curve used for device | Non-conservative PE sizing | Only use VERIFIED rows; require manual review |
| Interpolation error | Inaccurate I2t | Log-linear interpolation; validate against known points |
| Missing curve for device | No improvement | Fall back to Ik^2 * t (safe) |
| Curve outdated | Incorrect I2t | Track curve_date; prefer newer curves |

---

## Acceptance Criteria

- [x] `I2tCurveLoader.get_letthrough_i2t()` implemented and tested
- [x] Only `VERIFIED` rows loaded from `i2t_curves.csv`
- [x] F01 phase/PE fault-energy path uses the 3RV2021 let-through point
- [x] `pe_basis_str` identifies curve, device, Ik, I²t, and adiabatic area
- [x] Existing and new tests pass
- [x] `ORACLE_FINDINGS.md` updated
- [ ] `CHANGELOG.md` entry (not included in this scoped file set)

---

## Related Work

- fix/p10-3rv-letthrough: 3RV2021-4EA curve manually cross-read and verified;
  see `docs/VERIFICATION_NEP461270226000.md`
- F-031b: Fault energy check implementation
- F-01: Original discrepancy investigation

---

## Next Steps

1. Review the IN REVIEW implementation, including packaged-app data-file
   availability and feeder-end fault-energy treatment.
2. Keep unverified devices on the existing RMS fallback until their curves
   have equivalent source review.
