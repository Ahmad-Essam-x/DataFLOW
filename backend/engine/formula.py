"""
Alteryx Formula Engine & Safe Expression Evaluator.
Supports Alteryx-standard functions, bracketed column syntax [Field Name],
multi-branch conditional blocks (IF / ELSEIF / ELSE / ENDIF, IIF),
and vectorized Series evaluation.
"""
import re
import ast
import math
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple, Union


class FormulaExecutionError(Exception):
    """Raised when an expression has a syntax error, unknown column, or evaluation error."""
    pass


def parse_alteryx_conditionals(expr: str) -> str:
    """
    Transforms Alteryx SQL-style IF/ELSEIF/ELSE/ENDIF blocks into nested IIF() expressions.
    Supports arbitrary nesting and case-insensitive keywords.
    Example:
        IF [Score] >= 90 THEN "A" ELSEIF [Score] >= 80 THEN "B" ELSE "C" ENDIF
        -> IIF([Score] >= 90, "A", IIF([Score] >= 80, "B", "C"))
    """
    s = expr.strip()
    # Normalize keywords to uppercase while preserving strings
    tokens = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\[(?:\\.|[^\]\\])*\]|\b(?:IF|THEN|ELSEIF|ELSE\s+IF|ELSE|ENDIF)\b)', s, flags=re.IGNORECASE)

    # Reassemble normalized string
    normalized_parts = []
    for token in tokens:
        upper = token.upper().strip()
        if upper == "IF":
            normalized_parts.append("IF")
        elif upper == "THEN":
            normalized_parts.append("THEN")
        elif upper in ("ELSEIF", "ELSE IF") or re.match(r"^ELSE\s+IF$", upper):
            normalized_parts.append("ELSEIF")
        elif upper == "ELSE":
            normalized_parts.append("ELSE")
        elif upper == "ENDIF":
            normalized_parts.append("ENDIF")
        else:
            normalized_parts.append(token)

    unified = "".join(normalized_parts)

    # Recursive replacement of innermost IF ... ENDIF
    # Pattern matches IF <c> THEN <t> (ELSEIF <c2> THEN <t2>)* [ELSE <e>] ENDIF
    # without nested IF or ENDIF inside
    inner_if_re = re.compile(
        r'\bIF\b((?:(?!\bIF\b|\bENDIF\b).)+?)\bENDIF\b',
        flags=re.DOTALL
    )

    max_iterations = 20
    for _ in range(max_iterations):
        match = inner_if_re.search(unified)
        if not match:
            break

        content = match.group(1).strip()
        transformed = _transform_single_if_block(content)
        unified = unified[:match.start()] + transformed + unified[match.end():]

    return unified


def _transform_single_if_block(content: str) -> str:
    """
    Parses <cond> THEN <true_expr> (ELSEIF <cond_i> THEN <expr_i>)* [ELSE <else_expr>]
    into nested IIF(cond, true_expr, ...)
    """
    # Split by THEN, ELSEIF, ELSE outside of quotes/brackets
    parts = []
    curr = []
    paren_depth = 0
    in_quote = False
    quote_char = ""
    in_bracket = False

    tokens_re = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\[(?:\\.|[^\]\\])*\]|\bTHEN\b|\bELSEIF\b|\bELSE\b)', flags=re.DOTALL)
    
    sections = [] # list of (keyword, text)
    last_idx = 0
    current_kw = "IF"
    
    for m in tokens_re.finditer(content):
        token = m.group(0)
        start, end = m.span()
        if token in ("THEN", "ELSEIF", "ELSE"):
            chunk = content[last_idx:start].strip()
            sections.append((current_kw, chunk))
            current_kw = token
            last_idx = end

    chunk = content[last_idx:].strip()
    sections.append((current_kw, chunk))

    # Reconstruct into nested IIF
    # Sections have [(IF, cond0), (THEN, expr0), (ELSEIF, cond1), (THEN, expr1), ..., (ELSE, else_expr)]
    branches = []
    else_val = "Null()"
    i = 0
    while i < len(sections):
        kw, text = sections[i]
        if kw in ("IF", "ELSEIF"):
            cond = text
            then_val = "Null()"
            if i + 1 < len(sections) and sections[i+1][0] == "THEN":
                then_val = sections[i+1][1]
                i += 1
            branches.append((cond, then_val))
        elif kw == "ELSE":
            else_val = text
        i += 1

    if not branches:
        return content

    # Build nested IIF from end to start
    res = else_val
    for cond, then_expr in reversed(branches):
        res = f"IIF({cond}, {then_expr}, {res})"

    return res


