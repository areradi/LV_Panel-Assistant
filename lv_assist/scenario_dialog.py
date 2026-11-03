"""Typed scenario inputs and scope notes for the desktop application."""
from typing import get_args
from tkinter import messagebox

import customtkinter as ctk

from lv_assist.i18n import i18n, tr
from lv_assist.models import ScenarioInputs
from lv_assist.scenario_rules import FIELD_LABELS, PROFILES, localized
from lv_assist.ui_direction import DirectionalOptionMenu, align_persian_text


class ScenarioDialog(ctk.CTkToplevel):
    def __init__(self, master, project, on_save):
        super().__init__(master)
        self.title(tr('scenario_settings'))
        self.geometry('760x680')
        self.transient(master)
        self.grab_set()
        self.bind('<Escape>', lambda event: self.destroy())
        self._data = project.scenario_inputs
        self._on_save = on_save
        self._entries = {}
        self._boolean_choices = localized((('نامشخص', 'بله', 'خیر'), ('Unknown', 'Yes', 'No'), ('Unbekannt', 'Ja', 'Nein')))
        profile = PROFILES.get(project.special_scenario.value)
        font = (i18n.font_family(), 13)
        if profile is None:
            ctk.CTkLabel(self, text=tr('scenario_select_first'), font=font).pack(padx=16, pady=20)
            return
        ctk.CTkLabel(self, text=tr('scenario_' + project.special_scenario.value), font=(i18n.font_family(), 17, 'bold')).pack(fill='x', padx=16, pady=12)
        standards = ctk.CTkLabel(self, text=profile.standards, font=('Consolas', 12), wraplength=700, justify='left')
        standards.pack(fill='x', padx=16, pady=6)
        ctk.CTkLabel(self, text=localized(profile.notes), font=font, wraplength=700,
                     justify='right' if i18n.direction() == 'rtl' else 'left').pack(fill='x', padx=16, pady=8)
        form = ctk.CTkScrollableFrame(self)
        form.pack(fill='both', expand=True, padx=14, pady=8)
        rtl = i18n.direction() == 'rtl'
        form.grid_columnconfigure(0 if rtl else 1, weight=1)
        for row, name in enumerate((*profile.fields, 'review_reference')):
            label = ctk.CTkLabel(form, text=localized(FIELD_LABELS[name]), font=font, width=300,
                                 wraplength=290, anchor='e' if rtl else 'w')
            label.grid(row=row, column=1 if rtl else 0, sticky='ew', padx=8, pady=6)
            annotation = get_args(ScenarioInputs.model_fields[name].annotation)
            value = getattr(self._data, name)
            if bool in annotation:
                entry = DirectionalOptionMenu(form, values=list(self._boolean_choices), font=font)
                entry.set(self._boolean_choices[0 if value is None else 1 if value else 2])
            elif name == 'ev_supply_type':
                entry = DirectionalOptionMenu(form, values=['—', 'AC', 'DC', 'DC_LOW_VOLTAGE'], font=font)
                entry.set(value or '—')
            else:
                entry = ctk.CTkEntry(form, font=font)
                entry.insert(0, '' if value is None else str(value))
                if rtl and str in annotation:
                    entry.configure(justify='right')
            entry.grid(row=row, column=0 if rtl else 1, sticky='ew', padx=8, pady=6)
            self._entries[name] = entry
        ctk.CTkButton(self, text=tr('dlg_save'), height=38, command=self._save).pack(fill='x', padx=16, pady=12)
        align_persian_text(self, technical_widgets=(standards,))

    def _save(self):
        data = self._data.model_dump()
        try:
            for name, entry in self._entries.items():
                raw = entry.get().strip()
                annotation = get_args(ScenarioInputs.model_fields[name].annotation)
                if bool in annotation:
                    index = self._boolean_choices.index(raw)
                    data[name] = None if index == 0 else index == 1
                elif not raw or raw == '—':
                    data[name] = None
                elif float in annotation:
                    data[name] = float(raw)
                elif int in annotation or name == 'ac_phases':
                    data[name] = int(raw)
                else:
                    data[name] = raw
            parsed = ScenarioInputs.model_validate(data)
        except (ValueError, TypeError) as error:
            if hasattr(error, 'errors'):
                name = error.errors()[0]['loc'][0]
            label = localized(FIELD_LABELS[name])
            message = localized(('مقدار این ورودی با نوع یا محدوده مجاز سازگار نیست.',
                                 'This value does not match the permitted type or range.',
                                 'Dieser Wert entspricht nicht dem zulässigen Typ oder Bereich.'))
            messagebox.showerror(tr('msg_error'), label + '\n' + message, parent=self)
            return
        self._on_save(parsed)
        self.destroy()
