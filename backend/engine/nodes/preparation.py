import os
import re
import ast
import io
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from .base import BaseNode, NodeExecutionError, sanitize_dataframe
from backend.engine.formula import evaluate_expression, FormulaExecutionError

class SelectNode(BaseNode):
    type_name = "select"
    category = "preparation"
    display_name = "Select"
    description = "Rename, reorder, change types, or drop columns"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Select: No input connected.")

        fields = self.config.get("fields", [])
        if not fields:
            return {"O": df.copy()}

        out_df = pd.DataFrame()
        rename_map = {}

        for item in fields:
            orig = item.get("original") or item.get("name") or item.get("field")
            if not orig or orig not in df.columns:
                continue

            keep = item.get("keep") if "keep" in item else item.get("selected", True)
            if not keep:
                continue

            series = df[orig].copy()

            # Type conversion with Alteryx-grade support and symbol cleaning
            new_type = str(item.get("type", "none")).strip().lower()
            if new_type and new_type != "none":
                try:
                    if new_type in ("string", "v_string", "v_wstring", "wstring"):
                        series = series.astype(str).replace({"nan": None, "<NA>": None, "None": None})
                    elif new_type in ("integer", "int64", "int32", "int16", "byte"):
                        # Clean currency symbols, commas, percent signs
                        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                            s_clean = series.astype(str).str.strip().str.replace("$", "", regex=False).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
                            series = pd.to_numeric(s_clean, errors="coerce").round().astype("Int64")
                        else:
                            series = pd.to_numeric(series, errors="coerce").round().astype("Int64")
                    elif new_type in ("float", "double", "fixeddecimal"):
                        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                            s_clean = series.astype(str).str.strip().str.replace("$", "", regex=False).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
                            series = pd.to_numeric(s_clean, errors="coerce").astype(float)
                        else:
                            series = pd.to_numeric(series, errors="coerce").astype(float)
                    elif new_type in ("boolean", "bool"):
                        bool_map = {
                            "true": True, "1": True, "yes": True, "t": True, "y": True,
                            "false": False, "0": False, "no": False, "f": False, "n": False
                        }
                        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                            series = series.astype(str).str.strip().str.lower().map(bool_map).astype("boolean")
                        else:
                            series = series.astype(bool)
                    elif new_type == "datetime":
                        series = pd.to_datetime(series, errors="coerce", format="mixed")
                    elif new_type == "date":
                        series = pd.to_datetime(series, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
                    elif new_type == "time":
                        series = pd.to_datetime(series, errors="coerce", format="mixed").dt.strftime("%H:%M:%S")
                except Exception as e:
                    raise NodeExecutionError(f"Error casting column '{orig}' to {new_type}: {e}")

            rename_to = item.get("rename", "").strip()
            final_col = rename_to if rename_to else orig
            out_df[final_col] = series

        return {"O": out_df}


# ----------------------------------------------------------------------
# 3b. Auto Field Tool (Automatic Type Optimization)
# ----------------------------------------------------------------------
class AutoFieldNode(BaseNode):
    type_name = "auto_field"
    category = "preparation"
    display_name = "Auto Field"
    description = "Automatically set fields to the most appropriate, optimal data type"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Auto Field: No input connected.")

        if df.empty:
            return {"O": df.copy()}

        columns_to_process = self.config.get("columns", [])
        if not columns_to_process:
            # By default in Alteryx, all fields are auto-typed
            columns_to_process = list(df.columns)

        out_df = df.copy()
        for col in columns_to_process:
            if col not in out_df.columns:
                continue

            series = out_df[col]
            # If string/object, attempt smart auto-conversion
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                out_df[col] = self._auto_convert_series(series)

        return {"O": sanitize_dataframe(out_df)}

    def _auto_convert_series(self, series: pd.Series) -> pd.Series:
        non_null = series.dropna()
        if non_null.empty:
            return series

        str_series = non_null.astype(str).str.strip()
        if str_series.empty:
            return series

        # 1. Try boolean
        lower_str = str_series.str.lower()
        if lower_str.isin({"true", "false", "t", "f", "yes", "no"}).all():
            bool_map = {"true": True, "t": True, "yes": True, "false": False, "f": False, "no": False}
            return series.astype(str).str.strip().str.lower().map(bool_map).astype("boolean")

        # 2. Try integer or float
        has_leading_zero = str_series.apply(lambda s: len(s) > 1 and s.startswith("0") and not s.startswith("0.")).any()
        if not has_leading_zero:
            clean_num = str_series.str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace("%", "", regex=False)
            try:
                num_conv = pd.to_numeric(clean_num, errors="raise")
                full_clean = series.astype(str).str.strip().str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace("%", "", regex=False)
                if (num_conv % 1 == 0).all():
                    return pd.to_numeric(full_clean, errors="coerce").astype("Int64")
                else:
                    return pd.to_numeric(full_clean, errors="coerce").astype(float)
            except Exception:
                pass

        # 3. Try Date / DateTime
        date_pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if str_series.apply(lambda s: bool(date_pat.match(s))).all():
            try:
                return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        datetime_pat = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?")
        if str_series.apply(lambda s: bool(datetime_pat.match(s))).all():
            try:
                return pd.to_datetime(series, errors="coerce")
            except Exception:
                pass

        return series


# ----------------------------------------------------------------------
# 4. Filter Tool (True / False dual output)
# ----------------------------------------------------------------------
class FilterNode(BaseNode):
    type_name = "filter"
    category = "preparation"
    display_name = "Filter"
    description = "Filter records by conditions into True and False outputs"
    input_ports = ["I"]
    output_ports = ["T", "F"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Filter: No input connected.")

        if df.empty:
            return {"T": df.copy(), "F": df.copy()}

        mode = str(self.config.get("mode", "basic")).lower().strip()

        if mode in ("custom", "expression", "formula"):
            query_expr = self.config.get("expression", "").strip()
            if not query_expr:
                return {"T": df.copy(), "F": df.iloc[0:0].copy()}
            try:
                # Check bracketed column references
                bracket_cols = re.findall(r"\[(.*?)\]", query_expr)
                for col in bracket_cols:
                    if col not in df.columns:
                        raise NodeExecutionError(f"Column [{col}] not found in dataset. Available columns: {list(df.columns)}")

                res = evaluate_expression(df, query_expr)
                if not isinstance(res, pd.Series):
                    res = pd.Series(res, index=df.index)
                mask = res.fillna(False).astype(bool)
            except NodeExecutionError:
                raise
            except Exception as e:
                raise NodeExecutionError(f"Filter custom expression error: {str(e)}")

        elif mode in ("query", "text_query", "quick_query"):
            query_str = self.config.get("query", "").strip()
            if not query_str:
                return {"T": df.copy(), "F": df.iloc[0:0].copy()}
            mask = self._evaluate_text_query(df, query_str)

        else:
            # Basic mode
            conditions = self.config.get("conditions", [])
            if not conditions:
                return {"T": df.copy(), "F": df.iloc[0:0].copy()}

            logical_op = self.config.get("logical_op", "AND").upper()
            masks = []

            for cond in conditions:
                col = cond.get("column")
                if not col or col not in df.columns:
                    continue

                series = df[col]
                m = self._evaluate_condition(series, cond)
                masks.append(m)

            if not masks:
                return {"T": df.copy(), "F": df.iloc[0:0].copy()}

            if logical_op == "OR":
                final_mask = masks[0]
                for m in masks[1:]:
                    final_mask = final_mask | m
            else:
                final_mask = masks[0]
                for m in masks[1:]:
                    final_mask = final_mask & m

            mask = final_mask

        true_df = df[mask].copy()
        false_df = df[~mask].copy()
        return {"T": true_df, "F": false_df}

    def _evaluate_condition(self, series: pd.Series, cond: Dict[str, Any]) -> pd.Series:
        op = str(cond.get("operator", "==")).lower().strip()
        val = cond.get("value", "")
        val_max = cond.get("value_max", "")
        ignore_case = cond.get("ignore_case", True)

        # 1. Null / Empty
        if op == "is_null":
            return series.isna()
        if op in ("not_null", "is_not_null"):
            return series.notna()
        if op == "is_empty":
            return series.isna() | (series.astype(str).str.strip() == "")
        if op in ("not_empty", "is_not_empty"):
            return series.notna() & (series.astype(str).str.strip() != "")

        # 2. Boolean flags
        if op == "is_true":
            return series.astype(str).str.lower().isin(["true", "1", "yes", "t"])
        if op == "is_false":
            return series.astype(str).str.lower().isin(["false", "0", "no", "f"])

        # 3. Numeric & DateTime type detection
        is_numeric = pd.api.types.is_numeric_dtype(series)
        is_datetime = pd.api.types.is_datetime64_any_dtype(series)
        str_series = series.astype(str)

        # 4. Range / Between
        if op == "between":
            if is_numeric:
                try:
                    num_series = pd.to_numeric(series, errors="coerce")
                    return num_series.between(float(val), float(val_max))
                except Exception:
                    pass
            elif is_datetime:
                try:
                    dt_series = pd.to_datetime(series, errors="coerce")
                    return (dt_series >= pd.to_datetime(val)) & (dt_series <= pd.to_datetime(val_max))
                except Exception:
                    pass
            # String between
            low = str(val).lower() if ignore_case else str(val)
            high = str(val_max).lower() if ignore_case else str(val_max)
            cmp_s = str_series.str.lower() if ignore_case else str_series
            return (cmp_s >= low) & (cmp_s <= high)

        # 5. List Membership
        if op in ("in", "not_in"):
            raw_items = [x.strip() for x in str(val).split(",") if x.strip()]
            if is_numeric:
                try:
                    num_items = [float(x) for x in raw_items]
                    res = pd.to_numeric(series, errors="coerce").isin(num_items)
                    return ~res if op == "not_in" else res
                except ValueError:
                    pass
            if ignore_case:
                lower_items = [x.lower() for x in raw_items]
                res = str_series.str.lower().isin(lower_items)
            else:
                res = str_series.isin(raw_items)
            return ~res if op == "not_in" else res

        # 6. Regex match
        if op in ("regex_match", "regex"):
            try:
                return str_series.str.contains(str(val), case=not ignore_case, regex=True, na=False)
            except Exception:
                return pd.Series(False, index=series.index)

        # 7. Text matching operators
        if op == "contains":
            return str_series.str.contains(re.escape(str(val)), case=not ignore_case, na=False)
        elif op in ("not_contains", "does_not_contain"):
            return ~str_series.str.contains(re.escape(str(val)), case=not ignore_case, na=False)
        elif op == "starts_with":
            if ignore_case:
                return str_series.str.lower().str.startswith(str(val).lower(), na=False)
            return str_series.str.startswith(str(val), na=False)
        elif op == "ends_with":
            if ignore_case:
                return str_series.str.lower().str.endswith(str(val).lower(), na=False)
            return str_series.str.endswith(str(val), na=False)

        # 8. Standard Relational Comparisons
        if is_numeric:
            try:
                num_series = pd.to_numeric(series, errors="coerce")
                num_val = float(val) if "." in str(val) else int(val)
                if op in ("==", "="):
                    return num_series == num_val
                elif op in ("!=", "<>"):
                    return num_series != num_val
                elif op == ">":
                    return num_series > num_val
                elif op == ">=":
                    return num_series >= num_val
                elif op == "<":
                    return num_series < num_val
                elif op == "<=":
                    return num_series <= num_val
            except (ValueError, TypeError):
                pass

        if is_datetime:
            try:
                dt_series = pd.to_datetime(series, errors="coerce")
                dt_val = pd.to_datetime(val)
                if op in ("==", "="):
                    return dt_series == dt_val
                elif op in ("!=", "<>"):
                    return dt_series != dt_val
                elif op == ">":
                    return dt_series > dt_val
                elif op == ">=":
                    return dt_series >= dt_val
                elif op == "<":
                    return dt_series < dt_val
                elif op == "<=":
                    return dt_series <= dt_val
            except Exception:
                pass

        # String relational comparisons
        s1 = str_series.str.lower() if ignore_case else str_series
        s2 = str(val).lower() if ignore_case else str(val)

        if op in ("==", "="):
            return s1 == s2
        elif op in ("!=", "<>"):
            return s1 != s2
        elif op == ">":
            return s1 > s2
        elif op == ">=":
            return s1 >= s2
        elif op == "<":
            return s1 < s2
        elif op == "<=":
            return s1 <= s2

        raise NodeExecutionError(f"Unsupported filter operator '{op}'")

    def _evaluate_text_query(self, df: pd.DataFrame, query_str: str) -> pd.Series:
        """
        Parses search-like query text (e.g. 'Region:East Sales>500 Status:Active,Review')
        and evaluates into a boolean Series mask.
        """
        query = query_str.strip()
        if not query:
            return pd.Series(True, index=df.index)

        or_branches = re.split(r'\s+\bOR\b\s+', query, flags=re.IGNORECASE)
        branch_masks = []

        for branch in or_branches:
            branch = branch.strip()
            if not branch:
                continue

            pattern = re.compile(r'([\w\s]+?)\s*([:><=!]={0,2})\s*("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s]+)|("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s]+)')
            clause_masks = []
            cols_lower_map = {c.lower(): c for c in df.columns}

            for match in pattern.finditer(branch):
                col_part, op, val_part, free_word = match.groups()
                
                if free_word:
                    cleaned_word = free_word.strip('"\'')
                    if not cleaned_word:
                        continue
                    text_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
                    if not text_cols:
                        text_cols = list(df.columns)
                    word_mask = pd.Series(False, index=df.index)
                    for c in text_cols:
                        word_mask |= df[c].astype(str).str.contains(re.escape(cleaned_word), case=False, na=False)
                    clause_masks.append(word_mask)
                    continue

                col_name = col_part.strip()
                matched_col = cols_lower_map.get(col_name.lower())
                
                if not matched_col:
                    full_chunk = match.group(0).strip('"\'')
                    word_mask = pd.Series(False, index=df.index)
                    for c in df.columns:
                        word_mask |= df[c].astype(str).str.contains(re.escape(full_chunk), case=False, na=False)
                    clause_masks.append(word_mask)
                    continue

                raw_val = val_part.strip('"\'')
                series = df[matched_col]

                if ".." in raw_val:
                    r_parts = raw_val.split("..", 1)
                    clause_masks.append(self._evaluate_condition(series, {
                        "operator": "between",
                        "value": r_parts[0].strip(),
                        "value_max": r_parts[1].strip(),
                        "ignore_case": True
                    }))
                elif "," in raw_val:
                    clause_masks.append(self._evaluate_condition(series, {
                        "operator": "in",
                        "value": raw_val,
                        "ignore_case": True
                    }))
                elif op == ":":
                    clause_masks.append(self._evaluate_condition(series, {
                        "operator": "contains",
                        "value": raw_val,
                        "ignore_case": True
                    }))
                else:
                    clause_masks.append(self._evaluate_condition(series, {
                        "operator": op,
                        "value": raw_val,
                        "ignore_case": True
                    }))

            if clause_masks:
                final_branch_mask = clause_masks[0]
                for cm in clause_masks[1:]:
                    final_branch_mask &= cm
                branch_masks.append(final_branch_mask)

        if not branch_masks:
            return pd.Series(True, index=df.index)

        res_mask = branch_masks[0]
        for bm in branch_masks[1:]:
            res_mask |= bm
        return res_mask


# ----------------------------------------------------------------------
# 5. Formula Tool
# ----------------------------------------------------------------------
class FormulaNode(BaseNode):
    type_name = "formula"
    category = "preparation"
    display_name = "Formula"
    description = "Compute or update columns with math, string, and logic formulas"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Formula: No input connected.")

        out_df = df.copy()
        formulas = self.config.get("formulas") or self.config.get("expressions") or []

        for item in formulas:
            out_col = (item.get("output_field") or item.get("field") or item.get("column") or "").strip()
            expr = item.get("expression", "").strip()

            if not out_col or not expr:
                continue

            try:
                res = evaluate_expression(out_df, expr)
                out_type = item.get("type", "").lower()
                if out_type and out_type != "none":
                    try:
                        if out_type == "string":
                            res = pd.Series(res, index=out_df.index).astype(str).replace({"nan": "", "<NA>": "", "None": ""})
                        elif out_type == "integer":
                            res = pd.to_numeric(pd.Series(res, index=out_df.index), errors="coerce").fillna(0).astype(int)
                        elif out_type == "float":
                            res = pd.to_numeric(pd.Series(res, index=out_df.index), errors="coerce")
                        elif out_type == "boolean":
                            res = pd.Series(res, index=out_df.index).astype(bool)
                        elif out_type == "datetime":
                            res = pd.to_datetime(pd.Series(res, index=out_df.index), errors="coerce")
                        elif out_type == "date":
                            res = pd.to_datetime(pd.Series(res, index=out_df.index), errors="coerce").dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass
                out_df[out_col] = res
            except Exception as e:
                raise NodeExecutionError(f"Error in formula for '{out_col}': {str(e)}")

        return {"O": out_df}

    def _evaluate_formula(self, df: pd.DataFrame, expr: str) -> Any:
        """Backward-compatible helper delegating to safe expression evaluator."""
        return evaluate_expression(df, expr)


# ----------------------------------------------------------------------
# 6. Sort Tool
# ----------------------------------------------------------------------
class SortNode(BaseNode):
    type_name = "sort"
    category = "preparation"
    display_name = "Sort"
    description = "Sort records by one or multiple columns"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Sort: No input connected.")

        sort_by = self.config.get("sort_by") or self.config.get("sort_fields") or self.config.get("fields") or []
        if not sort_by:
            return {"O": df.copy()}

        columns = []
        ascending = []
        case_sensitive = self.config.get("case_sensitive", True)

        sorted_df = df.copy()
        temp_sort_cols = []

        for rule in sort_by:
            col = rule.get("column") or rule.get("field")
            if col and col in df.columns:
                if not case_sensitive and pd.api.types.is_string_dtype(sorted_df[col]):
                    temp_col = f"__sort_ci_{col}__"
                    sorted_df[temp_col] = sorted_df[col].astype(str).str.lower()
                    columns.append(temp_col)
                    temp_sort_cols.append(temp_col)
                else:
                    columns.append(col)
                is_asc = rule.get("ascending") if "ascending" in rule else (str(rule.get("order", "asc")).lower() != "desc")
                ascending.append(bool(is_asc))

        if not columns:
            return {"O": df.copy()}

        sorted_df = sorted_df.sort_values(by=columns, ascending=ascending)
        if temp_sort_cols:
            sorted_df = sorted_df.drop(columns=temp_sort_cols)

        return {"O": sorted_df}


# ----------------------------------------------------------------------
# 7. Clean / Impute Tool
# ----------------------------------------------------------------------
class CleanNode(BaseNode):
    type_name = "clean"
    category = "preparation"
    display_name = "Data Clean"
    description = "Trim whitespace, handle nulls, remove unwanted characters, and format text"
    input_ports = ["I"]
    output_ports = ["O"]

    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, config)
        self.messages = []

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        self.messages = []
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Clean: No input connected.")

        out_df = df.copy()
        raw_target_cols = self.config.get("columns", [])
        if raw_target_cols and isinstance(raw_target_cols, list):
            target_cols = [c for c in raw_target_cols if c in out_df.columns]
        else:
            target_cols = list(out_df.columns)

        def _is_text_col(series: pd.Series) -> bool:
            return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)

        def _is_numeric_col(series: pd.Series) -> bool:
            return pd.api.types.is_numeric_dtype(series)

        nulls_replaced = 0
        cells_modified = 0

        # 1. Drop rows where all columns are empty / whitespace / null
        if self.config.get("remove_empty_rows", False):
            orig_rows = len(out_df)
            is_empty_cell = out_df.isna()
            for col in out_df.columns:
                if _is_text_col(out_df[col]):
                    is_empty_cell[col] = is_empty_cell[col] | out_df[col].astype(str).str.strip().eq("")
            empty_mask = is_empty_cell.all(axis=1)
            out_df = out_df[~empty_mask].copy()
            dropped_rows = orig_rows - len(out_df)
            if dropped_rows > 0:
                self.messages.append(f"Removed {dropped_rows} completely empty row(s).")

        # 2. Drop columns where all values are empty / whitespace / null
        if self.config.get("remove_empty_cols", False):
            is_empty_cell = out_df.isna()
            for col in out_df.columns:
                if _is_text_col(out_df[col]):
                    is_empty_cell[col] = is_empty_cell[col] | out_df[col].astype(str).str.strip().eq("")
            empty_col_mask = is_empty_cell.all(axis=0)
            cols_to_drop = out_df.columns[empty_col_mask].tolist()
            if cols_to_drop:
                out_df = out_df.drop(columns=cols_to_drop)
                target_cols = [c for c in target_cols if c not in cols_to_drop]
                self.messages.append(f"Removed {len(cols_to_drop)} completely empty column(s): {', '.join(cols_to_drop)}.")

        # 3. Replace Null Data (Alteryx Parity)
        rep_null_str = bool(self.config.get("replace_nulls_string", False))
        rep_null_num = bool(self.config.get("replace_nulls_numeric", False))

        for col in target_cols:
            if col not in out_df.columns:
                continue
            if rep_null_str and _is_text_col(out_df[col]):
                cnt = int(out_df[col].isna().sum())
                if cnt > 0:
                    out_df[col] = out_df[col].fillna("")
                    nulls_replaced += cnt
            if rep_null_num and _is_numeric_col(out_df[col]):
                cnt = int(out_df[col].isna().sum())
                if cnt > 0:
                    out_df[col] = out_df[col].fillna(0)
                    nulls_replaced += cnt

        # 4. Remove Unwanted Characters
        trim_ws = bool(self.config.get("trim_whitespace", True))
        remove_tabs = bool(self.config.get("remove_tabs_linebreaks", False))
        remove_all_ws = bool(self.config.get("remove_all_ws", False))
        remove_letters = bool(self.config.get("remove_letters", False))
        remove_numbers = bool(self.config.get("remove_numbers", False))
        remove_punct = bool(self.config.get("remove_punctuation", False))
        custom_chars = str(self.config.get("remove_custom_chars", "") or self.config.get("custom_chars", ""))
        custom_regex = str(self.config.get("remove_custom_regex", "") or self.config.get("custom_regex", ""))

        has_char_cleanup = any([
            trim_ws, remove_tabs, remove_all_ws, remove_letters, remove_numbers,
            remove_punct, custom_chars, custom_regex
        ])

        if has_char_cleanup:
            for col in target_cols:
                if col in out_df.columns and _is_text_col(out_df[col]):
                    mask_notna = out_df[col].notna()
                    if not mask_notna.any():
                        continue
                    s = out_df.loc[mask_notna, col].astype(str)
                    orig_s = s.copy()

                    if remove_tabs:
                        # Alteryx: Tabs, Line Breaks, and Duplicate Whitespace
                        s = s.str.replace(r"[\r\n\t]+", " ", regex=True)
                        s = s.str.replace(r"[ ]{2,}", " ", regex=True)
                        s = s.str.strip()

                    if remove_all_ws:
                        s = s.str.replace(r"\s+", "", regex=True)
                    elif trim_ws and not remove_tabs:
                        s = s.str.strip()

                    if remove_letters:
                        s = s.str.replace(r"[a-zA-Z]+", "", regex=True)

                    if remove_numbers:
                        s = s.str.replace(r"[0-9]+", "", regex=True)

                    if remove_punct:
                        s = s.str.replace(r"[^\w\s]+", "", regex=True)

                    if custom_chars:
                        pat = "[" + re.escape(custom_chars) + "]+"
                        s = s.str.replace(pat, "", regex=True)

                    if custom_regex:
                        try:
                            s = s.str.replace(custom_regex, "", regex=True)
                        except Exception:
                            pass

                    diff_cnt = int((s != orig_s).sum())
                    cells_modified += diff_cnt
                    out_df.loc[mask_notna, col] = s

        # 5. Modify Case
        case_op = str(self.config.get("case_mode") or self.config.get("case_transformation", "none")).lower()
        if case_op and case_op != "none":
            for col in target_cols:
                if col in out_df.columns and _is_text_col(out_df[col]):
                    mask_notna = out_df[col].notna()
                    if not mask_notna.any():
                        continue
                    s = out_df.loc[mask_notna, col].astype(str)
                    orig_s = s.copy()
                    if case_op == "upper":
                        s = s.str.upper()
                    elif case_op == "lower":
                        s = s.str.lower()
                    elif case_op in ["title", "proper"]:
                        s = s.str.title()
                    diff_cnt = int((s != orig_s).sum())
                    cells_modified += diff_cnt
                    out_df.loc[mask_notna, col] = s

        # 6. Legacy / Advanced null strategies (backward compatibility)
        null_strat = str(self.config.get("null_strategy", "none")).lower()
        if null_strat == "drop_rows":
            subset = [c for c in target_cols if c in out_df.columns]
            out_df = out_df.dropna(subset=subset)
        elif null_strat == "replace_value":
            rep_val = self.config.get("null_replacement", "")
            for col in target_cols:
                if col in out_df.columns:
                    cnt = int(out_df[col].isna().sum())
                    if cnt > 0:
                        out_df[col] = out_df[col].fillna(rep_val)
                        nulls_replaced += cnt
        elif null_strat == "mean":
            for col in target_cols:
                if col in out_df.columns and _is_numeric_col(out_df[col]):
                    cnt = int(out_df[col].isna().sum())
                    if cnt > 0:
                        out_df[col] = out_df[col].fillna(out_df[col].mean())
                        nulls_replaced += cnt
        elif null_strat == "median":
            for col in target_cols:
                if col in out_df.columns and _is_numeric_col(out_df[col]):
                    cnt = int(out_df[col].isna().sum())
                    if cnt > 0:
                        out_df[col] = out_df[col].fillna(out_df[col].median())
                        nulls_replaced += cnt

        summary_parts = []
        if nulls_replaced > 0:
            summary_parts.append(f"Replaced {nulls_replaced} null(s)")
        if cells_modified > 0:
            summary_parts.append(f"Cleaned {cells_modified} text cell(s)")
        if summary_parts:
            self.messages.append(f"{', '.join(summary_parts)} across {len(target_cols)} field(s).")

        return {"O": out_df}


