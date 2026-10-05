"""
Parsing Node Implementations (Alteryx Designer Parity).
Houses TextToColumnsNode (split to columns/rows) and DateTimeNode (date/time parsing and formatting).
"""
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .base import BaseNode, NodeExecutionError, sanitize_dataframe


def split_delimited_string(
    text: Any,
    delimiters: str,
    ignore_quotes: bool = True,
    ignore_single_quotes: bool = False,
    ignore_parentheses: bool = False,
    ignore_brackets: bool = False,
    skip_empty: bool = False
) -> List[str]:
    """
    Splits text by delimiter characters taking into account quotes and enclosures.
    In Alteryx, each character in delimiters is treated as an individual delimiter.
    """
    if text is None or pd.isna(text):
        return []
    s = str(text)
    if not s:
        return [""] if not skip_empty else []

    # Parse delimiters and handle escapes (\t, \n, \r, \s)
    delim_set = set()
    i = 0
    while i < len(delimiters):
        if delimiters[i] == '\\' and i + 1 < len(delimiters):
            nxt = delimiters[i + 1]
            if nxt == 't':
                delim_set.add('\t')
            elif nxt == 'n':
                delim_set.add('\n')
            elif nxt == 'r':
                delim_set.add('\r')
            elif nxt == 's':
                delim_set.add(' ')
            else:
                delim_set.add(nxt)
            i += 2
        else:
            delim_set.add(delimiters[i])
            i += 1

    if not delim_set:
        delim_set.add(',')

    tokens: List[str] = []
    current_token: List[str] = []

    in_double_quote = False
    in_single_quote = False
    paren_depth = 0
    bracket_depth = 0

    for ch in s:
        if ch == '"' and ignore_quotes and not in_single_quote:
            in_double_quote = not in_double_quote
            current_token.append(ch)
        elif ch == "'" and ignore_single_quotes and not in_double_quote:
            in_single_quote = not in_single_quote
            current_token.append(ch)
        elif ch == '(' and ignore_parentheses and not in_double_quote and not in_single_quote:
            paren_depth += 1
            current_token.append(ch)
        elif ch == ')' and ignore_parentheses and paren_depth > 0 and not in_double_quote and not in_single_quote:
            paren_depth -= 1
            current_token.append(ch)
        elif ch == '[' and ignore_brackets and not in_double_quote and not in_single_quote:
            bracket_depth += 1
            current_token.append(ch)
        elif ch == ']' and ignore_brackets and bracket_depth > 0 and not in_double_quote and not in_single_quote:
            bracket_depth -= 1
            current_token.append(ch)
        elif ch in delim_set and not in_double_quote and not in_single_quote and paren_depth == 0 and bracket_depth == 0:
            token_str = "".join(current_token)
            if not (skip_empty and token_str == ""):
                tokens.append(token_str)
            current_token = []
        else:
            current_token.append(ch)

    last_token = "".join(current_token)
    if not (skip_empty and last_token == ""):
        tokens.append(last_token)

    cleaned_tokens = []
    for t in tokens:
        if ignore_quotes and len(t) >= 2 and t.startswith('"') and t.endswith('"'):
            cleaned_tokens.append(t[1:-1])
        elif ignore_single_quotes and len(t) >= 2 and t.startswith("'") and t.endswith("'"):
            cleaned_tokens.append(t[1:-1])
        else:
            cleaned_tokens.append(t)

    return cleaned_tokens


