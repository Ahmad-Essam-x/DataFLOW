"""
SQL Dialects Module for Workflow-to-SQL Transpilation.
Provides syntax rules, identifier quoting, type mapping, and function mappings
for ANSI SQL, Snowflake, PostgreSQL, DuckDB, BigQuery, and SQLite.
"""
from typing import Dict, Any, Optional, List


class SQLDialect:
    """Base dialect providing standard ANSI SQL behaviors."""
    name: str = "ansi"
    display_name: str = "ANSI SQL (Standard)"
    identifier_quote: str = '"'
    string_quote: str = "'"
    supports_try_cast: bool = False
    supports_ilike: bool = False
    supports_filter_clause: bool = False
    supports_read_csv: bool = False
    supports_star_exclude: bool = False

    TYPE_MAP: Dict[str, str] = {
        "string": "VARCHAR",
        "v_string": "VARCHAR",
        "v_wstring": "VARCHAR",
        "fixeddecimal": "NUMERIC(18, 4)",
        "int16": "SMALLINT",
        "int32": "INTEGER",
        "int64": "BIGINT",
        "float": "REAL",
        "double": "DOUBLE PRECISION",
        "date": "DATE",
        "time": "TIME",
        "datetime": "TIMESTAMP",
        "bool": "BOOLEAN",
        "blob": "BLOB",
    }

    def quote_identifier(self, identifier: str) -> str:
        """Escapes and quotes a column or table identifier."""
        clean = str(identifier).replace(self.identifier_quote, self.identifier_quote * 2)
        return f"{self.identifier_quote}{clean}{self.identifier_quote}"

    def quote_literal(self, val: Any) -> str:
        """Quotes a python string, number, or null literal for SQL."""
        if val is None:
            return "NULL"
        if isinstance(val, bool):
            return "TRUE" if val else "FALSE"
        if isinstance(val, (int, float)):
            return str(val)
        # String escape single quotes
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"

    def cast_type(self, col_name: str, target_type: str, safe: bool = False) -> str:
        """Generates a CAST or TRY_CAST expression."""
        sql_type = self.map_type(target_type)
        ident = self.quote_identifier(col_name) if not (col_name.startswith(self.identifier_quote) and col_name.endswith(self.identifier_quote)) else col_name
        if safe and self.supports_try_cast:
            return f"TRY_CAST({ident} AS {sql_type})"
        return f"CAST({ident} AS {sql_type})"

    def map_type(self, alteryx_type: str) -> str:
        """Maps an Alteryx data type to the dialect's SQL type."""
        key = str(alteryx_type).strip().lower()
        return self.TYPE_MAP.get(key, "VARCHAR")

    def concat_expr(self, parts: List[str]) -> str:
        """Generates string concatenation expression."""
        if not parts:
            return "''"
        if len(parts) == 1:
            return parts[0]
        return " || ".join(parts)

    def current_timestamp_expr(self) -> str:
        return "CURRENT_TIMESTAMP"

    def current_date_expr(self) -> str:
        return "CURRENT_DATE"

    def row_number_expr(self, partition_by: Optional[List[str]] = None, order_by: Optional[str] = None) -> str:
        parts = []
        if partition_by:
            quoted_p = [self.quote_identifier(p) for p in partition_by]
            parts.append(f"PARTITION BY {', '.join(quoted_p)}")
        if order_by:
            parts.append(f"ORDER BY {order_by}")
        else:
            parts.append("ORDER BY (SELECT NULL)")
        return f"ROW_NUMBER() OVER ({' '.join(parts)})"

    def limit_clause(self, limit: int, offset: Optional[int] = None) -> str:
        if offset is not None and offset > 0:
            return f"LIMIT {int(limit)} OFFSET {int(offset)}"
        return f"LIMIT {int(limit)}"


class SnowflakeDialect(SQLDialect):
    name = "snowflake"
    display_name = "Snowflake"
    identifier_quote = '"'
    supports_try_cast = True
    supports_ilike = True

    TYPE_MAP = {
        "string": "VARCHAR",
        "v_string": "VARCHAR",
        "v_wstring": "VARCHAR",
        "fixeddecimal": "NUMBER(18, 4)",
        "int16": "NUMBER(5, 0)",
        "int32": "NUMBER(10, 0)",
        "int64": "NUMBER(38, 0)",
        "float": "FLOAT",
        "double": "FLOAT",
        "date": "DATE",
        "time": "TIME",
        "datetime": "TIMESTAMP_NTZ",
        "bool": "BOOLEAN",
        "blob": "BINARY",
    }

    def current_timestamp_expr(self) -> str:
        return "CURRENT_TIMESTAMP()"

    def current_date_expr(self) -> str:
        return "CURRENT_DATE()"


