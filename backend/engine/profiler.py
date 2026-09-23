"""
Data Profiling & Quality Engine.
Provides comprehensive data profiling, dataset health scores, automated Tukey IQR outlier detection,
string hygiene diagnostics, semantic pattern recognition, pairwise correlations,
and standalone HTML quality audit report generation.
"""
import re
import math
import html
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from backend.engine.nodes.base import infer_alteryx_type, map_alteryx_to_category, sanitize_dataframe

# Common semantic regex patterns
PATTERN_REGEXES = {
    "Email": re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"),
    "Phone": re.compile(r"^(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$"),
    "URL": re.compile(r"^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$"),
    "US ZIP": re.compile(r"^\d{5}(-\d{4})?$"),
    "UUID": re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
    "IPv4": re.compile(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"),
    "ISO Date": re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)?$"),
}


def _to_float(v: Any, digits: int = 4) -> Optional[float]:
    """Safe float conversion avoiding NaNs and Infs."""
    if v is None or pd.isna(v) or np.isinf(v) or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(round(float(v), digits))
    except Exception:
        return None


def format_bytes(byte_count: int) -> str:
    """Human-friendly byte size format."""
    if byte_count < 1024:
        return f"{byte_count} B"
    elif byte_count < 1024 * 1024:
        return f"{byte_count / 1024:.1f} KB"
    elif byte_count < 1024 * 1024 * 1024:
        return f"{byte_count / (1024 * 1024):.1f} MB"
    else:
        return f"{byte_count / (1024 * 1024 * 1024):.2f} GB"


