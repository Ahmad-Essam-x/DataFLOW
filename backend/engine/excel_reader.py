"""
High-Performance, Resilient Excel Ingestion Engine.
Supports .xlsx, .xlsm, .xlsb, and .xls formats with multi-tiered acceleration:
1. Fast Rust-powered Calamine engine (8x-30x speedup, tiny memory footprint).
2. Streaming OpenPyXL (read_only=True, data_only=True).
3. Standard DOM OpenPyXL fallback.
4. Automatic disguised CSV/TSV text recovery.

Also provides resilient sheet name matching (case/whitespace tolerance,
default sheet resolution) and instant metadata/row-counting without
redundant full-file DataFrame parsing.
"""

import os
import io
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import python_calamine
    from python_calamine import CalamineWorkbook
    HAS_CALAMINE = True
except ImportError:
    HAS_CALAMINE = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


def is_excel_file(fpath: str) -> bool:
    """Checks whether the file path has an Excel workbook extension."""
    ext = os.path.splitext(fpath)[1].lower()
    return ext in [".xlsx", ".xlsm", ".xlsb", ".xls"]


def get_excel_sheet_names(fpath: str) -> List[str]:
    """
    Safely and rapidly extracts worksheet names from an Excel workbook
    without loading sheet data into memory.
    Guarantees that file handles on Windows are promptly closed.
    """
    if not os.path.exists(fpath):
        return []

    # Strategy 1: Calamine (Rust, sub-millisecond)
    if HAS_CALAMINE:
        try:
            with CalamineWorkbook.from_path(fpath) as wb:
                return list(wb.sheet_names)
        except Exception as e:
            logger.debug(f"Calamine sheet inspection failed for {fpath}: {e}")

    # Strategy 2: Openpyxl read-only (for .xlsx and .xlsm)
    ext = os.path.splitext(fpath)[1].lower()
    if HAS_OPENPYXL and ext in [".xlsx", ".xlsm"]:
        try:
            wb = openpyxl.load_workbook(fpath, read_only=True, keep_links=False)
            names = list(wb.sheetnames)
            wb.close()
            return names
        except Exception as e:
            logger.debug(f"Openpyxl sheet inspection failed for {fpath}: {e}")

    # Strategy 3: Standard pandas ExcelFile with explicit close
    try:
        with pd.ExcelFile(fpath) as ef:
            return list(ef.sheet_names)
    except Exception as e:
        logger.debug(f"pd.ExcelFile sheet inspection failed for {fpath}: {e}")

    return []


def resolve_sheet_name(requested_sheet: Any, available_sheets: List[str]) -> Tuple[Any, Optional[str]]:
    """
    Resiliently resolves a requested sheet name or index against the actual
    worksheet names in a workbook.

    Returns:
        (resolved_sheet_key, error_message)
        If successful, error_message is None.
        If requested_sheet requests all sheets ('*' or '__all__'), returns (None, None).
    """
    if not available_sheets:
        # Default fallback if workbook has no sheet metadata
        return 0, None

    # Check for all sheets request
    str_req = str(requested_sheet).strip() if requested_sheet is not None else ""
    if str_req in ["*", "all", "ALL", "__all__"]:
        return None, None

    # Check for default sheet tokens (empty string, None, 0, "0", "default", "none")
    if (
        requested_sheet is None
        or requested_sheet == ""
        or requested_sheet == 0
        or str_req in ["0", "default", "none", "First Sheet (Default)"]
    ):
        return available_sheets[0], None

    # Exact match (original type or string)
    if requested_sheet in available_sheets:
        return requested_sheet, None
    if str_req in available_sheets:
        return str_req, None

    # Whitespace-tolerant match (e.g. workbook sheet has trailing space 'Sheet1 ')
    for s in available_sheets:
        if s.strip() == str_req:
            return s, None

    # Case-insensitive match (e.g. 'sheet1' matches 'Sheet1')
    str_req_lower = str_req.lower()
    for s in available_sheets:
        if s.strip().lower() == str_req_lower:
            return s, None

    # Numeric index match (user passed 1 or "1" for first sheet, or 0-based)
    if isinstance(requested_sheet, int) or str_req.isdigit():
        idx = int(requested_sheet) if isinstance(requested_sheet, int) else int(str_req)
        # Check 0-based index
        if 0 <= idx < len(available_sheets):
            return available_sheets[idx], None
        # Check 1-based index
        if 1 <= idx <= len(available_sheets):
            return available_sheets[idx - 1], None

    # Sheet not found
    sheets_display = ", ".join(repr(s) for s in available_sheets)
    return None, f"Sheet '{requested_sheet}' not found in workbook. Available sheets: [{sheets_display}]"


