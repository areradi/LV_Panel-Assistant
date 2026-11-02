#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Priority 5 patch script — idempotent.

1. Creates ``lv_assist/catalog_smart_search.py``:
   - normalize_search_text()
   - extract_technical_numbers()
   - has_conflicting_technical_rating()   (numeric guard: 25A != 250A)
   - SmartCatalogSearch                    (exact ID -> FTS5 -> fuzzy)

2. Adds ``rapidfuzz>=3.0,<4.0`` to requirements.txt if missing.
   The module itself is **optional-import** — falls back to difflib.

Adapted to the real schema of ``catalog_devices``:
    device_id, category, manufacturer, series, model,
    in_a, poles, icu_ka_400v, ip_rating, ...

(Not the guide's ``part_number / device_type / rated_current_in_a``.)

Purely additive: ``catalog.py`` and ``gui.py`` are NOT modified.

Usage
-----
    python scripts/apply_priority5.py --dry-run
    python scripts/apply_priority5.py
    python scripts/apply_priority5.py --force   # overwrite module
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TARGET = Path("lv_assist/catalog_smart_search.py")
REQUIREMENTS = Path("requirements.txt")
RAPIDFUZZ_LINE = "rapidfuzz>=3.0,<4.0"


MODULE_CONTENT = '''# -*- coding: utf-8 -*-
"""Smart catalog search — Priority 5 of the audit fixes.

Three layers, in order:

1. **Exact ID match**  — compare normalized query to ``device_id``.
2. **Numeric guard**   — reject candidates whose technical rating conflicts
   with the query (e.g. query "25A" must NOT match a 250 A breaker).
3. **Fuzzy similarity** — RapidFuzz if installed, else stdlib ``difflib``.

Optional FTS5 index (``catalog_fts``) is built over ``catalog_devices`` when
the SQLite build supports it; otherwise the search falls back to a full scan
(perfectly fine for the current ~100-row catalog).

The real schema of ``catalog_devices`` (from ``migrate_to_sqlite.py``) is:
    device_id, category, manufacturer, series, model,
    in_a, poles, icu_ka_400v, ip_rating, data_quality, ...

No dependency on ``customtkinter`` at import time; unit-testable in CI.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional

try:
    from rapidfuzz import fuzz as _fuzz  # type: ignore
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


NUMERIC_UNIT_PATTERN = re.compile(
    r"(\\d+(?:\\.\\d+)?)\\s*(a|ka|v|kv|kw|kva|kvar|mm2|p|pole)\\b",
    re.IGNORECASE,
)

_PERSIAN_DIGITS = str.maketrans(
    "\\u06f0\\u06f1\\u06f2\\u06f3\\u06f4\\u06f5\\u06f6\\u06f7\\u06f8\\u06f9"
    "\\u0660\\u0661\\u0662\\u0663\\u0664\\u0665\\u0666\\u0667\\u0668\\u0669",
    "01234567890123456789",
)

_CHAR_MAP = str.maketrans({
    "\\u064a": "\\u06cc",   # ي -> ی
    "\\u0626": "\\u06cc",   # ئ -> ی
    "\\u0643": "\\u06a9",   # ك -> ک
    "\\u0629": "\\u0647",   # ة -> ه
})


def normalize_search_text(text: str) -> str:
    """Normalize Persian/Arabic letters, digits, and unit spacing."""
    if not text:
        return ""
    s = text.translate(_PERSIAN_DIGITS).translate(_CHAR_MAP).lower().strip()
    s = re.sub(r"(\\d+(?:\\.\\d+)?)\\s*(a|ka|v|kv|kw|kva|kvar|mm2)\\b", r"\\1 \\2", s)
    return re.sub(r"\\s+", " ", s)


def extract_technical_numbers(text: str) -> Dict[str, float]:
    """Extract ``{unit: value}`` pairs for the numeric guard."""
    norm = normalize_search_text(text)
    out: Dict[str, float] = {}
    for value_str, unit in NUMERIC_UNIT_PATTERN.findall(norm):
        out[unit.lower()] = float(value_str)
    return out


def has_conflicting_technical_rating(query_text: str, candidate_text: str) -> bool:
    """True if any shared unit has a different numeric value (25A != 250A)."""
    q = extract_technical_numbers(query_text)
    if not q:
        return False
    c = extract_technical_numbers(candidate_text)
    for unit, q_val in q.items():
        if unit in c and abs(c[unit] - q_val) > 1e-6:
            return True
    return False


def _fuzzy_score(a: str, b: str) -> float:
    """Similarity in [0, 100]."""
    if HAS_RAPIDFUZZ:
        return float(_fuzz.partial_ratio(a, b))
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() * 100.0


class SmartCatalogSearch:
    """Three-layer catalog search over ``catalog_devices``."""

    FTS5_TABLE = "catalog_fts"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.fts5_available = self._try_init_fts5()

    # ----- FTS5 (optional) -----

    def _try_init_fts5(self) -> bool:
        try:
            self.conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self.FTS5_TABLE} USING fts5(
                    device_id, manufacturer, series, model, category, ip_rating,
                    search_blob, tokenize='trigram'
                );
                """
            )
            self.conn.commit()
            return True
        except sqlite3.OperationalError:
            return False

    def rebuild_index(self) -> int:
        """Populate (or refresh) the FTS5 index. Returns row count indexed (0 if FTS5 unavailable)."""
        if not self.fts5_available:
            return 0
        rows = self.conn.execute(
            """
            SELECT device_id, manufacturer, series, model, category, ip_rating,
                   in_a, poles, icu_ka_400v
            FROM catalog_devices
            """
        ).fetchall()
        self.conn.execute(f"DELETE FROM {self.FTS5_TABLE}")
        for r in rows:
            blob = normalize_search_text(
                " ".join(
                    str(v or "")
                    for v in (
                        r["device_id"], r["manufacturer"], r["series"], r["model"],
                        r["category"], r["ip_rating"],
                        f"{r['in_a']}a" if r["in_a"] is not None else "",
                        f"{r['poles']}p" if r["poles"] is not None else "",
                        f"{r['icu_ka_400v']}ka" if r["icu_ka_400v"] is not None else "",
                    )
                )
            )
            self.conn.execute(
                f"""
                INSERT INTO {self.FTS5_TABLE}
                  (device_id, manufacturer, series, model, category, ip_rating, search_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["device_id"], r["manufacturer"], r["series"], r["model"],
                    r["category"], r["ip_rating"], blob,
                ),
            )
        self.conn.commit()
        return len(rows)

    # ----- Search -----

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        return {k: row[k] for k in row.keys()}

    def search(
        self,
        raw_query: str,
        category_filter: Optional[str] = None,
        in_a: Optional[float] = None,
        poles: Optional[int] = None,
        fuzzy_threshold: float = 82.0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return ``{exact_id_match, similar_product, verified_alternative}``."""
        norm_q = normalize_search_text(raw_query)
        grouped: Dict[str, List[Dict[str, Any]]] = {
            "exact_id_match": [],
            "similar_product": [],
            "verified_alternative": [],
        }

        rows = [
            self._row_to_dict(r)
            for r in self.conn.execute("SELECT * FROM catalog_devices").fetchall()
        ]

        for row in rows:
            if category_filter and row.get("category") != category_filter:
                continue
            if in_a is not None and row.get("in_a") != in_a:
                continue
            if poles is not None and row.get("poles") != poles:
                continue

            device_id_norm = normalize_search_text(str(row.get("device_id") or ""))
            full_text = normalize_search_text(
                " ".join(
                    str(v or "")
                    for v in (
                        row.get("device_id"), row.get("manufacturer"), row.get("series"),
                        row.get("model"), row.get("category"), row.get("ip_rating"),
                        f"{row['in_a']}a" if row.get("in_a") is not None else "",
                        f"{row['poles']}p" if row.get("poles") is not None else "",
                        f"{row['icu_ka_400v']}ka" if row.get("icu_ka_400v") is not None else "",
                    )
                )
            )

            if norm_q and norm_q == device_id_norm:
                row["match_note"] = "exact ID"
                grouped["exact_id_match"].append(row)
                continue

            if has_conflicting_technical_rating(norm_q, full_text):
                continue

            if norm_q and norm_q in full_text:
                grouped["similar_product"].append(row)
            elif norm_q:
                if _fuzzy_score(norm_q, full_text) >= fuzzy_threshold:
                    grouped["similar_product"].append(row)
            elif in_a is not None or category_filter:
                grouped["verified_alternative"].append(row)

        return grouped


def open_smart_search(db_path: str = "lv_assist/data/lv_assist.db") -> SmartCatalogSearch:
    """Convenience factory: open connection and rebuild FTS5 index if empty."""
    conn = sqlite3.connect(db_path)
    engine = SmartCatalogSearch(conn)
    if engine.fts5_available:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {engine.FTS5_TABLE}").fetchone()[0]
            if n == 0:
                engine.rebuild_index()
        except sqlite3.Error:
            pass
    return engine
'''


def _ensure_rapidfuzz_in_requirements(text: str) -> tuple[str, bool]:
    if "rapidfuzz" in text.lower():
        return text, False
    if not text.endswith("\n"):
        text += "\n"
    text += RAPIDFUZZ_LINE + "\n"
    return text, True


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Priority 5 (smart catalog search)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Overwrite module if it exists")
    args = ap.parse_args()

    changes = 0

    # ---- requirements.txt ----
    if REQUIREMENTS.exists():
        req = REQUIREMENTS.read_text(encoding="utf-8")
        new_req, changed = _ensure_rapidfuzz_in_requirements(req)
        if changed:
            print(f"[OK] requirements.txt: + {RAPIDFUZZ_LINE}")
            if not args.dry_run:
                REQUIREMENTS.write_text(new_req, encoding="utf-8", newline="")
            changes += 1
        else:
            print("[SKIP] requirements.txt already mentions rapidfuzz")
    else:
        print("[WARN] requirements.txt not found (skipped)")

    # ---- module ----
    if TARGET.exists() and not args.force:
        print(f"[SKIP] {TARGET} already exists (use --force to overwrite)")
    else:
        if TARGET.exists():
            print(f"[WARN] {TARGET} exists; overwriting (--force)")
        print(f"[OK] would write {len(MODULE_CONTENT)} bytes to {TARGET}")
        if not args.dry_run:
            TARGET.parent.mkdir(parents=True, exist_ok=True)
            TARGET.write_text(MODULE_CONTENT, encoding="utf-8", newline="")
        changes += 1

    if args.dry_run:
        print(f"[DRY-RUN] {changes} change(s) not written")
        return 0

    print(f"[OK] applied {changes} change(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())