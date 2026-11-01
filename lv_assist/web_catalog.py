# -*- coding: utf-8 -*-
"""جستجوی آنلاین تجهیزات و افزودن آن‌ها به کاتالوگ SQLite (فاز وب).

کاربرد: کاربر مشخصات «کلی» قطعه (نوع، جریان نامی، قدرت قطع، پل، ولتاژ) را وارد می‌کند؛
این ماژول:
  ۱. عبارت جستجوی مهندسی دقیق می‌سازد (build_query)
  ۲. برای هر منبع (موتور جستجوی عمومی + پورتال‌های سازنده/دیتاپورتال EPLAN) لینک آماده می‌سازد
  ۳. جستجوی متنی زنده را از موتور عمومی انجام می‌دهد (fetch_web_results) و نتایج
     (عنوان/لینک/خلاصه) را برمی‌گرداند تا کاربر دیتاشیت را پیدا و مشخصات را در فرم
     افزودن تجهیز کامل کند.

نکته صداقت مهندسی: هیچ مقدار فنی از صفحات وب به‌صورت خودکار استخراج و «تأییدشده»
فرض نمی‌شود؛ همه ورودی‌ها با data_quality=ESTIMATED ثبت می‌شوند تا در گزارش‌ها
برچسب «برآوردی» بگیرند (سازگار با F-016).
"""

from __future__ import annotations

import html as _html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LV-PanelAssist/0.7 "
    "(equipment datasheet research; contact: engineer@local)"
)
SEARCH_TIMEOUT_S = 12.0


@dataclass
class DeviceSearchSpec:
    """مشخصات کلی قطعه برای جستجو — همه فیلدها اختیاری جز device_type."""
    device_type: str                      # MCCB | MCB | MPCB | CONTACTOR | VFD | ...
    rated_current_in_a: Optional[float] = None
    breaking_capacity_ka: Optional[float] = None
    poles: Optional[int] = None
    voltage_v: Optional[float] = None
    motor_kw: Optional[float] = None
    manufacturer: Optional[str] = None
    keywords: List[str] = field(default_factory=list)

    def to_query_terms(self) -> List[str]:
        terms = [self.device_type.replace("_", " ")]
        if self.manufacturer:
            terms.append(self.manufacturer)
        if self.rated_current_in_a:
            terms.append(f"{self.rated_current_in_a:g}A")
        if self.breaking_capacity_ka:
            terms.append(f"Icu {self.breaking_capacity_ka:g}kA")
        if self.poles:
            terms.append(f"{self.poles}P")
        if self.voltage_v:
            terms.append(f"{self.voltage_v:g}V")
        if self.motor_kw:
            terms.append(f"{self.motor_kw:g}kW motor")
        terms.extend(self.keywords)
        terms.append("datasheet")
        return terms

    def build_query(self) -> str:
        return " ".join(self.to_query_terms())


# --------------------------------------------------------------- منابع جستجو
# لینک‌ساز هر منبع: پرس‌وجوی آماده برای باز شدن در مرورگر (بدون نیاز به API key).
def _q(query: str) -> str:
    return urllib.parse.quote_plus(query)


def search_sources() -> Dict[str, str]:
    """فهرست منابع جستجو با قالب URL حاوی {query}."""
    return {
        "Web (DuckDuckGo)": "https://duckduckgo.com/html/?q={query}",
        "EPLAN Data Portal": "https://data.eplan.com/en/search?searchtext={query}",
        "Siemens Industry Mall": "https://mall.industry.siemens.com/mall/en/ww/Catalog/search?searchTerm={query}",
        "Schneider Electric": "https://www.se.com/ww/en/search/?query={query}",
        "ABB": "https://new.abb.com/search?q={query}",
        "Eaton": "https://www.eaton.com/us/en-us/search.html?query={query}",
        "Rittal": "https://www.rittal.com/us-en/search?text={query}",
        "Phoenix Contact": "https://www.phoenixcontact.com/en-us/search/?q={query}",
    }


