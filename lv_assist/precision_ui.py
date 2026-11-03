"""Three-column desktop shell with live engineering context."""
import math
import sys
import textwrap
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk
from lv_assist.i18n import i18n, tr
from lv_assist.ui_direction import align_persian_text, align_persian_table
from lv_assist.summary_workflow import format_summary_cards

COPY = {
    'fa': ('خلاصه محاسبات', 'جریان طراحی', 'ابعاد پیشنهادی', 'پیش‌نمایش تابلو', 'کشوی فرمول',
           'محاسبه مجدد', 'تنظیمات پیشرفته', 'بارها', 'تجهیزات', 'شینه‌ها', 'نهایی',
           'مقادیر آخرین محاسبه؛ ورودی‌ها تغییر کرده‌اند', 'پروژه و بارها', 'تنظیمات',
           'جریان مرجع پیش از ضرایب همزمانی و رزرو'),
    'en': ('Calculation summary', 'Design current', 'Suggested enclosure', 'Panel overview', 'Formula drawer',
           'Recalculate', 'Advanced settings', 'Loads', 'Equipment', 'Busbars', 'Final',
           'Previous calculation; inputs have changed', 'Project and loads', 'Settings',
           'Reference current before simultaneity and reserve factors'),
    'de': ('Berechnungsübersicht', 'Bemessungsstrom', 'Gehäusevorschlag', 'Schaltschrankübersicht', 'Formeln',
           'Neu berechnen', 'Erweiterte Einstellungen', 'Lasten', 'Geräte', 'Sammelschienen', 'Abschluss',
           'Letzte Berechnung; Eingaben geändert', 'Projekt und Lasten', 'Einstellungen',
           'Referenzstrom vor Gleichzeitigkeits- und Reservefaktoren'),
}


