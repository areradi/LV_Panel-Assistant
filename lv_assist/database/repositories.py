"""Repository objects for read-only access to extracted component data."""

import math

from lv_assist.database.connection import PathLike, database_connection
from lv_assist.database.models import (
    Component,
    ComponentAttribute,
    MotorProtectionCandidate,
)
from lv_assist.database.queries import (
    find_attribute_rows,
    find_component_row,
    find_motor_candidate_rows,
)

_UNVERIFIED_PREVIEW_WARNING = "⚠️ تأییدنشده - فقط برای پیش‌نمایش"


def _positive_finite(value: float, field_name: str) -> float:
    """Validate a positive finite numeric input without accepting booleans."""
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} must be a positive finite number")
    return number


class ComponentRepository:
    """Read component identities and rating-range candidates from SQLite.

    This repository performs catalog discovery only. Even verified rows are
    data for review; this class does not approve or select a protective device.
    """

    def __init__(self, database_path: PathLike | None = None) -> None:
        """Create a repository using an explicit path or configured database path."""
        self.database_path = database_path

    def find_by_part_number(self, part_number: str) -> Component | None:
        """Find an exact part number while retaining the component's source reference."""
        if not isinstance(part_number, str):
            raise TypeError("part_number must be a string")
        with database_connection(self.database_path) as connection:
            row = find_component_row(connection, part_number)
        if row is None:
            return None
        return Component(
            component_id=row["component_id"],
            part_number=row["part_number"],
            manufacturer=row["manufacturer"],
            family=row["family"],
            component_type=row["component_type"],
            record_status=row["record_status"],
            source_file=row["source_file"],
            source_locator=row["source_locator"],
        )

    def find_components_for_motor(
        self,
        power_kw: float,
        voltage_v: float,
        verified_only: bool = False,
    ) -> list[MotorProtectionCandidate]:
        """Find rating-range matches for a 400 V motor preview.

        The requested estimate is ``current_a = power_kw * 2`` and is only
        defined here for 400 V. Results with any extracted rating are marked
        as preview-only. This query never evaluates safety or coordination.
        Only explicit A and V attributes are compared; the DAL does not convert
        or infer units. Records requiring review and raw/deprecated records are
        excluded from both preview and verified-only lookups.
        """
        power = _positive_finite(power_kw, "power_kw")
        voltage = _positive_finite(voltage_v, "voltage_v")
        if not math.isclose(voltage, 400.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("The approved motor-current estimate is defined only for 400 V")
        if not isinstance(verified_only, bool):
            raise TypeError("verified_only must be a boolean")

        current = power * 2.0
        statuses = ("verified",) if verified_only else ("verified", "extracted")
        with database_connection(self.database_path) as connection:
            rows = find_motor_candidate_rows(connection, current, voltage, statuses)

        candidates: list[MotorProtectionCandidate] = []
        seen: set[tuple[object, ...]] = set()
        for row in rows:
            status_values = (
                row["component_status"], row["current_status"], row["voltage_status"]
            )
            status = "verified" if all(value == "verified" for value in status_values) else "extracted"
            key = (row["component_id"], row["current_min_a"], row["current_max_a"],
                   row["voltage_v"], row["source_file"], row["source_locator"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(MotorProtectionCandidate(
                component_id=row["component_id"],
                part_number=row["part_number"],
                manufacturer=row["manufacturer"],
                component_type=row["component_type"],
                record_status=status,
                estimated_motor_current_a=current,
                rated_current_min_a=row["current_min_a"],
                rated_current_max_a=row["current_max_a"],
                rated_voltage_v=row["voltage_v"],
                current_unit=row["current_unit"],
                voltage_unit=row["voltage_unit"],
                current_record_status=row["current_status"],
                voltage_record_status=row["voltage_status"],
                source_file=row["source_file"],
                source_locator=row["source_locator"],
                is_preview_only=not verified_only,
                is_safety_recommendation=False,
                preview_warning=_UNVERIFIED_PREVIEW_WARNING if status == "extracted" else None,
            ))
        return candidates


class AttributeRepository:
    """Read component attributes with source units, quality status, and provenance."""

    def __init__(self, database_path: PathLike | None = None) -> None:
        """Create a repository using an explicit path or configured database path."""
        self.database_path = database_path

    def find_for_component(
        self,
        component_id: str,
        parameter_key: str | None = None,
        verified_only: bool = False,
    ) -> list[ComponentAttribute]:
        """Return source attributes without unit conversion or missing-value defaults."""
        if not isinstance(component_id, str) or not component_id:
            raise ValueError("component_id must be a non-empty string")
        if parameter_key is not None and not isinstance(parameter_key, str):
            raise TypeError("parameter_key must be a string or None")
        if not isinstance(verified_only, bool):
            raise TypeError("verified_only must be a boolean")
        with database_connection(self.database_path) as connection:
            rows = find_attribute_rows(
                connection, component_id, parameter_key, verified_only
            )
        return [ComponentAttribute(
            attribute_id=row["attribute_id"],
            component_id=row["component_id"],
            parameter_key=row["parameter_key"],
            raw_value=row["raw_value"],
            normalized_value=row["normalized_value"],
            numeric_value=row["numeric_value"],
            min_value=row["min_value"],
            max_value=row["max_value"],
            unit=row["unit"],
            record_status=row["record_status"],
            source_file=row["source_file"],
            source_locator=row["source_locator"],
        ) for row in rows]