# ----------------------------------------------------------------------
# Alteryx Function Library
# ----------------------------------------------------------------------

def _alteryx_left(val: Any, n: Any = 1) -> Any:
    n_int = int(n)
    if isinstance(val, pd.Series):
        return val.astype(str).str[:n_int]
    return str(val)[:n_int]


def _alteryx_right(val: Any, n: Any = 1) -> Any:
    n_int = int(n)
    if n_int <= 0:
        if isinstance(val, pd.Series):
            return pd.Series("", index=val.index)
        return ""
    if isinstance(val, pd.Series):
        return val.astype(str).str[-n_int:]
    return str(val)[-n_int:]


def _alteryx_substring(val: Any, start: Any = 0, length: Optional[Any] = None) -> Any:
    start_int = int(start)
    if isinstance(val, pd.Series):
        s = val.astype(str)
        if length is not None:
            return s.str[start_int:start_int + int(length)]
        return s.str[start_int:]
    s_val = str(val)
    if length is not None:
        return s_val[start_int:start_int + int(length)]
    return s_val[start_int:]


def _alteryx_uppercase(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).str.upper()
    return str(val).upper()


def _alteryx_lowercase(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).str.lower()
    return str(val).lower()


def _alteryx_trim(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).str.strip()
    return str(val).strip()


def _alteryx_length(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).str.len()
    return len(str(val))


def _alteryx_contains(val: Any, target: Any, case_insensitive: Any = True) -> Any:
    ci = bool(case_insensitive) if not isinstance(case_insensitive, (int, float, str)) else str(case_insensitive).lower() not in ("0", "false", "no")
    target_str = str(target)
    if isinstance(val, pd.Series):
        s = val.astype(str)
        if ci:
            return s.str.lower().str.contains(target_str.lower(), regex=False, na=False)
        return s.str.contains(target_str, regex=False, na=False)
    
    if ci:
        return target_str.lower() in str(val).lower()
    return target_str in str(val)


def _alteryx_startswith(val: Any, prefix: Any, case_insensitive: Any = True) -> Any:
    ci = bool(case_insensitive) if not isinstance(case_insensitive, (int, float, str)) else str(case_insensitive).lower() not in ("0", "false", "no")
    p = str(prefix)
    if isinstance(val, pd.Series):
        s = val.astype(str)
        if ci:
            return s.str.lower().str.startswith(p.lower(), na=False)
        return s.str.startswith(p, na=False)
    v = str(val)
    if ci:
        return v.lower().startswith(p.lower())
    return v.startswith(p)


def _alteryx_endswith(val: Any, suffix: Any, case_insensitive: Any = True) -> Any:
    ci = bool(case_insensitive) if not isinstance(case_insensitive, (int, float, str)) else str(case_insensitive).lower() not in ("0", "false", "no")
    sf = str(suffix)
    if isinstance(val, pd.Series):
        s = val.astype(str)
        if ci:
            return s.str.lower().str.endswith(sf.lower(), na=False)
        return s.str.endswith(sf, na=False)
    v = str(val)
    if ci:
        return v.lower().endswith(sf.lower())
    return v.endswith(sf)


def _alteryx_regex_match(val: Any, pattern: Any) -> Any:
    pat = str(pattern)
    if isinstance(val, pd.Series):
        return val.astype(str).str.contains(pat, regex=True, na=False)
    return bool(re.search(pat, str(val)))


def _alteryx_regex_count(val: Any, pattern: Any) -> Any:
    pat = str(pattern)
    if isinstance(val, pd.Series):
        return val.astype(str).str.count(pat)
    return len(re.findall(pat, str(val)))


def _alteryx_regex_replace(val: Any, pattern: Any, replacement: Any = "") -> Any:
    pat = str(pattern)
    rep = str(replacement)
    if isinstance(val, pd.Series):
        return val.astype(str).str.replace(pat, rep, regex=True)
    return re.sub(pat, rep, str(val))


def _alteryx_replace(val: Any, target: Any, replacement: Any = "") -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).str.replace(str(target), str(replacement), regex=False)
    return str(val).replace(str(target), str(replacement))


def _alteryx_titlecase(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).str.title()
    return str(val).title()