def get_excel_row_count(fpath: str, sheet_name: Any = 0, has_header: bool = True) -> int:
    """
    Rapidly calculates the row count of a worksheet without loading the entire
    sheet into a pandas DataFrame.
    """
    if not os.path.exists(fpath):
        return 0

    available_sheets = get_excel_sheet_names(fpath)
    target_sheet, _ = resolve_sheet_name(sheet_name, available_sheets)

    # Method 1: Calamine sheet height (instant metadata check)
    if HAS_CALAMINE:
        try:
            with CalamineWorkbook.from_path(fpath) as wb:
                s_name = str(target_sheet)
                if s_name in wb.sheet_names:
                    sheet = wb.get_sheet_by_name(s_name)
                    total_rows = sheet.height
                    data_rows = max(0, total_rows - (1 if has_header else 0))
                    return data_rows
        except Exception:
            pass

    # Method 2: Openpyxl read-only max_row
    ext = os.path.splitext(fpath)[1].lower()
    if HAS_OPENPYXL and ext in [".xlsx", ".xlsm"]:
        try:
            wb = openpyxl.load_workbook(fpath, read_only=True, keep_links=False)
            sheet_obj = None
            if target_sheet in wb.sheetnames:
                sheet_obj = wb[target_sheet]
            elif wb.sheetnames:
                sheet_obj = wb[wb.sheetnames[0]]

            if sheet_obj is not None:
                max_row = sheet_obj.max_row
                wb.close()
                if max_row is not None and max_row > 0:
                    return max(0, max_row - (1 if has_header else 0))
            else:
                wb.close()
        except Exception:
            pass

    # Method 3: Lightweight preview fallback
    try:
        df_sample = pd.read_excel(fpath, sheet_name=target_sheet or 0, nrows=100)
        return len(df_sample)
    except Exception:
        return 0