class PrecisionShell:
    def _build_precision_ui(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.title('PanelCalc Pro | LV Panel Assistant')
        self.configure(fg_color=('#EEF2F7', '#0D1724'))
        self._shell_copy = COPY[i18n.get_language()]
        font = i18n.font_family()
        card = {'fg_color': ('#FFFFFF', '#182536'), 'border_color': ('#CAD5E2', '#34485E'),
                'border_width': 1, 'corner_radius': 12}
        header = ctk.CTkFrame(self, height=60, **card)
        header.pack(fill='x', padx=16, pady=(12, 6))
        brand = ctk.CTkLabel(header, text='PanelCalc Pro', font=(font, 21, 'bold'))
        brand.pack(side='left', padx=18, pady=12)
        self.lbl_project_title = ctk.CTkLabel(header, text='', font=(font, 12), anchor='w', justify='left')
        self.lbl_project_title.pack(side='left', fill='x', expand=True, padx=12)
        languages = ctk.CTkSegmentedButton(header, values=['FA', 'EN', 'DE'], command=self._on_language_change)
        languages.set(i18n.get_language().upper())
        languages.pack(side='right', padx=14)
        self._theme_switch = ctk.CTkSwitch(header, text=tr('lbl_theme'), command=self._on_theme_change)
        if ctk.get_appearance_mode() == 'Light':
            self._theme_switch.select()
        self._theme_switch.pack(side='right', padx=12)
        body = ctk.CTkFrame(self, fg_color='transparent')
        body.pack(fill='both', expand=True, padx=16, pady=(4, 14))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        nav = ctk.CTkFrame(body, width=185, **card)
        nav.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        nav.grid_propagate(False)
        nav.grid_columnconfigure(0, weight=1)
        nav.grid_rowconfigure(7, weight=1)
        nav_identity = ctk.CTkLabel(nav, text='LV / IEC', text_color=('#39516A', '#A8C1DA'), font=('Consolas', 13))
        nav_identity.grid(row=0, column=0, pady=22)
        self._nav_buttons = []
        for index, key in enumerate(self.NAV_KEYS):
            button = ctk.CTkButton(nav, text=textwrap.fill(tr(key), width=22, break_long_words=False), height=46, anchor='e' if i18n.direction() == 'rtl' else 'w',
                                   font=(font, 14), command=lambda i=index: self._switch_view(i))
            button.grid(row=index+1, column=0, sticky='ew', padx=10, pady=5)
            self._nav_buttons.append(button)
        ctk.CTkButton(nav, text=self._shell_copy[13], height=42, fg_color='transparent',
                      text_color=('#203449', '#DFEAF6'), border_width=1,
                      command=self._open_precision_settings).grid(row=8, column=0, sticky='ew', padx=10, pady=14)
        middle = ctk.CTkFrame(body, fg_color='transparent')
        middle.grid(row=0, column=1, sticky='nsew')
        stepper = ctk.CTkFrame(middle, **card)
        stepper.pack(fill='x', pady=(0, 8))
        self._step_buttons = []
        for index in range(4):
            stepper.grid_columnconfigure(index, weight=1)
            button = ctk.CTkButton(stepper, text=self._shell_copy[7+index], height=38,
                                   fg_color=('#DEE9F4', '#24394F'), text_color=('#183B5D', '#E3F1FF'),
                                   command=lambda step=index: self._show_workflow_step(step))
            button.grid(row=0, column=3-index if i18n.direction() == 'rtl' else index, sticky='ew', padx=6, pady=12)
            self._step_buttons.append(button)
        self._status_lbl = ctk.CTkLabel(middle, text='', font=(font, 11), wraplength=700)
        self._status_lbl.pack(fill='x', pady=(0, 4))
        workspace = ctk.CTkFrame(middle, fg_color='transparent')
        workspace.pack(fill='both', expand=True)
        self.views = [ctk.CTkFrame(workspace, **card) for _ in range(6)]
        for builder, view in zip((self._build_view_project, self._build_view_feeders,
                                  self._build_view_instruments, self._build_view_results,
                                  self._build_view_exports, self._build_view_catalog), self.views):
            builder(view)
        for name in ('tree_feeders', 'tree_results_tbl', 'tree_rules', 'tree_wires_preview', 'tree_inst', 'tree_catalog', 'tree_busbars'):
            tree = getattr(self, name, None)
            if tree is not None:
                scroll = ttk.Scrollbar(tree.master, orient='horizontal', command=tree.xview)
                scroll.pack(side='bottom', fill='x', padx=8, pady=3)
                tree.configure(xscrollcommand=scroll.set)
        ctk.CTkButton(middle, text=self._shell_copy[5], height=46, fg_color='#1763C0', hover_color='#124E99',
                      command=self.action_recalculate, font=(font, 14, 'bold')).pack(fill='x', pady=(10, 0))
        context = ctk.CTkFrame(body, width=350, fg_color='transparent')
        context.grid(row=0, column=2, sticky='nsew', padx=(10, 0))
        context.grid_propagate(False)
        context.grid_columnconfigure(0, weight=1)
        context.grid_rowconfigure(1, weight=1)
        summary = ctk.CTkFrame(context, **card)
        summary.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ctk.CTkLabel(summary, text=self._shell_copy[0], font=(font, 17, 'bold')).pack(pady=(14, 8))
        self._current_caption = ctk.CTkLabel(summary, text=self._shell_copy[1], font=(font, 12))
        self._current_caption.pack()
        self._hero_current = ctk.CTkLabel(summary, text='—', font=('Consolas', 33, 'bold'))
        self._hero_current.pack(pady=(0, 8))
        self._main_details = ctk.CTkLabel(summary, text='', font=(font, 11), wraplength=310)
        self._main_details.pack(fill='x', padx=12, pady=(0, 8))
        ctk.CTkLabel(summary, text=self._shell_copy[2], font=(font, 12)).pack()
        self._hero_dimensions = ctk.CTkLabel(summary, text='—', font=('Consolas', 14, 'bold'), wraplength=310)
        self._hero_dimensions.pack(pady=(0, 12))
        diagram = ctk.CTkFrame(context, **card)
        diagram.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        ctk.CTkLabel(diagram, text=self._shell_copy[3], font=(font, 16, 'bold')).pack(pady=12)
        self._context_canvas = tk.Canvas(diagram, highlightthickness=0, height=240)
        self._context_canvas.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        self._context_canvas.bind('<Configure>', lambda event: self._refresh_precision_context())
        formula = ctk.CTkFrame(context, **card)
        formula.grid(row=2, column=0, sticky='ew')
        ctk.CTkLabel(formula, text=self._shell_copy[4], font=(font, 16, 'bold')).pack(pady=(12, 5))
        self._formula_text = ctk.CTkLabel(formula, text='', font=('Consolas', 15), wraplength=310, justify='left')
        self._formula_text.pack(padx=14, pady=8)
        self._formula_note = ctk.CTkLabel(formula, text='', font=(font, 11), wraplength=310)
        self._formula_note.pack(padx=12, pady=(0, 14))
        align_persian_text(self, technical_widgets=(brand, nav_identity, languages,
                           self._hero_current, self._hero_dimensions, self._formula_text,
                           self.txt_svg_inspector))
        for name, columns in (
            ('tree_feeders', ('desc', 'type')),
            ('tree_inst', ('desc', 'sig')),
            ('tree_results_tbl', ('desc', 'type', 'sel')),
            ('tree_rules', ('status', 'desc', 'evidence', 'action')),
            ('tree_catalog', ('quality',)),
            ('tree_wires_preview', ('role', 'spec')),
            ('tree_busbars', ('parameter',)),
        ):
            align_persian_table(getattr(self, name), columns)
        if i18n.direction() == 'rtl':
            for entry in (self.wiz_entries['wiz_project_name'], self.f_entries['wiz_f_desc'],
                          self.i_entries['wiz_i_desc'], self.ent_cat_search):
                entry.configure(justify='right')
        self._apply_tree_style(font)
        self._switch_view(0)
        self._apply_status()
        self._refresh_precision_context()
        self.after_idle(self._apply_windows_backdrop)

    def _open_precision_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title(self._shell_copy[13])
        dialog.geometry('360x240')
        dialog.transient(self)
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        ctk.CTkLabel(dialog, text=tr('lbl_theme'), font=(i18n.font_family(), 16)).pack(pady=24)
        ctk.CTkButton(dialog, text=tr('lbl_theme'), command=self._on_theme_change).pack(pady=10)
        ctk.CTkButton(dialog, text=self._shell_copy[6], command=lambda: (dialog.destroy(), self._switch_view(0),
                                                                                        self._toggle_advanced_fields(True))).pack(pady=10)
        align_persian_text(dialog)

    def _refresh_precision_context(self):
        if not hasattr(self, '_context_canvas'):
            return
        dark = ctk.get_appearance_mode() == 'Dark'
        canvas = self._context_canvas
        canvas.configure(bg='#182536' if dark else '#FFFFFF')
        canvas.delete('all')
        if not self.last_results:
            return
        feeders, summary, _ = self.last_results
        project = self.current_project
        from lv_assist.scenario_rules import localized
        unknown = localized(('نامشخص', 'Unknown', 'Unbekannt'))
        cards = format_summary_cards(summary.main_breaker, summary.selected_enclosure, na_label=unknown)
        main, enclosure = cards['main_protection'], cards['enclosure']
        self._current_caption.configure(text=localized(('جریان نامی کلید اصلی (In)', 'Main device rated current (In)', 'Bemessungsstrom des Hauptschutzgeräts (In)')))
        self._hero_current.configure(text=f'{summary.main_breaker.rated_current_in_a:,.1f} A'
                                     if summary.main_breaker else unknown)
        self._main_details.configure(text='\n'.join((main['device_model'], main['breaking_capacity'],
            localized(('تعداد پل', 'Poles', 'Pole')) + ': ' + main['poles'],
            localized(('تنظیمات', 'Settings', 'Einstellungen')) + ': ' + main['trip_settings'])))
        self._hero_dimensions.configure(text=f"W: {enclosure['width']}\nH: {enclosure['height']}\nD: {enclosure['depth']}")
        voltage = project.nominal_voltage_v
        power = summary.total_active_kw * 1000
        pf = summary.overall_cos_phi
        current = power / (math.sqrt(3) * voltage * pf) if voltage > 0 and pf > 0 else None
        self._formula_text.configure(text='I = P / (√3 × V × cos φ)\n' +
            (f'{power:,.0f} / (1.732 × {voltage:g} × {pf:.3f})\n= {current:.1f} A' if current is not None else '—'))
        self._formula_note.configure(text=self._shell_copy[11] if self._stale else self._shell_copy[14],
                                     text_color=('#805000', '#FFD48A') if self._stale else ('#435C74', '#AFC2D5'))
        width, height = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), 200)
        colors = ('#E35D6A', '#D9B83F', '#49B68B')
        ink = '#AFC7DF' if dark else '#38516A'
        canvas.create_line(18, 55, width*.47, 55, fill=ink, width=2)
        for index, feeder in enumerate(feeders[:6]):
            x = 23 + index * (width*.41 / max(len(feeders[:6]), 1))
            color = colors[index % 3]
            canvas.create_line(x, 55, x, 125, fill=color, width=2)
            canvas.create_rectangle(x-4, 80, x+4, 100, outline=color, width=2)
            canvas.create_text(x, 143, text=feeder.feeder_id, fill=ink, font=('Consolas', 9))
        scale = min(width*.28/max(summary.estimated_panel_width_mm, 1),
                    min(height-80, 240)/max(summary.estimated_panel_height_mm, 1))
        x, y = width*.59, 42
        w, h = summary.estimated_panel_width_mm*scale, summary.estimated_panel_height_mm*scale
        dx = min(summary.estimated_panel_depth_mm*scale*.35, 24)
        dy = -dx*.8
        for shift_x, shift_y in ((0, 0), (dx, dy)):
            canvas.create_rectangle(x+shift_x, y+shift_y, x+w+shift_x, y+h+shift_y, outline=ink)
        for px, py in ((x,y), (x+w,y), (x,y+h), (x+w,y+h)):
            canvas.create_line(px, py, px+dx, py+dy, fill=ink)
        for index, color in enumerate(colors):
            bx = x+15+index*(w-25)/3
            canvas.create_rectangle(bx, y+18, bx+7, y+h-14, fill=color, outline=color)

    def _apply_windows_backdrop(self):
        if sys.platform != 'win32':
            return
        import ctypes
        try:
            user32 = ctypes.windll.user32
            user32.GetAncestor.restype = ctypes.c_void_p
            hwnd = user32.GetAncestor(ctypes.c_void_p(self.winfo_id()), 2)
            for attribute, value in ((20, int(ctk.get_appearance_mode() == 'Dark')), (38, 2)):
                setting = ctypes.c_int(value)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attribute,
                                                          ctypes.byref(setting), ctypes.sizeof(setting))
        except (OSError, AttributeError):
            pass