def _alteryx_concat(*args) -> Any:
    if not args:
        return ""
    first = args[0]
    idx = first.index if isinstance(first, pd.Series) else None
    
    # Check if any argument is a series
    has_series = any(isinstance(a, pd.Series) for a in args)
    if has_series:
        res = pd.Series("", index=idx if idx is not None else [0] * len(first), dtype=object)
        for a in args:
            res = res + (a.astype(str) if isinstance(a, pd.Series) else str(a))
        return res
    return "".join(str(a) for a in args)


def _alteryx_datetime_today() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d")


def _alteryx_datetime_now() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _alteryx_datetime_add(dt: Any, num: Any, unit: Any = "days") -> Any:
    n = int(num)
    u = str(unit).strip().strip("'\"").lower().rstrip('s')
    
    is_ser = isinstance(dt, pd.Series)
    s_dt = pd.to_datetime(dt, errors="coerce")
    
    if u in ("day", "d"):
        res = s_dt + pd.to_timedelta(n, unit="D")
    elif u in ("hour", "h", "hr"):
        res = s_dt + pd.to_timedelta(n, unit="h")
    elif u in ("minute", "min", "m"):
        res = s_dt + pd.to_timedelta(n, unit="m")
    elif u in ("second", "sec", "s"):
        res = s_dt + pd.to_timedelta(n, unit="s")
    elif u in ("month", "mon"):
        if is_ser:
            res = s_dt.apply(lambda d: d + pd.DateOffset(months=n) if pd.notna(d) else d)
        else:
            res = s_dt + pd.DateOffset(months=n) if pd.notna(s_dt) else s_dt
    elif u in ("year", "yr", "y"):
        if is_ser:
            res = s_dt.apply(lambda d: d + pd.DateOffset(years=n) if pd.notna(d) else d)
        else:
            res = s_dt + pd.DateOffset(years=n) if pd.notna(s_dt) else s_dt
    else:
        res = s_dt + pd.to_timedelta(n, unit="D")

    if is_ser:
        return res.dt.strftime("%Y-%m-%d %H:%M:%S")
    return res.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(res) else None


def _alteryx_datetime_diff(dt1: Any, dt2: Any, unit: Any = "days") -> Any:
    u = str(unit).strip().strip("'\"").lower().rstrip('s')
    t1 = pd.to_datetime(dt1, errors="coerce")
    t2 = pd.to_datetime(dt2, errors="coerce")
    diff = (t1 - t2)
    
    if isinstance(diff, pd.Series):
        diff_sec = diff.dt.total_seconds()
        if u in ("day", "d"):
            return (diff_sec / 86400.0).round().astype("Int64")
        elif u in ("hour", "h", "hr"):
            return (diff_sec / 3600.0).round().astype("Int64")
        elif u in ("minute", "min", "m"):
            return (diff_sec / 60.0).round().astype("Int64")
        elif u in ("second", "sec", "s"):
            return diff_sec.round().astype("Int64")
        elif u in ("year", "yr", "y"):
            return (t1.dt.year - t2.dt.year).astype("Int64")
        elif u in ("month", "mon"):
            return ((t1.dt.year - t2.dt.year) * 12 + (t1.dt.month - t2.dt.month)).astype("Int64")
        return (diff_sec / 86400.0).round().astype("Int64")
    else:
        diff_sec = diff.total_seconds() if hasattr(diff, "total_seconds") else 0
        if u in ("day", "d"):
            return int(round(diff_sec / 86400.0))
        elif u in ("hour", "h", "hr"):
            return int(round(diff_sec / 3600.0))
        elif u in ("minute", "min", "m"):
            return int(round(diff_sec / 60.0))
        elif u in ("second", "sec", "s"):
            return int(round(diff_sec))
        elif u in ("year", "yr", "y"):
            return int(t1.year - t2.year)
        elif u in ("month", "mon"):
            return int((t1.year - t2.year) * 12 + (t1.month - t2.month))
        return int(round(diff_sec / 86400.0))


def _alteryx_datetime_format(dt: Any, fmt_str: Any = "%Y-%m-%d") -> Any:
    fmt = str(fmt_str).strip().strip("'\"")
    s_dt = pd.to_datetime(dt, errors="coerce")
    if isinstance(s_dt, pd.Series):
        return s_dt.dt.strftime(fmt)
    return s_dt.strftime(fmt) if pd.notna(s_dt) else None


def _alteryx_datetime_year(dt: Any) -> Any:
    s_dt = pd.to_datetime(dt, errors="coerce")
    if isinstance(s_dt, pd.Series):
        return s_dt.dt.year.astype("Int64")
    return int(s_dt.year) if pd.notna(s_dt) else None


