import os
import re
import ast
import io
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from .base import BaseNode, NodeExecutionError, sanitize_dataframe

class JoinNode(BaseNode):
    type_name = "join"
    category = "join"
    display_name = "Join"
    description = "Join two inputs on key fields with dual-table column selection and J (joined), L (unmatched left), R (unmatched right) outputs"
    input_ports = ["L", "R"]
    output_ports = ["J", "L", "R"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        left_df = inputs.get("L")
        right_df = inputs.get("R")

        if left_df is None:
            raise NodeExecutionError("Join: Left input ('L') is not connected.")
        if right_df is None:
            raise NodeExecutionError("Join: Right input ('R') is not connected.")

        if not isinstance(left_df, pd.DataFrame):
            left_df = pd.DataFrame(left_df)
        if not isinstance(right_df, pd.DataFrame):
            right_df = pd.DataFrame(right_df)

        join_mode = self.config.get("join_mode", "keys")
        if join_mode == "record_position":
            right_rename_map = {c: f"Right_{c}" for c in right_df.columns if c in left_df.columns}
            right_renamed = right_df.rename(columns=right_rename_map)
            min_len = min(len(left_df), len(right_df))
            left_pos = left_df.iloc[:min_len].reset_index(drop=True)
            right_pos = right_renamed.iloc[:min_len].reset_index(drop=True)
            j_df = pd.concat([left_pos, right_pos], axis=1)
            l_df = left_df.iloc[min_len:].copy()
            r_df = right_df.iloc[min_len:].copy()
        else:
            join_keys = self.config.get("join_keys", [])
            if not join_keys:
                lks = self.config.get("left_keys", [])
                rks = self.config.get("right_keys", [])
                if lks and rks:
                    join_keys = [{"left_key": l, "right_key": r} for l, r in zip(lks, rks)]

            if not join_keys:
                raise NodeExecutionError("Join: No join keys configured. Select key fields from Left and Right inputs.")

            left_on = []
            right_on = []
            for pair in join_keys:
                lk = pair.get("left_key")
                rk = pair.get("right_key")
                if lk and rk and lk in left_df.columns and rk in right_df.columns:
                    left_on.append(lk)
                    right_on.append(rk)

            if not left_on:
                raise NodeExecutionError(
                    f"Join: Configured join keys not found in datasets. "
                    f"Left columns: {list(left_df.columns)}, Right columns: {list(right_df.columns)}"
                )

            left_copy = left_df.copy()
            right_copy = right_df.copy()

            # Build normalized matching keys while preserving null-relational semantics (null != null)
            ignore_case = self.config.get("ignore_case", True)
            temp_left_keys = []
            temp_right_keys = []

            for i, (lk, rk) in enumerate(zip(left_on, right_on)):
                temp_lk = f"__join_k_l_{i}__"
                temp_rk = f"__join_k_r_{i}__"

                s_l = left_copy[lk]
                s_r = right_copy[rk]

                # If both numeric or both datetime, keep native type for exact matching
                if pd.api.types.is_numeric_dtype(s_l) and pd.api.types.is_numeric_dtype(s_r):
                    left_copy[temp_lk] = pd.to_numeric(s_l, errors="coerce")
                    right_copy[temp_rk] = pd.to_numeric(s_r, errors="coerce")
                elif pd.api.types.is_datetime64_any_dtype(s_l) or pd.api.types.is_datetime64_any_dtype(s_r):
                    left_copy[temp_lk] = pd.to_datetime(s_l, errors="coerce")
                    right_copy[temp_rk] = pd.to_datetime(s_r, errors="coerce")
                else:
                    l_str = s_l.astype(str).str.strip()
                    if ignore_case:
                        l_str = l_str.str.lower()
                    left_copy[temp_lk] = l_str

                    r_str = s_r.astype(str).str.strip()
                    if ignore_case:
                        r_str = r_str.str.lower()
                    right_copy[temp_rk] = r_str

                # Ensure null keys never match (null != null relational semantics)
                l_ser = left_copy[temp_lk].astype(object)
                r_ser = right_copy[temp_rk].astype(object)
                l_null = s_l.isna() | l_ser.isna()
                r_null = s_r.isna() | r_ser.isna()
                if l_null.any():
                    l_ser[l_null] = [f"__null_l_{i}_{idx}__" for idx in range(l_null.sum())]
                if r_null.any():
                    r_ser[r_null] = [f"__null_r_{i}_{idx}__" for idx in range(r_null.sum())]
                left_copy[temp_lk] = l_ser
                right_copy[temp_rk] = r_ser

                temp_left_keys.append(temp_lk)
                temp_right_keys.append(temp_rk)

            # In Alteryx, colliding Right columns are prefixed with "Right_"
            right_rename_map = {}
            for col in right_df.columns:
                if col in left_df.columns:
                    right_rename_map[col] = f"Right_{col}"
            right_copy = right_copy.rename(columns=right_rename_map)

            # Suffix matching
            merged = pd.merge(
                left_copy,
                right_copy,
                left_on=temp_left_keys,
                right_on=temp_right_keys,
                how="outer",
                indicator=True
            )

            # Drop temporary join key columns
            temp_cols = temp_left_keys + temp_right_keys
            merged = merged.drop(columns=[c for c in temp_cols if c in merged.columns])

            j_mask = merged["_merge"] == "both"
            l_mask = merged["_merge"] == "left_only"
            r_mask = merged["_merge"] == "right_only"

            # 1. Base Joined DataFrame (contains all columns from both tables, right collisions prefixed)
            j_df = merged[j_mask].drop(columns=["_merge"]).copy()

            # 2. Unjoined Left (original Left columns only)
            l_df = merged[l_mask][list(left_df.columns)].copy()

            # 3. Unjoined Right (original Right columns only)
            # Revert the Right_ prefix for the unjoined R output to give analysts their original schema
            r_merged_cols = [right_rename_map.get(c, c) for c in right_df.columns]
            r_revert_map = {right_rename_map.get(c, c): c for c in right_df.columns}
            r_df = merged[r_mask][r_merged_cols].rename(columns=r_revert_map).copy()

        # 4. Embedded Select on Joined (J) Output
        select_fields = self.config.get("select_fields")
        if select_fields and isinstance(select_fields, list):
            unknown_item = next(
                (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown")),
                None
            )
            if unknown_item is not None:
                select_unknown = unknown_item.get("selected", True) if "selected" in unknown_item else unknown_item.get("keep", True)
            elif "select_unknown" in self.config:
                select_unknown = bool(self.config["select_unknown"])
            else:
                select_unknown = False

            keep_cols = []
            rename_map = {}
            type_map = {}
            processed_fields = set()

            for sf in select_fields:
                f_name = sf.get("field") or sf.get("original")
                if not f_name:
                    continue

                if f_name == "*Unknown":
                    if select_unknown:
                        for col in j_df.columns:
                            if col not in processed_fields:
                                keep_cols.append(col)
                                processed_fields.add(col)
                    continue

                if f_name not in j_df.columns:
                    continue

                processed_fields.add(f_name)
                # Check if field is selected/included
                is_selected = sf.get("selected", True) if "selected" in sf else sf.get("keep", True)
                if is_selected:
                    keep_cols.append(f_name)
                    new_name = sf.get("rename")
                    if new_name and new_name.strip():
                        rename_map[f_name] = new_name.strip()
                    target_type = sf.get("type")
                    if target_type and target_type != "none":
                        type_map[f_name] = target_type

            if select_unknown and unknown_item is None:
                for col in j_df.columns:
                    if col not in processed_fields:
                        keep_cols.append(col)
                        processed_fields.add(col)

            # Reorder and filter columns to match select_fields sequence
            j_df = j_df[[c for c in keep_cols if c in j_df.columns]].copy()

            # Apply data type casting if configured
            for col, dt in type_map.items():
                if col not in j_df.columns:
                    continue
                dt_low = str(dt).lower().strip()
                try:
                    if dt_low in ("int", "integer", "int64", "int32"):
                        j_df[col] = pd.to_numeric(j_df[col], errors="coerce").astype("Int64")
                    elif dt_low in ("float", "double", "numeric"):
                        j_df[col] = pd.to_numeric(j_df[col], errors="coerce")
                    elif dt_low in ("bool", "boolean"):
                        j_df[col] = j_df[col].astype(str).str.lower().isin(["true", "1", "t", "yes"])
                    elif dt_low in ("date", "datetime"):
                        j_df[col] = pd.to_datetime(j_df[col], errors="coerce")
                    elif dt_low in ("str", "string"):
                        j_df[col] = j_df[col].astype(str)
                except Exception:
                    pass

            # Apply renames
            if rename_map:
                j_df = j_df.rename(columns=rename_map)

        return {"J": sanitize_dataframe(j_df), "L": sanitize_dataframe(l_df), "R": sanitize_dataframe(r_df)}


# ----------------------------------------------------------------------
# 11. Union Tool
# ----------------------------------------------------------------------
class UnionNode(BaseNode):
    type_name = "union"
    category = "join"
    display_name = "Union"
    description = "Stack multiple datasets vertically by name or position"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        input_data = inputs.get("I")
        if input_data is None:
            raise NodeExecutionError("Union: No inputs connected.")

        dfs: List[pd.DataFrame] = []
        if isinstance(input_data, list):
            dfs = [d for d in input_data if isinstance(d, pd.DataFrame) and not d.empty]
        elif isinstance(input_data, pd.DataFrame):
            dfs = [input_data]

        if not dfs:
            return {"O": pd.DataFrame()}

        mode = self.config.get("mode", "by_name").lower()
        non_matching = self.config.get("non_matching", "all").lower()

        if mode == "by_position":
            base_cols = list(dfs[0].columns)
            aligned_dfs = []
            for d in dfs:
                d_copy = d.copy()
                d_copy.columns = base_cols[:len(d_copy.columns)] + [f"Col_{i}" for i in range(len(base_cols), len(d_copy.columns))]
                aligned_dfs.append(d_copy)
            res_df = pd.concat(aligned_dfs, ignore_index=True, sort=False)
        else:
            # By column name
            if non_matching == "error":
                first_cols = set(dfs[0].columns)
                for idx, d in enumerate(dfs[1:], 2):
                    diff = set(d.columns) ^ first_cols
                    if diff:
                        raise NodeExecutionError(f"Union: Input #{idx} has differing columns: {sorted(list(diff))}")
                res_df = pd.concat(dfs, ignore_index=True, sort=False)
            elif non_matching == "common_only":
                common_cols = set(dfs[0].columns)
                for d in dfs[1:]:
                    common_cols = common_cols.intersection(set(d.columns))
                common_list = [c for c in dfs[0].columns if c in common_cols]
                if not common_list:
                    res_df = pd.DataFrame()
                else:
                    res_df = pd.concat([d[common_list] for d in dfs], ignore_index=True, sort=False)
            else:
                res_df = pd.concat(dfs, ignore_index=True, sort=False)

        return {"O": res_df}


# ----------------------------------------------------------------------
# 12. Text Input Tool
# ----------------------------------------------------------------------

class FindReplaceNode(BaseNode):
    type_name = "find_replace"
    category = "join"
    display_name = "Find Replace"
    description = "Find data in one table and replace or append from a reference table"
    input_ports = ["F", "R"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        f_df = inputs.get("F")
        r_df = inputs.get("R")

        if f_df is None:
            raise NodeExecutionError("Find Replace: 'F' (Find) input is not connected.")
        if r_df is None:
            raise NodeExecutionError("Find Replace: 'R' (Replace) input is not connected.")

        find_field = self.config.get("find_field")
        find_value_field = self.config.get("find_value_field")

        if not find_field or find_field not in f_df.columns:
            raise NodeExecutionError(f"Find Replace: Find field '{find_field}' not found in Find dataset.")
        if not find_value_field or find_value_field not in r_df.columns:
            raise NodeExecutionError(f"Find Replace: Find Value field '{find_value_field}' not found in Replace dataset.")

        search_mode = self.config.get("search_mode", "entire_field")
        case_sensitive = self.config.get("case_sensitive", False)
        whole_word = self.config.get("whole_word", False)
        action = self.config.get("action", "replace")
        replace_with_field = self.config.get("replace_with_field")
        append_fields = self.config.get("append_fields", [])

        res_df = f_df.copy()

        if action == "replace":
            if not replace_with_field or replace_with_field not in r_df.columns:
                raise NodeExecutionError(f"Find Replace: Replace With field '{replace_with_field}' not found in Replace dataset.")

            if search_mode == "entire_field":
                if case_sensitive:
                    mapping = dict(zip(r_df[find_value_field].astype(str), r_df[replace_with_field]))
                    res_df[find_field] = res_df[find_field].astype(str).map(lambda v: mapping.get(v, v))
                else:
                    mapping = {str(k).lower(): v for k, v in zip(r_df[find_value_field], r_df[replace_with_field])}
                    res_df[find_field] = res_df[find_field].astype(str).map(lambda v: mapping.get(str(v).lower(), v))
            elif search_mode == "beginning":
                patterns = []
                for _, r_row in r_df.iterrows():
                    val = str(r_row[find_value_field])
                    rep = str(r_row[replace_with_field])
                    if val:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        pat = re.compile("^" + re.escape(val), flags)
                        patterns.append((pat, rep))

                def _replace_beginning(text):
                    s = str(text)
                    for pat, rep in patterns:
                        if pat.search(s):
                            return pat.sub(rep, s, count=1)
                    return s

                res_df[find_field] = res_df[find_field].apply(_replace_beginning)
            else:  # any_part
                patterns = []
                for _, r_row in r_df.iterrows():
                    val = str(r_row[find_value_field])
                    rep = str(r_row[replace_with_field])
                    if val:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        if whole_word:
                            pat = re.compile(r"\b" + re.escape(val) + r"\b", flags)
                        else:
                            pat = re.compile(re.escape(val), flags)
                        patterns.append((pat, rep))

                def _replace_any(text):
                    s = str(text)
                    for pat, rep in patterns:
                        s = pat.sub(rep, s)
                    return s

                res_df[find_field] = res_df[find_field].apply(_replace_any)

        elif action == "append":
            valid_appends = [c for c in append_fields if c in r_df.columns]
            if not valid_appends:
                valid_appends = [c for c in r_df.columns if c != find_value_field]

            if search_mode == "entire_field":
                r_lookup = r_df[[find_value_field] + valid_appends].drop_duplicates(subset=[find_value_field]).copy()
                if not case_sensitive:
                    res_df["__find_key__"] = res_df[find_field].astype(str).str.lower()
                    r_lookup["__find_key__"] = r_lookup[find_value_field].astype(str).str.lower()
                    merged = pd.merge(res_df, r_lookup.drop(columns=[find_value_field]), on="__find_key__", how="left", suffixes=("", "_R"))
                    res_df = merged.drop(columns=["__find_key__"])
                else:
                    res_df["__find_key__"] = res_df[find_field].astype(str)
                    r_lookup["__find_key__"] = r_lookup[find_value_field].astype(str)
                    merged = pd.merge(res_df, r_lookup.drop(columns=[find_value_field]), on="__find_key__", how="left", suffixes=("", "_R"))
                    res_df = merged.drop(columns=["__find_key__"])
            else:
                patterns = []
                for _, r_row in r_df.iterrows():
                    val = str(r_row[find_value_field])
                    if val:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        if search_mode == "beginning":
                            pat = re.compile("^" + re.escape(val), flags)
                        else:
                            pat = re.compile(r"\b" + re.escape(val) + r"\b", flags) if whole_word else re.compile(re.escape(val), flags)
                        patterns.append((pat, r_row))

                appended_data = {col: [] for col in valid_appends}
                for val in res_df[find_field]:
                    s = str(val)
                    found_row = None
                    for pat, r_row in patterns:
                        if pat.search(s):
                            found_row = r_row
                            break
                    for col in valid_appends:
                        appended_data[col].append(found_row[col] if found_row is not None else np.nan)

                for col in valid_appends:
                    target_col = col if col not in res_df.columns else f"{col}_R"
                    res_df[target_col] = appended_data[col]

        return {"O": res_df}


# ----------------------------------------------------------------------
# Append Fields Tool (Cartesian Join)
# ----------------------------------------------------------------------

class AppendFieldsNode(BaseNode):
    type_name = "append_fields"
    category = "join"
    display_name = "Append Fields"
    description = "Append fields from a Source stream to every record of a Target stream (Cartesian join)"
    input_ports = ["T", "S"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        t_df = inputs.get("T")
        s_df = inputs.get("S")

        # Fallback if connected with default generic 'I' port
        if t_df is None and "I" in inputs and s_df is not None:
            t_df = inputs.get("I")

        if t_df is None:
            raise NodeExecutionError("Append Fields: 'T' (Target) input is not connected.")
        if s_df is None:
            raise NodeExecutionError("Append Fields: 'S' (Source) input is not connected.")

        cartesian_mode = self.config.get("cartesian_mode", "error_16")  # "error_16", "warn_16", "allow_all"
        source_prefix = self.config.get("source_prefix", "Source_")

        if len(s_df) > 16:
            if cartesian_mode == "error_16":
                raise NodeExecutionError(
                    f"Append Fields: The Source input contains {len(s_df)} records, exceeding the limit of 16 records. "
                    "To allow large Cartesian joins, change 'Cartesian Mode' to 'Allow All Appends' in the configuration."
                )

        if t_df.empty or s_df.empty:
            target_cols = list(t_df.columns)
            source_cols = [f"{source_prefix}{c}" if c in target_cols else c for c in s_df.columns]
            combined_df = pd.DataFrame(columns=target_cols + source_cols)
            return {"O": sanitize_dataframe(combined_df)}

        # Rename colliding source columns
        renamed_s_df = s_df.copy()
        rename_map = {}
        for c in renamed_s_df.columns:
            if c in t_df.columns:
                rename_map[c] = f"{source_prefix}{c}"
        if rename_map:
            renamed_s_df = renamed_s_df.rename(columns=rename_map)

        # Cross join (Cartesian product)
        try:
            merged_df = t_df.merge(renamed_s_df, how="cross")
        except Exception:
            merged_df = t_df.assign(_cross_key=1).merge(
                renamed_s_df.assign(_cross_key=1),
                on="_cross_key"
            ).drop(columns=["_cross_key"])

        # Select & Rename fields if configured
        select_fields = self.config.get("select_fields", [])
        if select_fields and isinstance(select_fields, list):
            unknown_item = next(
                (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown")),
                None
            )
            if unknown_item is not None:
                select_unknown = unknown_item.get("selected", True) if "selected" in unknown_item else unknown_item.get("keep", True)
            elif "select_unknown" in self.config:
                select_unknown = bool(self.config["select_unknown"])
            else:
                select_unknown = False

            kept_cols = []
            rename_out = {}
            processed_fields = set()

            for item in select_fields:
                if not isinstance(item, dict):
                    continue
                f_name = item.get("field") or item.get("original")
                if not f_name:
                    continue
                if f_name == "*Unknown":
                    if select_unknown:
                        for col in merged_df.columns:
                            if col not in processed_fields:
                                kept_cols.append(col)
                                processed_fields.add(col)
                    continue
                if f_name not in merged_df.columns:
                    continue
                processed_fields.add(f_name)

                selected = item.get("selected", True) if "selected" in item else item.get("keep", True)
                rename = item.get("rename")
                if selected:
                    kept_cols.append(f_name)
                    if rename and rename != f_name:
                        rename_out[f_name] = rename

            if select_unknown and unknown_item is None:
                for col in merged_df.columns:
                    if col not in processed_fields:
                        kept_cols.append(col)
                        processed_fields.add(col)

            merged_df = merged_df[[c for c in kept_cols if c in merged_df.columns]]
            if rename_out:
                merged_df = merged_df.rename(columns=rename_out)

        return {"O": sanitize_dataframe(merged_df)}


# ----------------------------------------------------------------------
# 15. Join Multiple (Multi-Join) Tool (Alteryx Parity)
# ----------------------------------------------------------------------
class JoinMultipleNode(BaseNode):
    type_name = "join_multiple"
    category = "join"
    display_name = "Join Multiple"
    description = "Combine 2 or more datasets based on common field(s) or record position with embedded select filtering"
    input_ports = ["I"]
    output_ports = ["J"]

    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        input_data = inputs.get("I")
        if input_data is None:
            raise NodeExecutionError("Join Multiple: No inputs connected. Connect 2 or more datasets to join.")

        dfs: List[pd.DataFrame] = []
        if isinstance(input_data, list):
            dfs = [pd.DataFrame(d) if not isinstance(d, pd.DataFrame) else d.copy() for d in input_data if d is not None]
        elif isinstance(input_data, pd.DataFrame):
            dfs = [input_data.copy()]

        if not dfs:
            raise NodeExecutionError("Join Multiple: No inputs connected. Connect 2 or more datasets to join.")

        if len(dfs) == 1:
            return {"J": sanitize_dataframe(dfs[0])}

        join_mode = self.config.get("join_mode", "specific_fields")
        join_all_only = self.config.get("join_all_only", False)
        if "output_all" in self.config:
            join_all_only = not bool(self.config["output_all"])
        if "inner_join" in self.config:
            join_all_only = bool(self.config["inner_join"])

        ignore_case = self.config.get("ignore_case", True)

        # Map each column to its original input table index (1-based)
        column_sources: Dict[str, int] = {}

        if join_mode == "record_position":
            # 1. Join by Record Position
            aligned_dfs = []
            seen_cols = set()
            for idx, df in enumerate(dfs, 1):
                df_copy = df.copy()
                rename_map = {}
                for col in df_copy.columns:
                    target_name = col
                    if col in seen_cols:
                        target_name = f"Input{idx}_{col}"
                    rename_map[col] = target_name
                    seen_cols.add(target_name)
                    column_sources[target_name] = idx
                df_copy = df_copy.rename(columns=rename_map)
                aligned_dfs.append(df_copy)

            if join_all_only:
                min_len = min(len(d) for d in aligned_dfs)
                sliced = [d.iloc[:min_len].reset_index(drop=True) for d in aligned_dfs]
                merged_df = pd.concat(sliced, axis=1)
            else:
                max_len = max(len(d) for d in aligned_dfs)
                reindexed = [d.reindex(range(max_len)).reset_index(drop=True) for d in aligned_dfs]
                merged_df = pd.concat(reindexed, axis=1)

        else:
            # 2. Join by Specific Fields
            join_keys = self.config.get("join_keys", [])
            # Support alternate configurations (e.g. input_keys list of lists)
            if not join_keys and "input_keys" in self.config:
                raw_keys = self.config["input_keys"]
                if raw_keys and isinstance(raw_keys[0], list):
                    max_keys = max(len(k_list) for k_list in raw_keys)
                    join_keys = []
                    for k_idx in range(max_keys):
                        row_dict = {}
                        for in_idx, k_list in enumerate(raw_keys, 1):
                            if k_idx < len(k_list):
                                row_dict[str(in_idx)] = k_list[k_idx]
                        join_keys.append(row_dict)

            # Auto-infer matching columns across tables if join_keys not provided
            if not join_keys:
                common_cols = list(dfs[0].columns)
                for d in dfs[1:]:
                    common_cols = [c for c in common_cols if c in d.columns]
                if common_cols:
                    join_keys = [{str(i + 1): common_cols[0] for i in range(len(dfs))}]

            if not join_keys:
                col_summaries = [f"Input #{i+1}: {list(d.columns)}" for i, d in enumerate(dfs)]
                raise NodeExecutionError(
                    f"Join Multiple: No join keys configured. Select key fields for all connected inputs.\n"
                    + "\n".join(col_summaries)
                )

            # Prepare each DataFrame with normalized temporary join keys
            dfs_prepared = []
            seen_cols = set()

            for in_idx, df in enumerate(dfs, 1):
                df_prep = df.copy()

                # Record sources for initial table columns
                rename_map = {}
                for col in df_prep.columns:
                    target_name = col
                    if col in seen_cols:
                        target_name = f"Input{in_idx}_{col}"
                    rename_map[col] = target_name
                    seen_cols.add(target_name)
                    column_sources[target_name] = in_idx

                df_prep = df_prep.rename(columns=rename_map)

                # Build normalized join keys for this input
                for pair_idx, k_spec in enumerate(join_keys):
                    # Key can be specified as k_spec.get(str(in_idx)) or k_spec.get(f"key_{in_idx}") or k_spec["keys"][in_idx-1]
                    key_field = None
                    if isinstance(k_spec, dict):
                        key_field = k_spec.get(str(in_idx)) or k_spec.get(f"key_{in_idx}") or k_spec.get(f"input_{in_idx}")
                        if not key_field and "keys" in k_spec and isinstance(k_spec["keys"], list):
                            if in_idx - 1 < len(k_spec["keys"]):
                                key_field = k_spec["keys"][in_idx - 1]
                    elif isinstance(k_spec, (list, tuple)) and in_idx - 1 < len(k_spec):
                        key_field = k_spec[in_idx - 1]

                    if not key_field:
                        # Fallback to key field with same name as first input's key
                        first_key = join_keys[pair_idx].get("1") if isinstance(join_keys[pair_idx], dict) else None
                        if first_key and first_key in df.columns:
                            key_field = first_key

                    # Check in original df columns
                    orig_field = key_field
                    mapped_field = rename_map.get(orig_field, orig_field)
                    if not mapped_field or mapped_field not in df_prep.columns:
                        # Attempt case-insensitive match in df
                        for c in df.columns:
                            if str(c).strip().lower() == str(orig_field).strip().lower():
                                mapped_field = rename_map.get(c, c)
                                break

                    if not mapped_field or mapped_field not in df_prep.columns:
                        raise NodeExecutionError(
                            f"Join Multiple: Key field '{orig_field}' not found in Input #{in_idx}. "
                            f"Available columns: {list(df.columns)}"
                        )

                    temp_key = f"__multi_k_{pair_idx}__"
                    ser = df_prep[mapped_field]

                    if pd.api.types.is_numeric_dtype(ser):
                        df_prep[temp_key] = pd.to_numeric(ser, errors="coerce")
                    elif pd.api.types.is_datetime64_any_dtype(ser):
                        df_prep[temp_key] = pd.to_datetime(ser, errors="coerce")
                    else:
                        str_ser = ser.astype(str).str.strip()
                        if ignore_case:
                            str_ser = str_ser.str.lower()
                        df_prep[temp_key] = str_ser

                    # Relational null semantics: nulls never match nulls
                    null_mask = ser.isna() | df_prep[temp_key].isna()
                    if null_mask.any():
                        obj_ser = df_prep[temp_key].astype(object).copy()
                        obj_ser[null_mask] = [f"__null_{in_idx}_{pair_idx}_{k}__" for k in range(null_mask.sum())]
                        df_prep[temp_key] = obj_ser

                dfs_prepared.append(df_prep)

            # Perform multi-way merge across all inputs
            join_how = "inner" if join_all_only else "outer"
            num_keys = len(join_keys)
            key_cols = [f"__multi_k_{p}__" for p in range(num_keys)]

            merged_df = dfs_prepared[0]

            for next_idx in range(1, len(dfs_prepared)):
                next_df = dfs_prepared[next_idx]
                merged = pd.merge(
                    merged_df,
                    next_df,
                    on=key_cols,
                    how=join_how
                )
                merged_df = merged

            # Drop temporary join key columns
            merged_df = merged_df.drop(columns=[c for c in key_cols if c in merged_df.columns])

        # 3. Embedded Select processing (keep, rename, reorder, type casting)
        select_fields = self.config.get("select_fields", [])
        if select_fields and isinstance(select_fields, list):
            unknown_item = next(
                (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown")),
                None
            )
            if unknown_item is not None:
                select_unknown = unknown_item.get("selected", True) if "selected" in unknown_item else unknown_item.get("keep", True)
            elif "select_unknown" in self.config:
                select_unknown = bool(self.config["select_unknown"])
            else:
                select_unknown = False

            keep_cols = []
            rename_map = {}
            type_map = {}
            processed_fields = set()

            for sf in select_fields:
                if not isinstance(sf, dict):
                    continue
                f_name = sf.get("field") or sf.get("original")
                if not f_name:
                    continue

                if f_name == "*Unknown":
                    if select_unknown:
                        for col in merged_df.columns:
                            if col not in processed_fields:
                                keep_cols.append(col)
                                processed_fields.add(col)
                    continue

                if f_name not in merged_df.columns:
                    continue
                processed_fields.add(f_name)

                selected = sf.get("selected", True) if "selected" in sf else sf.get("keep", True)
                if selected:
                    keep_cols.append(f_name)
                    new_name = sf.get("rename")
                    if new_name and new_name.strip():
                        rename_map[f_name] = new_name.strip()
                    target_type = sf.get("type")
                    if target_type and target_type != "none":
                        type_map[f_name] = target_type

            if select_unknown and unknown_item is None:
                for col in merged_df.columns:
                    if col not in processed_fields:
                        keep_cols.append(col)
                        processed_fields.add(col)

            merged_df = merged_df[[c for c in keep_cols if c in merged_df.columns]].copy()

            for col, dt in type_map.items():
                if col not in merged_df.columns:
                    continue
                dt_low = str(dt).lower().strip()
                try:
                    if dt_low in ("int", "integer", "int64", "int32"):
                        merged_df[col] = pd.to_numeric(merged_df[col], errors="coerce").astype("Int64")
                    elif dt_low in ("float", "double", "numeric"):
                        merged_df[col] = pd.to_numeric(merged_df[col], errors="coerce")
                    elif dt_low in ("bool", "boolean"):
                        merged_df[col] = merged_df[col].astype(str).str.lower().isin(["true", "1", "t", "yes"])
                    elif dt_low in ("date", "datetime"):
                        merged_df[col] = pd.to_datetime(merged_df[col], errors="coerce")
                    elif dt_low in ("str", "string"):
                        merged_df[col] = merged_df[col].astype(str)
                except Exception:
                    pass

            if rename_map:
                # Update column_sources map for renamed columns
                for old_col, new_col in rename_map.items():
                    if old_col in column_sources:
                        column_sources[new_col] = column_sources.pop(old_col)
                merged_df = merged_df.rename(columns=rename_map)

        sanitized = sanitize_dataframe(merged_df)
        sanitized.attrs["column_sources"] = column_sources
        return {"J": sanitized}