class TextToColumnsNode(BaseNode):
    """
    Splits text from one column into multiple columns or rows based on delimiters.
    Supports Alteryx quote-aware splitting, extra characters handling, and row exploding.
    """
    type_name = "text_to_columns"

    def execute(self, inputs: Dict[str, pd.DataFrame], context: Any) -> Dict[str, pd.DataFrame]:
        df = self.get_single_input(inputs)
        if df.empty:
            return {"O": df.copy()}

        col_name = self.config.get("column")
        if not col_name:
            raise NodeExecutionError("Text To Columns requires a column to split.")

        if col_name not in df.columns:
            raise NodeExecutionError(f"Column '{col_name}' not found in input data. Available: {list(df.columns)}")

        delimiters = self.config.get("delimiters", ",")
        if not delimiters:
            delimiters = ","

        split_type = self.config.get("split_type", "columns")  # "columns" or "rows"
        ignore_quotes = bool(self.config.get("ignore_quotes", True))
        ignore_single_quotes = bool(self.config.get("ignore_single_quotes", False))
        ignore_parentheses = bool(self.config.get("ignore_parentheses", False))
        ignore_brackets = bool(self.config.get("ignore_brackets", False))
        skip_empty = bool(self.config.get("skip_empty", False))

        primary_delim = delimiters[0] if delimiters else ","

        if split_type == "rows":
            # Split to Rows (Explode)
            rows = []
            for _, row in df.iterrows():
                val = row[col_name]
                tokens = split_delimited_string(
                    val,
                    delimiters,
                    ignore_quotes=ignore_quotes,
                    ignore_single_quotes=ignore_single_quotes,
                    ignore_parentheses=ignore_parentheses,
                    ignore_brackets=ignore_brackets,
                    skip_empty=skip_empty
                )
                if not tokens:
                    row_copy = row.to_dict()
                    row_copy[col_name] = None
                    rows.append(row_copy)
                else:
                    for tok in tokens:
                        row_copy = row.to_dict()
                        row_copy[col_name] = tok
                        rows.append(row_copy)

            out_df = pd.DataFrame(rows)
            return {"O": sanitize_dataframe(out_df)}

        # Split to Columns
        num_columns = int(self.config.get("num_columns", 2))
        if num_columns < 1:
            num_columns = 1

        root_name = self.config.get("root_name", "").strip()
        if not root_name:
            root_name = col_name

        extra_chars = self.config.get("extra_characters", "last")  # "last", "drop", "warn", "error"

        # Generate new column names (1-indexed per Alteryx Designer)
        new_col_names = [f"{root_name}{i + 1}" for i in range(num_columns)]

        split_results = []
        for idx, val in enumerate(df[col_name]):
            tokens = split_delimited_string(
                val,
                delimiters,
                ignore_quotes=ignore_quotes,
                ignore_single_quotes=ignore_single_quotes,
                ignore_parentheses=ignore_parentheses,
                ignore_brackets=ignore_brackets,
                skip_empty=skip_empty
            )

            if len(tokens) > num_columns:
                if extra_chars == "error":
                    raise NodeExecutionError(
                        f"Text To Columns: Extra characters detected in row {idx + 1} ({len(tokens)} parts exceeds limit of {num_columns} columns). "
                        f"Value: '{val}'"
                    )
                elif extra_chars == "last":
                    kept = tokens[:num_columns - 1]
                    last_part = primary_delim.join(tokens[num_columns - 1:])
                    tokens = kept + [last_part]
                else:  # "drop" or "warn"
                    tokens = tokens[:num_columns]

            # Pad with None if fewer tokens than num_columns
            if len(tokens) < num_columns:
                tokens = tokens + [None] * (num_columns - len(tokens))

            split_results.append(tokens)

        split_df = pd.DataFrame(split_results, columns=new_col_names, index=df.index)

        # Merge with existing columns, placing new split columns directly after original column if possible
        out_df = df.copy()
        col_loc = out_df.columns.get_loc(col_name) + 1
        for i, new_col in enumerate(new_col_names):
            out_df.insert(col_loc + i, new_col, split_df[new_col])

        return {"O": sanitize_dataframe(out_df)}


# Alteryx Standard Date Format Presets -> Python strftime patterns
DATE_FORMAT_PRESETS = {
    "yyyy-MM-dd": "%Y-%m-%d",
    "yyyy-MM-dd HH:mm:ss": "%Y-%m-%d %H:%M:%S",
    "MM/dd/yyyy": "%m/%d/%Y",
    "dd/MM/yyyy": "%d/%m/%Y",
    "dd-Mon-yyyy": "%d-%b-%Y",
    "dd-Mon-yy": "%d-%b-%y",
    "Month dd, yyyy": "%B %d, %Y",
    "MM-dd-yyyy": "%m-%d-%Y",
    "yyyy/MM/dd": "%Y/%m/%d",
    "hh:mm:ss": "%H:%M:%S",
}