def _alteryx_datetime_month(dt: Any) -> Any:
    s_dt = pd.to_datetime(dt, errors="coerce")
    if isinstance(s_dt, pd.Series):
        return s_dt.dt.month.astype("Int64")
    return int(s_dt.month) if pd.notna(s_dt) else None


def _alteryx_datetime_day(dt: Any) -> Any:
    s_dt = pd.to_datetime(dt, errors="coerce")
    if isinstance(s_dt, pd.Series):
        return s_dt.dt.day.astype("Int64")
    return int(s_dt.day) if pd.notna(s_dt) else None


def _alteryx_round(num: Any, decimals: Any = 0) -> Any:
    dec = int(decimals)
    if isinstance(num, pd.Series):
        s = pd.to_numeric(num, errors="coerce")
        res = s.round(dec)
        return res.astype(int) if dec == 0 else res
    val = float(num)
    res = round(val, dec)
    return int(res) if dec == 0 else res


def _alteryx_abs(num: Any) -> Any:
    if isinstance(num, pd.Series):
        return pd.to_numeric(num, errors="coerce").abs()
    return abs(float(num))


def _alteryx_ceil(num: Any) -> Any:
    if isinstance(num, pd.Series):
        return np.ceil(pd.to_numeric(num, errors="coerce")).astype("Int64")
    return math.ceil(float(num))


def _alteryx_floor(num: Any) -> Any:
    if isinstance(num, pd.Series):
        return np.floor(pd.to_numeric(num, errors="coerce")).astype("Int64")
    return math.floor(float(num))


def _alteryx_min(*args) -> Any:
    if not args:
        return None
    if len(args) == 1:
        return args[0]
    res = args[0]
    for nxt in args[1:]:
        if isinstance(res, pd.Series) or isinstance(nxt, pd.Series):
            v1 = pd.to_numeric(res, errors="coerce") if not isinstance(res, (int, float)) else res
            v2 = pd.to_numeric(nxt, errors="coerce") if not isinstance(nxt, (int, float)) else nxt
            res = np.minimum(v1, v2)
        else:
            res = min(res, nxt)
    return res


def _alteryx_max(*args) -> Any:
    if not args:
        return None
    if len(args) == 1:
        return args[0]
    res = args[0]
    for nxt in args[1:]:
        if isinstance(res, pd.Series) or isinstance(nxt, pd.Series):
            v1 = pd.to_numeric(res, errors="coerce") if not isinstance(res, (int, float)) else res
            v2 = pd.to_numeric(nxt, errors="coerce") if not isinstance(nxt, (int, float)) else nxt
            res = np.maximum(v1, v2)
        else:
            res = max(res, nxt)
    return res


def _alteryx_log(num: Any) -> Any:
    if isinstance(num, pd.Series):
        s = pd.to_numeric(num, errors="coerce")
        return pd.Series(np.log(np.where(s > 0, s, np.nan)), index=num.index)
    val = float(num)
    return math.log(val) if val > 0 else float("nan")


def _alteryx_log10(num: Any) -> Any:
    if isinstance(num, pd.Series):
        s = pd.to_numeric(num, errors="coerce")
        return pd.Series(np.log10(np.where(s > 0, s, np.nan)), index=num.index)
    val = float(num)
    return math.log10(val) if val > 0 else float("nan")


def _alteryx_sqrt(num: Any) -> Any:
    if isinstance(num, pd.Series):
        s = pd.to_numeric(num, errors="coerce")
        return pd.Series(np.sqrt(np.where(s >= 0, s, np.nan)), index=num.index)
    val = float(num)
    return math.sqrt(val) if val >= 0 else float("nan")


def _alteryx_exp(num: Any) -> Any:
    if isinstance(num, pd.Series):
        s = pd.to_numeric(num, errors="coerce")
        return pd.Series(np.exp(s), index=num.index)
    return math.exp(float(num))


def _alteryx_power(base: Any, exp: Any) -> Any:
    if isinstance(base, pd.Series) or isinstance(exp, pd.Series):
        b = pd.to_numeric(base, errors="coerce")
        e = pd.to_numeric(exp, errors="coerce")
        idx = base.index if isinstance(base, pd.Series) else (exp.index if isinstance(exp, pd.Series) else None)
        return pd.Series(np.power(b, e), index=idx)
    return math.pow(float(base), float(exp))


