"""Non-Tk checks for the motor-search view and its safety labeling."""

import inspect
import json
from pathlib import Path

from lv_assist.database.models import MotorProtectionCandidate
from lv_assist.gui import LVAssistApp
from lv_assist.i18n import i18n
from lv_assist.precision_ui import PrecisionShell


def _candidate():
    return MotorProtectionCandidate(
        component_id="C-001",
        part_number="TEST-MPCB-1",
        manufacturer="TestCo",
        component_type="Motor Protection",
        record_status="extracted",
        estimated_motor_current_a=8.0,
        rated_current_min_a=7.0,
        rated_current_max_a=10.0,
        rated_voltage_v=690.0,
        current_unit="A",
        voltage_unit="V",
        current_record_status="extracted",
        voltage_record_status="extracted",
        source_file="catalog.pdf",
        source_locator="page:3|table:1",
        is_preview_only=True,
        is_safety_recommendation=False,
        preview_warning="⚠️ تأییدنشده - فقط برای پیش‌نمایش",
    )


def test_motor_search_view_is_registered_in_sidebar_and_wizard():
    assert LVAssistApp.NAV_KEYS[4] == "nav_motor_search"
    assert hasattr(LVAssistApp, "_build_view_motor_search")
    assert hasattr(LVAssistApp, "_run_motor_search")
    assert "self._build_view_motor_search" in inspect.getsource(PrecisionShell._build_precision_ui)


def test_preview_result_format_shows_warning_and_provenance(monkeypatch):
    monkeypatch.setattr(i18n, "_language", "fa")
    text = LVAssistApp._format_motor_candidate(_candidate())

    assert "⚠️ تأییدنشده - فقط برای پیش‌نمایش" in text
    assert "این نتیجه پیشنهاد ایمنی" in text
    assert "catalog.pdf" in text
    assert "page:3|table:1" in text


def test_motor_search_translation_keys_exist_in_all_locales():
    translations = Path(__file__).parents[1] / "lv_assist" / "translations"
    keys = {
        "nav_motor_search", "motor_search_title", "motor_search_hint",
        "motor_search_verified_only", "motor_search_preview_warning",
        "motor_search_not_safety", "motor_search_no_verified",
    }
    for language in ("fa", "en", "de"):
        values = json.loads((translations / f"{language}.json").read_text(encoding="utf-8"))
        assert keys <= values.keys()
