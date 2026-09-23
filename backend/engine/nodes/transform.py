import os
import re
import ast
import io
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from .base import BaseNode, NodeExecutionError, sanitize_dataframe

# 9. Summarize / Group By Tool
# ----------------------------------------------------------------------
class SummarizeNode(BaseNode):
    type_name = "summarize"
    category = "transform"
    display_name = "Summarize"
    description = "Group by fields and calculate aggregate metrics"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Summarize: No input connected.")

        actions = self.config.get("actions", [])
        if not actions:
            return {"O": df.copy()}

        group_cols = []
        agg_specs = []
        action_target_map = []  # tracks (action_idx, target_col_name) for final ordering

        for idx, act in enumerate(actions):
            field = act.get("field")
            action_type = act.get("action", "GroupBy")
            custom_out = str(act.get("output_name") or "").strip()

            if not field or field not in df.columns:
                continue

            act_lower = action_type.lower()
            if act_lower == "groupby":
                out_name = custom_out or field
                group_cols.append((idx, field, out_name))
            else:
                if custom_out:
                    out_name = custom_out
                elif act_lower == "count":
                    out_name = f"Count_{field}"
                elif act_lower in ("mean", "average", "avg"):
                    out_name = f"Avg_{field}"
                elif act_lower == "countdistinct":
                    out_name = f"Distinct_{field}"
                elif act_lower in ("countdistinctnonnull", "count_distinct_non_null"):
                    out_name = f"DistinctNonNull_{field}"
                elif act_lower in ("countnull", "count_null"):
                    out_name = f"Nulls_{field}"
                elif act_lower in ("countnonnull", "count_non_null"):
                    out_name = f"NonNulls_{field}"
                elif act_lower in ("countblank", "count_blank"):
                    out_name = f"Blank_{field}"
                elif act_lower in ("countnonblank", "count_non_blank"):
                    out_name = f"NonBlank_{field}"
                elif act_lower == "product":
                    out_name = f"Product_{field}"
                elif act_lower == "percentile":
                    pct_str = str(act.get("percentile", 50)).replace(".0", "")
                    out_name = f"Percentile_{pct_str}_{field}"
                elif act_lower == "longest":
                    out_name = f"Longest_{field}"
                elif act_lower == "shortest":
                    out_name = f"Shortest_{field}"
                elif act_lower in ("concatdistinct", "concatenate_distinct"):
                    out_name = f"ConcatDistinct_{field}"
                elif act_lower in ("concat", "concatenate"):
                    out_name = f"Concat_{field}"
                elif act_lower == "npv":
                    out_name = f"NPV_{field}"
                elif act_lower == "xnpv":
                    out_name = f"XNPV_{field}"
                elif act_lower == "irr":
                    out_name = f"IRR_{field}"
                elif act_lower == "xirr":
                    out_name = f"XIRR_{field}"
                elif act_lower == "mirr":
                    out_name = f"MIRR_{field}"
                else:
                    out_name = f"{action_type}_{field}"
                agg_specs.append((idx, field, action_type, out_name, act))

        if not group_cols and not agg_specs:
            return {"O": df.copy()}

        # Perform aggregation
        if group_cols:
            grp_keys = [f for _, f, _ in group_cols]
            grouped = df.groupby(grp_keys, as_index=False, dropna=False)

            # Planned target names for group keys
            target_grp_names = set(target or orig for _, orig, target in group_cols)

            if not agg_specs:
                res_df = grouped.first()
            else:
                agg_dict = {}
                used_names = set(grp_keys) | target_grp_names
                for idx, f, op, out_name, act in agg_specs:
                    pd_op = self._map_agg_op(op, act, df)
                    safe_name = out_name
                    counter = 2
                    while safe_name in used_names or safe_name in agg_dict:
                        safe_name = f"{out_name}_{counter}"
                        counter += 1
                    agg_dict[safe_name] = pd.NamedAgg(column=f, aggfunc=pd_op)
                    action_target_map.append((idx, safe_name))
                res_df = grouped.agg(**agg_dict)

            # Rename group columns if custom out_name given
            rename_grp = {}
            for idx, orig, target in group_cols:
                final_target = target or orig
                if target and orig != target:
                    counter = 2
                    while final_target in res_df.columns or final_target in rename_grp.values():
                        final_target = f"{target}_{counter}"
                        counter += 1
                    rename_grp[orig] = final_target
                action_target_map.append((idx, final_target))

            if rename_grp:
                res_df = res_df.rename(columns=rename_grp)

        else:
            # Overall summary without grouping
            res_dict = {}
            used_names = set()
            for idx, f, op, out_name, act in agg_specs:
                pd_op = self._map_agg_op(op, act, df)
                series = df[f]
                val = pd_op(series)

                safe_name = out_name
                counter = 2
                while safe_name in used_names or safe_name in res_dict:
                    safe_name = f"{out_name}_{counter}"
                    counter += 1
                used_names.add(safe_name)
                res_dict[safe_name] = [val]
                action_target_map.append((idx, safe_name))

            res_df = pd.DataFrame(res_dict)

        # Reorder columns to faithfully match the exact top-to-bottom order of configured actions
        action_target_map.sort(key=lambda x: x[0])
        ordered_cols = []
        for _, col in action_target_map:
            if col in res_df.columns and col not in ordered_cols:
                ordered_cols.append(col)
        for col in res_df.columns:
            if col not in ordered_cols:
                ordered_cols.append(col)
        res_df = res_df[ordered_cols]

        return {"O": sanitize_dataframe(res_df)}

    def _map_agg_op(self, op: str, act: Dict[str, Any] = None, full_df: pd.DataFrame = None):
        op_lower = (op or "").lower()
        act = act or {}

        def _parse_escape(txt):
            if not txt:
                return ""
            return str(txt).replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r").replace("\\s", " ")

        # 1. String Concatenation
        if op_lower in ("concat", "concatenate"):
            start = _parse_escape(act.get("start", ""))
            sep = _parse_escape(act.get("separator", ", "))
            end = _parse_escape(act.get("end", ""))
            return lambda s: f"{start}{sep.join(s.dropna().astype(str).tolist())}{end}" if not s.dropna().empty else ""

        if op_lower in ("concatdistinct", "concatenate_distinct", "concat_distinct"):
            start = _parse_escape(act.get("start", ""))
            sep = _parse_escape(act.get("separator", ", "))
            end = _parse_escape(act.get("end", ""))
            def _concat_dist(s):
                vals = s.dropna().astype(str).tolist()
                seen = set()
                u_vals = []
                for v in vals:
                    if v not in seen:
                        seen.add(v)
                        u_vals.append(v)
                return f"{start}{sep.join(u_vals)}{end}" if u_vals else ""
            return _concat_dist

        # 2. String Metrics
        if op_lower in ("longest",):
            def _longest(s):
                cs = s.dropna().astype(str)
                if cs.empty: return None
                lens = cs.str.len()
                return cs[lens == lens.max()].iloc[0]
            return _longest

        if op_lower in ("shortest",):
            def _shortest(s):
                cs = s.dropna().astype(str)
                if cs.empty: return None
                lens = cs.str.len()
                return cs[lens == lens.min()].iloc[0]
            return _shortest

        if op_lower in ("countblank", "count_blank"):
            return lambda s: int((s.notna() & (s.astype(str).str.strip() == "")).sum())

        if op_lower in ("countnonblank", "count_non_blank"):
            return lambda s: int((s.notna() & (s.astype(str).str.strip() != "")).sum())

        # 3. Counting Variants
        if op_lower in ("countnull", "count_null"):
            return lambda s: int(s.isna().sum())
        if op_lower in ("countnonnull", "count_non_null"):
            return lambda s: int(s.notna().sum())
        if op_lower in ("countdistinctnonnull", "count_distinct_non_null"):
            return lambda s: int(s.nunique(dropna=True))
        if op_lower in ("countdistinct", "distinct_count"):
            return lambda s: int(s.nunique(dropna=False))
        if op_lower == "count":
            return lambda s: len(s)

        # 4. Positionals
        if op_lower == "first":
            return lambda s: s.iloc[0] if len(s) > 0 else None
        if op_lower == "last":
            return lambda s: s.iloc[-1] if len(s) > 0 else None

        # 5. Numeric Aggregations (with optional Ignore 0's)
        ignore_zeros = act.get("ignore_zeros", False)

        def _clean_numeric(s):
            nums = pd.to_numeric(s, errors="coerce").dropna()
            if ignore_zeros:
                nums = nums[nums != 0]
            return nums

        if op_lower == "sum":
            return lambda s: float(_clean_numeric(s).sum()) if not _clean_numeric(s).empty else 0.0

        if op_lower in ("mean", "average", "avg"):
            return lambda s: float(_clean_numeric(s).mean()) if not _clean_numeric(s).empty else None

        if op_lower == "min":
            return lambda s: float(_clean_numeric(s).min()) if not _clean_numeric(s).empty else None

        if op_lower == "max":
            return lambda s: float(_clean_numeric(s).max()) if not _clean_numeric(s).empty else None

        if op_lower == "median":
            return lambda s: float(_clean_numeric(s).median()) if not _clean_numeric(s).empty else None

        if op_lower == "product":
            return lambda s: float(np.prod(_clean_numeric(s))) if not _clean_numeric(s).empty else None

        if op_lower == "percentile":
            pct = float(act.get("percentile", 50.0))
            return lambda s: float(np.percentile(_clean_numeric(s), pct)) if not _clean_numeric(s).empty else None

        if op_lower in ("stddev", "std"):
            return lambda s: float(_clean_numeric(s).std(ddof=1)) if len(_clean_numeric(s)) > 1 else 0.0

        if op_lower in ("variance", "var"):
            return lambda s: float(_clean_numeric(s).var(ddof=1)) if len(_clean_numeric(s)) > 1 else 0.0

        if op_lower == "mode":
            # Check if numeric or string
            def _mode(s):
                if pd.api.types.is_numeric_dtype(s):
                    nums = _clean_numeric(s)
                    if nums.empty: return None
                    vc = nums.value_counts()
                    max_c = vc.max()
                    return float(vc[vc == max_c].index.min())
                else:
                    cs = s.dropna().astype(str)
                    if cs.empty: return None
                    vc = cs.value_counts()
                    max_c = vc.max()
                    candidates = vc[vc == max_c].index.tolist()
                    return sorted(candidates)[0]
            return _mode

        # 6. Financial Calculations
        if op_lower == "npv":
            rate = float(act.get("discount_rate", 8.0)) / 100.0
            def _npv(s):
                vals = pd.to_numeric(s, errors="coerce").dropna().values
                if len(vals) == 0: return None
                t = np.arange(len(vals))
                return float(np.sum(vals / ((1.0 + rate) ** t)))
            return _npv

        if op_lower == "xnpv":
            rate = float(act.get("discount_rate", act.get("finance_rate", 8.0))) / 100.0
            date_col = act.get("date_field")
            def _xnpv(s):
                if full_df is None or not date_col or date_col not in full_df.columns:
                    return None
                dates = pd.to_datetime(full_df.loc[s.index, date_col], errors="coerce")
                mask = s.notna() & dates.notna()
                vals = pd.to_numeric(s[mask], errors="coerce").dropna().values
                clean_d = dates[mask]
                if len(vals) == 0: return None
                d0 = clean_d.iloc[0]
                diffs = (clean_d - d0).dt.days.values / 365.0
                return float(np.sum(vals / ((1.0 + rate) ** diffs)))
            return _xnpv

        if op_lower == "irr":
            def _irr(s):
                vals = pd.to_numeric(s, errors="coerce").dropna().values
                if len(vals) < 2 or (vals > 0).all() or (vals < 0).all():
                    return None
                r = 0.1
                for _ in range(80):
                    t = np.arange(len(vals))
                    f = np.sum(vals / ((1.0 + r) ** t))
                    df = np.sum(-t * vals / ((1.0 + r) ** (t + 1)))
                    if abs(df) < 1e-12: break
                    r_new = r - f / df
                    if abs(r_new - r) < 1e-6:
                        return float(round(r_new, 6))
                    r = r_new
                return float(round(r, 6))
            return _irr

        if op_lower == "xirr":
            date_col = act.get("date_field")
            def _xirr(s):
                if full_df is None or not date_col or date_col not in full_df.columns:
                    return None
                dates = pd.to_datetime(full_df.loc[s.index, date_col], errors="coerce")
                mask = s.notna() & dates.notna()
                vals = pd.to_numeric(s[mask], errors="coerce").dropna().values
                clean_d = dates[mask]
                if len(vals) < 2 or (vals > 0).all() or (vals < 0).all():
                    return None
                d0 = clean_d.iloc[0]
                diffs = (clean_d - d0).dt.days.values / 365.0
                r = 0.1
                for _ in range(80):
                    f = np.sum(vals / ((1.0 + r) ** diffs))
                    df = np.sum(-diffs * vals / ((1.0 + r) ** (diffs + 1)))
                    if abs(df) < 1e-12: break
                    r_new = r - f / df
                    if abs(r_new - r) < 1e-6:
                        return float(round(r_new, 6))
                    r = r_new
                return float(round(r, 6))
            return _xirr

        if op_lower == "mirr":
            fin_rate = float(act.get("finance_rate", 8.0)) / 100.0
            reinv_rate = float(act.get("reinvest_rate", 8.0)) / 100.0
            def _mirr(s):
                vals = pd.to_numeric(s, errors="coerce").dropna().values
                if len(vals) < 2: return None
                pos = vals.copy().astype(float)
                pos[pos < 0] = 0
                neg = vals.copy().astype(float)
                neg[neg > 0] = 0
                n = len(vals)
                t = np.arange(n)
                pv_neg = np.sum(neg / ((1.0 + fin_rate) ** t))
                fv_pos = np.sum(pos * ((1.0 + reinv_rate) ** (n - 1 - t)))
                if pv_neg == 0 or fv_pos <= 0: return None
                return float(round((-fv_pos / pv_neg) ** (1.0 / (n - 1)) - 1.0, 6))
            return _mirr

        return lambda s: len(s)


# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 16. Transpose Tool (Unpivot)
# ----------------------------------------------------------------------
class TransposeNode(BaseNode):
    type_name = "transpose"
    category = "transform"
    display_name = "Transpose"
    description = "Pivot wide data to tall format (Key Columns + Data Columns)"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Transpose: No input connected.")

        if df.empty:
            return {"O": df.copy()}

        key_columns = self.config.get("key_columns", []) or []
        data_columns = self.config.get("data_columns", []) or []
        name_column = str(self.config.get("name_column") or "Name").strip() or "Name"
        value_column = str(self.config.get("value_column") or "Value").strip() or "Value"
        missing_action = str(self.config.get("missing_columns_action", "ignore")).lower()

        # Check for missing fields if missing_action == 'error'
        if missing_action == "error":
            missing_keys = [c for c in key_columns if c not in df.columns]
            missing_data = [c for c in data_columns if c not in df.columns]
            all_missing = missing_keys + missing_data
            if all_missing:
                raise NodeExecutionError(
                    f"Transpose: Configured column(s) not found in input: {', '.join(all_missing)}"
                )

        valid_keys = [c for c in key_columns if c in df.columns]
        if data_columns:
            valid_data = [c for c in data_columns if c in df.columns]
        else:
            valid_data = [c for c in df.columns if c not in valid_keys]

        if not valid_data:
            raise NodeExecutionError("Transpose: No data columns selected or available to transpose.")

        try:
            melted = pd.melt(
                df,
                id_vars=valid_keys if valid_keys else None,
                value_vars=valid_data,
                var_name=name_column,
                value_name=value_column
            )
            return {"O": sanitize_dataframe(melted)}
        except Exception as e:
            raise NodeExecutionError(f"Transpose execution failed: {str(e)}")


