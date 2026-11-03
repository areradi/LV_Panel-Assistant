# -*- coding: utf-8 -*-
"""GUI helpers for LV Panel Assistant.

Pure stdlib utilities used by gui.py:

- ``FieldValidationError``        : explicit field validation errors
- ``parse_cable_length_input``    : parse "30" / "۳۰" / "" safely
- ``AsyncWebSearchManager``       : run a blocking fetch in a background thread
- ``highlight_entry_error``       : visual feedback on a CTkEntry (reserved)

These helpers deliberately have **no dependency on customtkinter at import time**
(they accept generic widget-like objects), so they can be unit-tested without
a display. All widget interactions are duck-typed.
"""
from __future__ import annotations

import threading
import math
import queue
from typing import Any, Callable, Optional, Tuple


class FieldValidationError(ValueError):
    """Raised when a user-entered field fails validation."""

    def __init__(self, field_key: str, message: str) -> None:
        super().__init__(message)
        self.field_key = field_key
        self.message = message


def parse_cable_length_input(
    raw_value: str,
    field_key: str = "cable_length_m",
    default_if_empty: Optional[float] = None,
    max_reasonable_m: float = 2000.0,
) -> Tuple[float, Optional[str]]:
    """Parse a user-entered cable length.

    Returns ``(length_m, warning_or_None)``.

    Raises ``FieldValidationError`` for invalid input (non-numeric, ≤ 0).
    Empty input is accepted only when ``default_if_empty`` is provided.

    Persian/Arabic digits and decimal separators are normalized to ASCII.
    """
    cleaned = (raw_value or "").strip()
    # Normalize Persian/Arabic digits and the Arabic decimal separator (U+066B).
    persian_digits = str.maketrans(
        "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"
        "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
        "\u066b",
        "01234567890123456789.",
    )
    cleaned = cleaned.translate(persian_digits)

    if not cleaned:
        if default_if_empty is not None:
            return default_if_empty, "مقدار پیش‌فرض اعمال شد (ورودی خالی بود)."
        raise FieldValidationError(field_key, "طول کابل نمی‌تواند خالی باشد.")

    try:
        length_m = float(cleaned)
    except ValueError as exc:
        raise FieldValidationError(
            field_key,
            f"مقدار «{raw_value}» برای طول کابل معتبر نیست. یک عدد مثبت بر حسب متر وارد کنید.",
        ) from exc

    if not math.isfinite(length_m) or length_m <= 0:
        raise FieldValidationError(field_key, "طول کابل باید بزرگ‌تر از صفر متر باشد.")

    warning_msg: Optional[str] = None
    if length_m > max_reasonable_m:
        warning_msg = f"طول کابل ({length_m:g} m) غیرمعمول است؛ افت ولتاژ را بررسی کنید."

    return length_m, warning_msg


class AsyncWebSearchManager:
    """Run ``fetch_fn`` in a background thread, deliver results via Tk callbacks.

    ``fetch_fn`` receives a spec object and returns a list of results.
    Callbacks are invoked on the Tk main thread (via ``root.after``), so it is
    safe to update widgets inside them.

    The ``fetch_fn`` return value is passed through **unchanged**, so existing
    code that expects ``WebResult`` objects (``r.title``, ``r.url``, ...)
    keeps working.

    Starting a new search automatically cancels the previous one.
    """

    def __init__(self, root_widget: Any, fetch_fn: Callable[[Any], list]) -> None:
        self.root = root_widget
        self.fetch_fn = fetch_fn
        self._cancel_event = threading.Event()
        self._active_thread: Optional[threading.Thread] = None
        self._results = queue.SimpleQueue()

    def cancel_active_search(self) -> None:
        self._cancel_event.set()

    def start_search(
        self,
        user_spec: Any,
        on_start_ui: Callable[[], None],
        on_success_ui: Callable[[list], None],
        on_error_ui: Callable[[str], None],
    ) -> None:
        self.cancel_active_search()
        self._cancel_event = threading.Event()
        cancel_token = self._cancel_event

        on_start_ui()

        def _poll() -> None:
            if cancel_token.is_set():
                return
            try:
                token, succeeded, value = self._results.get_nowait()
            except queue.Empty:
                self.root.after(25, _poll)
                return
            if token is not cancel_token:
                self.root.after(25, _poll)
                return
            if succeeded:
                on_success_ui(value)
            else:
                on_error_ui(value)

        def _worker() -> None:
            try:
                results = self.fetch_fn(user_spec)
                if cancel_token.is_set():
                    return
                self._results.put((cancel_token, True, results))
            except Exception as err:
                if cancel_token.is_set():
                    return
                self._results.put((cancel_token, False, str(err)))

        self._active_thread = threading.Thread(target=_worker, daemon=True)
        self._active_thread.start()
        self.root.after(25, _poll)


def highlight_entry_error(
    entry_widget: Any,
    error_label: Optional[Any],
    error_text: Optional[str],
) -> None:
    """Visually highlight a CTkEntry on error, and update an optional label.

    Duck-typed: works on any widget exposing ``.configure(...)``.
    Reserved for future use — not yet wired into gui.py.
    """
    if error_text:
        try:
            entry_widget.configure(border_color="#D9383A", border_width=2)
        except Exception:
            pass
        if error_label is not None:
            try:
                error_label.configure(text=error_text, text_color="#FF6B6B")
            except Exception:
                pass
    else:
        try:
            entry_widget.configure(border_color=("#979DA2", "#565B5E"), border_width=1)
        except Exception:
            pass
        if error_label is not None:
            try:
                error_label.configure(text="")
            except Exception:
                pass
