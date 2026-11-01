# -*- coding: utf-8 -*-
"""Reference tests for P0 audit policy in lv_assist/engine.py."""
import types
from lv_assist import engine as eng


def test_estimate_clear_time_legacy_cap(monkeypatch):
    class Prot:
        series = "TEST"; rated_current_in_a = 100.0
    monkeypatch.setattr(eng.TripCurveRepository, "instantaneous_band_a", lambda s, i: (1000.0, 0.0))
    monkeypatch.setattr(eng.TripCurveRepository, "thermal_time_s", lambda s, m: 8.0)
    monkeypatch.setattr(eng, "ENGINE_AUDIT_STRICT_CLEAR_TIME", False)
    assert eng.EngineeringEngine._estimate_clear_time_s(Prot(), 0.3) == 5.0


def test_estimate_clear_time_strict_mode_returns_real_curve_time(monkeypatch):
    class Prot:
        series = "TEST"; rated_current_in_a = 100.0
    monkeypatch.setattr(eng.TripCurveRepository, "instantaneous_band_a", lambda s, i: (1000.0, 0.0))
    monkeypatch.setattr(eng.TripCurveRepository, "thermal_time_s", lambda s, m: 8.0)
    monkeypatch.setattr(eng, "ENGINE_AUDIT_STRICT_CLEAR_TIME", True)
    assert eng.EngineeringEngine._estimate_clear_time_s(Prot(), 0.3) == 8.0


def test_icu_ok_filter_allows_unknown_ik(monkeypatch):
    dummy = types.SimpleNamespace(_device_icu_ka=lambda dev, project: None)
    assert eng.EngineeringEngine._icu_ok(dummy, None, None, None) is True


def test_icu_ok_filter_allows_unknown_icu(monkeypatch):
    dummy = types.SimpleNamespace(_device_icu_ka=lambda dev, project: None)
    assert eng.EngineeringEngine._icu_ok(dummy, None, None, 25.0) is True


def test_icu_ok_rejects_when_icu_below_ik():
    dummy = types.SimpleNamespace(_device_icu_ka=lambda dev, project: 20.0)
    assert eng.EngineeringEngine._icu_ok(dummy, None, None, 25.0) is False


def test_icu_check_returns_four_state_results():
    dummy = types.SimpleNamespace(_device_icu_ka=lambda dev, project: 25.0)
    assert eng.EngineeringEngine._icu_check(dummy, None, None, 30.0).status.value == "ERROR"
    assert eng.EngineeringEngine._icu_check(dummy, None, None, None).status.value == "INSUFFICIENT_DATA"
    assert eng.EngineeringEngine._icu_check(dummy, None, None, 20.0).status.value == "COMPLETED"


def test_feeder_ik_profile_separates_source_and_feeder_end():
    project = types.SimpleNamespace(transformer_kva=1000.0, transformer_uk_pct=6.0, nominal_voltage_v=400.0)
    p = eng.EngineeringEngine._feeder_ik_profile(project, feeder_length_m=100.0, feeder_phase_mm2=10.0, feeder_pe_mm2=10.0)
    assert p.ik_transformer_3p_ka is not None
    assert p.ik_main_busbar_3p_ka is not None
    assert p.ik_feeder_start_3p_ka is not None
    assert p.ik_feeder_end_max_3p_ka is not None
    assert p.ik_feeder_end_min_1p_ka is not None
    assert p.ik_main_busbar_3p_ka <= p.ik_transformer_3p_ka + 1e-9
    assert p.ik_feeder_start_3p_ka <= p.ik_main_busbar_3p_ka + 1e-9
    assert p.ik_feeder_end_max_3p_ka <= p.ik_feeder_start_3p_ka + 1e-9
    assert p.ik_feeder_end_min_1p_ka <= p.ik_feeder_end_max_3p_ka + 1e-9
    if p.is_attenuated_by_feeder_cable:
        assert p.ik_feeder_end_max_3p_ka < p.ik_feeder_start_3p_ka - 1e-9
