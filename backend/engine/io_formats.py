"""
Unified I/O Formats, Extensions, MIME Types, and Parsers Registry.
Provides a single source of truth for tabular data ingestion, export, and schema detection.
"""
import os
import io
import re
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from backend.engine.excel_reader import fast_read_excel

SUPPORTED_FORMATS: Dict[str, Dict[str, Any]] = {
    "csv": {
        "label": "Comma Delimited (*.csv)",
        "extensions": [".csv", ".txt"],
        "mime": "text/csv",
        "default_delimiter": ",",
        "export_extension": ".csv"
    },
    "tsv": {
        "label": "Tab Delimited (*.tsv)",
        "extensions": [".tsv", ".tab"],
        "mime": "text/tab-separated-values",
        "default_delimiter": "\t",
        "export_extension": ".tsv"
    },
    "excel": {
        "label": "Excel Workbook (*.xlsx)",
        "extensions": [".xlsx", ".xls", ".xlsm", ".xlsb"],
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "default_delimiter": None,
        "export_extension": ".xlsx"
    },
    "parquet": {
        "label": "Apache Parquet (*.parquet, *.pq)",
        "extensions": [".parquet", ".pq"],
        "mime": "application/octet-stream",
        "default_delimiter": None,
        "export_extension": ".parquet"
    },
    "json": {
        "label": "JSON / JSON Lines (*.json, *.jsonl)",
        "extensions": [".json", ".jsonl", ".ndjson"],
        "mime": "application/json",
        "default_delimiter": None,
        "export_extension": ".json"
    }
}


def detect_format(filepath_or_name: str) -> str:
    """
    Infers data format identifier ('csv', 'tsv', 'excel', 'parquet', 'json')
    from file extension. Defaults to 'csv' if unknown.
    """
    if not filepath_or_name:
        return "csv"
    ext = os.path.splitext(filepath_or_name.lower().strip())[1]
    for fmt_name, meta in SUPPORTED_FORMATS.items():
        if ext in meta["extensions"]:
            return fmt_name
    return "csv"


def get_format_mime(fmt: str) -> str:
    """Returns the MIME type string for a given format key."""
    fmt_key = (fmt or "csv").lower()
    if fmt_key in ["xlsx", "excel"]:
        fmt_key = "excel"
    elif fmt_key in ["tab", "tsv"]:
        fmt_key = "tsv"
    return SUPPORTED_FORMATS.get(fmt_key, SUPPORTED_FORMATS["csv"])["mime"]


def get_format_extension(fmt: str) -> str:
    """Returns the standard file extension (including dot) for a format key."""
    fmt_key = (fmt or "csv").lower()
    if fmt_key in ["xlsx", "excel"]:
        fmt_key = "excel"
    elif fmt_key in ["tab", "tsv"]:
        fmt_key = "tsv"
    return SUPPORTED_FORMATS.get(fmt_key, SUPPORTED_FORMATS["csv"])["export_extension"]


def filter_dataframe_by_search(df: pd.DataFrame, search: str) -> pd.DataFrame:
    """
    Performs vectorized substring search matching across all columns.
    Returns filtered subset of DataFrame.
    """
    if df is None or df.empty or not search or not search.strip():
        return df

    s = search.strip().lower()
    masks = []
    for c in df.columns:
        series = df[c]
        try:
            if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
                masks.append(series.astype(str).str.lower().str.contains(s, regex=False, na=False))
            elif pd.api.types.is_numeric_dtype(series):
                masks.append(series.astype(str).str.contains(s, regex=False, na=False))
        except Exception:
            pass

    if masks:
        mask = np.logical_or.reduce(masks)
        return df[mask]
    return df.iloc[0:0]