def convert_alteryx_format_to_strftime(pattern: str) -> str:
    """
    Converts Alteryx pattern specifiers (yyyy, yy, MM, Mon, Month, dd, d, HH, hh, mm, ss)
    into standard Python strftime codes (%Y, %m, etc.) using a single-pass regex replacement.
    """
    if pattern in DATE_FORMAT_PRESETS:
        return DATE_FORMAT_PRESETS[pattern]

    token_map = {
        "yyyy": "%Y",
        "yy": "%y",
        "Month": "%B",
        "Mon": "%b",
        "MM": "%m",
        "dd": "%d",
        "d": "%d",
        "HH": "%H",
        "hh": "%I",
        "mm": "%M",
        "ss": "%S",
        "tt": "%p",
        "TT": "%p",
    }
    pattern_re = re.compile("|".join(re.escape(k) for k in sorted(token_map.keys(), key=len, reverse=True)))
    return pattern_re.sub(lambda m: token_map[m.group(0)], pattern)


class DateTimeNode(BaseNode):
    """
    Converts date-time data between standardized ISO formats and custom string formats.
    Supports String to Date/Time and Date/Time to String conversions.
    """
    type_name = "date_time"

    def execute(self, inputs: Dict[str, pd.DataFrame], context: Any) -> Dict[str, pd.DataFrame]:
        df = self.get_single_input(inputs)
        if df.empty:
            return {"O": df.copy()}

        col_name = self.config.get("column")
        if not col_name:
            raise NodeExecutionError("DateTime requires a field to convert.")

        if col_name not in df.columns:
            raise NodeExecutionError(f"Field '{col_name}' not found in input data. Available: {list(df.columns)}")

        conversion_type = self.config.get("conversion_type", "string_to_date")  # "string_to_date" or "date_to_string"
        format_template = self.config.get("format_template", "yyyy-MM-dd")
        custom_format = self.config.get("custom_format", "").strip()

        if format_template == "custom" and custom_format:
            py_format = convert_alteryx_format_to_strftime(custom_format)
        else:
            py_format = DATE_FORMAT_PRESETS.get(format_template, "%Y-%m-%d")

        output_column = self.config.get("output_column", "").strip()
        if not output_column:
            output_column = f"{col_name}_DateTime" if conversion_type == "string_to_date" else f"{col_name}_String"

        out_df = df.copy()

        if conversion_type == "string_to_date":
            # Convert text string to standard ISO Date / DateTime
            has_time = any(t in py_format for t in ["%H", "%I", "%M", "%S", "HH", "hh", "mm", "ss"])
            target_iso = "%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d"

            converted_series = []
            for val in df[col_name]:
                if val is None or pd.isna(val) or str(val).strip() == "":
                    converted_series.append(None)
                    continue

                s_val = str(val).strip()
                dt_obj = None

                # Try strict parsing with configured pattern first
                try:
                    dt_obj = datetime.strptime(s_val, py_format)
                except Exception:
                    # Fallback to dateutil / pandas flexible parser
                    try:
                        parsed = pd.to_datetime(s_val)
                        if not pd.isna(parsed):
                            dt_obj = parsed.to_pydatetime()
                    except Exception:
                        dt_obj = None

                if dt_obj:
                    converted_series.append(dt_obj.strftime(target_iso))
                else:
                    converted_series.append(None)

            out_df[output_column] = converted_series

        else:
            # Convert existing date/datetime column to custom formatted string
            try:
                dt_series = pd.to_datetime(df[col_name], errors='coerce')
                out_df[output_column] = dt_series.dt.strftime(py_format)
            except Exception as e:
                raise NodeExecutionError(f"Failed to format date field '{col_name}': {str(e)}")

        return {"O": sanitize_dataframe(out_df)}
