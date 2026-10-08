"""SQLite driver — file-based or in-memory SQLite databases (stdlib sqlite3)."""
import sqlite3
from typing import List, Optional
import pandas as pd

from ..driver_base import BaseDriver


class SQLiteDriver(BaseDriver):

    def __init__(self, file_path: str = ":memory:"):
        self._file_path = file_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._file_path)

    def test(self) -> bool:
        try:
            con = self._connect()
            con.execute("SELECT 1")
            con.close()
            return True
        except Exception:
            return False

    def list_tables(self) -> List[str]:
        con = self._connect()
        try:
            cur = con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
            )
            return [r[0] for r in cur.fetchall()]
        finally:
            con.close()

    def read_query(self, sql: str, limit: Optional[int] = None) -> pd.DataFrame:
        con = self._connect()
        try:
            q = f"SELECT * FROM ({sql}) AS _sub LIMIT {limit}" if limit else sql
            return pd.read_sql_query(q, con)
        finally:
            con.close()

    def write_dataframe(self, df: pd.DataFrame, table: str, if_exists: str = "append") -> int:
        con = self._connect()
        try:
            df.to_sql(table, con, if_exists=if_exists, index=False)
            return len(df)
        finally:
            con.close()
