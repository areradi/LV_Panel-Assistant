"""Parameterized SQL queries for read-only component and attribute lookups."""

import sqlite3
from collections.abc import Sequence


def find_component_row(connection: sqlite3.Connection, part_number: str) -> sqlite3.Row | None:
    """Return a component row by exact part number, or ``None`` when absent."""
    return connection.execute(
        """SELECT c.component_id, c.part_number, c.manufacturer_normalized AS manufacturer,
                  c.family, c.component_type, c.record_status,
                  COALESCE(s.path, c.source_file_ref) AS source_file, c.source_locator
           FROM components AS c
           LEFT JOIN sources AS s ON s.path = c.source_file_ref
           WHERE c.part_number = ?
           ORDER BY c.component_id
           LIMIT 1""",
        (part_number,),
    ).fetchone()


def find_attribute_rows(
    connection: sqlite3.Connection,
    component_id: str,
    parameter_key: str | None = None,
    verified_only: bool = False,
) -> Sequence[sqlite3.Row]:
    """Return source attributes for a component, optionally restricted to verified rows."""
    sql = """SELECT a.attribute_id, a.component_id, a.parameter_key, a.raw_value,
                    a.normalized_value, a.numeric_value, a.min_value, a.max_value,
                    a.unit, a.record_status,
                    COALESCE(s.path, a.source_file_ref) AS source_file, a.source_locator
             FROM component_attributes AS a
             JOIN components AS c ON c.component_id = a.component_id
             LEFT JOIN sources AS s ON s.path = a.source_file_ref
             WHERE a.component_id = ?"""
    params: list[object] = [component_id]
    if parameter_key is not None:
        sql += " AND a.parameter_key = ?"
        params.append(parameter_key)
    eligible_statuses = ("verified",) if verified_only else ("verified", "extracted")
    status_marks = ", ".join("?" for _ in eligible_statuses)
    sql += f" AND a.record_status IN ({status_marks}) AND c.record_status IN ({status_marks})"
    params.extend(eligible_statuses)
    params.extend(eligible_statuses)
    sql += " ORDER BY a.parameter_key, a.attribute_id"
    return connection.execute(sql, tuple(params)).fetchall()


def find_motor_candidate_rows(
    connection: sqlite3.Connection,
    estimated_current_a: float,
    system_voltage_v: float,
    allowed_statuses: Sequence[str],
) -> Sequence[sqlite3.Row]:
    """Find breaker/contactor rows whose explicit A and V ratings cover the query."""
    status_marks = ", ".join("?" for _ in allowed_statuses)
    sql = """SELECT c.component_id, c.part_number,
                     c.manufacturer_normalized AS manufacturer, c.component_type,
                     c.record_status AS component_status,
                     ca.record_status AS current_status, va.record_status AS voltage_status,
                     COALESCE(cas.path, ca.source_file_ref, cs.path, c.source_file_ref) AS source_file,
                     COALESCE(ca.source_locator, c.source_locator) AS source_locator,
                     COALESCE(ca.min_value, ca.numeric_value) AS current_min_a,
                     COALESCE(ca.max_value, ca.numeric_value) AS current_max_a,
                     ca.unit AS current_unit,
                     COALESCE(va.numeric_value, va.min_value, va.max_value) AS voltage_v,
                     va.unit AS voltage_unit
              FROM components AS c
              JOIN component_attributes AS ca ON ca.component_id = c.component_id
              JOIN component_attributes AS va ON va.component_id = c.component_id
              LEFT JOIN sources AS cs ON cs.path = c.source_file_ref
              LEFT JOIN sources AS cas ON cas.path = ca.source_file_ref
              WHERE (lower(COALESCE(c.component_type, ''))
                     LIKE '%circuit breaker%' OR lower(COALESCE(c.component_type, ''))
                     LIKE '%contactor%' OR lower(COALESCE(c.component_type, ''))
                     LIKE '%motor protection%')"""
    sql += f""" AND c.record_status IN ({status_marks})
                  AND ca.record_status IN ({status_marks})
                  AND va.record_status IN ({status_marks})
                  AND ca.parameter_key = ? AND va.parameter_key = ?
                  AND upper(trim(ca.unit)) = ? AND upper(trim(va.unit)) = ?
                  AND COALESCE(ca.min_value, ca.numeric_value) <= ?
                  AND COALESCE(ca.max_value, ca.numeric_value) >= ?
                  AND COALESCE(va.numeric_value, va.min_value, va.max_value) >= ?
              ORDER BY c.manufacturer_normalized, c.part_number, ca.attribute_id, va.attribute_id"""
    statuses = tuple(allowed_statuses)
    params = (*statuses, *statuses, *statuses, "rated_current", "rated_voltage", "A", "V",
              estimated_current_a, estimated_current_a, system_voltage_v)
    return connection.execute(sql, params).fetchall()
