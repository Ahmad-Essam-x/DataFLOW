import os
import re
import ast
import io
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from .base import BaseNode, NodeExecutionError, sanitize_dataframe
from backend.engine.security import is_safe_path, validate_safe_path, sanitize_file_basename, SecurityError
from backend.engine.excel_reader import fast_read_excel, resolve_sheet_name, get_excel_sheet_names
from backend.engine.io_formats import detect_format, read_tabular_file, SUPPORTED_FORMATS

class InputDataNode(BaseNode):
    type_name = "input_data"
    category = "in_out"
    display_name = "Input Data"
    description = "Ingest data from CSV, TSV, Excel, JSON, or Parquet files"
    input_ports = []
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, pd.DataFrame]:
        self.messages = []
        context = context or {}
        source_type = self.config.get("source_type", "file")
        if source_type == "inline" and "data" in self.config:
            raw_data = self.config.get("data")
            df = pd.DataFrame(raw_data)
            df.columns = [str(c) for c in df.columns]
            return {"O": df}

        if source_type == "database":
            import backend.extensions as _ext
            if _ext.connection_manager is None:
                raise NodeExecutionError("Input Data: Connection manager not initialized.")
            conn_id = self.config.get("connection_id", "").strip()
            if not conn_id:
                raise NodeExecutionError("Input Data: No connection_id configured.")
            query = self.config.get("query", "").strip()
            table = self.config.get("table", "").strip()
            if not query and not table:
                raise NodeExecutionError("Input Data: Either 'query' or 'table' must be configured.")
            if not query:
                query = f'SELECT * FROM "{table}"'
            max_rows_db = self.config.get("max_rows")
            if max_rows_db and str(max_rows_db).isdigit():
                max_rows_db = int(max_rows_db)
            else:
                max_rows_db = None
            try:
                driver = _ext.connection_manager.get_driver(conn_id)
                df = driver.read_query(query, limit=max_rows_db)
            except Exception as exc:
                raise NodeExecutionError(f"Input Data database error: {exc}")
            df.columns = [str(c) for c in df.columns]
            self.messages.append(
                f"Loaded {len(df):,} rows × {len(df.columns)} columns from database connection."
            )
            return {"O": df}

        file_path = self.config.get("file_path", "").strip()
        if not file_path:
            raise NodeExecutionError("Input Data: No file specified.")

        data_dir = context.get("data_dir", "")
        base_dir = context.get("base_dir", "")
        allowed_dirs = [d for d in [data_dir, base_dir] if d]

        # Add user-configured trusted external directories (Settings → Trusted External Data Directories).
        # Read directly from the settings file to avoid import-time coupling.
        try:
            import json as _json
            import backend.extensions as _ext_io
            _settings_file = getattr(_ext_io, "USER_SETTINGS_FILE", None)
            if _settings_file and os.path.isfile(_settings_file):
                with open(_settings_file, "r", encoding="utf-8") as _sf:
                    _user_cfg = _json.load(_sf)
                _extra = _user_cfg.get("extra_data_dirs", [])
                if isinstance(_extra, list):
                    allowed_dirs.extend([d for d in _extra if d and isinstance(d, str)])
        except Exception:
            pass  # Never block execution due to settings read failure

        # Check if file_path has wildcards (* or ?) for multi-file glob ingestion
        has_wildcard = any(char in file_path for char in ["*", "?"])
        import glob

        matched_files = []
        if has_wildcard:
            candidate_globs = []
            if os.path.isabs(file_path):
                candidate_globs.append(file_path)
            else:
                candidate_globs.append(file_path)
                if data_dir:
                    candidate_globs.append(os.path.join(data_dir, file_path))
                    if file_path.startswith(("data/", "data\\")):
                        candidate_globs.append(os.path.join(data_dir, file_path[5:]))
                    candidate_globs.append(os.path.join(data_dir, os.path.basename(file_path)))
                if base_dir:
                    candidate_globs.append(os.path.join(base_dir, file_path))

            for g_pat in candidate_globs:
                matches = glob.glob(g_pat)
                if matches:
                    matched_files.extend(matches)
            # Deduplicate and sort deterministically
            matched_files = sorted(list(dict.fromkeys(matched_files)))
        else:
            resolved_single = None
            if os.path.isabs(file_path) and os.path.exists(file_path):
                resolved_single = file_path
            elif os.path.exists(file_path):
                resolved_single = file_path
            elif data_dir and os.path.exists(os.path.join(data_dir, file_path)):
                resolved_single = os.path.join(data_dir, file_path)
            elif data_dir and file_path.startswith(("data/", "data\\")) and os.path.exists(os.path.join(data_dir, file_path[5:])):
                resolved_single = os.path.join(data_dir, file_path[5:])
            elif data_dir and os.path.exists(os.path.join(data_dir, os.path.basename(file_path))):
                resolved_single = os.path.join(data_dir, os.path.basename(file_path))
            elif base_dir and os.path.exists(os.path.join(base_dir, file_path)):
                resolved_single = os.path.join(base_dir, file_path)

            if resolved_single:
                matched_files = [resolved_single]

        if not matched_files:
            raise NodeExecutionError(f"Input Data: No file(s) found matching '{file_path}'")

        # Security containment check
        for f in matched_files:
            if allowed_dirs and not is_safe_path(f, allowed_dirs):
                raise NodeExecutionError(
                    f"Input Data security error: Access outside allowed workspace directories is forbidden: '{f}'"
                )

        max_rows = self.config.get("max_rows")
        if max_rows is not None and str(max_rows).isdigit():
            max_rows = int(max_rows)
        else:
            max_rows = None

        start_row = self.config.get("start_row", 1)
        try:
            start_row = int(start_row)
        except (ValueError, TypeError):
            start_row = 1
        skiprows = max(0, start_row - 1) if start_row > 1 else None

        delimiter = self.config.get("delimiter", ",")
        if delimiter in ["\\t", "tab"]:
            delimiter = "\t"
        elif delimiter in ["pipe", "\\|"]:
            delimiter = "|"
        elif delimiter == "semicolon":
            delimiter = ";"

        quote_char = self.config.get("quote_char", '"')
        if quote_char in ["none", "None", ""]:
            quote_char = None

        escape_char = self.config.get("escape_char", None)
        if escape_char in ["none", "None", ""]:
            escape_char = None

        encoding = self.config.get("encoding", "utf-8")
        has_header = self.config.get("has_header", True)
        header = 0 if has_header else None
        sheet_name = self.config.get("sheet_name", 0)
        read_all_sheets = bool(self.config.get("read_all_sheets", False))
        on_bad_lines = self.config.get("on_bad_lines", "error").lower()
        trim_headers = bool(self.config.get("trim_headers", True))
        output_fn = (
            self.config.get("output_file_name_mode") or
            self.config.get("output_filename_field") or
            "none"
        ).lower().strip()

        def read_single_file(fpath: str) -> pd.DataFrame:
            file_type = self.config.get("file_type", "").lower()
            if not file_type:
                file_type = detect_format(fpath)

            effective_delim = delimiter
            if file_type == "tsv" and (not delimiter or delimiter == ","):
                effective_delim = "\t"

            try:
                single_df = read_tabular_file(
                    filepath=fpath,
                    format_hint=file_type,
                    delimiter=effective_delim,
                    encoding=encoding,
                    header=header,
                    max_rows=max_rows,
                    skiprows=skiprows,
                    quote_char=quote_char,
                    escape_char=escape_char,
                    on_bad_lines=on_bad_lines,
                    sheet_name=sheet_name,
                    read_all_sheets=read_all_sheets,
                    trim_headers=trim_headers
                )
            except ValueError as ve:
                raise NodeExecutionError(f"Input Data error: {str(ve)}")
            except Exception as e:
                raise NodeExecutionError(f"Input Data error reading '{os.path.basename(fpath)}': {str(e)}")

            if output_fn in ("name", "name_only", "filename", "filename_only", "file_name_only"):
                single_df["FileName"] = os.path.basename(fpath)
            elif output_fn in ("path", "full_path"):
                single_df["FilePath"] = os.path.abspath(fpath)
            elif output_fn in ("both", "name_and_path"):
                single_df["FileName"] = os.path.basename(fpath)
                single_df["FilePath"] = os.path.abspath(fpath)

            return single_df

        dfs = []
        for fpath in matched_files:
            try:
                dfs.append(read_single_file(fpath))
            except Exception as e:
                if on_bad_lines == "warn":
                    self.messages.append(f"Input Data warning: Skipped '{os.path.basename(fpath)}' due to error: {str(e)}")
                else:
                    raise NodeExecutionError(f"Input Data error reading '{os.path.basename(fpath)}': {str(e)}")

        if not dfs:
            return {"O": pd.DataFrame()}

        if len(dfs) > 1:
            col_sets = [set(d.columns) for d in dfs]
            first_cols = col_sets[0]
            differing = [i for i, cs in enumerate(col_sets[1:], 1) if cs != first_cols]
            if differing:
                self.messages.append(f"Input Data notice: Multi-file schemas differ across {len(differing)} file(s). Data aligned and unioned by column name.")
            final_df = pd.concat(dfs, ignore_index=True)
        else:
            final_df = dfs[0]

        total_files = len(matched_files)
        total_rows = len(final_df)
        total_cols = len(final_df.columns)
        file_desc = f"{total_files} files matched ('{os.path.basename(file_path)}')" if total_files > 1 else f"'{os.path.basename(matched_files[0])}'"
        self.messages.append(f"Loaded {total_rows:,} rows across {total_cols} columns from {file_desc}.")

        return {"O": final_df}



