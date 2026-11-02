#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Priority 3 patch script — idempotent.

Applies three targeted edits to ``lv_assist/gui.py``:

1. Import ``format_summary_cards`` from ``lv_assist.summary_workflow``.
2. Replace the ``main_current`` KPI so that real breaker ``In`` and panel
   ``design current`` are shown separately (with a ⚠ marker when In < Id).
3. Make the ``enclosure`` KPI ``None``-safe.

Re-running is safe: each patch detects its own marker first and skips.

Usage
-----
    python scripts/apply_priority3.py --dry-run    # preview
    python scripts/apply_priority3.py              # apply
    python scripts/apply_priority3.py --file lv_assist/gui.py

Rollback: ``git restore lv_assist/gui.py`` (script never touches git).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------- markers and payloads ----------

IMPORT_MARKER = "from lv_assist.summary_workflow import format_summary_cards"
IMPORT_ANCHOR = "from lv_assist.gui_helpers import ("

MAIN_CURRENT_MARKER_NEW = "In: {_mp['rated_current_in']}"
MAIN_CURRENT_TARGET = (
    'self.kpi_labels["main_current"].configure(text=f"{summary.design_main_current_a}A'
)
MAIN_CURRENT_NEW = r'''        # Priority 3: separate real In from design current (was: design shown as In)
        _cards = format_summary_cards(
            summary.main_breaker,
            summary.selected_enclosure,
            design_current_a=summary.design_main_current_a,
        )
        _mp = _cards["main_protection"]
        _warn = ""
        if summary.main_breaker and summary.main_breaker.rated_current_in_a:
            if summary.main_breaker.rated_current_in_a < summary.design_main_current_a:
                _warn = " ⚠"
        _pn = summary.main_breaker.part_number if summary.main_breaker else "-"
        main_txt = f"In: {_mp['rated_current_in']} | Id: {_mp['design_current']}{_warn}\n{_pn}"
        self.kpi_labels["main_current"].configure(text=main_txt)
'''

ENCLOSURE_MARKER_NEW = (
    "_enc_pn = summary.selected_enclosure.part_number if summary.selected_enclosure else"
)
ENCLOSURE_TARGET = (
    'self.kpi_labels["enclosure"].configure(text=f"{summary.selected_enclosure.part_number}'
)
ENCLOSURE_NEW = r'''        _enc_pn = summary.selected_enclosure.part_number if summary.selected_enclosure else "-"
        self.kpi_labels["enclosure"].configure(text=f"{_enc_pn}\n({int(summary.estimated_panel_width_mm)}x{int(summary.estimated_panel_height_mm)})")
'''

# ---------- helpers ----------


def _replace_line_containing(
    lines: list[str], unique_substring: str, new_block: str, *, label: str
) -> tuple[list[str], bool]:
    idx = -1
    for i, line in enumerate(lines):
        if unique_substring in line:
            idx = i
            break
    if idx == -1:
        print(f"  [FAIL] {label}: target line not found")
        return lines, False

    dup = sum(1 for ln in lines if unique_substring in ln)
    if dup > 1:
        print(f"  [WARN] {label}: {dup} matches, replacing first")

    new_lines = new_block.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    lines[idx : idx + 1] = new_lines
    print(f"  [OK] {label}: replaced line {idx + 1}")
    return lines, True


def _insert_after_block(
    lines: list[str], anchor_start: str, insertion: str, *, label: str
) -> tuple[list[str], bool]:
    start_idx = -1
    for i, line in enumerate(lines):
        if anchor_start in line:
            start_idx = i
            break
    if start_idx == -1:
        print(f"  [FAIL] {label}: anchor not found")
        return lines, False

    end_idx = -1
    for j in range(start_idx, min(start_idx + 40, len(lines))):
        if lines[j].strip() == ")":
            end_idx = j
            break
    if end_idx == -1:
        print(f"  [FAIL] {label}: closing ')' not found")
        return lines, False

    insert_lines = insertion.splitlines(keepends=True)
    if insert_lines and not insert_lines[-1].endswith("\n"):
        insert_lines[-1] += "\n"

    lines[end_idx + 1 : end_idx + 1] = insert_lines
    print(f"  [OK] {label}: inserted after line {end_idx + 1}")
    return lines, True


# ---------- main ----------


def apply_all(content: str) -> tuple[str, int]:
    lines = content.splitlines(keepends=True)
    changes = 0

    # 1) import
    joined = "".join(lines)
    if IMPORT_MARKER in joined:
        print("  [SKIP] summary_workflow import already present")
    else:
        lines, changed = _insert_after_block(
            lines,
            anchor_start=IMPORT_ANCHOR,
            insertion=f"\n{IMPORT_MARKER}\n",
            label="import",
        )
        changes += int(changed)

    # 2) main_current KPI
    joined = "".join(lines)
    if MAIN_CURRENT_MARKER_NEW in joined:
        print("  [SKIP] main_current KPI already patched")
    else:
        lines, changed = _replace_line_containing(
            lines,
            unique_substring=MAIN_CURRENT_TARGET,
            new_block=MAIN_CURRENT_NEW,
            label="main_current KPI",
        )
        changes += int(changed)

    # 3) enclosure KPI
    joined = "".join(lines)
    if ENCLOSURE_MARKER_NEW in joined:
        print("  [SKIP] enclosure KPI already patched")
    else:
        lines, changed = _replace_line_containing(
            lines,
            unique_substring=ENCLOSURE_TARGET,
            new_block=ENCLOSURE_NEW,
            label="enclosure KPI",
        )
        changes += int(changed)

    return "".join(lines), changes


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Priority 3 patches to gui.py")
    ap.add_argument("--file", default="lv_assist/gui.py", help="Path to gui.py")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[FAIL] file not found: {path}")
        return 1

    with open(path, "r", encoding="utf-8", newline="") as f:
        original = f.read()

    print(f"[INFO] file: {path}  ({len(original)} bytes)")
    patched, changes = apply_all(original)

    if changes == 0:
        print("[INFO] nothing to do — all patches already applied")
        return 0

    if "def _refresh_results_views" not in patched:
        print("[FAIL] sanity: _refresh_results_views missing in result!")
        return 2
    if IMPORT_MARKER not in patched:
        print("[FAIL] sanity: import marker missing in result!")
        return 2

    if args.dry_run:
        print(f"[DRY-RUN] would apply {changes} patch(es); file not written")
        return 0

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(patched)
    print(f"[OK] applied {changes} patch(es); new size: {len(patched)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())