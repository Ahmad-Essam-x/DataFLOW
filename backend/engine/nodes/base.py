import os
import re
import ast
import io
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

class NodeExecutionError(Exception):
    pass


def sanitize_dataframe(df: Any) -> Any:
    """
    Ensures dataframe columns are clean, unique strings, and flattens MultiIndex if present.
    Prevents duplicate column names that cause AttributeError/TypeError downstream or in serialization.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return df

    # If MultiIndex columns, flatten them
    if isinstance(df.columns, pd.MultiIndex):
        flat_cols = []
        for col_tuple in df.columns:
            parts = [str(p) for p in col_tuple if p is not None and str(p).strip()]
            flat_cols.append("_".join(parts) if parts else "col")
        df = df.copy(deep=False)
        df.columns = flat_cols

    # Convert all columns to strings and ensure uniqueness
    cols = [str(c) if c is not None else "Unnamed" for c in df.columns]
    seen = {}
    unique_cols = []
    for c in cols:
        if c not in seen:
            seen[c] = 1
            unique_cols.append(c)
        else:
            seen[c] += 1
            unique_cols.append(f"{c}_{seen[c]}")

    attrs = getattr(df, "attrs", {}).copy() if hasattr(df, "attrs") else {}
    if list(df.columns) != unique_cols:
        df = df.copy(deep=False)
        df.columns = unique_cols
    if attrs:
        df.attrs = attrs

    return df


_DATE_PAT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_PAT = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?")


def infer_alteryx_type(series: pd.Series) -> str:
    """
    Returns an intuitive, Alteryx-standard data type name for any pandas series.
    Translates cryptic internal representations like 'object' into 'String',
    'int64' into 'Int64', 'float64' into 'Double', etc., and inspects
    object/string series to detect Dates, Booleans, or Numeric values.
    """
    if series is None:
        return "String"

    import datetime

    # Direct pandas/numpy dtype checks
    if pd.api.types.is_bool_dtype(series):
        return "Bool"
    elif pd.api.types.is_integer_dtype(series):
        dtype_name = str(series.dtype).lower()
        if "int64" in dtype_name:
            return "Int64"
        elif "int32" in dtype_name:
            return "Int32"
        elif "int16" in dtype_name:
            return "Int16"
        elif "int8" in dtype_name or "byte" in dtype_name:
            return "Byte"
        return "Int64"
    elif pd.api.types.is_float_dtype(series):
        dtype_name = str(series.dtype).lower()
        if "float32" in dtype_name:
            return "Float"
        return "Double"
    elif pd.api.types.is_datetime64_any_dtype(series):
        try:
            non_null = series.dropna()
            if not non_null.empty and hasattr(non_null.dt, "time"):
                # If all times are midnight 00:00:00, represent as Date
                if (non_null.dt.time == datetime.time(0, 0, 0)).all():
                    return "Date"
        except Exception:
            pass
        return "DateTime"
    elif pd.api.types.is_timedelta64_dtype(series):
        return "Time"

    # Object / String / Categorical columns: inspect non-null sample
    non_null = series.dropna()
    if non_null.empty:
        return "String"

    sample = non_null.head(100)
    str_sample = sample.astype(str).str.strip()

    # 1. Check for boolean values
    sample_lower = str_sample.str.lower()
    if sample_lower.isin({"true", "false", "yes", "no", "t", "f"}).all():
        return "Bool"

    # 2. Check for integer
    try:
        # Avoid treating numbers with leading zeros (e.g. zip codes '01234') as int
        has_leading_zero = str_sample.apply(lambda s: len(s) > 1 and s.startswith("0") and not s.startswith("0.")).any()
        if not has_leading_zero:
            int_converted = pd.to_numeric(sample, errors="raise")
            if (int_converted % 1 == 0).all():
                max_val = int_converted.max()
                min_val = int_converted.min()
                if -32768 <= min_val and max_val <= 32767:
                    return "Int16"
                elif -2147483648 <= min_val and max_val <= 2147483647:
                    return "Int32"
                return "Int64"
    except Exception:
        pass

    # 3. Check for float / decimal
    try:
        pd.to_numeric(sample, errors="raise")
        return "Double"
    except Exception:
        pass

    # 4. Check for Date / DateTime formats
    if str_sample.apply(lambda s: bool(_DATE_PAT.match(s))).all():
        return "Date"
    if str_sample.apply(lambda s: bool(_DATETIME_PAT.match(s))).all():
        return "DateTime"

    return "String"


def map_alteryx_to_category(alteryx_type: str) -> str:
    """Maps an Alteryx type name to a UI category ('numeric', 'datetime', 'boolean', 'string')."""
    t = (alteryx_type or "String").strip()
    if t in ("Int64", "Int32", "Int16", "Byte", "Double", "Float", "FixedDecimal", "Integer"):
        return "numeric"
    elif t in ("Date", "DateTime", "Time"):
        return "datetime"
    elif t == "Bool":
        return "boolean"
    return "string"


# ----------------------------------------------------------------------
# Base Node
# ----------------------------------------------------------------------
class BaseNode:
    type_name: str = "base"
    category: str = "general"
    display_name: str = "Base Node"
    description: str = "Base node interface"
    input_ports: List[str] = ["I"]
    output_ports: List[str] = ["O"]

    def __init__(self, node_id: str, config: Dict[str, Any]):
        self.node_id = node_id
        self.config = config or {}
        self.messages = []

    def get_single_input(self, inputs: Dict[str, Any], port: str = "I") -> pd.DataFrame:
        df = inputs.get(port)
        if df is None:
            name = getattr(self, "display_name", self.type_name)
            raise NodeExecutionError(f"{name}: No input connected.")
        return df

    def execute(self, inputs: Dict[str, pd.DataFrame], context: Optional[Dict[str, Any]] = None) -> Dict[str, pd.DataFrame]:
        """
        inputs: dict mapping input_port_name -> pd.DataFrame (or list of DataFrames for multi-inputs like Union)
        context: shared execution context (e.g. data_dir, output_dir, session_id)
        returns: dict mapping output_port_name -> pd.DataFrame
        """
        raise NotImplementedError



