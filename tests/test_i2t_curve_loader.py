from __future__ import annotations

import csv

import pytest

from tools.i2t_curve_loader import I2tCurveLoader


FIELDS = [
    "device_type", "rated_a", "ik_ka", "i2t_a2s", "verification_status",
]


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(device_type, rated_a, ik_ka, i2t_a2s, status="VERIFIED"):
    return {
        "device_type": device_type,
        "rated_a": str(rated_a),
        "ik_ka": str(ik_ka),
        "i2t_a2s": str(i2t_a2s),
        "verification_status": status,
    }


def test_unverified_rows_are_not_loaded(tmp_path):
    csv_path = tmp_path / "curves.csv"
    _write_csv(csv_path, [_row("MPCB_TEST", 32, 22.4, 80_000, "UNVERIFIED")])

    assert I2tCurveLoader(csv_path).get_letthrough_i2t("MPCB_TEST", 32, 22.4) is None


def test_single_point_matches_only_within_two_percent(tmp_path):
    csv_path = tmp_path / "curves.csv"
    _write_csv(csv_path, [_row("MPCB_TEST", 32, 22.404, 80_300)])
    loader = I2tCurveLoader(csv_path)

    assert loader.get_letthrough_i2t("MPCB_TEST", 32, 22.404) == pytest.approx(80_300)
    assert loader.get_letthrough_i2t("MPCB_TEST", 32, 22.404 * 1.02) == pytest.approx(80_300)
    assert loader.get_letthrough_i2t("MPCB_TEST", 32, 22.404 * 1.0201) is None


def test_multiple_points_use_log_log_interpolation(tmp_path):
    csv_path = tmp_path / "curves.csv"
    _write_csv(csv_path, [
        _row("MPCB_TEST", 32, 10, 100),
        _row("MPCB_TEST", 32, 100, 10_000),
    ])

    assert I2tCurveLoader(csv_path).get_letthrough_i2t("MPCB_TEST", 32, 20) == pytest.approx(400)


@pytest.mark.parametrize("ik_ka", [5, 120])
def test_multiple_points_do_not_extrapolate(tmp_path, ik_ka):
    csv_path = tmp_path / "curves.csv"
    _write_csv(csv_path, [
        _row("MPCB_TEST", 32, 10, 100),
        _row("MPCB_TEST", 32, 100, 10_000),
    ])

    assert I2tCurveLoader(csv_path).get_letthrough_i2t("MPCB_TEST", 32, ik_ka) is None


def test_missing_or_empty_curve_file_returns_none(tmp_path):
    missing = I2tCurveLoader(tmp_path / "missing.csv")
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("device_type,rated_a,ik_ka,i2t_a2s,verification_status\n", encoding="utf-8")

    assert missing.get_letthrough_i2t("MPCB_TEST", 32, 22.4) is None
    assert I2tCurveLoader(empty_path).get_letthrough_i2t("MPCB_TEST", 32, 22.4) is None
