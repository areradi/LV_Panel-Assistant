"""Read-only SQLite connection management for the extracted engineering data."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from lv_assist.database.errors import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseSchemaError,
)
from lv_assist.paths import config_file_path

PathLike = str | Path

_REQUIRED_COLUMNS = {
    "components": {"component_id", "manufacturer_normalized", "family", "part_number",
                    "component_type", "record_status", "source_file_ref", "source_locator"},
    "component_attributes": {"attribute_id", "component_id", "parameter_key", "raw_value",
                              "normalized_value", "numeric_value", "unit", "min_value",
                              "max_value", "record_status", "source_file_ref", "source_locator"},
    "sources": {"path"},
}


def configured_database_path(config_path: PathLike | None = None) -> Path:
    """Read and resolve ``database_path`` relative to the selected config file."""
    config_file = Path(config_path or config_file_path()).expanduser().resolve()
    try:
        with config_file.open("r", encoding="utf-8") as stream:
            config = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseConfigurationError(f"Cannot read database configuration: {config_file}") from exc
    if not isinstance(config, dict) or not isinstance(config.get("database_path"), str):
        raise DatabaseConfigurationError(
            f"config.json must define a string database_path: {config_file}"
        )

    configured_path = Path(config["database_path"]).expanduser()
    if not configured_path.is_absolute():
        configured_path = config_file.parent / configured_path
    return configured_path.resolve()


def _validate_schema(connection: sqlite3.Connection, database_path: Path) -> None:
    """Reject a database whose required tables or columns do not match the DAL."""
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
    )}
    for table, required_columns in _REQUIRED_COLUMNS.items():
        if table not in tables:
            raise DatabaseSchemaError(f"Missing table '{table}' in {database_path}")
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        missing = required_columns - columns
        if missing:
            names = ", ".join(sorted(missing))
            raise DatabaseSchemaError(f"Missing columns in '{table}': {names}")


@contextmanager
def database_connection(database_path: PathLike | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a query-only SQLite connection and always close it on exit.

    When no path is supplied, the path is read from ``config.json``. Relative
    configured paths are resolved beside that configuration file. URI mode and
    ``query_only`` both prevent repository callers from mutating the source.
    """
    path = Path(database_path).expanduser().resolve() if database_path is not None else configured_database_path()
    if not path.is_file():
        raise DatabaseConnectionError(f"Engineering database does not exist: {path}")

    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        _validate_schema(connection, path)
        yield connection
    except (DatabaseSchemaError, DatabaseConnectionError, DatabaseQueryError):
        raise
    except sqlite3.Error as exc:
        raise DatabaseQueryError(f"SQLite read failed for {path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
