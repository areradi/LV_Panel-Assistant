"""Load verified manufacturer let-through I²t points from the active CSV."""

from __future__ import annotations

import csv
import math
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path


class I2tCurveLoader:
    """Read verified I²t points and interpolate only within their data range."""

    SINGLE_POINT_TOLERANCE = 0.02

    def __init__(self, csv_path: str | Path | None = None):
        self.csv_path = Path(csv_path) if csv_path is not None else Path(__file__).with_name("i2t_curves.csv")
        self._curves: dict[tuple[str, float], list[tuple[float, float]]] = defaultdict(list)
        try:
            with self.csv_path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    if row.get("verification_status", "").strip().upper() != "VERIFIED":
                        continue
                    try:
                        device_type = row["device_type"].strip()
                        rated_a = float(row["rated_a"])
                        ik_ka = float(row["ik_ka"])
                        i2t_a2s = float(row["i2t_a2s"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if (not device_type or not all(map(math.isfinite, (rated_a, ik_ka, i2t_a2s)))
                            or rated_a <= 0 or ik_ka <= 0 or i2t_a2s <= 0):
                        continue
                    self._curves[(device_type, rated_a)].append((ik_ka, i2t_a2s))
        except (OSError, csv.Error):
            return

        for points in self._curves.values():
            points.sort()

    def get_letthrough_i2t(
        self, device_type: str, rated_a: float, ik_ka: float,
    ) -> float | None:
        """Return verified I²t, or None when there is no safe in-range match."""
        try:
            rating = float(rated_a)
            requested_ik = float(ik_ka)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(rating) or not math.isfinite(requested_ik) or rating <= 0 or requested_ik <= 0:
            return None

        curve_type = str(device_type).strip()
        points = next((values for (name, current_rating), values in self._curves.items()
                       if name == curve_type and math.isclose(current_rating, rating, rel_tol=0, abs_tol=1e-9)), None)
        if not points:
            return None

        if len(points) == 1:
            point_ik, point_i2t = points[0]
            relative_delta = abs(requested_ik - point_ik) / point_ik
            return point_i2t if relative_delta <= self.SINGLE_POINT_TOLERANCE + 1e-12 else None

        currents = [point[0] for point in points]
        index = bisect_left(currents, requested_ik)
        if index < len(points) and points[index][0] == requested_ik:
            return points[index][1]
        if index == 0 or index == len(points):
            return None

        low_ik, low_i2t = points[index - 1]
        high_ik, high_i2t = points[index]
        fraction = math.log(requested_ik / low_ik) / math.log(high_ik / low_ik)
        return math.exp(math.log(low_i2t) + fraction * math.log(high_i2t / low_i2t))
