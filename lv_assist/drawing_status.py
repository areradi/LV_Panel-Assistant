from functools import wraps
import json
from datetime import datetime, timezone
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


def preliminary_drawing(render):
    @wraps(render)
    def wrapped(*args, **kwargs):
        svg = render(*args, **kwargs)
        stamp = ('<text x="98%" y="98%" text-anchor="end" font-size="11" '
                 'fill="#805000">PRELIMINARY: engineering review required</text>')
        return svg.replace('</svg>', stamp + '</svg>')
    return wrapped
