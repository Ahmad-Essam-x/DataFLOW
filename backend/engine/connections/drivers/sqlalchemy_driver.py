"""SQLAlchemy driver for PostgreSQL and Snowflake."""
from typing import Dict, Any, List, Optional
import pandas as pd

from ..driver_base import BaseDriver

_URL_TEMPLATES: Dict[str, str] = {
    "postgresql": "postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}",
    "snowflake":  "snowflake://{username}:{password}@{account}/{database}/{schema_name}",
}


class SQLAlchemyDriver(BaseDriver):

    def __init__(self, conn: Dict[str, Any], password: Optional[str] = None):
        self._conn = conn
        self._password = password or ""
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine

        from sqlalchemy import create_engine

        conn_type = self._conn.get("type", "").lower()
        tmpl = _URL_TEMPLATES.get(conn_type)
        if not tmpl:
            raise ValueError(f"No URL template for connection type '{conn_type}'.")

        params = {
            "username":    self._conn.get("username", ""),
            "password":    self._password,
            "host":        self._conn.get("host", "localhost"),
            "port":        self._conn.get("port", 5432),
            "database":    self._conn.get("database", ""),
            "account":     self._conn.get("account", ""),
            "schema_name": self._conn.get("schema_name", "public"),
        }

        url = tmpl.format(**params)
        connect_args: Dict[str, Any] = {}
        if conn_type == "snowflake":
            connect_args["connect_timeout"] = 15

        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        return self._engine

    def test(self) -> bool:
        try:
            from sqlalchemy import text
            with self._get_engine().connect() as con:
                con.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def list_tables(self) -> List[str]:
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(self._get_engine())
        schema = self._conn.get("schema_name") or None
        try:
            tables = inspector.get_table_names(schema=schema)
            views = inspector.get_view_names(schema=schema)
            return sorted(tables + views)
        except Exception:
            return sorted(inspector.get_table_names())

    def read_query(self, sql: str, limit: Optional[int] = None) -> pd.DataFrame:
        q = f"SELECT * FROM ({sql}) AS _sub LIMIT {limit}" if limit else sql
        return pd.read_sql(q, self._get_engine())

    def write_dataframe(self, df: pd.DataFrame, table: str, if_exists: str = "append") -> int:
        df.to_sql(table, self._get_engine(), if_exists=if_exists, index=False, chunksize=1000)
        return len(df)
