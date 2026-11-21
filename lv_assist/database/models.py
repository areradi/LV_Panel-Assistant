"""Typed records returned by the extracted engineering database repositories."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Component:
    """Component identity and provenance without inferred engineering values."""

    component_id: str
    part_number: str | None
    manufacturer: str | None
    family: str | None
    component_type: str | None
    record_status: str | None
    source_file: str | None
    source_locator: str | None


@dataclass(frozen=True)
class ComponentAttribute:
    """One source attribute, retaining raw values, units, status, and locator."""

    attribute_id: str
    component_id: str
    parameter_key: str
    raw_value: str | None
    normalized_value: str | None
    numeric_value: float | None
    min_value: float | None
    max_value: float | None
    unit: str | None
    record_status: str | None
    source_file: str | None
    source_locator: str | None


@dataclass(frozen=True)
class MotorProtectionCandidate:
    """A rating-range search result, not a validated device selection."""

    component_id: str
    part_number: str | None
    manufacturer: str | None
    component_type: str | None
    record_status: str
    estimated_motor_current_a: float
    rated_current_min_a: float
    rated_current_max_a: float
    rated_voltage_v: float
    current_unit: str
    voltage_unit: str
    current_record_status: str
    voltage_record_status: str
    source_file: str | None
    source_locator: str | None
    is_preview_only: bool
    is_safety_recommendation: bool
    preview_warning: str | None