def fast_read_excel(
    fpath: str,
    sheet_name: Any = 0,
    header: Optional[int] = 0,
    skiprows: Optional[Union[int, List[int]]] = None,
    nrows: Optional[int] = None,
    trim_headers: bool = True,
    **kwargs
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Reads an Excel file using the fastest and most resilient available engine.
    Tiers:
    1. Calamine (Rust, 8x-30x faster, parses .xlsx, .xlsm, .xlsb, .xls)
    2. OpenPyXL read_only=True, data_only=True (streaming iterparse)
    3. OpenPyXL standard DOM (data_only=True)
    4. Disguised plain-text CSV/TSV recovery if file is not binary zip
    """
    available_sheets = get_excel_sheet_names(fpath)

    # Determine if requesting all sheets
    is_all_sheets = sheet_name is None or str(sheet_name).strip() in ["*", "all", "ALL", "__all__"]

    if not is_all_sheets:
        target_sheet, err = resolve_sheet_name(sheet_name, available_sheets)
        if err:
            raise ValueError(err)
    else:
        target_sheet = None

    read_kwargs: Dict[str, Any] = {
        "header": header,
        "nrows": nrows
    }
    if skiprows is not None and skiprows > 0:
        read_kwargs["skiprows"] = skiprows

    last_error: Optional[Exception] = None

    # Tier 1: Calamine Engine
    if HAS_CALAMINE:
        try:
            result = pd.read_excel(
                fpath,
                sheet_name=target_sheet,
                engine="calamine",
                **read_kwargs
            )
            return _postprocess_excel_df(result, trim_headers)
        except Exception as e:
            last_error = e
            logger.debug(f"Tier 1 Calamine failed on '{fpath}': {e}")

    # Tier 2: OpenPyXL Streaming (read_only=True, data_only=True)
    ext = os.path.splitext(fpath)[1].lower()
    if HAS_OPENPYXL and ext in [".xlsx", ".xlsm"]:
        try:
            result = pd.read_excel(
                fpath,
                sheet_name=target_sheet,
                engine="openpyxl",
                engine_kwargs={"data_only": True, "read_only": True},
                **read_kwargs
            )
            return _postprocess_excel_df(result, trim_headers)
        except Exception as e:
            last_error = e
            logger.debug(f"Tier 2 OpenPyXL read_only failed on '{fpath}': {e}")

    # Tier 3: OpenPyXL Standard DOM (data_only=True)
    if HAS_OPENPYXL and ext in [".xlsx", ".xlsm"]:
        try:
            result = pd.read_excel(
                fpath,
                sheet_name=target_sheet,
                engine="openpyxl",
                engine_kwargs={"data_only": True},
                **read_kwargs
            )
            return _postprocess_excel_df(result, trim_headers)
        except Exception as e:
            last_error = e
            logger.debug(f"Tier 3 OpenPyXL DOM failed on '{fpath}': {e}")

    # Tier 4: Default pandas read_excel fallback
    try:
        result = pd.read_excel(
            fpath,
            sheet_name=target_sheet,
            **read_kwargs
        )
        return _postprocess_excel_df(result, trim_headers)
    except Exception as e:
        last_error = e
        logger.debug(f"Default pd.read_excel failed on '{fpath}': {e}")

    # Tier 5: Disguised Plain-Text CSV / TSV / HTML detection
    # Common when export tools name a CSV or TSV file with a '.xlsx' extension
    try:
        if os.path.exists(fpath):
            with open(fpath, "rb") as f_head:
                header_bytes = f_head.read(2048)
            # Check if file is NOT a zip (PK..) or Compound Binary (0xD0CF..)
            if not header_bytes.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
                text_sample = header_bytes.decode("utf-8", errors="ignore")
                sep = "\t" if "\t" in text_sample and text_sample.count("\t") > text_sample.count(",") else ","
                csv_kwargs = {
                    "sep": sep,
                    "header": header,
                    "nrows": nrows
                }
                if skiprows is not None and skiprows > 0:
                    csv_kwargs["skiprows"] = skiprows
                df_csv = pd.read_csv(fpath, **csv_kwargs)
                return _postprocess_excel_df(df_csv, trim_headers)
    except Exception:
        pass

    # If all tiers fail, raise the informative error
    raise ValueError(f"Failed to read Excel file '{os.path.basename(fpath)}': {last_error or 'Unknown parsing error'}")


def _postprocess_excel_df(
    result: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    trim_headers: bool
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """Sanitizes columns and trims headers for single or multi-sheet DataFrames."""
    if isinstance(result, dict):
        cleaned_dict = {}
        for s_name, s_df in result.items():
            if s_df is not None and isinstance(s_df, pd.DataFrame):
                s_df.columns = [str(c) for c in s_df.columns]
                if trim_headers:
                    s_df.columns = [c.strip() for c in s_df.columns]
                cleaned_dict[s_name] = s_df
        return cleaned_dict
    elif isinstance(result, pd.DataFrame):
        result.columns = [str(c) for c in result.columns]
        if trim_headers:
            result.columns = [c.strip() for c in result.columns]
        return result
    return result