def _alteryx_is_null(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.isna()
    return pd.isna(val) or val is None


def _alteryx_null() -> Any:
    return None


def _alteryx_is_empty(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.isna() | (val.astype(str).str.strip() == "")
    return pd.isna(val) or val is None or str(val).strip() == ""


def _alteryx_to_number(val: Any) -> Any:
    if isinstance(val, pd.Series):
        clean = val.astype(str).str.replace(r"[^\d\.\-]", "", regex=True)
        return pd.to_numeric(clean, errors="coerce")
    clean = re.sub(r"[^\d\.\-]", "", str(val))
    try:
        return float(clean) if "." in clean else int(clean)
    except Exception:
        return np.nan


def _alteryx_to_string(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.astype(str).replace({"nan": "", "<NA>": "", "None": ""})
    return str(val) if val is not None and not pd.isna(val) else ""


def _alteryx_iif(condition: Any, true_val: Any, false_val: Any) -> Any:
    if isinstance(condition, pd.Series):
        cond_bool = condition.fillna(False).astype(bool)
        # Vectorized choice with np.where
        t = true_val if not isinstance(true_val, pd.Series) else true_val.values
        f = false_val if not isinstance(false_val, pd.Series) else false_val.values

        # If either side involves strings, objects, or nulls, evaluate in object dtype to prevent numpy coercing null to 'nan' string
        is_object = (
            isinstance(true_val, (str, bytes)) or isinstance(false_val, (str, bytes)) or
            true_val is None or false_val is None or
            (isinstance(t, np.ndarray) and t.dtype.kind in ('U', 'S', 'O')) or
            (isinstance(f, np.ndarray) and f.dtype.kind in ('U', 'S', 'O'))
        )
        if is_object:
            t_arr = np.array(t, dtype=object) if not isinstance(t, np.ndarray) else t.astype(object)
            f_arr = np.array(f, dtype=object) if not isinstance(f, np.ndarray) else f.astype(object)
            res = np.where(cond_bool, t_arr, f_arr)
        else:
            res = np.where(cond_bool, t, f)
        return pd.Series(res, index=condition.index)
    return true_val if condition else false_val


def _alteryx_between(val: Any, min_val: Any, max_val: Any) -> Any:
    low = float(min_val) if isinstance(min_val, (int, float)) or (isinstance(min_val, str) and min_val.replace('.', '', 1).replace('-', '', 1).isdigit()) else min_val
    high = float(max_val) if isinstance(max_val, (int, float)) or (isinstance(max_val, str) and max_val.replace('.', '', 1).replace('-', '', 1).isdigit()) else max_val
    if isinstance(val, pd.Series):
        if pd.api.types.is_numeric_dtype(val):
            num = pd.to_numeric(val, errors="coerce")
            return (num >= float(low)) & (num <= float(high))
        elif pd.api.types.is_datetime64_any_dtype(val):
            dt = pd.to_datetime(val, errors="coerce")
            return (dt >= pd.to_datetime(low)) & (dt <= pd.to_datetime(high))
        s = val.astype(str)
        return (s >= str(low)) & (s <= str(high))
    try:
        if isinstance(val, (int, float)):
            return float(low) <= float(val) <= float(high)
        return str(low) <= str(val) <= str(high)
    except Exception:
        return False


def _alteryx_not_null(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.notna() & (val.astype(str) != "nan")
    return not (pd.isna(val) or val is None or str(val) == "nan")


def _alteryx_not_empty(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.notna() & (val.astype(str).str.strip() != "")
    return not (pd.isna(val) or val is None or str(val).strip() == "")


def _alteryx_ifnull(val: Any, default_val: Any) -> Any:
    if isinstance(val, pd.Series):
        return val.fillna(default_val)
    if val is None or pd.isna(val) or str(val) == "nan":
        return default_val
    return val


def _alteryx_coalesce(*args: Any) -> Any:
    if not args:
        return None
    res = args[0]
    if isinstance(res, pd.Series):
        s = res.copy()
        for a in args[1:]:
            s = s.fillna(a)
        return s
    for a in args:
        if a is not None and not pd.isna(a) and str(a) != "nan":
            return a
    return None


def _alteryx_is_number(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return pd.to_numeric(val, errors="coerce").notna()
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def _alteryx_is_integer(val: Any) -> Any:
    if isinstance(val, pd.Series):
        num = pd.to_numeric(val, errors="coerce")
        return num.notna() & (num % 1 == 0)
    try:
        f = float(val)
        return f.is_integer()
    except (ValueError, TypeError):
        return False


def _alteryx_is_date(val: Any) -> Any:
    if isinstance(val, pd.Series):
        return pd.to_datetime(val, errors="coerce").notna()
    try:
        pd.to_datetime(val)
        return True
    except Exception:
        return False


# Registry of supported functions (case-insensitive keys)
FUNCTION_MAP = {
    # String
    "LEFT": _alteryx_left,
    "RIGHT": _alteryx_right,
    "SUBSTRING": _alteryx_substring,
    "UPPERCASE": _alteryx_uppercase,
    "UPPER": _alteryx_uppercase,
    "LOWERCASE": _alteryx_lowercase,
    "LOWER": _alteryx_lowercase,
    "TRIM": _alteryx_trim,
    "LENGTH": _alteryx_length,
    "LEN": _alteryx_length,
    "CONTAINS": _alteryx_contains,
    "STARTSWITH": _alteryx_startswith,
    "STARTS_WITH": _alteryx_startswith,
    "ENDSWITH": _alteryx_endswith,
    "ENDS_WITH": _alteryx_endswith,
    "REPLACE": _alteryx_replace,
    "TITLECASE": _alteryx_titlecase,
    "PROPER": _alteryx_titlecase,
    "CONCAT": _alteryx_concat,
    # Regex
    "REGEX_MATCH": _alteryx_regex_match,
    "REGEXMATCH": _alteryx_regex_match,
    "REGEX_COUNTMATCHES": _alteryx_regex_count,
    "REGEX_REPLACE": _alteryx_regex_replace,
    # DateTime
    "DATETIMETODAY": _alteryx_datetime_today,
    "TODAY": _alteryx_datetime_today,
    "DATETIMENOW": _alteryx_datetime_now,
    "NOW": _alteryx_datetime_now,
    "DATETIMEADD": _alteryx_datetime_add,
    "DATETIMEDIFF": _alteryx_datetime_diff,
    "DATETIMEFORMAT": _alteryx_datetime_format,
    "DATETIMEYEAR": _alteryx_datetime_year,
    "DATETIMEMONTH": _alteryx_datetime_month,
    "DATETIMEDAY": _alteryx_datetime_day,
    # Math
    "ROUND": _alteryx_round,
    "ABS": _alteryx_abs,
    "CEIL": _alteryx_ceil,
    "CEILING": _alteryx_ceil,
    "FLOOR": _alteryx_floor,
    "MIN": _alteryx_min,
    "MAX": _alteryx_max,
    "LOG": _alteryx_log,
    "LN": _alteryx_log,
    "LOG10": _alteryx_log10,
    "SQRT": _alteryx_sqrt,
    "EXP": _alteryx_exp,
    "POW": _alteryx_power,
    "POWER": _alteryx_power,
    # Range & Comparison
    "BETWEEN": _alteryx_between,
    # Nulls & Conversion
    "ISNULL": _alteryx_is_null,
    "NOTNULL": _alteryx_not_null,
    "NULL": _alteryx_null,
    "ISEMPTY": _alteryx_is_empty,
    "NOTEMPTY": _alteryx_not_empty,
    "IFNULL": _alteryx_ifnull,
    "COALESCE": _alteryx_coalesce,
    "TONUMBER": _alteryx_to_number,
    "TOSTRING": _alteryx_to_string,
    "ISNUMBER": _alteryx_is_number,
    "ISINTEGER": _alteryx_is_integer,
    "ISDATE": _alteryx_is_date,
    # Conditional
    "IIF": _alteryx_iif,
    "IF": _alteryx_iif,
}


# ----------------------------------------------------------------------
# Safe AST Expression Evaluator
# ----------------------------------------------------------------------

class SafeASTEvaluator:
    """Evaluates an AST expression against a Pandas DataFrame with safe operators and functions."""
    
    def __init__(self, df: pd.DataFrame, var_map: Dict[str, str]):
        self.df = df
        self.var_map = var_map # var_name -> orig_column_name

    def evaluate(self, node: ast.AST) -> Any:
        method_name = f"_eval_{node.__class__.__name__}"
        evaluator = getattr(self, method_name, None)
        if evaluator is None:
            raise FormulaExecutionError(f"Unsupported syntax expression element: {node.__class__.__name__}")
        return evaluator(node)

    def _eval_Expression(self, node: ast.Expression) -> Any:
        return self.evaluate(node.body)

    def _eval_Constant(self, node: ast.Constant) -> Any:
        return node.value

    # Legacy python AST nodes (<= 3.7)
    def _eval_Num(self, node: ast.Num) -> Any:
        return node.n

    def _eval_Str(self, node: ast.Str) -> Any:
        return node.s

    def _eval_NameConstant(self, node: ast.NameConstant) -> Any:
        return node.value

    def _eval_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name in self.var_map:
            col = self.var_map[name]
            if col not in self.df.columns:
                raise FormulaExecutionError(f"Column [{col}] not found in dataset. Available columns: {list(self.df.columns)}")
            return self.df[col]

        # Named constants
        if name in ("True", "true", "TRUE"):
            return True
        if name in ("False", "false", "FALSE"):
            return False
        if name in ("None", "null", "NULL"):
            return None

        # Direct column reference without brackets
        for c in self.df.columns:
            if c.lower() == name.lower():
                return self.df[c]

        # Check zero-argument functions called without parenthesis (e.g. Null, DateTimeToday)
        upper_name = name.upper()
        if upper_name in FUNCTION_MAP:
            fn = FUNCTION_MAP[upper_name]
            try:
                return fn()
            except TypeError:
                pass

        raise FormulaExecutionError(f"Unknown variable or identifier: '{name}'")

    def _eval_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            if isinstance(operand, pd.Series):
                return ~operand.fillna(False).astype(bool)
            return not operand
        elif isinstance(node.op, ast.Invert):
            if isinstance(operand, pd.Series):
                return ~operand
            return ~operand
        elif isinstance(node.op, ast.UAdd):
            return +operand
        elif isinstance(node.op, ast.USub):
            return -operand
        raise FormulaExecutionError(f"Unsupported unary operator: {node.op.__class__.__name__}")

    def _eval_BinOp(self, node: ast.BinOp) -> Any:
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        op = node.op

        # Series vs scalar alignment
        if isinstance(op, ast.Add):
            # Special case: string concatenation if either side is string
            if isinstance(left, str) or isinstance(right, str) or (isinstance(left, pd.Series) and left.dtype == object) or (isinstance(right, pd.Series) and right.dtype == object):
                if isinstance(left, pd.Series):
                    return left.astype(str) + (right.astype(str) if isinstance(right, pd.Series) else str(right))
                elif isinstance(right, pd.Series):
                    return str(left) + right.astype(str)
                return str(left) + str(right)
            return left + right
        elif isinstance(op, ast.Sub):
            return left - right
        elif isinstance(op, ast.Mult):
            return left * right
        elif isinstance(op, ast.Div):
            return left / right
        elif isinstance(op, ast.FloorDiv):
            return left // right
        elif isinstance(op, ast.Mod):
            return left % right
        elif isinstance(op, ast.Pow):
            return left ** right
        elif isinstance(op, ast.BitAnd):
            if isinstance(left, pd.Series) or isinstance(right, pd.Series):
                return left.fillna(False).astype(bool) & right.fillna(False).astype(bool)
            return left and right
        elif isinstance(op, ast.BitOr):
            if isinstance(left, pd.Series) or isinstance(right, pd.Series):
                return left.fillna(False).astype(bool) | right.fillna(False).astype(bool)
            return left or right

        raise FormulaExecutionError(f"Unsupported binary operator: {op.__class__.__name__}")

    def _eval_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.evaluate(v) for v in node.values]
        if not values:
            return True

        is_and = isinstance(node.op, ast.And)
        res = values[0]
        for v in values[1:]:
            if isinstance(res, pd.Series) or isinstance(v, pd.Series):
                b1 = res.fillna(False).astype(bool) if isinstance(res, pd.Series) else pd.Series(res, index=self.df.index)
                b2 = v.fillna(False).astype(bool) if isinstance(v, pd.Series) else pd.Series(v, index=self.df.index)
                res = (b1 & b2) if is_and else (b1 | b2)
            else:
                res = (res and v) if is_and else (res or v)
        return res

    def _eval_Compare(self, node: ast.Compare) -> Any:
        left = self.evaluate(node.left)
        res = None

        for op, comparator in zip(node.ops, node.comparators):
            right = self.evaluate(comparator)
            if isinstance(op, ast.Eq):
                curr = (left == right)
            elif isinstance(op, ast.NotEq):
                curr = (left != right)
            elif isinstance(op, ast.Lt):
                curr = (left < right)
            elif isinstance(op, ast.LtE):
                curr = (left <= right)
            elif isinstance(op, ast.Gt):
                curr = (left > right)
            elif isinstance(op, ast.GtE):
                curr = (left >= right)
            elif isinstance(op, ast.In):
                if isinstance(right, (list, tuple, set)):
                    curr = left.isin(right) if isinstance(left, pd.Series) else left in right
                else:
                    curr = _alteryx_contains(right, left)
            elif isinstance(op, ast.NotIn):
                if isinstance(right, (list, tuple, set)):
                    curr = ~left.isin(right) if isinstance(left, pd.Series) else left not in right
                else:
                    curr = ~_alteryx_contains(right, left)
            else:
                raise FormulaExecutionError(f"Unsupported comparison operator: {op.__class__.__name__}")

            if res is None:
                res = curr
            else:
                if isinstance(res, pd.Series) or isinstance(curr, pd.Series):
                    res = res & curr
                else:
                    res = res and curr
            left = right

        return res

    def _eval_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise FormulaExecutionError("Dynamic or complex function calls are not permitted.")

        func_name = node.func.id.upper()
        if func_name not in FUNCTION_MAP:
            raise FormulaExecutionError(f"Unknown function '{node.func.id}()'. Check function name spelling.")

        fn = FUNCTION_MAP[func_name]
        args = [self.evaluate(a) for a in node.args]

        try:
            return fn(*args)
        except TypeError as te:
            raise FormulaExecutionError(f"Error calling {node.func.id}(): invalid argument count or types ({str(te)})")
        except Exception as e:
            raise FormulaExecutionError(f"Error executing {node.func.id}(): {str(e)}")

    def _eval_IfExp(self, node: ast.IfExp) -> Any:
        cond = self.evaluate(node.test)
        body = self.evaluate(node.body)
        orelse = self.evaluate(node.orelse)
        return _alteryx_iif(cond, body, orelse)

    def _eval_List(self, node: ast.List) -> Any:
        return [self.evaluate(el) for el in node.elts]

    def _eval_Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.evaluate(el) for el in node.elts)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def evaluate_expression(df: pd.DataFrame, expr: str) -> Any:
    """
    Evaluates an Alteryx-standard formula expression against a DataFrame.
    Returns a Pandas Series or scalar value.
    """
    if not expr or not expr.strip():
        return pd.Series(np.nan, index=df.index)

    # 1. Transform Alteryx conditional IF...THEN...ELSEIF...ELSE...ENDIF to IIF(...)
    preprocessed = parse_alteryx_conditionals(expr)

    # 2. Extract and map bracketed column names [Column Name]
    var_map = {}
    col_counter = 0

    def replace_bracket(m):
        nonlocal col_counter
        col_name = m.group(1).strip()
        var_name = f"_af_col_{col_counter}_"
        col_counter += 1
        var_map[var_name] = col_name
        return var_name

    sanitized = re.sub(r"\[(.*?)\]", replace_bracket, preprocessed)

    # 3. Handle symbol-based logical operators: && -> and, || -> or, ! -> not
    # Only replace outside strings
    parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', sanitized)
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        chunk = re.sub(r'&&', ' and ', chunk)
        chunk = re.sub(r'\|\|', ' or ', chunk)
        chunk = re.sub(r'(?<![!=<>])!(?!=)', ' not ', chunk)
        # Also replace standalone AND / OR / NOT with lowercase and/or/not for python AST parser
        chunk = re.sub(r'\bAND\b', ' and ', chunk, flags=re.IGNORECASE)
        chunk = re.sub(r'\bOR\b', ' or ', chunk, flags=re.IGNORECASE)
        chunk = re.sub(r'\bNOT\b', ' not ', chunk, flags=re.IGNORECASE)
        parts[i] = chunk
    sanitized = "".join(parts).strip()

    # 4. Parse into AST
    try:
        parsed_ast = ast.parse(sanitized, mode="eval")
    except SyntaxError as se:
        raise FormulaExecutionError(f"Syntax error in formula '{expr}': {se.msg} (line {se.lineno}, col {se.offset})")

    # 5. Evaluate safely
    evaluator = SafeASTEvaluator(df, var_map)
    result = evaluator.evaluate(parsed_ast)

    # 6. Ensure consistent Series output aligned with input index when appropriate
    if not isinstance(result, pd.Series) and isinstance(result, (int, float, str, bool, np.number, np.bool_)):
        return pd.Series(result, index=df.index)

    return result
