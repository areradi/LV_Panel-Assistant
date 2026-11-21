# Enhancement: Use Manufacturer Let-Through Curves in Fault Energy Check

**Ticket ID:** ENH-2026-001  
**Status:** OPEN  
**Priority:** Medium  
**Branch:** feat/use-letthrough-curves  
**Author:** [Your Name]  
**Date:** 2026-11-21  

---

## Current Behavior

Engine uses fallback formula for PE sizing:  S_PE = sqrt(Ik^2 * t_clearing) / k


Example F01:
- Ik = 22.404 kA, t = 0.02 s, k = 115
- I2t = 22404^2 * 0.02 = 10,038,784 A2s
- S_PE = sqrt(10,038,784) / 115 = 27.6 mm2 -> 35 mm2 selected

---

## Problem

Fallback is conservative (safe) but inefficient:
- Actual let-through energy from manufacturer curve (3RV2021-4EA): 80,300 A2s
- Required S_PE with curve: sqrt(80,300) / 115 = 2.46 mm2 (PE min 10 mm2 sufficient)
- 125x overestimate leads to oversized cables

---

## Proposed Enhancement

When manufacturer let-through curve is available:
1. Look up device in tools/i2t_curves.csv (when verified)
2. Interpolate I2t at prospective current Ik
3. Use actual I2t instead of Ik^2 * t
4. Fall back to Ik^2 * t only if curve unavailable

---

## Implementation Plan

### 1. Add get_letthrough_i2t(device_part, ik_ka) to lv_assist/engine.py

Function signature:
- device_part: Part number (e.g., '3RV2021-4EA10')
- ik_ka: Prospective fault current in kA
- Returns: Let-through I2t in A2s, or None if not available

Data source:
- tools/i2t_curves.csv (only verification_status='VERIFIED' rows)

Interpolation:
- Log-linear between data points
- No extrapolation outside data range

### 2. Modify PE sizing to use actual I2t when available

Current:
- i2t = ik_ka^2 * clearing_time_s (fallback)

Proposed:
- i2t = get_letthrough_i2t(device_part, ik_ka)
- if i2t is None: i2t = ik_ka^2 * clearing_time_s (fallback)

### 3. Add pe_basis_str field to show which method was used

When fallback:
- "S_PE >= (I_ef * sqrt(t)) / k = (22.4 kA * 1000 * sqrt(0.02)) / 115 = 27.6 mm2 -> 35 mm2"

When curve:
- "S_PE from let-through curve 3RV2021-4EA10: I2t=80,300 A2s -> 10 mm2"

---

## Expected Impact

| Feeder | Current (fallback) | Proposed (curve) | Savings |
|--------|-------------------|-----------------|---------|
| F01 | 35 mm2 | ~16 mm2 | ~54% |
| Other feeders | TBD | TBD | TBD |

---

## Testing

1. Unit tests for get_letthrough_i2t():
   - Test lookup by part number
   - Test interpolation between points
   - Test fallback when curve unavailable
   - Test rejection of unverified rows

2. Integration tests:
   - Verify F01 PE sizing changes from 35 mm2 to ~16 mm2
   - Verify other feeders unaffected (no curve available)
   - Verify pe_basis_str correctly shows method used

3. Documentation:
   - Update ORACLE_FINDINGS.md with enhancement
   - Add entry to CHANGELOG.md

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

- [ ] get_letthrough_i2t() implemented and tested
- [ ] Only VERIFIED rows loaded from i2t_curves.csv
- [ ] F01 PE sizing uses let-through curve when available
- [ ] pe_basis_str shows method used
- [ ] All existing tests pass
- [ ] ORACLE_FINDINGS.md updated
- [ ] CHANGELOG.md entry added

---

## Related Work

- fix/p10-3rv-letthrough: Digitized 3RV2021-4EA curve (NOT_VERIFIED)
- F-031b: Fault energy check implementation
- F-01: Original discrepancy investigation

---

## Next Steps

1. Verify NEP461270226000 digitized values (currently NEEDS_REVIEW)
2. Add curve to tools/i2t_curves.csv with VERIFIED status
3. Implement get_letthrough_i2t()
4. Test and merge