# ----------------------------------------------------------------------
# 2. Output Data Node
# ----------------------------------------------------------------------
class OutputDataNode(BaseNode):
    type_name = "output_data"
    category = "in_out"
    display_name = "Output Data"
    description = "Export data to CSV, Excel, TSV, JSON, or Parquet file"
    input_ports = ["I"]
    output_ports = ["O"]

    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, config)
        self.written_files = []

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, pd.DataFrame]:
        self.messages = []
        context = context or {}
        df = self.get_single_input(inputs)

        output_dir = context.get("output_dir", ".")
        base_dir = context.get("base_dir", "")

        cfg_out_dir = self.config.get("output_dir", "").strip()
        if cfg_out_dir:
            if not os.path.isabs(cfg_out_dir) and base_dir:
                output_dir = os.path.normpath(os.path.join(base_dir, cfg_out_dir))
            else:
                output_dir = os.path.normpath(cfg_out_dir)

        raw_path = self.config.get("file_path", "").strip() or self.config.get("filename", "").strip() or f"output_{self.node_id}"
        if os.path.isabs(raw_path) or "/" in raw_path or "\\" in raw_path:
            dir_part = os.path.dirname(raw_path)
            if dir_part:
                if not os.path.isabs(dir_part) and base_dir and not cfg_out_dir:
                    output_dir = os.path.normpath(os.path.join(base_dir, dir_part))
                elif not cfg_out_dir:
                    output_dir = os.path.normpath(dir_part)
            filename = os.path.basename(raw_path)
        else:
            filename = raw_path

        os.makedirs(output_dir, exist_ok=True)

        for ext_strip in [".csv", ".xlsx", ".xls", ".tsv", ".json", ".parquet"]:
            if filename.lower().endswith(ext_strip):
                filename = filename[:-len(ext_strip)]
                break

        fmt = self.config.get("format", "csv").lower()
        if fmt in ["xlsx", "excel"]:
            fmt = "excel"
        elif fmt in ["tsv", "tab"]:
            fmt = "tsv"

        delimiter = self.config.get("delimiter", ",")
        if delimiter in ["\\t", "tab"]:
            delimiter = "\t"
        elif delimiter in ["pipe", "\\|"]:
            delimiter = "|"
        elif delimiter == "semicolon":
            delimiter = ";"

        if fmt == "tsv":
            delimiter = "\t"

        encoding = self.config.get("encoding", "utf-8")
        has_header = bool(self.config.get("has_header", True))
        include_index = bool(self.config.get("include_index", False))
        write_mode = self.config.get("write_mode", "overwrite").lower()
        sheet_name = self.config.get("sheet_name", "Sheet1").strip() or "Sheet1"
        quote_mode = self.config.get("quote_mode", "minimal").lower()
        line_ending = self.config.get("line_ending", "crlf").lower()
        lineterminator = "\r\n" if line_ending == "crlf" else "\n"
        drop_filename_field = bool(self.config.get("drop_filename_field", False))

        import csv
        quoting_map = {
            "minimal": csv.QUOTE_MINIMAL,
            "all": csv.QUOTE_ALL,
            "none": csv.QUOTE_NONE,
            "nonnumeric": csv.QUOTE_NONNUMERIC
        }
        quoting = quoting_map.get(quote_mode, csv.QUOTE_MINIMAL)

        take_dynamic = self.config.get("take_filename_from_field", False)
        take_field = ""
        if isinstance(take_dynamic, str) and take_dynamic:
            take_field = take_dynamic.strip()
        elif take_dynamic:
            take_field = self.config.get("filename_field", "").strip()

        filename_action = self.config.get("filename_action", "change_entire")

        self.written_files = []

        def save_file(target_df: pd.DataFrame, base_name: str) -> str:
            export_df = target_df.copy()
            if drop_filename_field and take_field and take_field in export_df.columns:
                export_df = export_df.drop(columns=[take_field])

            clean_base = sanitize_file_basename(base_name, fallback=f"output_{self.node_id}")

            if fmt == "excel":
                ext = ".xlsx"
                full_name = clean_base + ext
                target_path = os.path.join(output_dir, full_name)
                validate_safe_path(target_path, [output_dir], label="Output Data")
                if write_mode == "append" and os.path.exists(target_path):
                    with pd.ExcelWriter(target_path, mode="a", engine="openpyxl", if_sheet_exists="replace") as writer:
                        export_df.to_excel(writer, sheet_name=sheet_name, index=include_index, header=has_header)
                else:
                    export_df.to_excel(target_path, sheet_name=sheet_name, index=include_index, header=has_header)

            elif fmt == "parquet":
                ext = ".parquet"
                full_name = clean_base + ext
                target_path = os.path.join(output_dir, full_name)
                validate_safe_path(target_path, [output_dir], label="Output Data")
                export_df.to_parquet(target_path, index=include_index)

            elif fmt == "json":
                ext = ".json"
                full_name = clean_base + ext
                target_path = os.path.join(output_dir, full_name)
                validate_safe_path(target_path, [output_dir], label="Output Data")
                export_df.to_json(target_path, orient="records", indent=2)

            else:  # csv or tsv
                ext = ".tsv" if fmt == "tsv" else ".csv"
                full_name = clean_base + ext
                target_path = os.path.join(output_dir, full_name)
                validate_safe_path(target_path, [output_dir], label="Output Data")

                if write_mode == "create_new" and os.path.exists(target_path):
                    raise NodeExecutionError(f"Output Data: File '{full_name}' already exists (Write Mode: Create New).")

                mode_flag = "a" if write_mode == "append" and os.path.exists(target_path) else "w"
                header_flag = has_header and not (write_mode == "append" and os.path.exists(target_path))

                export_df.to_csv(
                    target_path,
                    sep=delimiter,
                    index=include_index,
                    mode=mode_flag,
                    header=header_flag,
                    encoding=encoding,
                    quoting=quoting,
                    lineterminator=lineterminator
                )

            f_size = os.path.getsize(target_path) if os.path.exists(target_path) else 0
            file_meta = {
                "filename": full_name,
                "path": target_path,
                "records": len(export_df),
                "size_bytes": f_size,
                "format": fmt
            }
            self.written_files.append(file_meta)
            if "written_files" in context and isinstance(context["written_files"], list):
                context["written_files"].append(file_meta)
            return target_path

        try:
            if take_field and take_field in df.columns:
                for val, sub_df in df.groupby(take_field):
                    safe_val = re.sub(r'[^\w\-_\.]', '_', str(val))
                    if filename_action == "append_suffix":
                        sub_fname = f"{filename}_{safe_val}"
                    elif filename_action == "prepend_prefix":
                        sub_fname = f"{safe_val}_{filename}"
                    else:
                        sub_fname = safe_val
                    save_file(sub_df, sub_fname)
            else:
                save_file(df, filename)
        except NodeExecutionError:
            raise
        except Exception as e:
            raise NodeExecutionError(f"Output Data: Failed to write file: {str(e)}")

        summary_parts = [f"Successfully wrote {len(self.written_files)} file(s):"]
        for f in self.written_files[:3]:
            summary_parts.append(f"• '{f['filename']}' ({f['records']:,} rows, {f['size_bytes']:,} bytes)")
        if len(self.written_files) > 3:
            summary_parts.append(f"• ... and {len(self.written_files) - 3} more files.")
        self.messages.append(" ".join(summary_parts))

        return {"O": sanitize_dataframe(df)}


