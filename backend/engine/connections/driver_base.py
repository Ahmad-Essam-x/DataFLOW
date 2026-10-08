"""Abstract base class all database drivers must implement."""
from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd


class BaseDriver(ABC):

    @abstractmethod
    def test(self) -> bool:
        """Returns True if a connection can be established."""

    @abstractmethod
    def list_tables(self) -> List[str]:
        """Returns table/view names available in the target database or schema."""

    @abstractmethod
    def read_query(self, sql: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Execute a SQL SELECT and return results as a DataFrame.
        When limit is provided, cap results without loading the full result set.
        """

    @abstractmethod
    def write_dataframe(self, df: pd.DataFrame, table: str, if_exists: str = "append") -> int:
        """
        Write a DataFrame to a table.
        if_exists: 'append' | 'replace' | 'fail'
        Returns the number of rows written.
        """

    def read_table(self, table: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Convenience wrapper: SELECT * FROM table with optional LIMIT."""
        q = f'SELECT * FROM "{table}"'
        if limit:
            q += f" LIMIT {limit}"
        return self.read_query(q)
