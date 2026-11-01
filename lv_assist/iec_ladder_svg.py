# -*- coding: utf-8 -*-
"""
lv_assist/iec_ladder_svg.py
موتور ترسیم نقشه نردبانی مدار فرمان (IEC 60617 / IEC 61082 / IEC 81346)
با مدل توپولوژیک Rung، نمایش مسیر تحریک بوبین و اعتبارسنجی الکتریکی مدار
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union
import html

SVG_W = 1220.0
COL_X0 = 155.0
COIL_X = 980.0
X_STEP = 135.0
RAIL_TOP = 92.0
RUNG_TOP = 155.0
RUNG_STEP = 145.0

C_WIRE = "#1E293B"
C_RAIL_L = "#DC2626"
C_RAIL_M = "#2563EB"
C_SYM = "#0F172A"
C_TAG = "#1E293B"
C_PIN = "#475569"
C_MUTED = "#64748B"
C_WIRE_NO = "#1D4ED8"
C_COIL_BG = "#EFF6FF"
C_PATH_BG = "#F8FAFC"


@dataclass
class Contact:
    tag: str
    kind: str = "NO"          # "NO" | "NC" | "TH_NC" | "PB_NO" | "PB_NC"
    pins: str = "13-14"
    role: str = ""


@dataclass
class Terminal:
    strip: str = "-X2"
    pin: str = "1"


@dataclass
class WireMark:
    no: str
    role: str = ""


@dataclass
class Branch:
    """شاخه موازی (مانند خودنگهدار کنتاکتور موازی با شستی استارت)."""
    paths: List[List[Union[Contact, WireMark]]] = field(default_factory=list)


@dataclass
class Coil:
    tag: str
    pins: str = "A1-A2"
    role: str = ""
    part_number: str = ""


@dataclass
class Rung:
    no: int
    title: str
    elements: List[Union[Contact, Terminal, WireMark, Branch]]
    coil: Coil
    activation_formula: str = ""


@dataclass
class FeederLadderDTO:
    feeder_index: int
    sheet_no: int
    project_name: str
    panel_tag: str
    feeder_id: str
    func_tag: str
    loc_tag: str
    description: str
    load_type: str
    power_kw: float
    ib_a: float
    prot_tag: str
    prot_part: str
    prot_in_a: float
    km_tag: str = "-K1M"
    km_part: str = ""
    kd_tag: str = "-K1D"
    kd_part: str = ""
    ky_tag: str = "-K1Y"
    ky_part: str = ""
    bimetal_tag: str = "-F1"
    bimetal_part: str = ""
    timer_tag: str = "-K1T"
    timer_part: str = ""
    power_cable_str: str = ""
    psu_part: str = "24VDC"
    delta_current_a: float = 0.0
    star_current_a: float = 0.0
    vfd_tag: str = ""
    vfd_part: str = ""


def esc(val: object) -> str:
    return html.escape(str(val or ""))


class IECLadderSvgGenerator:
    """تولیدکننده مستقل نقشه مدار فرمان با مسیر فعال‌سازی بوبین و کنترل صحت مدار."""

    @classmethod
    def _build_rungs(cls, d: FeederLadderDTO) -> List[Rung]:
        w = d.feeder_index * 10
        x_base = (d.feeder_index - 1) * 4 + 1
        lt = (d.load_type or "MOTOR_DOL").upper()

        f_tag = d.bimetal_tag or f"-F{d.feeder_index}"
        s0_tag = f"-S{d.feeder_index}0"
        s1_tag = f"-S{d.feeder_index}1"
        km_tag = d.km_tag or f"-K{d.feeder_index}M"

        if "STAR_DELTA" in lt:
            ky_tag = d.ky_tag or f"-K{d.feeder_index}Y"
            kd_tag = d.kd_tag or f"-K{d.feeder_index}D"
            kt_tag = d.timer_tag or f"-K{d.feeder_index}T"
            return [
                Rung(
                    no=1,
                    title="مسیر ۱: فرمان استارت، خودنگهدار و کنتاکتور اصلی + تایمر",
                    elements=[
                        Contact(f"-F0", "NO", "1-2", "MCB 24V"),
                        Contact(f_tag, "TH_NC", "95-96", "Thermal O/L"),
                        Terminal("-X2", str(x_base)),
                        Contact(s0_tag, "PB_NC", "11-12", "Stop PB"),
                        WireMark(f"-{w+1}", "Stop node"),
                        Branch(paths=[
                            [Contact(s1_tag, "PB_NO", "13-14", "Start PB")],
                            [Contact(km_tag, "NO", "13-14", "Self-hold")],
                        ]),
                        Terminal("-X2", str(x_base + 1)),
                        WireMark(f"-{w+2}", "Main coil feed"),
                    ],
                    coil=Coil(km_tag, "A1-A2", "Main Contactor + Timer " + kt_tag, d.km_part),
                    activation_formula=(
                        f"Energize {km_tag} = L+ AND -F0 AND {f_tag}(95-96 NC) "
                        f"AND {s0_tag}(11-12 NC) AND [{s1_tag}(13-14 NO) OR {km_tag}(13-14 NO)]"
                    ),
                ),
                Rung(
                    no=2,
                    title="مسیر ۲: کنتاکتور ستاره (با اینترلاک الکتریکی NC از مثلث)",
                    elements=[
                        Contact(km_tag, "NO", "53-54", "Main active"),
                        Contact(kt_tag, "NC", "15-16", "Star time"),
                        Contact(kd_tag, "NC", "21-22", "Interlock D"),
                        WireMark(f"-{w+4}", "Star coil feed"),
                    ],
                    coil=Coil(ky_tag, "A1-A2", "Star Contactor (Y)", d.ky_part),
                    activation_formula=(
                        f"Energize {ky_tag} = L+ AND {km_tag}(53-54 NO) "
                        f"AND {kt_tag}(15-16 NC) AND NOT {kd_tag}(21-22 NC Interlock)"
                    ),
                ),
                Rung(
                    no=3,
                    title="مسیر ۳: کنتاکتور مثلث (با اینترلاک الکتریکی NC از ستاره)",
                    elements=[
                        Contact(km_tag, "NO", "63-64", "Main active"),
                        Contact(kt_tag, "NO", "15-18", "Delta time"),
                        Contact(ky_tag, "NC", "21-22", "Interlock Y"),
                        WireMark(f"-{w+5}", "Delta coil feed"),
                    ],
                    coil=Coil(kd_tag, "A1-A2", "Delta Contactor (D)", d.kd_part),
                    activation_formula=(
                        f"Energize {kd_tag} = L+ AND {km_tag}(63-64 NO) "
                        f"AND {kt_tag}(15-18 NO) AND NOT {ky_tag}(21-22 NC Interlock)"
                    ),
                ),
            ]

        if "VFD" in lt:
            u_tag = d.vfd_tag or f"-U{d.feeder_index}"
            k_run = f"-K{d.feeder_index}R"
            return [
                Rung(
                    no=1,
                    title="مسیر ۱: فرمان اجرای درایو (Run Enable) با خودنگهدار و فالت درایو",
                    elements=[
                        Contact("-F0", "NO", "1-2", "MCB 24V"),
                        Contact(f"{u_tag}:FLT", "NC", "R1B-R1C", "VFD Fault NC"),
                        Terminal("-X2", str(x_base)),
                        Contact(s0_tag, "PB_NC", "11-12", "Stop PB"),
                        Branch(paths=[
                            [Contact(s1_tag, "PB_NO", "13-14", "Start PB")],
                            [Contact(k_run, "NO", "13-14", "Self-hold")],
                        ]),
                        Terminal("-X2", str(x_base + 1)),
                        WireMark(f"-{w+2}", "DI1 Run"),
                    ],
                    coil=Coil(k_run, "A1-A2", f"Run Relay -> {u_tag}:DI1", d.km_part),
                    activation_formula=(
                        f"Energize {k_run} = L+ AND -F0 AND {u_tag}:FLT(NC) "
                        f"AND {s0_tag}(11-12 NC) AND [{s1_tag}(13-14 NO) OR {k_run}(13-14 NO)]"
                    ),
                ),
            ]

        # پیش‌فرض: MOTOR_DOL یا فیدر کلیدخور با کنتاکتور
        return [
            Rung(
                no=1,
                title="مسیر ۱: مدار فرمان مستقیم (DOL) — حفاظت حرارتی، استپ، استارت و خودنگهدار",
                elements=[
                    Contact("-F0", "NO", "1-2", "MCB 24V"),
                    Contact(f_tag, "TH_NC", "95-96", "Thermal O/L"),
                    Terminal("-X2", str(x_base)),
                    Contact(s0_tag, "PB_NC", "11-12", "Stop PB"),
                    WireMark(f"-{w+1}", "After Stop"),
                    Branch(paths=[
                        [Contact(s1_tag, "PB_NO", "13-14", "Start PB")],
                        [Contact(km_tag, "NO", "13-14", "Self-hold")],
                    ]),
                    Terminal("-X2", str(x_base + 1)),
                    WireMark(f"-{w+2}", "Coil A1 feed"),
                ],
                coil=Coil(km_tag, "A1-A2", "Main Contactor", d.km_part),
                activation_formula=(
                    f"Energize {km_tag} = L+ AND -F0(1-2) AND {f_tag}(95-96 NC) "
                    f"AND {s0_tag}(11-12 NC) AND [{s1_tag}(13-14 NO) OR {km_tag}(13-14 NO)]"
                ),
            ),
        ]

    @classmethod
    def validate_control_circuit(cls, d: FeederLadderDTO) -> List[str]:
        """کنترل صحت الکتریکی مدار فرمان طبق بند ۹.۵ دستورکار."""
        issues: List[str] = []
        rungs = cls._build_rungs(d)
        known_coils = {r.coil.tag for r in rungs if r.coil and r.coil.tag}
        for r in rungs:
            if not r.coil or not r.coil.tag.strip():
                issues.append(f"Rung {r.no}: بوبین فاقد شناسه معتبر است.")
            if not r.elements:
                issues.append(f"Rung {r.no}: بوبین {r.coil.tag} بدون کنتاکت کنترلی مستقیم به منبع متصل شده است (اتصال ناخواسته).")
            for el in r.elements:
                if isinstance(el, Contact) and not el.tag.strip():
                    issues.append(f"Rung {r.no}: کنتاکت با شناسه نامشخص وجود دارد.")
                elif isinstance(el, Branch):
                    for p in el.paths:
                        for sub in p:
                            if isinstance(sub, Contact) and not sub.tag.strip():
                                issues.append(f"Rung {r.no}: کنتاکت شاخه موازی فاقد شناسه است.")
        # کنترل اینترلاک در ستاره-مثلث
        if "STAR_DELTA" in (d.load_type or "").upper() and len(rungs) >= 3:
            r2_tags = [e.tag for e in rungs[1].elements if isinstance(e, Contact) and e.kind == "NC"]
            r3_tags = [e.tag for e in rungs[2].elements if isinstance(e, Contact) and e.kind == "NC"]
            if (d.kd_tag or f"-K{d.feeder_index}D") not in r2_tags:
                issues.append("اینترلاک NC کنتاکتور مثلث در مسیر بوبین ستاره یافت نشد.")
            if (d.ky_tag or f"-K{d.feeder_index}Y") not in r3_tags:
                issues.append("اینترلاک NC کنتاکتور ستاره در مسیر بوبین مثلث یافت نشد.")
        return issues

    @classmethod
    def build_feeder_wires_and_terminals(cls, d: FeederLadderDTO) -> Dict[str, list]:
        edges = []
        marks = []
        terminals = {}
        parent = {}

        def root(pin):
            parent.setdefault(pin, pin)
            if parent[pin] != pin:
                parent[pin] = root(parent[pin])
            return parent[pin]

        def connect(sources, destination, role):
            for source in sources:
                if source != destination:
                    edges.append((source, destination, role))
                    parent[root(source)] = root(destination)

        def walk(elements, sources):
            for element in elements:
                if isinstance(element, WireMark):
                    marks.extend((pin, element.no) for pin in sources)
                elif isinstance(element, Contact):
                    first, second = element.pins.split("-", 1)
                    connect(sources, f"{element.tag}:{first}", element.role)
                    sources = [f"{element.tag}:{second}"]
                elif isinstance(element, Terminal):
                    pin = f"{element.strip}:{element.pin}"
                    connect(sources, pin, "")
                    terminals[pin] = element
                    sources = [pin]
                elif isinstance(element, Branch):
                    # Parallel paths share their input and output nets, not their contacts.
                    sources = [pin for path in element.paths for pin in walk(path, sources)]
            return sources

        for rung in cls._build_rungs(d):
            sources = walk(rung.elements, ["L+"])
            first, second = rung.coil.pins.split("-", 1)
            connect(sources, f"{rung.coil.tag}:{first}", rung.coil.role)
            connect([f"{rung.coil.tag}:{second}"], "M", "0VDC")

        net_numbers = {}
        for pin, number in marks:
            net_numbers.setdefault(root(pin), set()).add(number)

        def number_for(pin):
            return " / ".join(sorted(net_numbers.get(root(pin), ())))

        wires = []
        seen = set()
        for source, destination, role in edges:
            pair = frozenset((source, destination))
            if pair in seen:
                continue
            seen.add(pair)
            wires.append({
                "wire_no": number_for(source), "feeder_id": d.feeder_id,
                "potential_role": role, "from_pin": source, "to_pin": destination,
                "wire_spec": "",
            })
        terminal_rows = [{
            "feeder_id": d.feeder_id, "terminal_strip": terminal.strip,
            "terminal_pin": terminal.pin, "internal_wire_no": number_for(pin),
            "internal_target": "", "cable_tag": "", "cable_core": "",
            "cable_spec": "", "external_location": "", "external_target": "",
        } for pin, terminal in terminals.items()]
        return {"wires": wires, "terminals": terminal_rows}

    @classmethod
    def render_feeder_ladder_svg(cls, d: FeederLadderDTO) -> str:
        rungs = cls._build_rungs(d)
        issues = cls.validate_control_circuit(d)
        rail_bottom = RUNG_TOP + (len(rungs) - 1) * RUNG_STEP + 75.0
        svg_h = rail_bottom + 145.0

        parts: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W:.0f} {svg_h:.0f}" width="100%" '
            f'style="background:#FFFFFF; font-family:Tahoma,Calibri,sans-serif;">',
            f'<rect x="10" y="10" width="{SVG_W - 20:.0f}" height="{svg_h - 20:.0f}" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.5" rx="6"/>',
            # هدر استاندارد مهندسی
            f'<rect x="10" y="10" width="{SVG_W - 20:.0f}" height="52" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1"/>',
            f'<text x="26" y="32" font-size="13" font-weight="bold" fill="{C_TAG}">'
            f'CONTROL CIRCUIT SCHEMATIC (IEC 60617) — Feeder {esc(d.feeder_id)} ({esc(d.func_tag)} / {esc(d.loc_tag)})</text>',
            f'<text x="26" y="50" font-size="11" fill="{C_MUTED}">'
            f'{esc(d.description)} | {esc(d.load_type)} | P = {d.power_kw:.2f} kW | Ib = {d.ib_a:.1f} A | '
            f'Protection: {esc(d.prot_tag)} ({esc(d.prot_part)}) | Sheet {d.sheet_no}</text>',
            # ریل‌های تغذیه چپ (L+) و راست (M)
            f'<line x1="{COL_X0 - 45:.0f}" y1="{RAIL_TOP:.0f}" x2="{COL_X0 - 45:.0f}" y2="{rail_bottom:.0f}" stroke="{C_RAIL_L}" stroke-width="3"/>',
            f'<text x="{COL_X0 - 45:.0f}" y="{RAIL_TOP - 10:.0f}" font-size="11" font-weight="bold" fill="{C_RAIL_L}">L+ (+24VDC)</text>',
            f'<line x1="{COIL_X + 75:.0f}" y1="{RAIL_TOP:.0f}" x2="{COIL_X + 75:.0f}" y2="{rail_bottom:.0f}" stroke="{C_RAIL_M}" stroke-width="3"/>',
            f'<text x="{COIL_X + 75:.0f}" y="{RAIL_TOP - 10:.0f}" text-anchor="end" font-size="11" font-weight="bold" fill="{C_RAIL_M}">M (0VDC)</text>',
        ]

        x_rail_l = COL_X0 - 45.0
        x_rail_m = COIL_X + 75.0

        for idx, rung in enumerate(rungs):
            y = RUNG_TOP + idx * RUNG_STEP
            n_slots = max(1, len(rung.elements))
            step = min(X_STEP, (COIL_X - 65.0 - COL_X0) / n_slots)

            # عنوان Rung
            parts.append(
                f'<text x="{x_rail_l + 8:.0f}" y="{y - 46:.0f}" font-size="10" font-weight="bold" fill="{C_MUTED}">'
                f'Rung {rung.no} — {esc(rung.title)}</text>'
            )

            x_cursor = x_rail_l
            for s_idx, el in enumerate(rung.elements):
                xc = COL_X0 + s_idx * step + step * 0.5
                if isinstance(el, Contact):
                    left, right = xc - 22.0, xc + 22.0
                    parts.append(f'<line x1="{x_cursor:.0f}" y1="{y:.0f}" x2="{left:.0f}" y2="{y:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
                    parts.append(cls._svg_contact(xc, y, el))
                    x_cursor = right
                elif isinstance(el, Terminal):
                    left, right = xc - 6.0, xc + 6.0
                    parts.append(f'<line x1="{x_cursor:.0f}" y1="{y:.0f}" x2="{left:.0f}" y2="{y:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
                    parts.append(cls._svg_terminal(xc, y, el))
                    x_cursor = right
                elif isinstance(el, WireMark):
                    left, right = xc - 20.0, xc + 20.0
                    parts.append(f'<line x1="{x_cursor:.0f}" y1="{y:.0f}" x2="{left:.0f}" y2="{y:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
                    parts.append(cls._svg_wire_mark(xc, y, el.no))
                    x_cursor = right
                elif isinstance(el, Branch):
                    b_left = xc - step * 0.42
                    b_right = xc + step * 0.42
                    parts.append(f'<line x1="{x_cursor:.0f}" y1="{y:.0f}" x2="{b_left:.0f}" y2="{y:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
                    parts.append(cls._svg_branch(b_left, b_right, y, el))
                    x_cursor = b_right

            # اتصال به بوبین و ریل M
            coil_left = COIL_X - 28.0
            coil_right = COIL_X + 28.0
            parts.append(f'<line x1="{x_cursor:.0f}" y1="{y:.0f}" x2="{coil_left:.0f}" y2="{y:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
            parts.append(cls._svg_coil(COIL_X, y, rung.coil))
            parts.append(f'<line x1="{coil_right:.0f}" y1="{y:.0f}" x2="{x_rail_m:.0f}" y2="{y:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')

            # باکس مسیر منطقی فعال‌سازی بوبین زیر هر Rung (بند ۹.۴ دستورکار)
            parts.append(
                f'<rect x="{COL_X0 - 30:.0f}" y="{y + 44:.0f}" width="{COIL_X - COL_X0 + 85:.0f}" height="22" '
                f'rx="4" fill="{C_PATH_BG}" stroke="#E2E8F0" stroke-width="1"/>'
                f'<text x="{COL_X0 - 20:.0f}" y="{y + 59:.0f}" font-size="10" font-family="Consolas,monospace" fill="#0F172A">'
                f'Activation Path: {esc(rung.activation_formula)}</text>'
            )

        # نوار وضعیت اعتبارسنجی الکتریکی مدار در پایین شیت (بند ۹.۵ دستورکار)
        y_stat = rail_bottom + 28.0
        if not issues:
            parts.append(
                f'<rect x="24" y="{y_stat:.0f}" width="{SVG_W - 48:.0f}" height="32" rx="6" fill="#DCFCE7" stroke="#16A34A" stroke-width="1"/>'
                f'<text x="38" y="{y_stat + 20:.0f}" font-size="11" font-weight="bold" fill="#166534">'
                f'✓ Electrical Verification OK: All coils have valid L+/M supply paths, contact tags are resolved, and NC interlocks are verified.</text>'
            )
        else:
            msg = " | ".join(issues)
            parts.append(
                f'<rect x="24" y="{y_stat:.0f}" width="{SVG_W - 48:.0f}" height="32" rx="6" fill="#FEE2E2" stroke="#DC2626" stroke-width="1"/>'
                f'<text x="38" y="{y_stat + 20:.0f}" font-size="11" font-weight="bold" fill="#991B1B">'
                f'⚠ Circuit Verification Warning: {esc(msg)}</text>'
            )

        parts.append("</svg>")
        return "\n".join(parts)

    @staticmethod
    def _svg_contact(xc: float, y: float, c: Contact) -> str:
        p1, p2 = (c.pins.split("-") + ["", ""])[:2]
        blade = (
            f'<line x1="{xc - 14:.0f}" y1="{y - 10:.0f}" x2="{xc + 14:.0f}" y2="{y - 2:.0f}" stroke="{C_SYM}" stroke-width="2.2"/>'
            if "NC" in c.kind
            else f'<line x1="{xc - 14:.0f}" y1="{y - 2:.0f}" x2="{xc + 12:.0f}" y2="{y - 14:.0f}" stroke="{C_SYM}" stroke-width="2.2"/>'
        )
        return (
            f'<g>'
            f'<line x1="{xc - 22:.0f}" y1="{y:.0f}" x2="{xc - 14:.0f}" y2="{y:.0f}" stroke="{C_SYM}" stroke-width="2"/>'
            f'<line x1="{xc + 14:.0f}" y1="{y:.0f}" x2="{xc + 22:.0f}" y2="{y:.0f}" stroke="{C_SYM}" stroke-width="2"/>'
            f'<line x1="{xc - 14:.0f}" y1="{y - 12:.0f}" x2="{xc - 14:.0f}" y2="{y + 12:.0f}" stroke="{C_SYM}" stroke-width="2"/>'
            f'<line x1="{xc + 14:.0f}" y1="{y - 12:.0f}" x2="{xc + 14:.0f}" y2="{y + 12:.0f}" stroke="{C_SYM}" stroke-width="2"/>'
            f'{blade}'
            f'<text x="{xc:.0f}" y="{y - 18:.0f}" text-anchor="middle" font-size="10" font-weight="bold" fill="{C_TAG}">{esc(c.tag)}</text>'
            f'<text x="{xc - 18:.0f}" y="{y + 22:.0f}" text-anchor="middle" font-size="8.5" fill="{C_PIN}">{esc(p1)}</text>'
            f'<text x="{xc + 18:.0f}" y="{y + 22:.0f}" text-anchor="middle" font-size="8.5" fill="{C_PIN}">{esc(p2)}</text>'
            f'<text x="{xc:.0f}" y="{y + 33:.0f}" text-anchor="middle" font-size="8.5" fill="{C_MUTED}">{esc(c.role)}</text>'
            f'</g>'
        )

    @staticmethod
    def _svg_terminal(xc: float, y: float, t: Terminal) -> str:
        return (
            f'<g>'
            f'<circle cx="{xc:.0f}" cy="{y:.0f}" r="5.5" fill="#FFFFFF" stroke="{C_SYM}" stroke-width="2"/>'
            f'<text x="{xc:.0f}" y="{y - 11:.0f}" text-anchor="middle" font-size="9" font-weight="bold" fill="{C_TAG}">{esc(t.strip)}:{esc(t.pin)}</text>'
            f'</g>'
        )

    @staticmethod
    def _svg_wire_mark(xc: float, y: float, no: str) -> str:
        return (
            f'<g>'
            f'<rect x="{xc - 18:.0f}" y="{y - 9:.0f}" width="36" height="18" rx="9" fill="#EFF6FF" stroke="{C_WIRE_NO}" stroke-width="1.2"/>'
            f'<text x="{xc:.0f}" y="{y + 4:.0f}" text-anchor="middle" font-size="9" font-weight="bold" fill="{C_WIRE_NO}">{esc(no)}</text>'
            f'</g>'
        )

    @classmethod
    def _svg_branch(cls, x_left: float, x_right: float, y: float, b: Branch) -> str:
        dy = 36.0
        paths = b.paths or [[]]
        n = len(paths)
        ys = [y + (i - (n - 1) / 2.0) * dy for i in range(n)]
        xm = (x_left + x_right) * 0.5
        out = [
            f'<line x1="{x_left:.0f}" y1="{ys[0]:.0f}" x2="{x_left:.0f}" y2="{ys[-1]:.0f}" stroke="{C_WIRE}" stroke-width="2"/>',
            f'<line x1="{x_right:.0f}" y1="{ys[0]:.0f}" x2="{x_right:.0f}" y2="{ys[-1]:.0f}" stroke="{C_WIRE}" stroke-width="2"/>',
        ]
        for y_p, path in zip(ys, paths):
            if not path:
                out.append(f'<line x1="{x_left:.0f}" y1="{y_p:.0f}" x2="{x_right:.0f}" y2="{y_p:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
                continue
            el = path[0]
            if isinstance(el, Contact):
                out.append(f'<line x1="{x_left:.0f}" y1="{y_p:.0f}" x2="{xm - 22:.0f}" y2="{y_p:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
                out.append(cls._svg_contact(xm, y_p, el))
                out.append(f'<line x1="{xm + 22:.0f}" y1="{y_p:.0f}" x2="{x_right:.0f}" y2="{y_p:.0f}" stroke="{C_WIRE}" stroke-width="2"/>')
        return "\n".join(out)

    @staticmethod
    def _svg_coil(xc: float, y: float, c: Coil) -> str:
        p1, p2 = (c.pins.split("-") + ["A1", "A2"])[:2]
        return (
            f'<g>'
            f'<rect x="{xc - 28:.0f}" y="{y - 16:.0f}" width="56" height="32" rx="4" fill="{C_COIL_BG}" stroke="{C_SYM}" stroke-width="2.2"/>'
            f'<text x="{xc:.0f}" y="{y + 4:.0f}" text-anchor="middle" font-size="11" font-weight="bold" fill="{C_TAG}">{esc(c.tag)}</text>'
            f'<text x="{xc - 34:.0f}" y="{y - 6:.0f}" text-anchor="end" font-size="8.5" fill="{C_PIN}">{esc(p1)}</text>'
            f'<text x="{xc + 34:.0f}" y="{y - 6:.0f}" text-anchor="start" font-size="8.5" fill="{C_PIN}">{esc(p2)}</text>'
            f'<text x="{xc:.0f}" y="{y - 22:.0f}" text-anchor="middle" font-size="9.5" font-weight="bold" fill="{C_WIRE_NO}">{esc(c.role)}</text>'
            f'<text x="{xc:.0f}" y="{y + 28:.0f}" text-anchor="middle" font-size="8.5" fill="{C_MUTED}">{esc(c.part_number)}</text>'
            f'</g>'
        )