# ----------------------------------------------------------------------

class TextInputNode(BaseNode):
    type_name = "text_input"
    category = "in_out"
    display_name = "Text Input"
    description = "Manually input data via table grid or paste clipboard text"
    input_ports = []
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        raw_text = self.config.get("raw_text", "")
        delimiter = self.config.get("delimiter", "\t")
        columns = self.config.get("columns", [])
        data = self.config.get("data", [])

        if raw_text and str(raw_text).strip():
            try:
                sep = "\t" if delimiter in ("\t", "\\t", "tab") else delimiter
                df = pd.read_csv(io.StringIO(str(raw_text).strip()), sep=sep, dtype=str)
                for col in df.columns:
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except (ValueError, TypeError):
                        pass
                return {"O": sanitize_dataframe(df)}
            except Exception as e:
                raise NodeExecutionError(f"Text Input: Failed to parse raw text: {str(e)}")

        if columns or data:
            try:
                if not columns and data and isinstance(data, list) and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                else:
                    df = pd.DataFrame(data if data else [], columns=columns if columns else None)
                for col in df.columns:
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except (ValueError, TypeError):
                        pass
                return {"O": sanitize_dataframe(df)}
            except Exception as e:
                raise NodeExecutionError(f"Text Input: Failed to construct table: {str(e)}")

        return {"O": pd.DataFrame()}



# ----------------------------------------------------------------------
# Browse Tool (Data Profiling & Passthrough)
# ----------------------------------------------------------------------
class BrowseNode(BaseNode):
    type_name = "browse"
    category = "in_out"
    display_name = "Browse"
    description = "View data and comprehensive data profiling studio"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, pd.DataFrame]:
        self.messages = []
        df = inputs.get("I")
        if df is None:
            df = pd.DataFrame()

        clean_df = sanitize_dataframe(df)
        total_rows = len(clean_df)
        total_cols = len(clean_df.columns)
        mem_bytes = int(clean_df.memory_usage(deep=True).sum()) if total_rows > 0 else 0
        from backend.engine.profiler import format_bytes
        mem_str = format_bytes(mem_bytes)

        self.messages.append(f"Browse: Inspected {total_rows:,} records and {total_cols} fields ({mem_str}). Full profiling active.")
        return {"O": clean_df}
