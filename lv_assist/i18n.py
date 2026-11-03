# -*- coding: utf-8 -*-
import json
import os

SUPPORTED_LANGUAGES = ("fa", "en", "de")

LANGUAGE_META = {
    "fa": {"name": "فارسی", "direction": "rtl", "font": "Tahoma"},
    "en": {"name": "English", "direction": "ltr", "font": "Segoe UI"},
    "de": {"name": "Deutsch", "direction": "ltr", "font": "Segoe UI"},
}

from lv_assist.paths import get_translations_dir

_TRANSLATIONS_DIR = str(get_translations_dir())
_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class I18n:
    def __init__(self):
        self._language = "fa"
        self._tables = {}
        self._config_path = None

    def set_config_path(self, path):
        self._config_path = path
        self.load_config()

    def load_config(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("language")
            if lang in SUPPORTED_LANGUAGES:
                self._language = lang
        except (OSError, json.JSONDecodeError):
            pass

    def save_config(self, extra=None):
        if not self._config_path:
            return
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["language"] = self._language
        if extra:
            data.update(extra)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_language(self):
        return self._language

    def set_language(self, lang):
        if lang in SUPPORTED_LANGUAGES:
            self._language = lang
            self.save_config()

    def get_theme(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                return json.load(f).get("theme", "dark")
        except (OSError, json.JSONDecodeError):
            return "dark"

    def set_theme(self, theme):
        self.save_config(extra={"theme": theme})

    def direction(self):
        return LANGUAGE_META[self._language]["direction"]

    def font_family(self):
        return LANGUAGE_META[self._language]["font"]

    def _table(self, lang):
        if lang not in self._tables:
            try:
                with open(os.path.join(_TRANSLATIONS_DIR, f"{lang}.json"), encoding="utf-8") as f:
                    self._tables[lang] = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._tables[lang] = {}
        return self._tables[lang]

    def tr(self, key, **fmt):
        text = None
        for lang in dict.fromkeys((self._language, "en", "fa")):
            text = self._table(lang).get(key)
            if text is not None:
                break
        if text is None:
            text = key
        text = text.translate(_LATIN_DIGITS)
        try:
            text = text.format(**fmt)
        except (KeyError, IndexError):
            pass
        return text


i18n = I18n()


def tr(key, **fmt):
    return i18n.tr(key, **fmt)
