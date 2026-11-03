"""Apply Persian text alignment without rewriting engineering values."""
import customtkinter as ctk
import tkinter as tk
from tkinter import font as tkfont

from lv_assist.i18n import i18n


class PersianDropdown(tk.Frame):
    """Right-aligned popup with native list selection and keyboard navigation."""

    def __init__(self, owner):
        parent = owner.winfo_toplevel()
        super().__init__(parent)
        self.owner = owner
        dark = ctk.get_appearance_mode() == 'Dark'
        bg, fg = ('#203246', '#E3F1FF') if dark else ('#FFFFFF', '#203449')
        self.configure(bg='#4A6580', borderwidth=1)
        values = list(owner._values)
        font = tkfont.Font(root=self, family=i18n.font_family(), size=11)
        self._font = font
        self.listbox = tk.Listbox(self, justify='right', font=font, bg=bg, fg=fg,
                                 selectbackground='#1763C0', selectforeground='#FFFFFF',
                                 highlightthickness=0, borderwidth=0, activestyle='none',
                                 exportselection=False, height=min(len(values), 8))
        scrollbar = tk.Scrollbar(self, command=self.listbox.yview)
        scrollbar.pack(side='left', fill='y')
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(fill='both', expand=True, padx=6, pady=4)
        for value in values:
            self.listbox.insert('end', value)
        selected = owner._current_value if hasattr(owner, '_current_value') else owner.get()
        if selected in values:
            index = values.index(selected)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
        width = min(max(owner.winfo_width(), max((font.measure(v) for v in values), default=120) + 40),
                    parent.winfo_width() - 24)
        height = min(len(values), 8) * (font.metrics('linespace') + 2) + 12
        x = max(0, min(owner.winfo_rootx() - parent.winfo_rootx() + owner.winfo_width() - width,
                       parent.winfo_width() - width))
        y = owner.winfo_rooty() - parent.winfo_rooty() + owner.winfo_height()
        if y + height > parent.winfo_height() - 12:
            y = max(0, owner.winfo_rooty() - parent.winfo_rooty() - height)
        self.place(x=x, y=y, width=width, height=height)
        self.listbox.bind('<Escape>', lambda event: self.close())
        self.listbox.bind('<Return>', lambda event: self.choose())
        self.listbox.bind('<ButtonRelease-1>', self._choose_click)
        self.bind('<ButtonPress-1>', self._outside_click, add='+')
        self.update_idletasks()
        self.lift()
        self.listbox.focus_force()
        self.grab_set()

    def _choose_click(self, event):
        index = self.listbox.nearest(event.y)
        bounds = self.listbox.bbox(index)
        if bounds and bounds[1] <= event.y < bounds[1] + bounds[3]:
            self.choose()

    def _outside_click(self, event):
        if not (self.winfo_rootx() <= event.x_root < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= event.y_root < self.winfo_rooty() + self.winfo_height()):
            self.close()

    def choose(self):
        selected = self.listbox.curselection()
        if selected:
            value = self.listbox.get(selected[0])
            owner = self.owner
            self.close()
            owner._dropdown_callback(value)

    def close(self):
        if self.winfo_exists():
            previous_grab = self.owner.winfo_toplevel()
            self.grab_release()
            self.destroy()
            if previous_grab.winfo_exists():
                self.owner.focus_set()
                if isinstance(previous_grab, ctk.CTkToplevel):
                    previous_grab.grab_set()


class PersianDropdownMixin:
    def _open_dropdown_menu(self):
        if i18n.direction() != 'rtl':
            return super()._open_dropdown_menu()
        popup = getattr(self, '_persian_popup', None)
        if popup is not None and popup.winfo_exists():
            popup.close()
        self._persian_popup = PersianDropdown(self)


class DirectionalOptionMenu(PersianDropdownMixin, ctk.CTkOptionMenu):
    pass


class DirectionalComboBox(PersianDropdownMixin, ctk.CTkComboBox):
    pass


def align_persian_text(root, technical_widgets=()):
    if i18n.direction() != 'rtl':
        return
    excluded = set(technical_widgets)

    def visit(widget):
        if widget in excluded:
            return
        children = widget.winfo_children()
        fields = (ctk.CTkEntry, ctk.CTkOptionMenu, ctk.CTkComboBox)
        packed = [child for child in children if child.winfo_manager() == 'pack']
        if (not getattr(widget, '_persian_row_mirrored', False)
                and any(isinstance(child, fields) for child in packed)
                and any(isinstance(child, ctk.CTkLabel) and child.pack_info()['side'] == 'left'
                        for child in packed)):
            for child in packed:
                side = child.pack_info()['side']
                if side in ('left', 'right'):
                    child.pack_configure(side='right' if side == 'left' else 'left')
            widget._persian_row_mirrored = True
        if isinstance(widget, ctk.CTkLabel):
            widget.configure(anchor='e', justify='right')
            if widget.cget('wraplength'):
                limit = widget.cget('wraplength')

                def fit_text(event, label=widget, parent=widget.master, maximum=limit):
                    width = min(maximum, max(parent.winfo_width() - 24, 100))
                    if label.winfo_exists() and label.cget('wraplength') != width:
                        label.configure(wraplength=width)

                widget.master.bind('<Configure>', fit_text, add='+')
            manager = widget.winfo_manager()
            if manager == 'pack':
                info = widget.pack_info()
                if info['side'] in ('top', 'bottom'):
                    widget.pack_configure(fill='x', anchor='e')
                    if not info['padx']:
                        widget.pack_configure(padx=12)
            elif manager == 'grid':
                widget.grid_configure(sticky='ew')
        elif isinstance(widget, ctk.CTkButton):
            widget.configure(anchor='e', border_spacing=6)
            # CTkButton exposes anchor but not multiline text justification.
            if widget._text_label is not None:
                widget._text_label.configure(justify='right')
        elif isinstance(widget, ctk.CTkOptionMenu):
            widget.configure(anchor='e')
        elif isinstance(widget, ctk.CTkComboBox):
            widget.configure(justify='right')
        for child in children:
            visit(child)

    visit(root)


def align_persian_table(tree, text_columns):
    heading_font = tkfont.Font(root=tree, family=i18n.font_family(), size=10, weight='bold')
    for column in tree['columns']:
        width = max(tree.column(column, 'width'), heading_font.measure(tree.heading(column, 'text')) + 18)
        tree.column(column, width=width, minwidth=width)
    if i18n.direction() != 'rtl':
        return
    columns = tuple(tree['columns'])
    tree.configure(displaycolumns=tuple(reversed(columns)))
    for column in columns:
        tree.heading(column, anchor='e')
        tree.column(column, anchor='e' if column in text_columns else 'center')
    tree.bind('<Map>', lambda event: tree.xview_moveto(1), add='+')
    tree.after_idle(lambda: tree.xview_moveto(1) if tree.winfo_exists() else None)
