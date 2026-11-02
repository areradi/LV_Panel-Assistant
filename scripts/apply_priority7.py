#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Priority 7 patch script - use _cards["enclosure"] for enclosure KPI.

Idempotent, safe:
1. Insert _enc_cards = _cards["enclosure"] before the _enc_pn line.
2. Replace the enclosure KPI configure() call to use W/H/D from _enc_cards
   (with proper units, "نامشخص" fallback when missing) instead of raw
   estimated_panel_* values.

Usage:
    python scripts/apply_priority7.py --dry-run
    python scripts/apply_priority7.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


TARGET = Path("lv_assist/gui.py")

MARKER = "# Priority 7: W/H/D from _cards"
START_ANCHOR = '_enc_pn = summary.selected_enclosure.part_number if'
CONFIGURE_ANCHOR = 'self.kpi_labels["enclosure"].configure(text=f"{_enc_pn}'

INSERT_BLOCK = '''        # Priority 7: W/H/D from _cards["enclosure"] (proper units, نامشخص when missing)
        _enc_cards = _cards["enclosure"]
'''

REPLACE_BLOCK = '''        enc_txt = f"{_enc_pn}\\nW:{_enc_cards['width']} H:{_enc_cards['height']} D:{_enc_cards['depth']}"
        self.kpi_labels["enclosure"].configure(text=enc_txt)
'''


def apply_all(content: str):
    if MARKER in content:
        print("  [SKIP] Priority 7 already applied")
        return content, 0

    lines = content.splitlines(keepends=True)
    changes = 0

    # 1) insert before _enc_pn line
    ins_at = None
    for i, line in enumerate(lines):
        if START_ANCHOR in line:
            ins_at = i
            break
    if ins_at is None:
        print("  [FAIL] _enc_pn anchor not found")
        return content, 0

    block = INSERT_BLOCK if INSERT_BLOCK.endswith("\n") else INSERT_BLOCK + "\n"
    lines[ins_at:ins_at] = block.splitlines(keepends=True)
    print(f"  [OK] inserted Priority 7 block before line {ins_at + 1}")
    changes += 1

    # 2) replace the configure line (search after insertion)
    cfg_idx = None
    for j in range(ins_at + 3, len(lines)):
        if CONFIGURE_ANCHOR in lines[j]:
            cfg_idx = j
            break
    if cfg_idx is None:
        print("  [FAIL] enclosure configure line not found")
        return "".join(lines), changes

    rep = REPLACE_BLOCK if REPLACE_BLOCK.endswith("\n") else REPLACE_BLOCK + "\n"
    lines[cfg_idx:cfg_idx + 1] = rep.splitlines(keepends=True)
    print(f"  [OK] replaced enclosure configure at line {cfg_idx + 1}")
    changes += 1

    return "".join(lines), changes


def main() -> int:
    ap = argparse.ArgumentParser(description="Priority 7: enclosure KPI uses _cards['enclosure']")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not TARGET.exists():
        print(f"[FAIL] {TARGET} not found")
        return 1

    with open(TARGET, "r", encoding="utf-8", newline="") as f:
        original = f.read()

    print(f"[INFO] file: {TARGET} ({len(original)} bytes)")
    patched, changes = apply_all(original)

    if changes == 0:
        print("[INFO] nothing to do - already applied")
        return 0

    if MARKER not in patched:
        print("[FAIL] sanity: marker missing")
        return 2

    if args.dry_run:
        print(f"[DRY-RUN] would apply {changes} change(s); not written")
        return 0

    with open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(patched)
    print(f"[OK] applied {changes} change(s); new size: {len(patched)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
