# -*- coding: utf-8 -*-
"""Summary card formatter and calculation workflow engine.

Priority 3 of the audit fixes:

1. ``format_summary_cards`` — build the two summary cards ("حفاظت اصلی" and
   "محفظه") with proper IEC labels (Icu / Ics / Icn) and a **separate** design
   current. Accepts both the legacy ``CatalogDevice`` and the new
   ``MainBreakerSpec`` / ``EnclosureSpec``.

2. ``CalculationWorkflowEngine`` — per-step dependency tracking that marks
   downstream steps STALE when an upstream input changes. Currently opt-in;
   ``gui.py`` keeps its boolean ``_stale`` flag for now, and can adopt the
   engine incrementally.

Pure stdlib + ``lv_assist.models``. No ``customtkinter`` import at module
load time, so it is unit-testable in CI without a display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lv_assist.models import (
    CatalogProvenance,
    EnclosureSpec,
    MainBreakerSpec,
    StepEngStatus,
    StepExecState,
)


NA_LABEL_FA = "نامشخص"


def _catalog_to_breaker(breaker: Any) -> Optional[MainBreakerSpec]:
    """Adapt a legacy ``CatalogDevice`` to ``MainBreakerSpec`` (passthrough if already one)."""
    if breaker is None:
        return None
    if isinstance(breaker, MainBreakerSpec):
        return breaker

    in_a = getattr(breaker, "rated_current_in_a", None)
    icu = getattr(breaker, "icu_ka_400v", None)
    return MainBreakerSpec(
        device_type=getattr(breaker, "device_type", None),
        model_name=getattr(breaker, "series", None),
        part_number=getattr(breaker, "part_number", None),
        in_a=in_a if in_a else None,
        poles=None,
        rated_voltage_v=400.0 if icu else None,
        icu_ka=icu if icu else None,
        ics_ka=None,
        icn_ka=None,
        icw_ka_1s=None,
        verification_status=CatalogProvenance.VERIFIED_CATALOG,
    )


def _catalog_to_enclosure(enclosure: Any) -> Optional[EnclosureSpec]:
    """Adapt a legacy ``CatalogDevice`` to ``EnclosureSpec`` (passthrough if already one)."""
    if enclosure is None:
        return None
    if isinstance(enclosure, EnclosureSpec):
        return enclosure

    w = getattr(enclosure, "width_mm", 0.0) or None
    h = getattr(enclosure, "height_mm", 0.0) or None
    d = getattr(enclosure, "depth_mm", 0.0) or None
    return EnclosureSpec(
        width_mm=int(w) if w else None,
        height_mm=int(h) if h else None,
        depth_mm=int(d) if d else None,
        mounting_type=None,
        ip_rating=getattr(enclosure, "ip_rating", None),
    )


def format_summary_cards(
    breaker: Any,
    enclosure: Any,
    design_current_a: Optional[float] = None,
    na_label: str = NA_LABEL_FA,
) -> Dict[str, Dict[str, str]]:
    """Build the two summary cards ("main_protection" and "enclosure").

    Values are plain strings; Tk renders Unicode isolation marks as boxes.

    The ``main_protection`` card contains both the **real breaker rating**
    (``rated_current_in``) and the **panel design current** (``design_current``)
    under separate keys, so the two are never confused.
    """
    spec = _catalog_to_breaker(breaker)

    if spec is None:
        main_protection_card = {
            "device_model": na_label,
            "rated_current_in": na_label,
            "breaking_capacity": na_label,
            "poles": na_label,
            "trip_settings": na_label,
        }
    else:
        model_parts = [p for p in (spec.device_type, spec.model_name, spec.part_number) if p]
        device_model_str = " — ".join(model_parts) if model_parts else na_label

        in_str = f"\u2066{spec.in_a:g} A\u2069" if spec.in_a is not None else na_label

        cap_tokens: List[str] = []
        v_ref = f" @ {spec.rated_voltage_v:g} V" if spec.rated_voltage_v else ""
        if spec.icu_ka is not None:
            cap_tokens.append(f"Icu = {spec.icu_ka:g} kA")
        if spec.ics_ka is not None:
            cap_tokens.append(f"Ics = {spec.ics_ka:g} kA")
        if spec.icn_ka is not None:
            cap_tokens.append(f"Icn = {spec.icn_ka:g} kA")
        if spec.icw_ka_1s is not None:
            cap_tokens.append(f"Icw(1s) = {spec.icw_ka_1s:g} kA")
        breaking_cap_str = (
            f"\u2066{' / '.join(cap_tokens)}{v_ref}\u2069" if cap_tokens else na_label
        )

        poles_str = f"\u2066{spec.poles}P\u2069" if spec.poles is not None else na_label

        settings_tokens: List[str] = []
        if spec.ir_setting_a is not None:
            settings_tokens.append(f"Ir={spec.ir_setting_a:g} A")
        if spec.isd_setting_a is not None:
            settings_tokens.append(f"Isd={spec.isd_setting_a:g} A")
        if spec.im_setting_a is not None:
            settings_tokens.append(f"Im={spec.im_setting_a:g} A")
        if spec.ig_setting_a is not None:
            settings_tokens.append(f"Ig={spec.ig_setting_a:g} A")
        trip_settings_str = (
            f"\u2066{', '.join(settings_tokens)}\u2069" if settings_tokens else na_label
        )

        main_protection_card = {
            "device_model": device_model_str,
            "rated_current_in": in_str,
            "breaking_capacity": breaking_cap_str,
            "poles": poles_str,
            "trip_settings": trip_settings_str,
        }

    # Design current is a SEPARATE concept from the breaker's In.
    main_protection_card["design_current"] = (
        f"\u2066{design_current_a:g} A\u2069" if design_current_a is not None else na_label
    )

    enc = _catalog_to_enclosure(enclosure)
    if enc is None:
        enclosure_card = {"width": na_label, "height": na_label, "depth": na_label}
    else:
        enclosure_card = {
            "width": f"\u2066{enc.width_mm} mm\u2069" if enc.width_mm else na_label,
            "height": f"\u2066{enc.height_mm} mm\u2069" if enc.height_mm else na_label,
            "depth": f"\u2066{enc.depth_mm} mm\u2069" if enc.depth_mm else na_label,
        }

    isolation_marks = dict.fromkeys(map(ord, '\u2066\u2067\u2068\u2069'))
    return {name: {key: value.translate(isolation_marks) for key, value in card.items()}
            for name, card in {'main_protection': main_protection_card, 'enclosure': enclosure_card}.items()}


@dataclass
class WorkflowNode:
    """A single node in the calculation workflow."""

    step_id: str
    title_fa: str
    depends_on: List[str] = field(default_factory=list)
    optional: bool = False
    exec_state: StepExecState = StepExecState.PENDING
    eng_status: StepEngStatus = StepEngStatus.INSUFFICIENT_DATA
    missing_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class CalculationWorkflowEngine:
    """Dependency-aware workflow tracker.

    Infrastructure for a future refactor of ``gui.py``'s boolean ``_stale``
    flag. Adopt incrementally: call ``mark_input_changed(step_id)`` whenever an
    input in that step changes, ``mark_calculated(step_id)`` when a step
    finishes, and read ``get_stale_steps()`` / ``any_stale()`` to reflect the
    UI state.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, WorkflowNode] = {
            "project_inputs": WorkflowNode(
                "project_inputs", "مشخصات پروژه و اعتبارسنجی ورودی‌ها"
            ),
            "plc_inst": WorkflowNode(
                "plc_inst", "PLC و ابزار دقیق", depends_on=["project_inputs"], optional=True
            ),
            "grid_sc": WorkflowNode(
                "grid_sc", "شبکه، ترانس و اتصال کوتاه", depends_on=["project_inputs"]
            ),
            "feeders": WorkflowNode(
                "feeders",
                "محاسبات فیدر، کابل، افت ولتاژ و PE",
                depends_on=["grid_sc", "plc_inst"],
            ),
            "aggregation_spd": WorkflowNode(
                "aggregation_spd", "تجمیع بار، PFC و SPD", depends_on=["feeders"]
            ),
            "main_breaker": WorkflowNode(
                "main_breaker", "کلید اصلی و هماهنگی حفاظت", depends_on=["aggregation_spd"]
            ),
            "enclosure_ctrl": WorkflowNode(
                "enclosure_ctrl",
                "تغذیه کنترل، تلفات و ابعاد محفظه",
                depends_on=["main_breaker"],
            ),
            "busbar_thermal": WorkflowNode(
                "busbar_thermal", "شینه و بررسی حرارتی", depends_on=["enclosure_ctrl"]
            ),
            "scenario_rules": WorkflowNode(
                "scenario_rules",
                "کنترل‌های سناریوی ویژه",
                depends_on=["feeders", "aggregation_spd"],
            ),
            "final_report": WorkflowNode(
                "final_report",
                "اعتبارسنجی نهایی و گزارش",
                depends_on=["busbar_thermal", "scenario_rules"],
            ),
        }

    def mark_input_changed(self, modified_step_id: str) -> List[str]:
        """Mark all downstream steps STALE. Return the list of newly stale step ids."""
        stale_marked: List[str] = []
        node = self.nodes.get(modified_step_id)
        if node and node.exec_state == StepExecState.CALCULATED:
            node.exec_state = StepExecState.STALE
            stale_marked.append(modified_step_id)
        queue: List[str] = [modified_step_id]
        visited: set = set()

        while queue:
            current = queue.pop(0)
            for node_id, node in self.nodes.items():
                if current in node.depends_on and node_id not in visited:
                    visited.add(node_id)
                    if node.exec_state == StepExecState.CALCULATED:
                        node.exec_state = StepExecState.STALE
                        stale_marked.append(node_id)
                    queue.append(node_id)
        return stale_marked

    def mark_calculated(self, step_id: str) -> None:
        if step_id in self.nodes:
            self.nodes[step_id].exec_state = StepExecState.CALCULATED

    def get_stale_steps(self) -> List[str]:
        return [nid for nid, n in self.nodes.items() if n.exec_state == StepExecState.STALE]

    def any_stale(self) -> bool:
        return any(n.exec_state == StepExecState.STALE for n in self.nodes.values())
