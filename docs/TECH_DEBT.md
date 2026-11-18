# Technical Debt Registry

## T-027d-e — Print QA Sprint 2 (P1/P2)

**Status:** Pending, low priority. Sprint 1 (P0) completed. Base commit: f95203b.
Items from Print QA report (2026-11-14) still open.

### P1 Items
- **G-01** BiDi validation in Chrome Headless PDF (pdftotext roundtrip)
- **Q-04** Multiple tags in single cell (one tag per line)
- **Q-08** Double-counting risk (busbar meters vs CU-BUSBAR-SET)
- **Q-09** Summary tiles without intermediate net cost
- **Q-10** Page break protection for totals/footer blocks
- **E-01** Wide tables in A4 portrait (8-column checks table)
- ~~**E-02** PANEL-DATACODE-PROVENANCE with 11 part numbers in one cell~~ (fixed in PR-A via `cell-evidence` class)
- **E-06** TCC chart legend overlap
- **E-07** Header/body column count mismatch
- **E-08** Disclaimer text glued to footer

### P2 Items
- **G-12** Table of contents / PDF bookmarks
- **Q-11** Grouping and subtotals per section
- **Q-12** Commercial document components (quote no, validity, payment terms)
- **E-10** Reduce report volume (12 pages to 7-8)

### Remaining from final QA (2026-11-14)
- [x] Signature block in Design Verification (fixed in PR-A)
- [ ] `file:///...` path in footer (check HTML vs Chrome)
- [ ] Section 10.5 in Design Verification clipped at page bottom
- [ ] ASSUMED_DEFAULT / "T2" / spd_class columns merging in Assumptions
- [ ] Footer text leaking into table on page 4 of Engineering Report
- [ ] Last page with single orphan row

## Proposed Approach

Consolidate 3 print CSS files into shared `print_common.py`:
- `lv_assist/exporters.py` (Engineering + Design Verification)
- `lv_assist/commercial.py` (Commercial Quotation)
- `lv_assist/outputs.py` (PDF pipeline)

Single source of truth for:
- Page size and margins (@page)
- Header/footer templates
- Table styles (border, header bg, zebra, padding)
- Page-break rules (orphans, widows, break-inside)
- BiDi isolation classes
- Number formatting (LTR, tabular-nums)

## Priority Order

1. Sprint 2 (P1): G-01, Q-04, Q-08, E-01, E-02, E-06, E-07
2. Sprint 3 (P2): G-12, Q-09, Q-11, Q-12, E-10
3. Final cleanup: Remaining QA items above
## T-036-SVG-BiDi — SVG Persian text BiDi + Overflow (UNRESOLVED)

**Status:** UNRESOLVED. WIP committed in wip(svg): tspan attempt (T-036-BiDi).

### Symptoms (visual QA 2026-11-16)
- IEC 61439 renders as C 61439 (IE dropped) in disclaimer FA
- (typisch) and Im appear in wrong positions
- Layout footer text overlaps with disclaimer
- Disclaimer overflows and is cut at edges in Layout/SLD/TCC

### Attempts made
1. **FSI/PDI** (\u2068...\u2069) — first attempt in 223909c — failed: Chrome Headless does not render Unicode isolation controls in SVG
2. **<tspan direction="ltr">** — WIP attempt — failed: still shows wrong order / cut

### Root cause (hypothesis, needs investigation)
- Chrome Headless SVG BiDi rendering may differ from browser rendering
- Text anchor (	ext-anchor="start"/"end") interacts with direction="rtl" in ways that break rendering
- Possibly PDF pipeline (--print-to-pdf) doesn't preserve SVG text BiDi attributes
- iewBox math + font metrics estimation for wrap may be inaccurate

### Investigation plan (for Sprint 3)
1. Reproduce in browser first (open generated SVG directly in Chrome/Firefox) vs PDF
2. If SVG is OK in browser but PDF is broken → it's the PDF pipeline, not SVG
3. If SVG is broken in browser too → check 	ext-anchor + direction combination
4. Consider alternative: use separate <text> elements per Latin/FA run with manual x positioning
5. Consider: render FA text as raster/image (not vector) — loses selectability but guarantees visual
6. Consider: use Vazirmatn font explicitly in SVG with ont-family="Vazirmatn"

### Files touched (WIP)
- lv_assist/drawing_status.py (render_bidi_text helper)
- 	ests/test_phase7_disclaimers.py (29 tests — pass but don't cover visual correctness)

### Not blocking
- Phase 7 can proceed to T-034
- T-036 (Disclaimer exists in SVG) technically complete, but visual rendering issue remains

## T-036-SVG-BiDi — RESOLVED AS ACCEPTED LIMITATION (2026-11-18)

**Status:** ACCEPTED LIMITATION — not blocking B2B.

### Background
SVG Persian text (disclaimer) has unresolved BiDi rendering issues in Chrome
Headless PDF generation. Three vector approaches failed:
1. FSI/PDI (U+2068...U+2069) — Chrome Headless does not render Unicode controls in SVG
2. <tspan direction="ltr"> — order still broken
3. wrap + tspan (drawing_status.py) — overflow fixed, BiDi not

### Decision
Accept as known limitation. Rationale:
- SVG is secondary B2B deliverable (PDF/Excel are primary)
- Raster fallback (Pillow + libraqm) requires:
  * FriBiDi DLL on Windows (not guaranteed in PyInstaller)
  * Vazirmatn font packaging + OFL license
  * 1.5-3 days work with PyInstaller risk
- Value vs cost is not favorable

### Workaround for customers
- Use HTML/PDF report (which has correct FA rendering via bdi + unicode-bidi)
- SVG disclaimer FA shows 'مقدماتی' correctly; only mixed Latin (IEC 61439)
  has minor order issue. This is cosmetic, not functional.

### If revisited (future)
Options:
1. Raster: Pillow + libraqm + Vazirmatn + PyInstaller config (risky)
2. Replace Chrome PDF pipeline with WeasyPrint (larger refactor)
3. HTML-only for FA: use 'Preliminary' EN universally in SVG (acceptable trade-off)

**Evidence:** See commits cfd71e7 (tspan WIP), 223909c (tspan, initial).
