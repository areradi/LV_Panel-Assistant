from functools import wraps
import json
from datetime import datetime, timezone
import re
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

_LATIN_RUN_RE = re.compile(
    r"(\([A-Za-z0-9 .\-/]+\)|[A-Za-z0-9][A-Za-z0-9 .\-/]*[A-Za-z0-9]|[A-Za-z0-9])"
)


def render_bidi_text(
    text: str,
    x: float | str,
    y: float,
    lang: str,
    font_size: float = 6,
    max_width: Optional[float] = None,
    max_lines: int = 3,
    **attrs,
) -> str:
    """Render mixed Persian/Latin SVG text with optional width-based wrapping."""
    def split_parts(value: str):
        parts = []
        position = 0
        for match in _LATIN_RUN_RE.finditer(value):
            if match.start() > position:
                parts.append(("rtl", value[position:match.start()]))
            parts.append(("ltr", match.group(0)))
            position = match.end()
        if position < len(value):
            parts.append(("rtl", value[position:]))
        return parts

    def build_line(parts, line_x, line_y):
        line_attrs = f'x="{_xml_escape(str(line_x))}" y="{line_y:g}"'
        if lang != "fa":
            plain = "".join(chunk for _, chunk in parts)
            return f"<tspan {line_attrs}>{_xml_escape(plain)}</tspan>"

        children = []
        for kind, chunk in parts:
            escaped = _xml_escape(chunk)
            if kind == "ltr":
                children.append(
                    f'<tspan direction="ltr" unicode-bidi="embed">{escaped}</tspan>'
                )
            else:
                children.append(f"<tspan>{escaped}</tspan>")
        return f"<tspan {line_attrs}>{''.join(children)}</tspan>"

    lines = [text]
    if max_width is not None:
        avg_char_width = font_size * 0.55
        max_chars = max(10, int(max_width / avg_char_width))
        lines = []
        current = ""
        for token in re.findall(r"\s+|\S+", text):
            if token.isspace():
                current += token
                continue
            if current.strip() and len(current.rstrip()) + 1 + len(token) > max_chars:
                lines.append(current)
                current = token
            else:
                current += token
            while len(current) > max_chars:
                lines.append(current[:max_chars])
                current = current[max_chars:]
        if current:
            lines.append(current)
        max_lines = max(1, max_lines)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip() + "…"

    line_height = font_size * 1.4
    tspans = [
        build_line(split_parts(line), x, y + index * line_height)
        for index, line in enumerate(lines)
    ]
    escaped_attrs = " ".join(
        f'{name}="{_xml_escape(str(value)).replace(chr(34), "&quot;")}"'
        for name, value in attrs.items()
    )
    direction = "rtl" if lang == "fa" else "ltr"
    bidi_attr = ' unicode-bidi="embed"'
    attrs_text = f" {escaped_attrs}" if escaped_attrs else ""
    return (
        f'<text font-size="{font_size:g}" direction="{direction}"{bidi_attr}'
        f'{attrs_text}>{"".join(tspans)}</text>'
    )


def _svg_view_width(svg: str) -> float:
    opening = re.search(r"<svg\b[^>]*>", svg, flags=re.IGNORECASE)
    if opening is None:
        return 1000.0
    tag = opening.group(0)
    view_box = re.search(r'''\bviewBox\s*=\s*(["'])([^"']+)\1''', tag)
    if view_box:
        values = view_box.group(2).split()
        if len(values) == 4:
            return float(values[2])
    width = re.search(r'''\bwidth\s*=\s*(["'])([\d.]+)(?:px)?\1''', tag)
    return float(width.group(2)) if width else 1000.0


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
            return svg[:match.start()] + opening + svg[match.end():], old_height + 27.0

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
        return svg[:match.start()] + opening + svg[match.end():], old_height + 27.0

    return svg, 0.0


def preliminary_drawing(render):
    @wraps(render)
    def wrapped(*args, **kwargs):
        from lv_assist.i18n import i18n, tr

        svg = render(*args, **kwargs)
        direction = i18n.direction()
        language = i18n.get_language()
        rtl = direction == "rtl"
        svg_width = _svg_view_width(svg)
        disclaimer_x = "98%" if rtl else "2%"
        text_anchor = "end" if rtl else "start"
        disclaimer_text = tr("disclaimer_general")
        font_size = 6.0
        max_lines = 4
        max_width = svg_width * 0.96
        preview = render_bidi_text(
            disclaimer_text,
            x=disclaimer_x,
            y=0,
            lang=language,
            font_size=font_size,
            max_width=max_width,
            max_lines=max_lines,
            **{"font-family": "sans-serif", "fill": "#666", "text-anchor": text_anchor},
        )
        line_count = preview.count('<tspan x=')
        line_height = font_size * 1.4
        padding = 36.0 + max(0, line_count - 1) * line_height
        svg, disclaimer_y = _extend_svg_bottom(svg, padding=padding)
        stamp_y = disclaimer_y - 15.0
        stamp = (
            f'<text x="98%" y="{stamp_y:g}" text-anchor="end" font-size="11" '
            'font-family="sans-serif" fill="#805000">'
            'PRELIMINARY: engineering review required</text>'
        )
        disclaimer = render_bidi_text(
            disclaimer_text,
            x=disclaimer_x,
            y=disclaimer_y,
            lang=language,
            font_size=font_size,
            max_width=max_width,
            max_lines=max_lines,
            **{"font-family": "sans-serif", "fill": "#666", "text-anchor": text_anchor},
        )
        return svg.replace('</svg>', stamp + disclaimer + '</svg>')
    return wrapped
