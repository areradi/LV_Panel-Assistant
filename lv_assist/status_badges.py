# -*- coding: utf-8 -*-
"""
lv_assist/status_badges.py
کامپوننت نشان وضعیت اعتبار مدارک مهندسی.

توجه: این ماژول صرفاً لایهٔ نمایش است. هیچ دادهٔ تجهیزی تولید،
تکمیل یا اعتبارسنجی نمی‌کند و به هستهٔ محاسباتی وابسته نیست.
"""
import customtkinter as ctk
from lv_assist.i18n import i18n


class StatusBadge(ctk.CTkFrame):
    """برچسپ کپسولی وضعیت. اندازه به‌صورت خودکار از روی متن تعیین می‌شود."""

    STYLES = {
        "verified": {
            "fg_color": ("#DCFCE7", "#064E3B"),
            "text_color": ("#166534", "#34D399"),
            "border_color": "#10B981",
            "text": {"fa": "✓ تأییدشده", "en": "✓ Verified", "de": "✓ Verifiziert"},
        },
        "preview": {
            "fg_color": ("#E0F2FE", "#0C4A6E"),
            "text_color": ("#0369A1", "#38BDF8"),
            "border_color": "#38BDF8",
            "text": {"fa": "~ پیش‌نمایش", "en": "~ Preview", "de": "~ Vorschau"},
        },
        "awaiting": {
            "fg_color": ("#FEF3C7", "#78350F"),
            "text_color": ("#B45309", "#FBBF24"),
            "border_color": "#F59E0B",
            "text": {"fa": "؟ در انتظار سازنده", "en": "? Awaiting vendor",
                     "de": "? Hersteller ausstehend"},
        },
        "insufficient": {
            "fg_color": ("#F1F5F9", "#334155"),
            "text_color": ("#475569", "#94A3B8"),
            "border_color": "#64748B",
            "text": {"fa": "− داده ناکافی", "en": "− Insufficient data",
                     "de": "− Daten unzureichend"},
        },
        "unverified": {
            "fg_color": ("#FEE2E2", "#7F1D1D"),
            "text_color": ("#B91C1C", "#F87171"),
            "border_color": "#EF4444",
            "text": {"fa": "! فاقد سند", "en": "! No source", "de": "! Kein Nachweis"},
        },
    }

    def __init__(self, master, status="insufficient", **kwargs):
        style = self.STYLES.get(status, self.STYLES["insufficient"])
        lang = i18n.get_language()
        label = style["text"].get(lang, style["text"]["en"])

        # خط‌چین در CustomTkinter پشتیبانی نمی‌شود؛ رنگ معنایی + پیشوند "~"
        # وظیفهٔ تمایز بصری شاخهٔ پیش‌نمایش را بر عهده دارد.
        super().__init__(
            master,
            fg_color=style["fg_color"],
            border_color=style["border_color"],
            border_width=1,
            corner_radius=12,
            **kwargs
        )
        ctk.CTkLabel(
            self,
            text=label,
            text_color=style["text_color"],
            font=ctk.CTkFont(family=i18n.font_family(), size=11, weight="bold"),
        ).pack(padx=10, pady=2)

    @classmethod
    def apply_treeview_tag(cls, tree, status):
        """فقط foreground را رنگی می‌کند، background پیش‌فرض می‌ماند."""
        style = cls.STYLES.get(status, cls.STYLES["insufficient"])
        dark = ctk.get_appearance_mode() == "Dark"
        idx = 1 if dark else 0
        tree.tag_configure(
            "badge_" + status,
            foreground=style["text_color"][idx],
        )