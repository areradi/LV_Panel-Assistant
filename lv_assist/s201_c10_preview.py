"""Inspect ABB S201-C10 chart readings outside the calculation engine."""

import argparse
import json
import math


PART = "S201-C10"
ORDER_CODE = "2CDS251001R0104"
SOURCE = {
    "catalogue": "ABB System pro M compact, 2CDC 002 001 D0203",
    "sha256": "f316bea91f5c68330d7aa7c08eb5464c638b39a539eff894938e96f5d8bca1f4",
    "identity_page": 31,
    "test_conditions_page": 9,
    "trip_page": 11,
    "trip_figure": "SK 0128 Z 00",
    "energy_page": 13,
    "energy_figure": "2CDC 022 132 F0203",
}

# Stop each interpolated branch before its magnetic knee.
FAST_SECONDS = ((20, 9.5), (30, 3.3), (40, 1.9), (48, 1.5))
SLOW_SECONDS = ((20, 240), (30, 60), (40, 31), (50, 20), (60, 15),
                (70, 13), (80, 11), (90, 9.6))
ENERGY_A2S = ((1000, 1900), (1500, 3300), (2000, 4900), (3000, 7600),
              (4000, 10700), (4500, 12200), (5000, 13800), (6000, 17000))
TEST_LIMITS = {11.3: (">", 3600), 14.5: ("<", 3600), 50: (">", 0.1), 100: ("<", 0.1)}


def _sample(points, current_a):
    for current, value in points:
        if current_a == current:
            return value
    for (left, low), (right, high) in zip(points, points[1:]):
        if left < current_a < right:
            fraction = math.log(current_a / left) / math.log(right / left)
            return low * (high / low) ** fraction
    return None


def _trip_reading(current_a):
    fast = _sample(FAST_SECONDS, current_a)
    slow = _sample(SLOW_SECONDS, current_a)
    limit = TEST_LIMITS.get(current_a)
    fast_note = None
    if current_a == 60:
        fast_note = "Near the chart floor (0.01 s)."
    elif 60 < current_a <= 90:
        fast_note = "Below the plotted scale (0.01 s)."
    if fast is not None and slow is not None:
        status = "GRAPHICAL_BAND"
    elif slow is not None or limit is not None:
        status = "PARTIAL_EVIDENCE"
    else:
        status = "INSUFFICIENT_DATA"
    return {
        "status": status,
        "fast_s_approx": fast,
        "slow_s_approx": slow,
        "fast_boundary_note": fast_note,
        "test_limit": {"operator": limit[0], "seconds": limit[1]} if limit else None,
    }


def preview(part_number, *, current_type, frequency_hz, reference_temp_c,
            trip_current_a=None, fault_current_a=None, voltage_across_pole_v=None):
    if trip_current_a is None and fault_current_a is None:
        raise ValueError("Provide trip_current_a or fault_current_a.")
    for name, value in (("trip_current_a", trip_current_a),
                        ("fault_current_a", fault_current_a)):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be finite and positive.")

    result = {"mode": "PREVIEW_ONLY", "part_number": part_number}
    if part_number != PART:
        return {**result, "status": "INSUFFICIENT_DATA", "reason": "Model outside pilot scope."}
    result.update(order_code=ORDER_CODE, source=dict(SOURCE))
    if current_type != "AC" or not 50 <= frequency_hz <= 60 or reference_temp_c != 30:
        return {**result, "status": "INSUFFICIENT_DATA",
                "reason": "Pilot scope is 50–60 Hz AC at the 30 °C trip reference."}

    result.update(
        status="GRAPHICAL_PREVIEW",
        conditions={"current_type": current_type, "frequency_hz": frequency_hz,
                    "trip_reference_temp_c": reference_temp_c,
                    "voltage_across_pole_v": voltage_across_pole_v},
    )
    if trip_current_a is not None:
        result["trip"] = {"current_a": trip_current_a, **_trip_reading(trip_current_a)}
    if fault_current_a is not None:
        if voltage_across_pole_v != 230:
            energy = {"status": "INSUFFICIENT_DATA", "reason": "Pilot requires 230 V across the pole."}
        else:
            reading = _sample(ENERGY_A2S, fault_current_a)
            energy = ({"status": "GRAPHICAL_READING", "a2s_approx": reading} if reading is not None else
                      {"status": "INSUFFICIENT_DATA", "reason": "Outside sampled range of 1000–6000 A."})
        result["energy"] = {"prospective_fault_current_a": fault_current_a, **energy}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", default=PART)
    parser.add_argument("--current-type", choices=("AC", "DC"), required=True)
    parser.add_argument("--frequency-hz", type=float, required=True)
    parser.add_argument("--reference-temp-c", type=float, required=True)
    parser.add_argument("--trip-current-a", type=float)
    parser.add_argument("--fault-current-a", type=float)
    parser.add_argument("--voltage-across-pole-v", type=float)
    args = parser.parse_args()
    if args.voltage_across_pole_v is not None and not math.isfinite(args.voltage_across_pole_v):
        parser.error("--voltage-across-pole-v must be finite.")
    try:
        result = preview(args.part, current_type=args.current_type, frequency_hz=args.frequency_hz,
                         reference_temp_c=args.reference_temp_c, trip_current_a=args.trip_current_a,
                         fault_current_a=args.fault_current_a,
                         voltage_across_pole_v=args.voltage_across_pole_v)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