class PostgresDialect(SQLDialect):
    name = "postgres"
    display_name = "PostgreSQL"
    identifier_quote = '"'
    supports_try_cast = False
    supports_ilike = True
    supports_filter_clause = True

    TYPE_MAP = {
        "string": "VARCHAR",
        "v_string": "VARCHAR",
        "v_wstring": "TEXT",
        "fixeddecimal": "NUMERIC(18, 4)",
        "int16": "SMALLINT",
        "int32": "INTEGER",
        "int64": "BIGINT",
        "float": "REAL",
        "double": "DOUBLE PRECISION",
        "date": "DATE",
        "time": "TIME",
        "datetime": "TIMESTAMP",
        "bool": "BOOLEAN",
        "blob": "BYTEA",
    }


class DuckDBDialect(SQLDialect):
    name = "duckdb"
    display_name = "DuckDB"
    identifier_quote = '"'
    supports_try_cast = True
    supports_ilike = True
    supports_read_csv = True
    supports_star_exclude = True

    TYPE_MAP = {
        "string": "VARCHAR",
        "v_string": "VARCHAR",
        "v_wstring": "VARCHAR",
        "fixeddecimal": "DECIMAL(18, 4)",
        "int16": "SMALLINT",
        "int32": "INTEGER",
        "int64": "BIGINT",
        "float": "FLOAT",
        "double": "DOUBLE",
        "date": "DATE",
        "time": "TIME",
        "datetime": "TIMESTAMP",
        "bool": "BOOLEAN",
        "blob": "BLOB",
    }


class BigQueryDialect(SQLDialect):
    name = "bigquery"
    display_name = "Google BigQuery"
    identifier_quote = '`'
    supports_try_cast = True
    supports_ilike = False

    TYPE_MAP = {
        "string": "STRING",
        "v_string": "STRING",
        "v_wstring": "STRING",
        "fixeddecimal": "NUMERIC",
        "int16": "INT64",
        "int32": "INT64",
        "int64": "INT64",
        "float": "FLOAT64",
        "double": "FLOAT64",
        "date": "DATE",
        "time": "TIME",
        "datetime": "DATETIME",
        "bool": "BOOL",
        "blob": "BYTES",
    }

    def concat_expr(self, parts: List[str]) -> str:
        if not parts:
            return "''"
        if len(parts) == 1:
            return parts[0]
        return f"CONCAT({', '.join(parts)})"

    def current_timestamp_expr(self) -> str:
        return "CURRENT_TIMESTAMP()"

    def current_date_expr(self) -> str:
        return "CURRENT_DATE()"


class SQLiteDialect(SQLDialect):
    name = "sqlite"
    display_name = "SQLite"
    identifier_quote = '"'
    supports_try_cast = False

    TYPE_MAP = {
        "string": "TEXT",
        "v_string": "TEXT",
        "v_wstring": "TEXT",
        "fixeddecimal": "NUMERIC",
        "int16": "INTEGER",
        "int32": "INTEGER",
        "int64": "INTEGER",
        "float": "REAL",
        "double": "REAL",
        "date": "TEXT",
        "time": "TEXT",
        "datetime": "TEXT",
        "bool": "INTEGER",
        "blob": "BLOB",
    }

    def quote_literal(self, val: Any) -> str:
        if val is None:
            return "NULL"
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, (int, float)):
            return str(val)
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"


DIALECT_REGISTRY: Dict[str, SQLDialect] = {
    "ansi": SQLDialect(),
    "snowflake": SnowflakeDialect(),
    "postgres": PostgresDialect(),
    "duckdb": DuckDBDialect(),
    "bigquery": BigQueryDialect(),
    "sqlite": SQLiteDialect(),
}


def get_dialect(name: Optional[str] = None) -> SQLDialect:
    """Returns the dialect instance for the given dialect name or default ANSI."""
    if not name:
        return DIALECT_REGISTRY["ansi"]
    key = str(name).strip().lower()
    return DIALECT_REGISTRY.get(key, DIALECT_REGISTRY["ansi"])
