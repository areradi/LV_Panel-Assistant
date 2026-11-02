#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Priority 8: SPD pre-check via pe_spd_engine (additive diagnostic)."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

TARGET = Path("lv_assist/engine.py")
IMPORT_MARKER = "from lv_assist.pe_spd_engine import evaluate_spd_requirements"
IMPORT_ANCHOR = "from lv_assist.models import ("
DIAG_MARKER = "# ---------- Priority 8: SPD pre-check via pe_spd_engine ----------"
PHASE6_ANCHOR = "# ---------- Phase 6:"

DIAG_BLOCK = '''        # ---------- Priority 8: SPD pre-check via pe_spd_engine ----------
        if project.spd_class != SpdClass.NONE:
            try:
                _has_lps = project.spd_class in (SpdClass.T1, SpdClass.T1_T2)
                _spd_diag = evaluate_spd_requirements(
                    earthing_system=getattr(project.earthing_system, "value", str(project.earthing_system)),
                    nominal_voltage_ln_v=u0_v,
                    has_external_lps=_has_lps,
                    is_sensitive_terminal_load=False,
                    prospective_ik_ka=ik_ka,
                    candidates=[],
                )
                if _spd_diag.engineering_status.value == "insufficient_data" and _spd_diag.missing_parameters:
                    vals.append(ValidationResult(
                        rule_id="RULE-SPD-035", feeder_id="PANEL", standard_ref="IEC 61643-11",
                        status=ValidationStatus.WARNING,
                        description="SPD pre-check: missing data (" + ", ".join(_spd_diag.missing_parameters) + ")",
                        supporting_evidence="pe_spd_engine.evaluate_spd_requirements",
                        consequence="SPD sufficiency cannot be fully verified.",
                        recommended_action="Complete missing inputs: " + ", ".join(_spd_diag.missing_parameters),
                    ))
            except Exception:
                pass

'''


def _insert_after_import(lines):
    start = None
    for i, line in enumerate(lines):
        if line.startswith(IMPORT_ANCHOR):
            start = i
            break
    if start is None:
        return lines, False, -1
    end = None
    for j in range(start, min(start + 60, len(lines))):
        if lines[j].rstrip() == ")":
            end = j
            break
    if end is None:
        return lines, False, -1
    block = "\n" + IMPORT_MARKER + "\n"
    lines[end + 1:end + 1] = block.splitlines(keepends=True)
    return lines, True, end + 1


def apply_all(content):
    lines = content.splitlines(keepends=True)
    changes = 0

    if IMPORT_MARKER in content:
        print("  [SKIP] import already present")
    else:
        lines, ok, pos = _insert_after_import(lines)
        if ok:
            print(f"  [OK] import inserted after line {pos}")
            changes += 1
        else:
            print("  [FAIL] import anchor not found")
            return "".join(lines), 0

    joined = "".join(lines)
    if DIAG_MARKER in joined:
        print("  [SKIP] diagnostic already present")
    else:
        target_idx = None
        for i, line in enumerate(lines):
            if PHASE6_ANCHOR in line:
                target_idx = i
                break
        if target_idx is None:
            print("  [FAIL] Phase 6 anchor not found")
            return "".join(lines), 0
        block = DIAG_BLOCK if DIAG_BLOCK.endswith("\n") else DIAG_BLOCK + "\n"
        lines[target_idx:target_idx] = block.splitlines(keepends=True)
        print(f"  [OK] diagnostic inserted before line {target_idx + 1}")
        changes += 1

    return "".join(lines), changes


def main():
    ap = argparse.ArgumentParser()
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
    if IMPORT_MARKER not in patched or DIAG_MARKER not in patched:
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
