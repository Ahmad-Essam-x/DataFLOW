"""DuckDB driver — file-based or in-memory DuckDB databases."""
from typing import List, Optional
import pandas as pd

from ..driver_base import BaseDriver


class DuckDBDriver(BaseDriver):

    def __init__(self, file_path: str = ":memory:"):
        self._file_path = file_path

    def _connect(self):
        import duckdb
        return duckdb.connect(self._file_path)

    def test(self) -> bool:
        try:
            con = self._connect()
            con.execute("SELECT 1").fetchone()
            con.close()
            return True
        except Exception:
            return False

    def list_tables(self) -> List[str]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            con.close()

    def read_query(self, sql: str, limit: Optional[int] = None) -> pd.DataFrame:
        con = self._connect()
        try:
            q = f"SELECT * FROM ({sql}) AS _sub LIMIT {limit}" if limit else sql
            return con.execute(q).df()
        finally:
            con.close()

    def write_dataframe(self, df: pd.DataFrame, table: str, if_exists: str = "append") -> int:
        con = self._connect()
        try:
            if if_exists == "replace":
                con.execute(f'DROP TABLE IF EXISTS "{table}"')
                con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM df')
            elif if_exists == "append":
                try:
                    con.execute(f'INSERT INTO "{table}" SELECT * FROM df')
                except Exception:
                    con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM df')
            else:
                con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM df')
            return len(df)
        finally:
            con.close()
