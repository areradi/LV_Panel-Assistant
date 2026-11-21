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
  `catalogo-fusivel-2012-ingles.pdf`, page 15 (printed page 13). The table
  identifies family `5SE2 NEOZED`, operational class `gG`, and rated voltage
  400 V AC / 250 V DC. It gives I²ts columns at 1 ms and 4 ms, and I²ta columns
  at 230 V AC and 400 V AC. The 230 V I²ta header carries the `t < 4 ms`
  qualifier; the 400 V column is separately recorded. For 32 A, the 400 V AC
  I²ta entry is 5,500 A²s. The prospective Ik is not stated, and the catalog
  legend has not been checked to determine whether the values are maximum
  limiting values or typical/sample values. Envelope direction remains
  unknown. All rows remain unverified and are not loaded by the oracle.
- The catalog pages 142–143 belong to the SITOR Semiconductor Fuses section.
  Their `Ip >= 10 × In` and `p.f. = 0.35` rules are not applied to 5SE2 NEOZED
  gG; no extension to that family is made without an explicit general or
  NEOZED legend.
- Page 252 of local `manual_SIRIUS_circuit_breaker_3RV_en-US.pdf`, section
  11.13, covers the 3RV2917-1A / 3RV2917-1E busbar infeed system. Its table
  states upstream protective-device limits (`Id max` / `I2t max`) for that
  infeed accessory. It is not data for the F01 feeder cable or PE and is not
  used to close F01. If those table values are cited elsewhere, `I2t max` must
  retain the source unit kA²s; do not label it A²s or import it into the cable
  I²t calculation.
- The locally archived Siemens drawing applicable to F01 is
  `NEP461270226000-02_AA`, titled `I²t-characteristic`, page 1/1. It identifies
  model `3RV2021-4EA.. + 3RV2121-4EA..`, setting range 27–32 A, and separate
  400 V, 500 V, and 690 V traces. Its internal approval date is `2018-12-20`.
  Local path:
  `C:\Users\AsuS\Desktop\DataBase\_organized\A_critical_datasheets\siemens\NEP461270226000-02_AA_201907050913320867.pdf`.
  SHA-256: `542715B3D7EE18FB866B0460A627D70A91EEA60B7A93B4FE1BEDC8ADBB2A051B`.
  The file hash, embedded title/model/range, drawing number, and approval date
  were checked on `2026-11-21`. The model and setting range match the F01
  selection `3RV2021-4EA10`, 27–32 A. Use the 400 V trace for the F01 point.
- Controlled digitization of the 400 V trace at prospective current
  `Ik = 22,404 A` gives a candidate `I²t ≈ 80,300 A²s`, with a visual reading
  interval of `78,100–82,500 A²s`. This interval represents digitization and
  line-width/calibration reading uncertainty only; it is not a manufacturer
  tolerance or statistical confidence interval. The PDF contains vector paths:
  the horizontal current axis was calibrated at `10⁴ A` and `10⁵ A`, and the
  vertical I²t axis at `10⁴ A²s` and `10⁵ A²s`. Logarithmic interpolation was
  made on the 400 V path segment bracketing the target. The target lies inside
  the plotted 400 V trace range; no extrapolation was used. The trace point is
  retained only in `tools/i2t_curves_unverified.csv` with
  `verification_status=NEEDS_REVIEW`; it is not loaded by the oracle and has
  not been added to `tools/i2t_curves.csv`.
- The previously considered drawing `A5E31487886029A-02_AA` is the standalone
  `3RV2031-4EA..-0BA0` chart with setting range 22–32 A. It is not the F01
  device `3RV2021-4EA10`, so it remains **NOT_APPLICABLE_TO_F01** and may be
  retained only as a reference for the 3RV2031 family. Its local SHA-256 is
  `FB770834ED632995C6689888DD31A1CB34C725CC6C68D2FEEF508E3C86C8335C`.
  This Siemens Industry Online Support chart is Entry ID `104095708`, drawing
  version `A5E31487886029A-02_AA`, dated `2018-03-01`, page 1/1; its 400 V
  trace and 22–32 A range describe the 3RV2031 family only. Source URL:
  `https://support.industry.siemens.com/cs/attachments/104095708/A5E31487886029A-02_AA_201804091016500799.pdf`
  (accessed `2026-11-21`). Exact-part SIMARIS link:
  `https://curves.simaris.siemens.com/curves/3RV2031-4EA10-0BA0`.
- Drawing `A5E31515454006N-02_AA` is explicitly titled
  `3RV2331-4WC.. + 3RV2021-4EA..`, setting range 27–32 A, and its chart note
  specifies `690V_In=27 - 32 A / Limiter 3RV2331-4WC..+ 3RV2021-4EA..`.
  Because its trace represents the 3RV2331 limiter combined with the MPCB, it
  is **NOT_APPLICABLE_TO_F01**, which selects the standalone 3RV2021-4EA10.
  Retain it as a reference for limiter+MPCB combinations only. Local file:
  `C:\Users\AsuS\Desktop\DataBase\_organized\A_critical_datasheets\siemens\A5E31515454006N-02_AA_201604111202410176.pdf`;
  SHA-256 `E95894DF0F7A4EEE193C908DE3766D41B183ACC952A3F2D00701CF72A1E5BF35`.
  Neither older drawing is used to infer F01 let-through energy.
- F01 curve status: **LOCAL_COPY_ARCHIVED; CANDIDATE_DIGITIZED;
  NOT_VERIFIED; NEEDS_REVIEW; NOT_IN_ACTIVE_CURVES**. The candidate remains
  quarantined and is not promoted to verified curve data.
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
  clearing interval instead of the device transient let-through I²t is expected
  to be conservative (an energy overestimate). The F01-matching 3RV2021
  400 V trace now gives a quarantined candidate near 80,300 A²s at 22,404 A,
  versus the RMS fallback `22,404² × 0.02 = 10,038,784 A²s` (about 125 times
  larger). With Cu/PVC `k=115`, the candidate corresponds to an adiabatic
  requirement of about `2.46 mm²`, versus about `27.55 mm²` from the fallback.
  If review confirms the digitization and applicability, this bus-energy point
  alone would not explain a 35 mm² cable selection; the other engine checks,
  feeder-end fault point, and full trip behavior still require separate
  validation. The candidate remains quarantined and is not used by the oracle.

## F-031a scope and next steps

- F-031a covers baseline cable selection and reports its copied table
  assumptions.
- F-031b adds a standalone fault-energy layer with source labels and explicit
  assumptions.
- Before design approval use, verify the adopted standards edition and use
  manufacturer curves for the actual protective device.