def source_urls(spec: DeviceSearchSpec) -> List[tuple]:
    """[(نام منبع، URL آماده برای باز شدن)] — ترتیب: عمومی سپس پورتال سازنده."""
    query = spec.build_query()
    urls = []
    for name, pattern in search_sources().items():
        if spec.manufacturer and spec.manufacturer.lower() not in name.lower():
            # پورتال سازنده دیگری هم نتیجه عمومی می‌دهد؛ حفظ می‌شود ولی اولویت با خودِ سازنده است
            pass
        urls.append((name, pattern.format(query=_q(query))))
    if spec.manufacturer:
        urls.sort(key=lambda item: (0 if spec.manufacturer.lower() in item[0].lower() else 1))
    return urls


# --------------------------------------------------------------- جستجوی زنده
@dataclass
class WebResult:
    title: str
    url: str
    snippet: str = ""


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return _html.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_duckduckgo_html(page_html: str, limit: int = 12) -> List[WebResult]:
    """پارس خروجی HTML سبک DuckDuckGo (result__a / result__snippet) بدون وابستگی بیرونی."""
    results: List[WebResult] = []
    blocks = re.split(r'class="result__body"', page_html)[1:]
    for block in blocks[:limit]:
        link_m = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                           block, re.DOTALL)
        if not link_m:
            continue
        url = _html.unescape(link_m.group(1))
        # ریدایرکت داخلی DDG (uddg=) به URL واقعی تبدیل می‌شود
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            url = urllib.parse.unquote_plus(m.group(1))
        snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
        results.append(WebResult(
            title=_strip_tags(link_m.group(2)),
            url=url,
            snippet=_strip_tags(snip_m.group(1)) if snip_m else "",
        ))
    return results


def fetch_web_results(spec: DeviceSearchSpec, limit: int = 12,
                      timeout_s: float = SEARCH_TIMEOUT_S) -> List[WebResult]:
    """جستجوی زنده عمومی؛ در نبود شبکه یا خطا فهرست خالی برمی‌گردد (بدون Exception به GUI)."""
    query = spec.build_query()
    url = search_sources()["Web (DuckDuckGo)"].format(query=_q(query))
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            page = response.read().decode("utf-8", errors="replace")
        return parse_duckduckgo_html(page, limit=limit)
    except (OSError, ValueError):
        return []


# --------------------------------------------------------------- ساخت قطعه از نتیجه وب
def device_from_search(spec: DeviceSearchSpec, part_number: str, series: str,
                       manufacturer: str, rated_in_a: Optional[float] = None,
                       icu_ka: Optional[float] = None,
                       source_url: str = "") -> "CatalogDevice":
    """مدل CatalogDevice آماده ذخیره از نتیجه جستجوی وب — همیشه ESTIMATED (سازگار با F-016).

    سریِ قطعه ارجاع منبع وب را نگه می‌دارد تا در گزارش‌ها قابل ردیابی باشد.
    خروجی مستقیماً به CatalogRepository.add_device(device, price_source='WEB_IMPORT') داده می‌شود.
    """
    from lv_assist.models import CatalogDevice, DataQuality  # import محلی برای پرهیز از چرخه

    series_ref = (series or "WEB").strip() or "WEB"
    if source_url:
        series_ref = f"{series_ref} [src: {source_url[:80]}]"
    return CatalogDevice(
        part_number=part_number.strip(),
        manufacturer=manufacturer.strip() or (spec.manufacturer or "UNKNOWN"),
        series=series_ref,
        device_type=spec.device_type,
        rated_current_in_a=float(rated_in_a if rated_in_a is not None else (spec.rated_current_in_a or 0.0)),
        icu_ka_400v=float(icu_ka if icu_ka is not None else (spec.breaking_capacity_ka or 0.0)),
        motor_kw_400v=float(spec.motor_kw or 0.0),
        data_quality=DataQuality.ESTIMATED,
        ip_rating="IP20",
    )
