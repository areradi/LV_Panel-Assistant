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
- **E-02** PANEL-DATACODE-PROVENANCE with 11 part numbers in one cell
- **E-06** TCC chart legend overlap
- **E-07** Header/body column count mismatch
- **E-08** Disclaimer text glued to footer

### P2 Items
- **G-12** Table of contents / PDF bookmarks
- **Q-11** Grouping and subtotals per section
- **Q-12** Commercial document components (quote no, validity, payment terms)
- **E-10** Reduce report volume (12 pages to 7-8)

### Remaining from final QA (2026-11-14)
- [ ] Signature block in Design Verification still orphaned on own page
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