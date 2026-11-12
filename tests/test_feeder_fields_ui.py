import pytest
import customtkinter as ctk

from lv_assist import gui
from lv_assist.gui import FeederEditDialog
from lv_assist.models import ConductorMaterial, FeederInput, LoadType


class _FakeWidget:
    def __init__(self, *_args, **kwargs):
        self.value = ""
        self.values = kwargs.get("values", [])

    def pack(self, **_kwargs):
        return None

    def insert(self, _index, value):
        self.value = str(value)

    def delete(self, *_args):
        self.value = ""

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, **_kwargs):
        return None


class _FakeBooleanVar:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value


@pytest.fixture
def dialog_factory(monkeypatch):
    for name in ("__init__", "title", "geometry", "resizable", "grab_set", "bind", "destroy"):
        monkeypatch.setattr(ctk.CTkToplevel, name, lambda *_args, **_kwargs: None)
    for name in ("CTkScrollableFrame", "CTkFrame", "CTkLabel", "CTkEntry", "CTkCheckBox", "CTkButton"):
        monkeypatch.setattr(ctk, name, _FakeWidget)
    monkeypatch.setattr(ctk, "CTkFont", lambda **_kwargs: None)
    monkeypatch.setattr(ctk, "BooleanVar", _FakeBooleanVar)
    monkeypatch.setattr(gui, "DirectionalOptionMenu", _FakeWidget)
    monkeypatch.setattr(gui, "LocalizedOptionMenu", _FakeWidget)
    monkeypatch.setattr(gui, "align_persian_text", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui.i18n, "direction", lambda: "ltr")

    def create(feeder, saved):
        dialog = FeederEditDialog.__new__(FeederEditDialog)
        FeederEditDialog.__init__(dialog, object(), feeder, saved.append)
        return dialog

    return create


def _make_feeder(**overrides):
    values = {
        "feeder_id": "F-UI-01",
        "description": "Test load",
        "load_type": LoadType.MOTOR_DOL,
        "power_kw": 7.5,
        "cable_section_mm2": 6.0,
        "conductor_material": ConductorMaterial.CU,
        "thdi_pct": 12.0,
    }
    return FeederInput(**(values | overrides))


def _set_entry(dialog, key, value):
    widget, _caster = dialog._entries[key]
    widget.delete(0, "end")
    widget.insert(0, value)


def test_three_controls_exist_and_are_editable(dialog_factory):
    dialog = dialog_factory(_make_feeder(), [])
    section_entry, _ = dialog._entries["cable_section_mm2"]
    thdi_entry, _ = dialog._entries["thdi_pct"]
    assert isinstance(section_entry, ctk.CTkEntry)
    assert isinstance(thdi_entry, ctk.CTkEntry)
    assert dialog._conductor_menu.get() == "CU"

    _set_entry(dialog, "cable_section_mm2", "10")
    _set_entry(dialog, "thdi_pct", "25")
    dialog._conductor_menu.set("AL")
    assert section_entry.get() == "10"
    assert thdi_entry.get() == "25"
    assert dialog._conductor_menu.get() == "AL"
    dialog.destroy()


def test_form_loads_values_from_feeder(dialog_factory):
    feeder = _make_feeder(cable_section_mm2=16.0, conductor_material=ConductorMaterial.AL, thdi_pct=45.0)
    dialog = dialog_factory(feeder, [])
    assert dialog._entries["cable_section_mm2"][0].get() == "16.0"
    assert dialog._conductor_menu.get() == "AL"
    assert dialog._entries["thdi_pct"][0].get() == "45.0"
    dialog.destroy()


def test_form_save_transfers_all_three_values(dialog_factory):
    saved = []
    dialog = dialog_factory(_make_feeder(), saved)
    _set_entry(dialog, "cable_section_mm2", "25")
    _set_entry(dialog, "thdi_pct", "55")
    dialog._conductor_menu.set("AL")
    dialog._save()

    assert len(saved) == 1
    assert saved[0].cable_section_mm2 == 25.0
    assert saved[0].conductor_material == ConductorMaterial.AL
    assert saved[0].thdi_pct == 55.0


def test_blank_optional_cable_fields_save_as_none(dialog_factory):
    saved = []
    feeder = _make_feeder(cable_section_mm2=6.0, thdi_pct=12.0)
    dialog = dialog_factory(feeder, saved)
    _set_entry(dialog, "cable_section_mm2", "")
    _set_entry(dialog, "thdi_pct", "")
    dialog._save()

    assert len(saved) == 1
    assert saved[0].cable_section_mm2 is None
    assert saved[0].thdi_pct is None


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("CU", ConductorMaterial.CU), ("AL", ConductorMaterial.AL)],
)
def test_conductor_enum_choices_save_as_enum(dialog_factory, choice, expected):
    saved = []
    dialog = dialog_factory(_make_feeder(), saved)
    dialog._conductor_menu.set(choice)
    dialog._save()
    assert len(saved) == 1
    assert saved[0].conductor_material == expected


def test_fields_roundtrip_load_save_load(dialog_factory):
    first = _make_feeder(cable_section_mm2=35.0, conductor_material=ConductorMaterial.AL, thdi_pct=80.0)
    saved = []
    dialog = dialog_factory(first, saved)
    dialog._save()
    assert len(saved) == 1

    reloaded = dialog_factory(saved[0], [])
    assert reloaded._entries["cable_section_mm2"][0].get() == "35.0"
    assert reloaded._conductor_menu.get() == "AL"
    assert reloaded._entries["thdi_pct"][0].get() == "80.0"
    reloaded.destroy()