# ----------------------------------------------------------------------
# 8. Unique Tool (Unique / Duplicate dual output)
# ----------------------------------------------------------------------
class UniqueNode(BaseNode):
    type_name = "unique"
    category = "preparation"
    display_name = "Unique"
    description = "Separate unique records from duplicate records"
    input_ports = ["I"]
    output_ports = ["U", "D"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Unique: No input connected.")

        cols = self.config.get("columns", [])
        subset = [c for c in cols if c in df.columns] if cols else None

        # dup_mask: True for duplicate rows (excluding first occurrence)
        dup_mask = df.duplicated(subset=subset, keep="first")
        unique_df = df[~dup_mask].copy()
        dup_df = df[dup_mask].copy()

        return {"U": unique_df, "D": dup_df}



class SampleNode(BaseNode):
    type_name = "sample"
    category = "preparation"
    display_name = "Sample"
    description = "Limit records using first/last N, percentage, or 1 of N sample"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Sample: No input connected.")

        if df.empty:
            return {"O": df.copy()}

        sample_type = self.config.get("sample_type", "first_n")
        n_records = int(self.config.get("n_records", 100))
        percent = float(self.config.get("percent", 10.0))
        group_by = self.config.get("group_by", [])
        if isinstance(group_by, str) and group_by:
            group_by = [group_by]
        group_cols = [c for c in group_by if c in df.columns]

        def _sample_group(sub_df: pd.DataFrame) -> pd.DataFrame:
            total = len(sub_df)
            if total == 0:
                return sub_df

            if sample_type == "first_n":
                return sub_df.head(max(0, n_records))
            elif sample_type == "last_n":
                return sub_df.tail(max(0, n_records))
            elif sample_type == "skip_first_n":
                return sub_df.iloc[max(0, n_records):]
            elif sample_type == "sample_1_in_n":
                step = max(1, n_records)
                return sub_df.iloc[::step]
            elif sample_type == "random_1_in_n":
                chance = 1.0 / max(1, n_records)
                seed = self.config.get("seed", 42)
                rng = np.random.default_rng(seed)
                mask = rng.random(total) < chance
                return sub_df[mask]
            elif sample_type == "first_n_percent":
                pct = max(0.0, min(100.0, percent))
                count = int(np.ceil(total * (pct / 100.0)))
                return sub_df.head(count)
            else:
                return sub_df.head(max(0, n_records))

        if group_cols:
            sampled_dfs = []
            for _, grp in df.groupby(group_cols, as_index=False, sort=False):
                sampled_dfs.append(_sample_group(grp))
            res_df = pd.concat(sampled_dfs, ignore_index=True) if sampled_dfs else pd.DataFrame(columns=df.columns)
        else:
            res_df = _sample_group(df).reset_index(drop=True)

        return {"O": res_df}


# ----------------------------------------------------------------------
# 14. Record ID Tool
# ----------------------------------------------------------------------
class RecordIDNode(BaseNode):
    type_name = "record_id"
    category = "preparation"
    display_name = "Record ID"
    description = "Assign a unique sequential identifier to each record"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Record ID: No input connected.")

        res_df = df.copy()
        col_name = self.config.get("column_name", "RecordID") or "RecordID"
        start_val = int(self.config.get("start_value", 1))
        position = self.config.get("position", "first")
        group_by = self.config.get("group_by", [])
        if isinstance(group_by, str) and group_by:
            group_by = [group_by]
        group_cols = [c for c in group_by if c in df.columns]

        if group_cols:
            res_df[col_name] = res_df.groupby(group_cols).cumcount() + start_val
        else:
            res_df[col_name] = np.arange(start_val, start_val + len(res_df))

        if position == "first":
            cols = [col_name] + [c for c in res_df.columns if c != col_name]
            res_df = res_df[cols]

        return {"O": res_df}


# ----------------------------------------------------------------------
# 15. Multi-Row Formula Tool
# ----------------------------------------------------------------------
class MultiRowFormulaNode(BaseNode):
    type_name = "multi_row_formula"
    category = "preparation"
    display_name = "Multi-Row Formula"
    description = "Calculate running totals, lag/lead differences, and recursive row logic"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Multi-Row Formula: No input connected.")
        if df.empty:
            return {"O": df.copy()}

        out_df = df.copy()
        config = self.config or {}

        output_field = str(config.get("output_field", "")).strip() or "New_Field"
        is_new_field = config.get("is_new_field", True)
        output_type = str(config.get("output_type", "none")).strip().lower()
        boundary_mode = str(config.get("values_for_rows_not_exist", "null")).strip().lower()
        group_by = config.get("group_by_fields") or config.get("group_by", [])
        if isinstance(group_by, str) and group_by:
            group_by = [group_by]
        group_cols = [c for c in group_by if c in out_df.columns]

        expr = str(config.get("expression", "")).strip()
        if not expr:
            return {"O": out_df}

        # Normalize bracketed row offset tokens:
        # [Row - 1 : Col] -> [Row-1:Col], [Row + 0 : Col] -> [Col]
        def _clean_token(m):
            offset_sign = m.group(1).replace(" ", "")
            col = m.group(2).strip()
            offset_num = int(offset_sign)
            if offset_num == 0:
                return f"[{col}]"
            sign_char = "+" if offset_num > 0 else ""
            return f"[Row{sign_char}{offset_num}:{col}]"

        clean_expr = re.sub(r"\[\s*Row\s*([+-]?\s*\d+)\s*:\s*([^\]]+)\s*\]", _clean_token, expr, flags=re.IGNORECASE)

        # Identify all referenced Row[+-]N:Col tokens
        row_refs = re.findall(r"\[Row([+-]\d+):([^\]]+)\]", clean_expr)

        # Check if expression is self-referencing on output_field
        is_self_referencing = any(col == output_field for _, col in row_refs)

        if group_cols:
            partitions = [group for _, group in out_df.groupby(group_cols, sort=False, as_index=False)]
        else:
            partitions = [out_df]

        res_series_list = []
        for part in partitions:
            if part.empty:
                continue
            part_res = self._eval_partition(part, clean_expr, row_refs, output_field, is_self_referencing, boundary_mode)
            res_series_list.append(part_res)

        if res_series_list:
            final_series = pd.concat(res_series_list)
            out_df[output_field] = final_series.reindex(out_df.index)
        else:
            out_df[output_field] = np.nan

        # Type conversion if specified
        if output_type and output_type not in ("none", "keep"):
            try:
                if output_type in ("integer", "int64", "int32", "byte"):
                    out_df[output_field] = pd.to_numeric(out_df[output_field], errors="coerce").round().astype("Int64")
                elif output_type in ("float", "double", "fixeddecimal"):
                    out_df[output_field] = pd.to_numeric(out_df[output_field], errors="coerce").astype(float)
                elif output_type in ("string", "v_string", "v_wstring"):
                    out_df[output_field] = out_df[output_field].astype(str).replace({"nan": None, "<NA>": None, "None": None})
                elif output_type in ("boolean", "bool"):
                    out_df[output_field] = out_df[output_field].astype(bool)
                elif output_type == "date":
                    out_df[output_field] = pd.to_datetime(out_df[output_field], errors="coerce").dt.strftime("%Y-%m-%d")
                elif output_type in ("datetime", "timestamp"):
                    out_df[output_field] = pd.to_datetime(out_df[output_field], errors="coerce")
            except Exception:
                pass

        return {"O": out_df}

    def _eval_partition(
        self,
        part: pd.DataFrame,
        clean_expr: str,
        row_refs: List[Tuple[str, str]],
        output_field: str,
        is_self_referencing: bool,
        boundary_mode: str
    ) -> pd.Series:
        n_rows = len(part)

        # 1. Non-self-referencing: 100% Vectorized
        if not is_self_referencing:
            eval_df = part.copy()
            for offset_str, col_name in row_refs:
                offset = int(offset_str)
                token_col = f"Row{'+' if offset > 0 else ''}{offset}:{col_name}"
                if col_name in part.columns:
                    base_s = part[col_name]
                    # In Pandas, shift(k) shifts rows down (row i gets value from i-k)
                    # For [Row-1:Col], we want value from i-1, which is shift(1)!
                    # For [Row+1:Col], we want value from i+1, which is shift(-1)!
                    shifted = base_s.shift(-offset)
                    if boundary_mode == "zero_or_empty":
                        if pd.api.types.is_numeric_dtype(base_s):
                            shifted = shifted.fillna(0)
                        elif pd.api.types.is_bool_dtype(base_s):
                            shifted = shifted.fillna(False)
                        else:
                            shifted = shifted.fillna("")
                    elif boundary_mode == "nearest":
                        if offset < 0:
                            shifted = shifted.ffill()
                        else:
                            shifted = shifted.bfill()
                    eval_df[token_col] = shifted
                else:
                    eval_df[token_col] = np.nan

            res = evaluate_expression(eval_df, clean_expr)
            if not isinstance(res, pd.Series):
                res = pd.Series(res, index=part.index)
            return res

        # 2. Self-referencing optimizations for standard presets
        norm_upper = clean_expr.upper().replace(" ", "")

        # Preset A: Sequential ID -> [Row-1:Output] + 1
        if norm_upper in (f"[ROW-1:{output_field.upper()}]+1", f"1+[ROW-1:{output_field.upper()}]"):
            return pd.Series(np.arange(1, n_rows + 1), index=part.index)

        # Preset B: Cumulative Sum -> [Row-1:Output] + [Col]
        for offset_str, col_name in row_refs:
            if int(offset_str) == -1 and col_name == output_field:
                other_cols = [c for c in part.columns if norm_upper in (
                    f"[ROW-1:{output_field.upper()}]+[{c.upper()}]",
                    f"[{c.upper()}]+[ROW-1:{output_field.upper()}]"
                )]
                if other_cols:
                    s = pd.to_numeric(part[other_cols[0]], errors="coerce").fillna(0)
                    return s.cumsum()

        # Preset C: Fill Down / Forward Fill
        for col in part.columns:
            if (f"ISNULL([{col.upper()}])" in norm_upper and 
                (f"[ROW-1:{output_field.upper()}]" in norm_upper or f"[ROW-1:{col.upper()}]" in norm_upper)):
                return part[col].ffill()

        # 3. General recursive sequential loop
        out_vals = [None] * n_rows
        part_records = part.to_dict(orient="records")
        default_bound = 0 if boundary_mode == "zero_or_empty" else None

        for i in range(n_rows):
            row_dict = dict(part_records[i])
            for offset_str, col_name in row_refs:
                offset = int(offset_str)
                token_col = f"Row{'+' if offset > 0 else ''}{offset}:{col_name}"
                # In Multi-Row formula, [Row-1:Col] means 1 row prior (i - 1)
                # [Row+1:Col] means 1 row after (i + 1)
                ref_idx = i + offset
                if col_name == output_field:
                    if 0 <= ref_idx < i:
                        val = out_vals[ref_idx]
                    else:
                        if boundary_mode == "nearest" and i > 0 and ref_idx < 0:
                            val = out_vals[0]
                        else:
                            val = default_bound
                else:
                    if 0 <= ref_idx < n_rows:
                        val = part_records[ref_idx].get(col_name)
                    else:
                        if boundary_mode == "nearest":
                            clamp_idx = 0 if ref_idx < 0 else n_rows - 1
                            val = part_records[clamp_idx].get(col_name)
                        elif boundary_mode == "zero_or_empty":
                            sample_val = part_records[0].get(col_name)
                            if isinstance(sample_val, (int, float, np.number)):
                                val = 0
                            elif isinstance(sample_val, bool):
                                val = False
                            else:
                                val = ""
                        else:
                            val = None
                row_dict[token_col] = val

            single_df = pd.DataFrame([row_dict])
            row_res = evaluate_expression(single_df, clean_expr)
            if isinstance(row_res, pd.Series):
                out_vals[i] = row_res.iloc[0]
            else:
                out_vals[i] = row_res

        return pd.Series(out_vals, index=part.index)


# ----------------------------------------------------------------------
# 16. Multi-Field Formula Tool
# ----------------------------------------------------------------------
class MultiFieldFormulaNode(BaseNode):
    type_name = "multi_field_formula"
    category = "preparation"
    display_name = "Multi-Field Formula"
    description = "Apply formulas, cleaning, and transformations across multiple fields at once"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Multi-Field Formula: No input connected.")
        if df.empty:
            return {"O": df.copy()}

        out_df = df.copy()
        config = self.config or {}

        selected_fields = config.get("selected_fields") or config.get("fields") or []
        type_filter = str(config.get("field_type_filter", "all")).strip().lower()
        output_mode = str(config.get("output_mode", "update")).strip().lower()
        output_prefix = str(config.get("output_prefix", "") or "")
        output_suffix = str(config.get("output_suffix", "") or "")
        output_type = str(config.get("output_type", "none")).strip().lower()
        expr = str(config.get("expression", "")).strip()

        if not expr:
            return {"O": out_df}

        # Determine target fields
        target_cols = []
        for col in out_df.columns:
            # Check type filter
            if type_filter == "numeric" and not pd.api.types.is_numeric_dtype(out_df[col]):
                continue
            elif type_filter == "text" and not (pd.api.types.is_string_dtype(out_df[col]) or pd.api.types.is_object_dtype(out_df[col])):
                continue
            elif type_filter == "datetime" and not pd.api.types.is_datetime64_any_dtype(out_df[col]):
                continue
            elif type_filter == "boolean" and not pd.api.types.is_bool_dtype(out_df[col]):
                continue

            if selected_fields:
                if col in selected_fields:
                    target_cols.append(col)
            else:
                target_cols.append(col)

        if not target_cols:
            return {"O": out_df}

        for col in target_cols:
            # Substitute _CurrentField_ with [{col}] outside string literals
            # Substitute _CurrentFieldName_ with "{col}" outside string literals
            parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', expr)
            for i in range(0, len(parts), 2):
                chunk = parts[i]
                chunk = re.sub(r'\[\s*_CurrentField_\s*\]', f'[{col}]', chunk, flags=re.IGNORECASE)
                chunk = re.sub(r'\b_CurrentField_\b', f'[{col}]', chunk, flags=re.IGNORECASE)
                chunk = re.sub(r'\[\s*_CurrentFieldName_\s*\]', f'"{col}"', chunk, flags=re.IGNORECASE)
                chunk = re.sub(r'\b_CurrentFieldName_\b', f'"{col}"', chunk, flags=re.IGNORECASE)
                parts[i] = chunk
            col_expr = "".join(parts)

            try:
                res = evaluate_expression(out_df, col_expr)
                if not isinstance(res, pd.Series):
                    res = pd.Series(res, index=out_df.index)

                # Type conversion if specified
                if output_type and output_type not in ("none", "keep"):
                    if output_type in ("integer", "int64", "int32", "byte"):
                        res = pd.to_numeric(res, errors="coerce").round().astype("Int64")
                    elif output_type in ("float", "double", "fixeddecimal"):
                        res = pd.to_numeric(res, errors="coerce").astype(float)
                    elif output_type in ("string", "v_string", "v_wstring"):
                        res = res.astype(str).replace({"nan": None, "<NA>": None, "None": None})
                    elif output_type in ("boolean", "bool"):
                        res = res.astype(bool)
                    elif output_type == "date":
                        res = pd.to_datetime(res, errors="coerce").dt.strftime("%Y-%m-%d")
                    elif output_type in ("datetime", "timestamp"):
                        res = pd.to_datetime(res, errors="coerce")

                if output_mode == "create_new":
                    out_name = f"{output_prefix}{col}{output_suffix}"
                    out_df[out_name] = res
                else:
                    out_df[col] = res
            except Exception as e:
                raise NodeExecutionError(f"Multi-Field Formula error on column '{col}': {str(e)}")

        return {"O": out_df}

