#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Priority 6 patch script - wire SmartCatalogSearch into the catalog tab.

Idempotent, additive, safe. Does NOT touch add/update/delete or prices logic.

Usage:
    python scripts/apply_priority6.py --dry-run
    python scripts/apply_priority6.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


TARGET = Path("lv_assist/gui.py")

IMPORT_MARKER = "from lv_assist.catalog_smart_search import open_smart_search"
IMPORT_ANCHOR = "from lv_assist.summary_workflow import format_summary_cards"

HELPER_MARKER = "def _smart_catalog_search_ids("
HELPER_METHOD = '''    def _smart_catalog_search_ids(self, query: str) -> set:
        """Priority 6: return set of matched device_ids (empty on error)."""
        try:
            if not hasattr(self, "_smart_catalog_search"):
                self._smart_catalog_search = open_smart_search()
            result = self._smart_catalog_search.search(query)
        except Exception:
            return set()
        ids = set()
        for group in result.values():
            for row in group:
                did = row.get("device_id")
                if did:
                    ids.add(str(did))
        return ids

'''

REFRESH_START = "    def _refresh_catalog_tree(self):"
REFRESH_END = "    def catalog_repo_devices(self) -> List[CatalogDevice]:"
REFRESH_IDEMPOTENT_MARKER = "# Priority 6: SmartCatalogSearch"

REFRESH_NEW = '''    def _refresh_catalog_tree(self):
        if not hasattr(self, "tree_catalog"):
            return
        query = (self.ent_cat_search.get() or "").strip() if hasattr(self, "ent_cat_search") else ""
        for item in self.tree_catalog.get_children():
            self.tree_catalog.delete(item)
        self._prices_cache = CatalogRepository().list_prices()

        devices = self.catalog_repo_devices()

        # Priority 6: SmartCatalogSearch (Persian normalization + numeric guard
        # + fuzzy matching). Falls back to naive substring if unavailable.
        if query:
            matched_ids = self._smart_catalog_search_ids(query)
            if not matched_ids:
                ql = query.lower()
                devices = [
                    d for d in devices
                    if ql in d.part_number.lower()
                    or ql in d.series.lower()
                    or ql in d.manufacturer.lower()
                ]
            else:
                devices = [d for d in devices if d.part_number in matched_ids]

        for d in devices:
            price = self._prices_cache.get(d.part_number)
            price_txt = f"{price['unit_price']:g} {price['currency']}" if price else "-"
            self.tree_catalog.insert("", "end", values=(
                d.part_number, d.manufacturer, d.series, d.device_type,
                d.rated_current_in_a, d.icu_ka_400v, d.motor_kw_400v, d.power_loss_w,
                price_txt, tr(f"quality_{d.data_quality.value}")))

'''


def _insert_after(lines, anchor, new_block):
    for i, line in enumerate(lines):
        if anchor in line:
            block = new_block if new_block.endswith("\n") else new_block + "\n"
            lines[i + 1:i + 1] = block.splitlines(keepends=True)
            return lines, True, i + 1
    return lines, False, -1


def _insert_before(lines, anchor, new_block):
    for i, line in enumerate(lines):
        if line.startswith(anchor):
            block = new_block if new_block.endswith("\n") else new_block + "\n"
            lines[i:i] = block.splitlines(keepends=True)
            return lines, True, i
    return lines, False, -1


def apply_all(content: str):
    lines = content.splitlines(keepends=True)
    changes = 0

    # 1) import
    if IMPORT_MARKER in content:
        print("  [SKIP] import already present")
    else:
        lines, ok, pos = _insert_after(lines, IMPORT_ANCHOR, "\n" + IMPORT_MARKER)
        if ok:
            print(f"  [OK] import inserted after line {pos}")
            changes += 1
        else:
            print("  [FAIL] import: anchor not found")

    # 2) helper method
    joined = "".join(lines)
    if HELPER_MARKER in joined:
        print("  [SKIP] helper method already present")
    else:
        lines, ok, pos = _insert_before(lines, REFRESH_START, HELPER_METHOD)
        if ok:
            print(f"  [OK] helper method inserted before line {pos + 1}")
            changes += 1
        else:
            print("  [FAIL] helper method: anchor not found")

    # 3) refresh body
    start = end = None
    for i, line in enumerate(lines):
        if start is None and line.startswith(REFRESH_START):
            start = i
        elif start is not None and line.startswith(REFRESH_END):
            end = i
            break
    if start is None or end is None:
        print("  [FAIL] _refresh_catalog_tree: markers not found")
    else:
        current = "".join(lines[start:end])
        if REFRESH_IDEMPOTENT_MARKER in current:
            print("  [SKIP] _refresh_catalog_tree already patched")
        else:
            block = REFRESH_NEW if REFRESH_NEW.endswith("\n") else REFRESH_NEW + "\n"
            lines[start:end] = block.splitlines(keepends=True)
            print(f"  [OK] _refresh_catalog_tree replaced lines {start + 1}..{end}")
            changes += 1

    return "".join(lines), changes


def main() -> int:
    ap = argparse.ArgumentParser(description="Priority 6: wire SmartCatalogSearch into catalog tab")
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
        print("[INFO] nothing to do - all patches already applied")
        return 0

    for marker, label in (
        (IMPORT_MARKER, "import"),
        (HELPER_MARKER, "helper"),
        (REFRESH_IDEMPOTENT_MARKER, "refresh marker"),
    ):
        if marker not in patched:
            print(f"[FAIL] sanity: {label} missing from result")
            return 2

    if args.dry_run:
        print(f"[DRY-RUN] would apply {changes} change(s); file not written")
        return 0

    with open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(patched)
    print(f"[OK] applied {changes} change(s); new size: {len(patched)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