def compute_dataset_profile(df: pd.DataFrame, max_correlation_cols: int = 15) -> Dict[str, Any]:
    """
    Computes a comprehensive, superior data profile for a given DataFrame.
    Includes overall Health Score, Quad-Color quality distribution, Outlier bounds,
    String Hygiene analysis, Semantic Pattern inference, and Correlation matrix.
    """
    if not isinstance(df, pd.DataFrame):
        return {"available": False, "message": "Input is not a valid DataFrame."}

    df = sanitize_dataframe(df)
    total_rows = len(df)
    total_cols = len(df.columns)

    if total_rows == 0 or total_cols == 0:
        return {
            "available": True,
            "total_rows": total_rows,
            "total_columns": total_cols,
            "total_cells": 0,
            "memory_bytes": 0,
            "memory_formatted": "0 B",
            "duplicate_rows_count": 0,
            "duplicate_rows_pct": 0.0,
            "missing_cells_count": 0,
            "missing_cells_pct": 0.0,
            "composite_health_score": 100.0,
            "health_grade": "A",
            "health_penalties": {"completeness": 0.0, "uniqueness": 0.0, "hygiene": 0.0, "outliers": 0.0},
            "key_candidates": [],
            "columns": [],
            "correlations": {"columns": [], "matrix": {}, "top_correlations": []}
        }

    # 1. Dataset Overview & Memory
    memory_bytes = int(df.memory_usage(deep=True).sum()) if total_rows > 0 else 0
    total_cells = total_rows * total_cols
    missing_cells = int(df.isna().sum().sum())
    missing_cells_pct = round((missing_cells / total_cells * 100.0), 2) if total_cells > 0 else 0.0

    # Duplicates check (sample if large to keep snappy)
    if total_rows > 50000:
        dup_sample = df.sample(n=20000, random_state=42)
        sample_dups = int(dup_sample.duplicated().sum())
        duplicate_rows_count = int(round((sample_dups / 20000) * total_rows))
        duplicate_rows_pct = round((sample_dups / 20000 * 100.0), 2)
    else:
        duplicate_rows_count = int(df.duplicated().sum())
        duplicate_rows_pct = round((duplicate_rows_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

    # Sub-sample for expensive string regex & pairwise correlations on big tables
    use_sample = total_rows > 25000
    sample_df = df.sample(n=min(25000, total_rows), random_state=42) if use_sample else df

    columns_profile = []
    key_candidates = []
    total_whitespace_cells = 0
    total_outlier_cells = 0

    # 2. Per-Column Diagnostics
    for i, col in enumerate(df.columns):
        series = df.iloc[:, i]
        col_name = str(col)
        alteryx_type = infer_alteryx_type(series)
        category = map_alteryx_to_category(alteryx_type)

        null_count = int(series.isna().sum())
        null_pct = round((null_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

        # Cardinality
        unique_count = int(series.nunique(dropna=True))
        unique_pct = round((unique_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

        if null_count == 0 and unique_count == total_rows:
            key_candidates.append(col_name)

        # Whitespace / blanks (for string/object series)
        blank_count = 0
        leading_space_count = 0
        trailing_space_count = 0
        double_space_count = 0
        non_printable_count = 0
        mixed_casing_detected = False
        mixed_casing_examples = []
        inferred_patterns = []

        # Outliers
        outlier_count = 0
        outlier_pct = 0.0
        num_stats = {}
        date_stats = {}
        bool_stats = {}
        str_stats = {}
        histogram_bins = []

        is_numeric = category == "numeric" and not pd.api.types.is_bool_dtype(series)
        is_string = category == "string"
        is_datetime = category == "datetime" or pd.api.types.is_datetime64_any_dtype(series)
        is_bool = category == "bool" or pd.api.types.is_bool_dtype(series)

        # --- A. NUMERIC PROFILING ---
        if is_numeric:
            non_null_num = pd.to_numeric(series.dropna(), errors="coerce").dropna()
            non_null_cnt = len(non_null_num)

            if non_null_cnt > 0:
                val_min = _to_float(non_null_num.min())
                val_max = _to_float(non_null_num.max())
                val_mean = _to_float(non_null_num.mean())
                val_median = _to_float(non_null_num.median())
                val_std = _to_float(non_null_num.std()) if non_null_cnt > 1 else 0.0
                val_var = _to_float(non_null_num.var()) if non_null_cnt > 1 else 0.0
                val_range = _to_float(val_max - val_min) if val_max is not None and val_min is not None else 0.0

                # Quartiles & IQR
                q1 = _to_float(non_null_num.quantile(0.25))
                q3 = _to_float(non_null_num.quantile(0.75))
                iqr = _to_float(q3 - q1) if q1 is not None and q3 is not None else 0.0

                # Outlier detection via Tukey's IQR rule
                if iqr is not None and iqr > 0:
                    lower_fence = _to_float(q1 - 1.5 * iqr)
                    upper_fence = _to_float(q3 + 1.5 * iqr)
                    lower_outliers = int((non_null_num < lower_fence).sum())
                    upper_outliers = int((non_null_num > upper_fence).sum())
                    outlier_count = lower_outliers + upper_outliers
                else:
                    lower_fence = val_min
                    upper_fence = val_max
                    lower_outliers = 0
                    upper_outliers = 0
                    outlier_count = 0

                outlier_pct = round((outlier_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0
                total_outlier_cells += outlier_count

                # Z-score extreme outliers (|z| > 3)
                zscore_outliers_count = 0
                if val_std and val_std > 0:
                    z_scores = (non_null_num - val_mean) / val_std
                    zscore_outliers_count = int((z_scores.abs() > 3).sum())

                # Skewness & Kurtosis
                skew = _to_float(non_null_num.skew()) if non_null_cnt >= 3 else 0.0
                kurt = _to_float(non_null_num.kurt()) if non_null_cnt >= 4 else 0.0

                # Zeros & Negatives
                zeros_count = int((non_null_num == 0).sum())
                zeros_pct = round((zeros_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0
                negatives_count = int((non_null_num < 0).sum())
                negatives_pct = round((negatives_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

                num_stats = {
                    "min": val_min,
                    "max": val_max,
                    "range": val_range,
                    "mean": val_mean,
                    "median": val_median,
                    "std": val_std,
                    "variance": val_var,
                    "q1": q1,
                    "q3": q3,
                    "iqr": iqr,
                    "lower_fence": lower_fence,
                    "upper_fence": upper_fence,
                    "outlier_count": outlier_count,
                    "outlier_percent": outlier_pct,
                    "outliers_lower_count": lower_outliers,
                    "outliers_upper_count": upper_outliers,
                    "zscore_outliers_count": zscore_outliers_count,
                    "skewness": skew,
                    "kurtosis": kurt,
                    "zeros_count": zeros_count,
                    "zeros_percent": zeros_pct,
                    "negatives_count": negatives_count,
                    "negatives_percent": negatives_pct,
                }

                # 12-bin histogram
                bin_cnt = min(12, max(1, len(non_null_num.unique())))
                try:
                    counts, bin_edges = np.histogram(non_null_num, bins=bin_cnt)
                    for b in range(len(counts)):
                        b_start = _to_float(bin_edges[b])
                        b_end = _to_float(bin_edges[b + 1])
                        c = int(counts[b])
                        histogram_bins.append({
                            "bin_start": b_start,
                            "bin_end": b_end,
                            "count": c,
                            "percent": round((c / total_rows * 100.0), 1) if total_rows > 0 else 0.0,
                            "label": f"{b_start} - {b_end}"
                        })
                except Exception:
                    pass

        # --- B. STRING / TEXT PROFILING ---
        elif is_string or series.dtype == object:
            non_null_str = series.dropna().astype(str)
            non_null_cnt = len(non_null_str)

            if non_null_cnt > 0:
                lengths = non_null_str.str.len()
                min_len = int(lengths.min())
                max_len = int(lengths.max())
                avg_len = round(float(lengths.mean()), 1)

                # Whitespace and Hygiene checks
                blank_count = int((non_null_str.str.strip() == "").sum())
                total_whitespace_cells += blank_count

                leading_space_count = int(non_null_str.str.startswith((" ", "\t")).sum())
                trailing_space_count = int(non_null_str.str.endswith((" ", "\t")).sum())
                double_space_count = int(non_null_str.str.contains(r"\s{2,}", regex=True).sum())
                non_printable_count = int(non_null_str.str.contains(r"[\x00-\x1f\x7f-\x9f]", regex=True).sum())

                # Mixed casing detection (detects when words appear in different casings, e.g. "Active" vs "active")
                sample_str = sample_df.iloc[:, i].dropna().astype(str)
                val_counts_raw = sample_str.value_counts().head(50)
                lowered_map: Dict[str, List[str]] = {}
                for v in val_counts_raw.index:
                    lv = v.strip().lower()
                    if lv:
                        lowered_map.setdefault(lv, []).append(v)
                for lv, orig_variants in lowered_map.items():
                    if len(orig_variants) > 1:
                        mixed_casing_detected = True
                        mixed_casing_examples.append(" / ".join(orig_variants[:3]))
                        if len(mixed_casing_examples) >= 3:
                            break

                # Pattern recognition inference on sample
                for pat_name, pat_regex in PATTERN_REGEXES.items():
                    try:
                        matches = int(sample_str.str.match(pat_regex).sum())
                        if matches > 0:
                            m_pct = round((matches / len(sample_str) * 100.0), 1)
                            if m_pct >= 20.0 or matches >= 5:
                                inferred_patterns.append({
                                    "pattern": pat_name,
                                    "count": int(round((matches / len(sample_str)) * total_rows)),
                                    "percent": m_pct
                                })
                    except Exception:
                        pass

                top_vc = non_null_str.value_counts().head(10)
                top_values = []
                for k, v in top_vc.items():
                    c = int(v)
                    pct = round((c / total_rows * 100.0), 1) if total_rows > 0 else 0.0
                    top_values.append({"value": str(k), "count": c, "percent": pct})
                    histogram_bins.append({
                        "value": str(k),
                        "count": c,
                        "percent": pct,
                        "label": str(k)[:18] + ("..." if len(str(k)) > 18 else "")
                    })

                str_stats = {
                    "min_length": min_len,
                    "max_length": max_len,
                    "avg_length": avg_len,
                    "leading_whitespace_count": leading_space_count,
                    "leading_whitespace_percent": round((leading_space_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0,
                    "trailing_whitespace_count": trailing_space_count,
                    "trailing_whitespace_percent": round((trailing_space_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0,
                    "consecutive_spaces_count": double_space_count,
                    "non_printable_count": non_printable_count,
                    "mixed_casing_detected": mixed_casing_detected,
                    "mixed_casing_examples": mixed_casing_examples,
                    "inferred_patterns": inferred_patterns,
                    "top_values": top_values,
                }

        # --- C. DATETIME PROFILING ---
        elif is_datetime:
            try:
                dt_series = pd.to_datetime(series.dropna(), errors="coerce").dropna()
                if not dt_series.empty:
                    d_min = dt_series.min()
                    d_max = dt_series.max()
                    span_days = (d_max - d_min).days

                    # Day of week distribution
                    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                    dow_counts = dt_series.dt.dayofweek.value_counts().to_dict()
                    dow_dist = [{"day": dow_names[d], "count": int(dow_counts.get(d, 0))} for d in range(7)]

                    # Month distribution
                    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                    m_counts = dt_series.dt.month.value_counts().to_dict()
                    month_dist = [{"month": month_names[m - 1], "count": int(m_counts.get(m, 0))} for m in range(1, 13) if m in m_counts]

                    date_stats = {
                        "earliest": str(d_min)[:19],
                        "latest": str(d_max)[:19],
                        "span_days": span_days,
                        "day_of_week": dow_dist,
                        "months": month_dist,
                    }

                    for d in dow_dist:
                        histogram_bins.append({
                            "value": d["day"],
                            "count": d["count"],
                            "percent": round((d["count"] / total_rows * 100.0), 1) if total_rows > 0 else 0.0,
                            "label": d["day"]
                        })
            except Exception:
                pass

        # --- D. BOOLEAN PROFILING ---
        elif is_bool:
            non_null_b = series.dropna()
            true_count = int(non_null_b.astype(bool).sum())
            false_count = len(non_null_b) - true_count
            bool_stats = {
                "true_count": true_count,
                "true_percent": round((true_count / total_rows * 100.0), 1) if total_rows > 0 else 0.0,
                "false_count": false_count,
                "false_percent": round((false_count / total_rows * 100.0), 1) if total_rows > 0 else 0.0
            }
            histogram_bins = [
                {"value": "True", "count": true_count, "percent": bool_stats["true_percent"], "label": "True"},
                {"value": "False", "count": false_count, "percent": bool_stats["false_percent"], "label": "False"}
            ]

        # Quad-Color Segment Counts (summing up to total_rows)
        # 1. Null / Missing (Gray)
        # 2. Whitespace / Blank (Yellow)
        # 3. Outlier / Anomaly (Red)
        # 4. OK / Valid (Green)
        whitespace_count = blank_count
        effective_outlier_count = min(outlier_count, max(0, total_rows - null_count - whitespace_count))
        ok_count = max(0, total_rows - null_count - whitespace_count - effective_outlier_count)

        ok_pct = round((ok_count / total_rows * 100.0), 2) if total_rows > 0 else 100.0
        null_pct = round((null_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0
        ws_pct = round((whitespace_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0
        out_pct = round((effective_outlier_count / total_rows * 100.0), 2) if total_rows > 0 else 0.0

        # Column Health Score (0-100)
        col_health = 100.0
        col_health -= (null_pct * 0.5)
        col_health -= (ws_pct * 0.4)
        col_health -= (out_pct * 0.25)
        if leading_space_count > 0 or trailing_space_count > 0:
            col_health -= 5.0
        if mixed_casing_detected:
            col_health -= 5.0
        col_health = max(0.0, min(100.0, round(col_health, 1)))

        semantic_type = None
        if str_stats and str_stats.get("inferred_patterns"):
            semantic_type = str_stats["inferred_patterns"][0]["pattern"]

        col_dict = {
            "name": col_name,
            "dtype": alteryx_type,
            "raw_dtype": str(series.dtype),
            "category": category,
            "total_rows": total_rows,
            "health_score": col_health,
            "semantic_type": semantic_type,
            "unique_count": unique_count,
            "unique_percent": unique_pct,
            "is_key_candidate": (null_count == 0 and unique_count == total_rows),
            "quality": {
                "ok_count": ok_count,
                "ok_percent": ok_pct,
                "whitespace_count": whitespace_count,
                "whitespace_percent": ws_pct,
                "outlier_count": effective_outlier_count,
                "outlier_percent": out_pct,
                "null_count": null_count,
                "null_percent": null_pct,
            },
            "histogram": histogram_bins,
            "numeric_stats": num_stats if is_numeric else None,
            "string_stats": str_stats if is_string or series.dtype == object else None,
            "datetime_stats": date_stats if is_datetime else None,
            "boolean_stats": bool_stats if is_bool else None,
        }

        # Backwards compatible top-level stat keys for existing cards
        col_dict["null_count"] = null_count
        col_dict["null_percent"] = null_pct
        col_dict["empty_count"] = whitespace_count
        col_dict["empty_percent"] = ws_pct
        col_dict["ok_count"] = ok_count
        col_dict["ok_percent"] = ok_pct
        col_dict["is_numeric"] = is_numeric
        col_dict["is_datetime"] = is_datetime

        if is_numeric and num_stats:
            col_dict.update({
                "min": num_stats.get("min"),
                "max": num_stats.get("max"),
                "mean": num_stats.get("mean"),
                "median": num_stats.get("median"),
                "std": num_stats.get("std"),
            })
        if (is_string or series.dtype == object) and str_stats and str_stats.get("top_values"):
            col_dict["top_values"] = str_stats["top_values"]

        columns_profile.append(col_dict)

    # 3. Pairwise Pearson Correlation Matrix for numeric columns
    numeric_cols = [c["name"] for c in columns_profile if c["category"] == "numeric"][:max_correlation_cols]
    corr_matrix: Dict[str, Dict[str, Optional[float]]] = {}
    top_correlations: List[Dict[str, Any]] = []

    if len(numeric_cols) >= 2:
        try:
            num_sub_df = sample_df[numeric_cols].apply(pd.to_numeric, errors="coerce")
            corr_df = num_sub_df.corr(method="pearson")

            for c1 in numeric_cols:
                corr_matrix[c1] = {}
                for c2 in numeric_cols:
                    val = corr_df.loc[c1, c2] if c1 in corr_df.index and c2 in corr_df.columns else None
                    corr_matrix[c1][c2] = _to_float(val, digits=3)

            # Extract strongest non-self correlations
            pairs_seen = set()
            for c1 in numeric_cols:
                for c2 in numeric_cols:
                    if c1 != c2:
                        pair_key = tuple(sorted([c1, c2]))
                        if pair_key not in pairs_seen:
                            pairs_seen.add(pair_key)
                            r_val = corr_matrix[c1].get(c2)
                            if r_val is not None and not math.isnan(r_val):
                                top_correlations.append({
                                    "col1": c1,
                                    "col2": c2,
                                    "r": r_val,
                                    "abs_r": abs(r_val),
                                    "direction": "positive" if r_val > 0 else "negative"
                                })
            top_correlations.sort(key=lambda x: x["abs_r"], reverse=True)
            top_correlations = top_correlations[:15]
        except Exception:
            pass

    # 4. Composite Dataset Health Score & Letter Grade
    # Weighted calculation: Completeness (40%), Uniqueness (20%), Conformance/Outliers (20%), String Hygiene (20%)
    penalties = {}
    completeness_penalty = min(40.0, missing_cells_pct * 0.8)
    uniqueness_penalty = min(20.0, duplicate_rows_pct * 0.4)
    outlier_rate = (total_outlier_cells / total_cells * 100.0) if total_cells > 0 else 0.0
    conformance_penalty = min(20.0, outlier_rate * 0.8)
    hygiene_rate = (total_whitespace_cells / total_cells * 100.0) if total_cells > 0 else 0.0
    hygiene_penalty = min(20.0, hygiene_rate * 1.0)

    penalties["completeness"] = round(completeness_penalty, 1)
    penalties["uniqueness"] = round(uniqueness_penalty, 1)
    penalties["conformance"] = round(conformance_penalty, 1)
    penalties["hygiene"] = round(hygiene_penalty, 1)

    total_penalty = completeness_penalty + uniqueness_penalty + conformance_penalty + hygiene_penalty
    composite_health = max(0.0, min(100.0, round(100.0 - total_penalty, 1)))

    if composite_health >= 90.0:
        health_grade = "A"
    elif composite_health >= 80.0:
        health_grade = "B"
    elif composite_health >= 70.0:
        health_grade = "C"
    elif composite_health >= 60.0:
        health_grade = "D"
    else:
        health_grade = "F"

    return {
        "available": True,
        "total_rows": total_rows,
        "total_columns": total_cols,
        "total_cells": total_cells,
        "memory_bytes": memory_bytes,
        "memory_formatted": format_bytes(memory_bytes),
        "duplicate_rows_count": duplicate_rows_count,
        "duplicate_rows_pct": duplicate_rows_pct,
        "missing_cells_count": missing_cells,
        "missing_cells_pct": missing_cells_pct,
        "composite_health_score": composite_health,
        "health_score": composite_health,
        "health_grade": health_grade,
        "health_penalties": penalties,
        "key_candidates": key_candidates,
        "columns": columns_profile,
        "correlations": {
            "columns": numeric_cols,
            "matrix": corr_matrix,
            "top_correlations": top_correlations
        }
    }


def generate_html_report(profile_data: Dict[str, Any], title: str = "Data Quality Audit Report") -> str:
    """
    Generates a beautiful, standalone, responsive HTML Quality Audit Report.
    Embeds all CSS and interactive scripts with zero external dependencies.
    """
    total_rows = profile_data.get("total_rows", 0)
    total_cols = profile_data.get("total_columns", 0)
    health_score = profile_data.get("composite_health_score", 100.0)
    health_grade = profile_data.get("health_grade", "A")
    mem_str = profile_data.get("memory_formatted", "0 B")
    dup_rows = profile_data.get("duplicate_rows_count", 0)
    dup_pct = profile_data.get("duplicate_rows_pct", 0.0)
    missing_cells = profile_data.get("missing_cells_count", 0)
    missing_pct = profile_data.get("missing_cells_pct", 0.0)
    key_candidates = profile_data.get("key_candidates", [])
    columns = profile_data.get("columns", [])
    correlations = profile_data.get("correlations", {}).get("top_correlations", [])

    grade_colors = {
        "A": "#22c55e",
        "B": "#3b82f6",
        "C": "#f59e0b",
        "D": "#f97316",
        "F": "#ef4444"
    }
    accent_color = grade_colors.get(health_grade, "#3b82f6")

    col_rows_html = []
    for c in columns:
        q = c.get("quality", {})
        ok_p = q.get("ok_percent", 100.0)
        ws_p = q.get("whitespace_percent", 0.0)
        out_p = q.get("outlier_percent", 0.0)
        null_p = q.get("null_percent", 0.0)

        # Ribbon SVG bar
        ribbon_html = f"""
        <div class="q-ribbon" title="OK: {ok_p}% | Space: {ws_p}% | Outlier: {out_p}% | Null: {null_p}%">
          <div class="q-seg q-ok" style="width: {ok_p}%"></div>
          <div class="q-seg q-ws" style="width: {ws_p}%"></div>
          <div class="q-seg q-out" style="width: {out_p}%"></div>
          <div class="q-seg q-null" style="width: {null_p}%"></div>
        </div>
        """

        stats_summary = ""
        if c.get("numeric_stats"):
            ns = c["numeric_stats"]
            stats_summary = f"Range: [{ns.get('min')}, {ns.get('max')}] | Mean: {ns.get('mean')} | Outliers: {ns.get('outlier_count')} ({ns.get('outlier_percent')}%)"
        elif c.get("string_stats"):
            ss = c["string_stats"]
            stats_summary = f"Len: {ss.get('min_length')}..{ss.get('max_length')} (Avg {ss.get('avg_length')})"
            if ss.get("mixed_casing_detected"):
                stats_summary += " | <span style='color: #f59e0b;'>Mixed Casing</span>"
            if ss.get("inferred_patterns"):
                pats = ", ".join([p["pattern"] for p in ss["inferred_patterns"][:2]])
                stats_summary += f" | <span style='color: #38bdf8;'>{pats}</span>"
        elif c.get("datetime_stats"):
            ds = c["datetime_stats"]
            stats_summary = f"Span: {ds.get('earliest')} to {ds.get('latest')} ({ds.get('span_days')} days)"

        row_html = f"""
        <tr>
          <td><b>{html.escape(c.get('name', ''))}</b></td>
          <td><span class="type-pill">{html.escape(c.get('dtype', ''))}</span></td>
          <td><b>{c.get('health_score', 100)}%</b></td>
          <td>{ribbon_html}</td>
          <td>{c.get('unique_count', 0):,} ({c.get('unique_percent', 0)}%)</td>
          <td>{stats_summary}</td>
        </tr>
        """
        col_rows_html.append(row_html)

    corr_rows_html = []
    for cr in correlations[:8]:
        dir_color = "#22c55e" if cr["r"] > 0 else "#ef4444"
        dir_icon = "&uarr;" if cr["r"] > 0 else "&darr;"
        corr_rows_html.append(f"""
        <tr>
          <td>{html.escape(cr['col1'])}</td>
          <td>{html.escape(cr['col2'])}</td>
          <td style="color: {dir_color}; font-weight: 700;">{dir_icon} {cr['r']}</td>
          <td>{html.escape(cr['direction'].capitalize())}</td>
        </tr>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg-base: #0f172a;
      --bg-surface: #1e293b;
      --bg-card: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --accent: {accent_color};
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg-base);
      color: var(--text-main);
      padding: 32px;
      line-height: 1.5;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
      margin-bottom: 24px;
    }}
    .header h1 {{ font-size: 24px; font-weight: 700; }}
    .header p {{ color: var(--text-muted); font-size: 13px; margin-top: 4px; }}
    .health-badge {{
      background: var(--bg-surface);
      border: 2px solid var(--accent);
      border-radius: 12px;
      padding: 12px 24px;
      text-align: center;
    }}
    .health-badge-grade {{ font-size: 32px; font-weight: 900; color: var(--accent); }}
    .health-badge-score {{ font-size: 13px; color: var(--text-muted); }}

    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }}
    .kpi-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }}
    .kpi-title {{ font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }}
    .kpi-value {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
    .kpi-sub {{ font-size: 11px; color: var(--text-muted); margin-top: 2px; }}

    .section-title {{
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--bg-surface);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 32px;
      border: 1px solid var(--border);
    }}
    .data-table th, .data-table td {{
      padding: 10px 14px;
      font-size: 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    .data-table th {{ background: rgba(0,0,0,0.25); color: var(--text-muted); font-weight: 600; }}
    .type-pill {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-family: monospace;
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
    }}
    .q-ribbon {{
      display: flex;
      height: 8px;
      width: 140px;
      border-radius: 4px;
      overflow: hidden;
      background: #0f172a;
    }}
    .q-seg {{ height: 100%; }}
    .q-ok {{ background: #22c55e; }}
    .q-ws {{ background: #f59e0b; }}
    .q-out {{ background: #ef4444; }}
    .q-null {{ background: #64748b; }}

    .legend {{
      display: flex;
      gap: 16px;
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}
    .legend-item {{ display: flex; align-items: center; gap: 6px; }}
    .legend-dot {{ width: 10px; height: 10px; border-radius: 2px; }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>{html.escape(title)}</h1>
      <p>Automated Dataset Health Score & Field Diagnostics &bull; Generated by Antigravity DataFlow</p>
    </div>
    <div class="health-badge">
      <div class="health-badge-grade">Grade {health_grade}</div>
      <div class="health-badge-score">{health_score}% Health Score</div>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-title">Total Records</div>
      <div class="kpi-value">{total_rows:,}</div>
      <div class="kpi-sub">Across {total_cols} fields</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Memory Footprint</div>
      <div class="kpi-value">{mem_str}</div>
      <div class="kpi-sub">Resident in cache</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Missing Cells</div>
      <div class="kpi-value">{missing_cells:,}</div>
      <div class="kpi-sub">{missing_pct}% of total cells</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Duplicate Rows</div>
      <div class="kpi-value">{dup_rows:,}</div>
      <div class="kpi-sub">{dup_pct}% of dataset</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Candidate Primary Keys</div>
      <div class="kpi-value">{len(key_candidates)}</div>
      <div class="kpi-sub">{', '.join(key_candidates[:2]) if key_candidates else 'None detected'}</div>
    </div>
  </div>

  <div class="section-title">Column Diagnostics & Quality Ribbon</div>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background: #22c55e;"></div> Valid (OK)</div>
    <div class="legend-item"><div class="legend-dot" style="background: #f59e0b;"></div> Whitespace / Blank</div>
    <div class="legend-item"><div class="legend-dot" style="background: #ef4444;"></div> Outlier (IQR)</div>
    <div class="legend-item"><div class="legend-dot" style="background: #64748b;"></div> Missing / Null</div>
  </div>

  <table class="data-table">
    <thead>
      <tr>
        <th>Column Name</th>
        <th>Type</th>
        <th>Health</th>
        <th>Data Quality Bar</th>
        <th>Uniqueness</th>
        <th>Key Statistics / Hygiene / Inferred Patterns</th>
      </tr>
    </thead>
    <tbody>
      {''.join(col_rows_html)}
    </tbody>
  </table>

  {f'''
  <div class="section-title">Top Pairwise Correlations</div>
  <table class="data-table" style="max-width: 650px;">
    <thead>
      <tr>
        <th>Field A</th>
        <th>Field B</th>
        <th>Pearson r</th>
        <th>Relationship</th>
      </tr>
    </thead>
    <tbody>
      {''.join(corr_rows_html)}
    </tbody>
  </table>
  ''' if corr_rows_html else ''}

</body>
</html>
"""
