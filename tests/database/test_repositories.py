"""Contract tests for the read-only extracted engineering database DAL."""

import json
import sqlite3
from pathlib import Path

import pytest

from lv_assist.database.connection import configured_database_path, database_connection
from lv_assist.database.errors import DatabaseConfigurationError, DatabaseConnectionError
from lv_assist.database.repositories import AttributeRepository, ComponentRepository

FIXTURE_SQL = Path(__file__).parents[1] / "fixtures" / "engineering_database.sql"


@pytest.fixture
def sample_database(tmp_path):
    """Create an isolated SQLite database from synthetic, test-only records."""
    database_path = tmp_path / "engineering.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    return database_path


def test_database_connection_is_read_only(sample_database):
    with database_connection(sample_database) as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("UPDATE components SET part_number = ?", ("CHANGED",))
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO components (component_id) VALUES (?)", ("NEW",))

    assert ComponentRepository(sample_database).find_by_part_number("TEST-001") is not None


def test_invalid_database_path_raises_domain_error(tmp_path):
    with pytest.raises(DatabaseConnectionError, match="does not exist"):
        with database_connection(tmp_path / "missing.sqlite"):
            pass


def test_configured_relative_path_resolves_beside_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"database_path": "data/catalog.sqlite"}), encoding="utf-8")

    assert configured_database_path(config_file) == (tmp_path / "data" / "catalog.sqlite").resolve()


def test_missing_config_database_path_is_reported(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"language": "en"}), encoding="utf-8")

    with pytest.raises(DatabaseConfigurationError, match="database_path"):
        configured_database_path(config_file)


def test_preview_search_labels_extracted_and_excludes_unreviewed_states(sample_database):
    repository = ComponentRepository(sample_database)

    candidates = repository.find_components_for_motor(4.0, 400, verified_only=False)
    by_part_number = {candidate.part_number: candidate for candidate in candidates}

    assert set(by_part_number) == {"TEST-001", "TEST-002"}
    assert by_part_number["TEST-001"].record_status == "extracted"
    assert by_part_number["TEST-001"].preview_warning == "⚠️ تأییدنشده - فقط برای پیش‌نمایش"
    assert by_part_number["TEST-001"].estimated_motor_current_a == 8.0
    assert by_part_number["TEST-001"].source_file == "test-catalog.pdf"
    assert by_part_number["TEST-001"].source_locator == "page:1|row:1"
    assert by_part_number["TEST-001"].is_preview_only is True
    assert by_part_number["TEST-001"].is_safety_recommendation is False
    assert by_part_number["TEST-002"].preview_warning is None
    assert by_part_number["TEST-002"].is_preview_only is True


def test_verified_only_search_returns_only_verified_rows(sample_database):
    candidates = ComponentRepository(sample_database).find_components_for_motor(
        4.0, 400, verified_only=True
    )

    assert [candidate.part_number for candidate in candidates] == ["TEST-002"]
    assert all(candidate.record_status == "verified" for candidate in candidates)
    assert all(candidate.is_preview_only is False for candidate in candidates)
    assert all(candidate.is_safety_recommendation is False for candidate in candidates)


def test_part_number_search_is_parameterized(sample_database):
    repository = ComponentRepository(sample_database)

    assert repository.find_by_part_number("' OR 1=1 --") is None
    assert repository.find_by_part_number("TEST-001").source_file == "test-catalog.pdf"


def test_attribute_repository_preserves_none_units_and_provenance(sample_database):
    repository = AttributeRepository(sample_database)

    attributes = repository.find_for_component("C-010")
    current = next(attribute for attribute in attributes if attribute.parameter_key == "rated_current")

    assert current.numeric_value is None
    assert current.min_value is None
    assert current.max_value is None
    assert current.unit == "A"
    assert current.source_file is None
    assert current.source_locator is None


def test_attribute_repository_excludes_unreviewed_and_unverified_owners(sample_database):
    repository = AttributeRepository(sample_database)

    assert repository.find_for_component("C-003") == []
    assert repository.find_for_component("C-001", verified_only=True) == []
    assert all(attribute.record_status == "verified" for attribute in
               repository.find_for_component("C-002", verified_only=True))


def test_motor_preview_does_not_guess_other_voltage_formula(sample_database):
    with pytest.raises(ValueError, match="only for 400 V"):
        ComponentRepository(sample_database).find_components_for_motor(4.0, 415)

