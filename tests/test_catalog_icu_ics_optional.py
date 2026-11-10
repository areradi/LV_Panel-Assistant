import pytest
from pydantic import ValidationError

from lv_assist.models import CatalogDevice


def _device(**values):
    return CatalogDevice(
        part_number="X",
        manufacturer="TEST",
        series="TEST",
        device_type="MCCB",
        **values,
    )


def test_catalog_device_icu_default_is_none():
    assert _device().icu_ka_400v is None


def test_catalog_device_icu_explicit_zero_preserved():
    assert _device(icu_ka_400v=0.0).icu_ka_400v == 0.0


def test_catalog_device_ics_default_is_none():
    assert _device().ics_ka_400v is None


def test_catalog_device_rated_voltage_default_is_none():
    assert _device().rated_voltage_v is None


def test_catalog_device_rejects_negative_icu():
    with pytest.raises(ValidationError):
        _device(icu_ka_400v=-1.0)


def test_catalog_device_rejects_negative_rated_voltage():
    with pytest.raises(ValidationError):
        _device(rated_voltage_v=-400.0)