# ----------------------------------------------------------------------
# 17. Cross Tab Tool (Pivot)
# ----------------------------------------------------------------------
def sanitize_alteryx_header(header_val: Any) -> str:
    """Sanitize column headers following Alteryx identifier conventions."""
    if header_val is None or pd.isna(header_val):
        return "Null"
    s = str(header_val).strip()
    if not s:
        return "Blank"
    # Replace whitespace and non-alphanumeric characters with underscore
    s = re.sub(r'[^a-zA-Z0-9_]', '_', s)
    # Collapse consecutive underscores
    s = re.sub(r'_+', '_', s)
    # Strip trailing underscores if longer than 1 character
    if len(s) > 1:
        s = s.rstrip('_')
    # If starting with a digit, prepend an underscore
    if s and s[0].isdigit():
        s = '_' + s
    return s or "_"


class CrossTabNode(BaseNode):
    type_name = "crosstab"
    category = "transform"
    display_name = "Cross Tab"
    description = "Pivot tall data to wide format (Group By, Column Headers, Values)"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        df = inputs.get("I")
        if df is None:
            raise NodeExecutionError("Cross Tab: No input connected.")

        if df.empty:
            return {"O": df.copy()}

        group_by = self.config.get("group_by", []) or []
        header_field = self.config.get("header_field")
        value_field = self.config.get("value_field")
        separator = str(self.config.get("separator", ", "))
        clean_headers = bool(self.config.get("clean_headers", True))

        if not header_field or header_field not in df.columns:
            raise NodeExecutionError(f"Cross Tab: Header field '{header_field}' not found in input data.")
        if not value_field or value_field not in df.columns:
            raise NodeExecutionError(f"Cross Tab: Value field '{value_field}' not found in input data.")

        # Determine aggregation methods: supports list 'agg_methods' or legacy scalar 'agg_func'
        agg_methods_cfg = self.config.get("agg_methods")
        if not agg_methods_cfg:
            legacy_func = self.config.get("agg_func", "sum")
            if isinstance(legacy_func, list):
                agg_methods_cfg = legacy_func
            elif isinstance(legacy_func, str):
                agg_methods_cfg = [legacy_func]
            else:
                agg_methods_cfg = ["sum"]

        normalized_methods = [str(m).strip().lower() for m in agg_methods_cfg if str(m).strip()]
        if not normalized_methods:
            normalized_methods = ["sum"]

        # Separate base aggregations from post-processing summaries/percentages
        summary_methods = {"total_row", "total_col", "pct_row", "pct_col"}
        base_methods = [m for m in normalized_methods if m not in summary_methods]
        if not base_methods:
            base_methods = ["sum"]

        # Setup working dataframe
        df_work = df.copy()

        # Handle Header field sanitization or string formatting
        if clean_headers:
            df_work["_pivot_header"] = df_work[header_field].apply(sanitize_alteryx_header)
        else:
            df_work["_pivot_header"] = df_work[header_field].apply(lambda x: "Null" if pd.isna(x) else str(x))

        # Preserve appearance order of headers
        unique_headers = list(dict.fromkeys(df_work["_pivot_header"].tolist()))

        # Handle Group By columns
        valid_groups = [c for c in group_by if c in df.columns]
        has_dummy_group = False
        if not valid_groups:
            valid_groups = ["_dummy_group_id"]
            df_work["_dummy_group_id"] = 1
            has_dummy_group = True

        prefix_map = {
            "sum": "Sum",
            "avg": "Avg",
            "mean": "Avg",
            "count": "Count",
            "count_non_null": "CountNonNull",
            "count_without_nulls": "CountNonNull",
            "min": "Min",
            "max": "Max",
            "first": "First",
            "last": "Last",
            "concat": "Concat",
        }

        should_prefix = len(base_methods) > 1

        pivoted_frames: List[pd.DataFrame] = []

        try:
            for bm in base_methods:
                if bm == "sum":
                    df_work["_val_num"] = pd.to_numeric(df_work[value_field], errors="coerce")
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values="_val_num",
                        aggfunc="sum",
                        fill_value=0
                    )
                elif bm in ("avg", "mean"):
                    df_work["_val_num"] = pd.to_numeric(df_work[value_field], errors="coerce")
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values="_val_num",
                        aggfunc="mean"
                    )
                elif bm == "count":
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values=value_field,
                        aggfunc=len,
                        fill_value=0
                    )
                elif bm in ("count_non_null", "count_without_nulls"):
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values=value_field,
                        aggfunc=lambda s: s.notna().sum(),
                        fill_value=0
                    )
                elif bm == "min":
                    val_conv = pd.to_numeric(df_work[value_field], errors="ignore")
                    df_work["_val_min"] = val_conv
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values="_val_min",
                        aggfunc="min"
                    )
                elif bm == "max":
                    val_conv = pd.to_numeric(df_work[value_field], errors="ignore")
                    df_work["_val_max"] = val_conv
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values="_val_max",
                        aggfunc="max"
                    )
                elif bm == "first":
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values=value_field,
                        aggfunc="first"
                    )
                elif bm == "last":
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values=value_field,
                        aggfunc="last"
                    )
                elif bm == "concat":
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values=value_field,
                        aggfunc=lambda s: separator.join(s.dropna().astype(str)),
                        fill_value=""
                    )
                else:
                    # Fallback to sum
                    df_work["_val_num"] = pd.to_numeric(df_work[value_field], errors="coerce")
                    piv = pd.pivot_table(
                        df_work,
                        index=valid_groups,
                        columns="_pivot_header",
                        values="_val_num",
                        aggfunc="sum",
                        fill_value=0
                    )

                # Reorder columns to match unique appearance order
                ordered_cols = [h for h in unique_headers if h in piv.columns]
                piv = piv.reindex(columns=ordered_cols)

                # Column naming
                prefix = f"{prefix_map.get(bm, bm.title())}_" if should_prefix else ""
                piv.columns = [f"{prefix}{c}" for c in piv.columns]

                # Row total calculation for this base pivot if requested
                if "total_row" in normalized_methods:
                    num_sub = piv.select_dtypes(include=[np.number])
                    if not num_sub.empty:
                        total_col_name = f"{prefix}Total" if should_prefix else "Total"
                        piv[total_col_name] = num_sub.sum(axis=1)

                # Row percentage calculation if requested
                if "pct_row" in normalized_methods:
                    num_sub = piv.select_dtypes(include=[np.number])
                    if not num_sub.empty:
                        row_sum = num_sub.sum(axis=1).replace(0, np.nan)
                        for col in num_sub.columns:
                            pct_name = f"PctRow_{col}"
                            piv[pct_name] = (num_sub[col] / row_sum * 100).round(2).fillna(0)

                # Column percentage calculation if requested
                if "pct_col" in normalized_methods:
                    num_sub = piv.select_dtypes(include=[np.number])
                    if not num_sub.empty:
                        col_sum = num_sub.sum(axis=0).replace(0, np.nan)
                        for col in num_sub.columns:
                            pct_name = f"PctCol_{col}"
                            piv[pct_name] = (num_sub[col] / col_sum[col] * 100).round(2).fillna(0)

                pivoted_frames.append(piv)

            # Combine all pivoted frames side by side
            combined_piv = pd.concat(pivoted_frames, axis=1)
            combined_piv.columns.name = None
            result_df = combined_piv.reset_index()

            if has_dummy_group:
                result_df = result_df.drop(columns=["_dummy_group_id"], errors="ignore")

            # Column total summary row if requested ('total_col')
            if "total_col" in normalized_methods and not result_df.empty:
                summary_row: Dict[str, Any] = {}
                is_first_group = True
                for g in valid_groups:
                    if not has_dummy_group and g in result_df.columns:
                        summary_row[g] = "Total" if is_first_group else ""
                        is_first_group = False
                for col in result_df.columns:
                    if col in valid_groups:
                        continue
                    if pd.api.types.is_numeric_dtype(result_df[col]):
                        summary_row[col] = result_df[col].sum()
                    else:
                        summary_row[col] = ""
                total_row_df = pd.DataFrame([summary_row])
                result_df = pd.concat([result_df, total_row_df], ignore_index=True)

            return {"O": sanitize_dataframe(result_df)}
        except NodeExecutionError:
            raise
        except Exception as e:
            raise NodeExecutionError(f"Cross Tab execution failed: {str(e)}")


# ----------------------------------------------------------------------
# Node Registry Mapping
# ----------------------------------------------------------------------
