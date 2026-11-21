"""Tests for the motor-protection search command and its user-facing output."""

from lv_assist.cli.motor_search import main, search_motor_protection
from lv_assist.database.models import MotorProtectionCandidate
from lv_assist.i18n import tr


def _candidate(**overrides):
    values = {
        "component_id": "C-001",
        "part_number": "TEST-MPCB-1",
        "manufacturer": "TestCo",
        "component_type": "Motor Protection",
        "record_status": "extracted",
        "estimated_motor_current_a": 8.0,
        "rated_current_min_a": 7.0,
        "rated_current_max_a": 10.0,
        "rated_voltage_v": 690.0,
        "current_unit": "A",
        "voltage_unit": "V",
        "current_record_status": "extracted",
        "voltage_record_status": "extracted",
        "source_file": "catalog.pdf",
        "source_locator": "page:3|table:1",
        "is_preview_only": True,
        "is_safety_recommendation": False,
        "preview_warning": "⚠️ تأییدنشده - فقط برای پیش‌نمایش",
    }
    values.update(overrides)
    return MotorProtectionCandidate(**values)


def test_search_motor_protection_passes_verified_filter(monkeypatch):
    calls = {}

    class FakeRepository:
        def find_components_for_motor(self, power_kw, voltage_v, verified_only=False):
            calls.update(power_kw=power_kw, voltage_v=voltage_v, verified_only=verified_only)
            return [_candidate()]

    monkeypatch.setattr("lv_assist.cli.motor_search.ComponentRepository", FakeRepository)

    results = search_motor_protection(4.0, 400, verified_only=True)

    assert results[0].part_number == "TEST-MPCB-1"
    assert calls == {"power_kw": 4.0, "voltage_v": 400, "verified_only": True}


def test_cli_prints_preview_warning_and_source(monkeypatch, capsys):
    monkeypatch.setattr("lv_assist.cli.motor_search.search_motor_protection", lambda *a, **k: [_candidate()])

    assert main(["--power", "4.0", "--voltage", "400"]) == 0
    output = capsys.readouterr().out
    assert tr("motor_search_preview_warning") in output
    assert "catalog.pdf" in output
    assert "page:3|table:1" in output
    assert "TEST-MPCB-1" in output


def test_cli_reports_no_verified_components(monkeypatch, capsys):
    monkeypatch.setattr("lv_assist.cli.motor_search.search_motor_protection", lambda *a, **k: [])

    assert main(["--power", "4.0", "--voltage", "400", "--verified-only"]) == 0
    assert tr("motor_search_no_verified") in capsys.readouterr().out

