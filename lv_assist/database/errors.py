"""Domain exceptions raised by the extracted-database access layer."""


class DatabaseError(Exception):
    """Base exception for configuration, connection, schema, or query failures."""


class DatabaseConfigurationError(DatabaseError):
    """The configured database path is missing or invalid."""


class DatabaseConnectionError(DatabaseError):
    """The read-only SQLite database cannot be opened."""


class DatabaseSchemaError(DatabaseError):
    """The database does not contain the tables and columns required by the DAL."""


class DatabaseQueryError(DatabaseError):
    """SQLite rejected a read operation against the engineering database."""
