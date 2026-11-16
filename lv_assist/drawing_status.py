from functools import wraps
import json
from datetime import datetime, timezone
import re
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape


def build_provenance_metadata(summary_or_dto, report_at: Optional[str] = None) -> str:
    """Build a machine-readable SVG metadata block for a calculation report."""
    if report_at is None:
        report_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "Input Hash": getattr(summary_or_dto, "verified_input_hash", None) or "not recorded",
        "Engine Version": getattr(summary_or_dto, "engine_version", None) or "not recorded",
        "Catalog Revision": getattr(summary_or_dto, "catalog_revision", None) or "not recorded",
        "Rules Revision": getattr(summary_or_dto, "rules_revision", None) or "not recorded",
        "Calculated At": getattr(summary_or_dto, "calculated_at", None) or "not recorded",
        "Report Generated At": report_at,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"<metadata>{_xml_escape(body)}</metadata>"


def _extend_svg_bottom(svg: str, padding: float = 36.0) -> tuple[str, float]:
    """Reserve a footer band and return the updated SVG plus its text baseline."""
    match = re.search(r"<svg\b[^>]*>", svg, flags=re.IGNORECASE)
    if match is None:
        return svg, 0.0

    opening = match.group(0)
    view_box = re.search(r'''\bviewBox\s*=\s*(["'])([^"']+)\1''', opening)
    if view_box:
        values = view_box.group(2).split()
        if len(values) == 4:
            old_height = float(values[3])
            new_height = old_height + padding
            values[3] = f"{new_height:g}"
            replacement = f'viewBox="{" ".join(values)}"'
            opening = opening[:view_box.start()] + replacement + opening[view_box.end():]

            height_attr = re.search(r'''\bheight\s*=\s*(["'])([\d.]+)(px)?\1''', opening)
            if height_attr and old_height > 0:
                physical_height = float(height_attr.group(2)) * new_height / old_height
                unit = height_attr.group(3) or ""
                height_value = f"{physical_height:g}{unit}"
                opening = (
                    opening[:height_attr.start(2)] + height_value
                    + opening[height_attr.end(3) if height_attr.group(3) else height_attr.end(2):]
                )
            return svg[:match.start()] + opening + svg[match.end():], old_height + padding - 9.0

    height_attr = re.search(r'''\bheight\s*=\s*(["'])([\d.]+)(px)?\1''', opening)
    if height_attr:
        old_height = float(height_attr.group(2))
        new_height = old_height + padding
        unit = height_attr.group(3) or ""
        height_value = f"{new_height:g}{unit}"
        opening = (
            opening[:height_attr.start(2)] + height_value
            + opening[height_attr.end(3) if unit else height_attr.end(2):]
        )
        return svg[:match.start()] + opening + svg[match.end():], old_height + padding - 9.0

    return svg, 0.0


def preliminary_drawing(render):
    @wraps(render)
    def wrapped(*args, **kwargs):
        from lv_assist.i18n import tr

        svg = render(*args, **kwargs)
        svg, disclaimer_y = _extend_svg_bottom(svg)
        stamp_y = disclaimer_y - 15.0
        stamp = (
            f'<text x="98%" y="{stamp_y:g}" text-anchor="end" font-size="11" '
            'font-family="sans-serif" fill="#805000">'
            'PRELIMINARY: engineering review required</text>'
        )
        disclaimer = (
            f'<text x="2%" y="{disclaimer_y:g}" text-anchor="start" font-size="8" '
            f'font-family="sans-serif" fill="#666">'
            f'{_xml_escape(tr("disclaimer_general"))}</text>'
        )
        return svg.replace('</svg>', stamp + disclaimer + '</svg>')
    return wrapped
