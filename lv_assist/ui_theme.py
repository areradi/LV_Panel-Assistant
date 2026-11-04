# -*- coding: utf-8 -*-
"""
lv_assist/ui_theme.py
رنگ‌ها و سبک‌های مشترک رابط کاربری دسکتاپ.
"""
from typing import Dict, Any, Tuple

TOKENS: Dict[str, str] = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "calculate_primary": "#1763C0",
    "calculate_hover": "#124E99",
    "sidebar": "#0F172A",
    "sidebar_active": "#1E293B",
    "sidebar_text": "#F8FAFC",
    "sidebar_muted": "#94A3B8",
    "background": "#F8FAFC",
    "surface": "#FFFFFF",
    "surface_alt": "#F1F5F9",
    "text_main": "#1E293B",
    "text_secondary": "#64748B",
    "border": "#E2E8F0",
    "success": "#16A34A",
    "success_bg": "#DCFCE7",
    "warning": "#D97706",
    "warning_bg": "#FEF3C7",
    "error": "#DC2626",
    "error_bg": "#FEE2E2",
}

SPACING: Dict[str, int] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
}

RADIUS: Dict[str, int] = {
    "sm": 6,
    "md": 8,
    "lg": 12,
}

FONTS: Dict[str, Tuple[str, int, str]] = {
    "h1": ("Tahoma", 16, "bold"),
    "h2": ("Tahoma", 13, "bold"),
    "body": ("Tahoma", 11, "normal"),
    "body_bold": ("Tahoma", 11, "bold"),
    "caption": ("Tahoma", 10, "normal"),
    "mono": ("Consolas", 10, "normal"),
}


def button_style(variant: str = "primary") -> Dict[str, Any]:
    """استایل استاندارد دکمه‌ها (Primary, Secondary, Success, Warning, Danger)."""
    styles = {
        "primary": {
            "fg_color": TOKENS["primary"],
            "hover_color": TOKENS["primary_hover"],
            "text_color": "#FFFFFF",
            "corner_radius": RADIUS["md"],
            "height": 34,
        },
        "secondary": {
            "fg_color": TOKENS["surface_alt"],
            "hover_color": TOKENS["border"],
            "text_color": TOKENS["text_main"],
            "border_width": 1,
            "border_color": TOKENS["border"],
            "corner_radius": RADIUS["md"],
            "height": 34,
        },
        "success": {
            "fg_color": TOKENS["success"],
            "hover_color": "#15803D",
            "text_color": "#FFFFFF",
            "corner_radius": RADIUS["md"],
            "height": 36,
        },
        "warning": {
            "fg_color": TOKENS["warning"],
            "hover_color": "#B45309",
            "text_color": "#FFFFFF",
            "corner_radius": RADIUS["md"],
            "height": 36,
        },
        "danger": {
            "fg_color": TOKENS["error"],
            "hover_color": "#B91C1C",
            "text_color": "#FFFFFF",
            "corner_radius": RADIUS["md"],
            "height": 34,
        },
    }
    return styles.get(variant, styles["primary"]).copy()


def card_style() -> Dict[str, Any]:
    """استایل کارت‌های محتوا روی پس‌زمینه خنثی."""
    return {
        "fg_color": TOKENS["surface"],
        "corner_radius": RADIUS["lg"],
        "border_width": 1,
        "border_color": TOKENS["border"],
    }


def input_style() -> Dict[str, Any]:
    """استایل یکنواخت فیلدهای ورودی."""
    return {
        "fg_color": TOKENS["surface"],
        "border_color": TOKENS["border"],
        "text_color": TOKENS["text_main"],
        "corner_radius": RADIUS["sm"],
        "height": 32,
    }