def read_tabular_file(
    filepath: str,
    format_hint: Optional[str] = None,
    delimiter: Optional[str] = None,
    encoding: str = "utf-8",
    header: Optional[int] = 0,
    max_rows: Optional[int] = None,
    skiprows: Optional[int] = None,
    quote_char: Optional[str] = '"',
    escape_char: Optional[str] = None,
    on_bad_lines: str = "error",
    sheet_name: Any = 0,
    read_all_sheets: bool = False,
    trim_headers: bool = True
) -> pd.DataFrame:
    """
    Robust reader for CSV, TSV, Excel, Parquet, and JSON files with automatic
    encoding fallbacks and JSON Lines detection.
    """
    fmt = (format_hint or detect_format(filepath)).lower()
    if fmt in ["xlsx", "xls"]:
        fmt = "excel"

    if fmt == "excel":
        is_all_sheets = read_all_sheets or str(sheet_name).strip() in ["*", "all", "ALL", "__all__"]
        if is_all_sheets:
            sheets_dict = fast_read_excel(
                filepath,
                sheet_name=None,
                header=header,
                skiprows=skiprows,
                nrows=max_rows,
                trim_headers=trim_headers
            )
            sheet_dfs = []
            if isinstance(sheets_dict, dict):
                for s_name, s_df in sheets_dict.items():
                    if s_df is not None and not s_df.empty:
                        s_df["SheetName"] = str(s_name)
                        sheet_dfs.append(s_df)
            elif isinstance(sheets_dict, pd.DataFrame):
                sheet_dfs.append(sheets_dict)
            df = pd.concat(sheet_dfs, ignore_index=True) if sheet_dfs else pd.DataFrame()
        else:
            df = fast_read_excel(
                filepath,
                sheet_name=sheet_name,
                header=header,
                skiprows=skiprows,
                nrows=max_rows,
                trim_headers=trim_headers
            )
            if isinstance(df, dict):
                df = next(iter(df.values())) if df else pd.DataFrame()

    elif fmt == "parquet":
        df = pd.read_parquet(filepath)
        if max_rows and len(df) > max_rows:
            df = df.iloc[:max_rows]

    elif fmt == "json":
        ext = os.path.splitext(filepath)[1].lower()
        is_lines = ext in [".jsonl", ".ndjson"]
        try:
            df = pd.read_json(filepath, lines=is_lines)
        except Exception:
            # Fallback attempt with opposite lines mode
            try:
                df = pd.read_json(filepath, lines=not is_lines)
            except Exception:
                # Fallback to standard python json load in case orientation is records
                import json
                with open(filepath, "r", encoding=encoding, errors="replace") as jf:
                    data = json.load(jf)
                df = pd.DataFrame(data)

        if max_rows and len(df) > max_rows:
            df = df.iloc[:max_rows]

    else:  # CSV or TSV
        sep = delimiter
        if not sep:
            sep = "\t" if fmt == "tsv" else ","
        elif sep in ["\\t", "tab"]:
            sep = "\t"
        elif sep in ["pipe", "\\|"]:
            sep = "|"
        elif sep == "semicolon":
            sep = ";"

        csv_kwargs: Dict[str, Any] = {
            "sep": sep,
            "encoding": encoding,
            "header": header,
            "nrows": max_rows,
            "skiprows": skiprows
        }
        if quote_char and quote_char not in ["none", "None"]:
            csv_kwargs["quotechar"] = quote_char
        if escape_char and escape_char not in ["none", "None"]:
            csv_kwargs["escapechar"] = escape_char
        if on_bad_lines in ["skip", "warn"]:
            csv_kwargs["on_bad_lines"] = "skip"

        try:
            df = pd.read_csv(filepath, **csv_kwargs)
        except UnicodeDecodeError:
            csv_kwargs["encoding"] = "latin1"
            df = pd.read_csv(filepath, **csv_kwargs)
        except Exception as e:
            # Fallback with python engine
            try:
                csv_kwargs["engine"] = "python"
                df = pd.read_csv(filepath, **csv_kwargs)
            except Exception:
                raise e

    if df is not None:
        df.columns = [str(c) for c in df.columns]
        if trim_headers:
            df.columns = [c.strip() for c in df.columns]

    return df if df is not None else pd.DataFrame()


def export_dataframe_to_stream(
    df: pd.DataFrame,
    fmt: str = "csv",
    delimiter: str = ",",
    include_index: bool = False,
    sheet_name: str = "Export"
) -> Tuple[io.BytesIO, str, str]:
    """
    Exports a DataFrame into an in-memory BytesIO stream according to the specified format.
    Returns: (BytesIO_stream, mime_type, file_extension)
    """
    fmt_clean = (fmt or "csv").lower()
    if fmt_clean in ["xlsx", "excel"]:
        fmt_clean = "excel"
    elif fmt_clean in ["tab", "tsv"]:
        fmt_clean = "tsv"

    if fmt_clean == "excel":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=include_index, sheet_name=sheet_name or "Export")
        output.seek(0)
        return output, SUPPORTED_FORMATS["excel"]["mime"], ".xlsx"

    elif fmt_clean == "parquet":
        output = io.BytesIO()
        df.to_parquet(output, index=include_index)
        output.seek(0)
        return output, SUPPORTED_FORMATS["parquet"]["mime"], ".parquet"

    elif fmt_clean == "tsv":
        output = io.StringIO()
        df.to_csv(output, index=include_index, sep="\t", encoding="utf-8")
        mem = io.BytesIO(output.getvalue().encode("utf-8"))
        mem.seek(0)
        return mem, SUPPORTED_FORMATS["tsv"]["mime"], ".tsv"

    elif fmt_clean == "json":
        json_str = df.to_json(orient="records", indent=2)
        mem = io.BytesIO((json_str or "[]").encode("utf-8"))
        mem.seek(0)
        return mem, SUPPORTED_FORMATS["json"]["mime"], ".json"

    else:  # CSV default
        delim = delimiter or ","
        if delim in ["\\t", "tab"]:
            delim = "\t"
        elif delim in ["pipe", "\\|"]:
            delim = "|"
        elif delim == "semicolon":
            delim = ";"

        output = io.StringIO()
        df.to_csv(output, index=include_index, sep=delim, encoding="utf-8")
        mem = io.BytesIO(output.getvalue().encode("utf-8"))
        mem.seek(0)
        return mem, SUPPORTED_FORMATS["csv"]["mime"], ".csv"
