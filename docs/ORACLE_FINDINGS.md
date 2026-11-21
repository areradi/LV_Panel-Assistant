# Oracle Findings

This file records differences and limits found while comparing the independent
oracles with the engineering engine. Oracle results are cross-checks; they are
not certificates of compliance or substitutes for manufacturer data.

## F-01: F01 cable section (Oracle vs full engine) — 2026-11-16

**Discovered in**: F-031a (Cable Selection Oracle)

### Setup
- Feeder F01, MCC1 demo project
- Ib approximately 27.99 A, 400 V three-phase, PVC Cu, method C, length 55 m
- Maximum voltage drop 3%

### Result
| Layer | Phase section | Reason |
|---|---:|---|
| Cable-selection oracle | 10 mm² | Ampacity, voltage drop and baseline PE sizing pass |
| `select_feeder_cable` without `additional_check` | 10 mm² | Base selector agrees |
| Full engine with `additional_check` | 35 mm² | Fault-current compatibility rejects smaller sections |

### Interpretation
- The F-031a oracle covers cable selection without the engine's final
  fault-compatibility callback.
- The engine checks both bus and feeder-end fault energy against phase and PE
  adiabatic limits. At 10 mm² the callback rejects the candidate, so the engine
  continues to a larger phase section.
- F-031b adds an independent single-point fault-energy calculation. Its inputs
  do not include the network source impedance or feeder-end Ik profile needed
  to reproduce the engine callback exactly; it must not claim full parity.

## F-031b: Fault-energy oracle data and limits

### Source snapshot
- `tools/i2t_curves.csv` contains only the header. There are no verified,
  Ik-indexed points available to the oracle.
- All 15 previously copied fuse rows are quarantined in
  `tools/i2t_curves_unverified.csv`. They identify the actual source file
  `catalogo-fusivel-2012-ingles.pdf`, page 15, and the table header
  `I2ta [A2s] / 400 V AC (t < 4 ms)`. The prospective test current and test
  conditions needed to relate them to Ik are not stated in the extracted row.
  The value direction (upper/lower envelope) remains unknown until the source
  page is visually verified. These rows are not loaded by the oracle.
- A Siemens 3RV2031-4EA..-0BA0 I²t characteristic chart is available for the
  22–32 A setting range. The official one-page chart, drawing
  `A5E31487886029A-02_AA`, is dated 2018-03-01 and includes 400 V traces:
  [Siemens 3RV2031-4EA..-0BA0 I²t characteristic](https://support.industry.siemens.com/cs/attachments/104095708/A5E31487886029A-02_AA_201804091016500799.pdf).
  The local bank contains the matching datasheet and 3RV manuals; the 2009
  manual (page 23) says the characteristic curves can be ordered from Siemens
  Technical Assistance. The numeric chart was located in Siemens' online
  source, not as a local bank file. Its existence is confirmed, but a numeric
  value at the F01 fault current has not been digitized and independently
  checked. No points from it are entered in the active CSV yet.
- Verified curve data is used only at an exact point or by interpolation
  between bracketing source points. Extrapolation beyond the source range is
  rejected. A device with no verified curve uses the explicit RMS estimate
  described below, never quarantined rows.

### Estimates and interpretation
- With no verified curve, the fallback for every protective-device type is
  `I²t = Ik_RMS² × t`; no 2.5 peak multiplier is applied. This is a formula
  estimate, not a manufacturer let-through result.
- Clearing time is mandatory when the fallback is used. Missing, non-positive,
  non-finite, or greater-than-5-second times raise `ValueError`; no default
  clearing time is substituted. The 5-second ceiling follows the adiabatic
  method's validity limit used by this oracle.
- Approximate selections report `selection_status="PROVISIONAL"` and
  `is_safety_recommendation=False`. Warnings identify the unavailable curve,
  assumed Ik/time, computed I²t and required PE section, and the selected phase
  and PE sections (or the absence of a compatible pair).
- Icu denotes a breaking-capacity rating; it is not a let-through peak current.
  No Icu-to-let-through conversion is performed.
- PE sizing applies `S = sqrt(I²t) / k` with the requested Cu/Al and PVC/XLPE
  factors, then selects the next standard section. Unsupported data returns a
  warning or no feasible standard section rather than a fabricated rating.

### Parity boundary
- `select_cable_with_fault_energy` uses a single supplied Ik point. The current
  engine callback uses the greater of bus energy and feeder-end energy, with
  separate estimated clearing times and a TN disconnection-time constraint.
- Exact full-engine comparison needs per-device trip/let-through curves plus
  source and feeder-end network inputs. F-031b is therefore a complementary
  check and not a replacement for engine validation.
- The selector's `reason` reports selection mode (`AUTO` or `USER_FIXED`), while
  `selection_status` separately reports whether that mode passed its checks.
- The F01 demo is a three-phase motor feeder and the engine labels its cable
  `3P+PE`, without a neutral core. Here `neutral_mm2=0` means no neutral
  conductor is required by the modeled feeder. A neutral for auxiliary loads
  needs an explicit input; assigning one to every three-phase motor would add
  an unsupported cable requirement.
- The F01 test is a **formula-level cross-check with shared clearing-time
  input**, not an independent full validation. It takes bus-total Ik from
  `PanelSummaryOutput.ik_bus_total_ka` (22.404 kA for the demo; displayed as
  22.4 kA at one decimal), clearing time
  from the engine output (0.02 s), and the auto-sizing state from
  `FeederInput.cable_section_mm2` (`None`). It therefore does not independently
  validate those engine-derived values or manufacturer let-through behavior.
- The F01 Oracle input uses the engine's MPCB overload-ratio fallback of 1.3
  (`engine.py`, `i2_factor` selection). The 1.45 value in the cable selector is
  the IEC coordination ratio for `I2 <= 1.45 Iz`; it is not the MPCB-specific
  `I2/In` input. The test asserts the resolved MPCB ratio is 1.3. Its maximum
  voltage-drop limit and adjustable-protection flag follow the same engine
  policy based on feeder load type and selected device type.
- F-01 is not fully resolved.
- For this formula-level comparison, using prospective RMS Ik over the shared
  clearing interval instead of a device transient let-through I²t is expected
  to be conservative (an energy overestimate). This direction is an engineering
  assumption pending comparison with the device curve. The official Siemens
  3RV2031 I²t curve for 22–32 A at 400 V has been located, but is not a local
  bank file and has not been digitized, verified, or added to the CSV. Next
  task: extract and verify that curve.

## F-031a scope and next steps

- F-031a covers baseline cable selection and reports its copied table
  assumptions.
- F-031b adds a standalone fault-energy layer with source labels and explicit
  assumptions.
- Before design approval use, verify the adopted standards edition and use
  manufacturer curves for the actual protective device.
