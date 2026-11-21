# Oracle Findings

This file records differences and limits found while comparing the independent
oracles with the engineering engine. Oracle results are cross-checks; they are
not certificates of compliance or substitutes for manufacturer data.

## F-01 Resolution Path

**Discovered in**: F-031a (Cable Selection Oracle)

### Setup
- Feeder F01, MCC1 demo project
- Ib approximately 27.99 A, 400 V three-phase, PVC Cu, method C, length 45 m
- Maximum voltage drop 5% for this motor feeder

| Analysis layer | F01 phase section | Interpretation |
|---|---:|---|
| F-031a pure selection | 10 mm² | Minimum section passing thermal ampacity and voltage-drop checks |
| F-031b fault energy, RMS fallback | 35 mm² | At `t=0.02 s`, the single bus Ik point requires about 27.55 mm² adiabatic section; next standard cable is 35 mm² |
| F-031b manufacturer-curve candidate | ~2.5 mm² | At the bus point, candidate I²t implies about 2.46 mm² with Cu/PVC `k=115`; this constraint is not governing, pending review |
| Engine actual | 35 mm² | Engine uses the RMS fault-energy callback plus feeder-end checks; it does not consume the quarantined manufacturer-curve candidate |

## Constraint Analysis for F01

| Constraint | F01 evidence | Engine / oracle coverage | Conclusion |
|---|---|---|---|
| Thermal ampacity | With the copied Cu/PVC/method C table and correction factors, `k_total=0.696`. At 6 mm², corrected `Iz=28.5 A`, below the required `28.69 A`; at 10 mm², corrected `Iz=39.7 A`. | F-031a models this check; engine also applies its derating tables. | **Governing constraint in pure selection:** ampacity moves the minimum from 6 to 10 mm². Derating-factor accuracy remains a review item. |
| Voltage drop | At 10 mm², calculated drop is `1.27%`, below the 5% motor-feeder limit. At 4 mm² it is `3.15%`, still below the limit, but ampacity fails; 2.5 mm² gives `5.03%`. | F-031a and engine both check steady-state voltage drop during cable selection. | Not governing the 10 mm² pure-selection result. |
| Bus fault energy, RMS fallback | `Ik_bus=22.404 kA`, `t=0.02 s`; `I²t=10,038,784 A²s`. The adiabatic section at `k=115` is `27.55 mm²`, so the standard step is 35 mm². | F-031b checks this one supplied bus point. The engine uses an RMS estimate for its callback; the quarantined curve is not used. | Explains why the fallback path reaches 35 mm²; this is conservative and not a verified device let-through result. |
| Bus fault energy, manufacturer-curve candidate | Candidate is ~80,300 A²s (reading interval 78,100–82,500 A²s), equivalent to ~2.46 mm² at `k=115`. | Digitized candidate is quarantined and unverified; F-031b does not load it. | If confirmed, this bus-point energy check would not govern the 10 mm² thermal selection. It does not prove the engine's final result because feeder-end behavior remains unmodeled by this point. |
| Feeder-end fault energy and TN disconnection | The engine builds minimum end-of-line Ik from source impedance and the selected cable, estimates a separate clearing time, and checks phase/PE withstand using the greater of bus and feeder-end energy. | Engine checks are in `_candidate_fault_compatible` and `RULE-PHASE-I2T` / `RULE-PE-I2T`; F-031b uses only one bus Ik and one shared clearing time. | **Engine constraint not covered by F-031b:** the feeder-end fault profile and its clearing-time / TN ADS constraint (`RULE-FAULT-END`, `RULE-ADS-TN`). Its numerical contribution to the 35 mm² result is not isolated here. |

The pure-selection minimum is governed by thermal ampacity, not steady-state
voltage drop. The engine's final 35 mm² is the result of an additional
fault-compatibility path that uses estimated RMS energy at the bus and at the
feeder end; the available manufacturer-curve candidate changes only the
single bus-point estimate and is not yet verified. Therefore the exact
physical constraint governing the engine result is not fully resolved until
the 400 V curve candidate and feeder-end profile are reviewed together.

## Remaining Work

- **Thermal review:** verify the ambient-temperature and grouping derating
  factors used for F01, especially `k_total=0.696`, against the adopted
  installation conditions and source tables. This is the constraint governing
  F-031a's 10 mm² pure-selection result.
- **Fault-energy reconciliation:** review/promote the quarantined 3RV2021
  400 V candidate only after source and digitization review, then compare it
  with the engine's bus and feeder-end energy checks. Add the end-of-line Ik
  profile and its separate clearing time to any future oracle parity claim.
- **F-031c voltage-drop oracle:** not indicated by F01's current results;
  steady-state drop is 1.27% at the 10 mm² pure-selection result versus a 5%
  limit. Create F-031c only if broader coverage or another case shows voltage
  drop governing.

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
