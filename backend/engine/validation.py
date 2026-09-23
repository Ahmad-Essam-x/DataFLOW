"""
Node Configuration Validation Engine.
Provides rule-based validation for each tool type before execution.
Detects missing files, blank conditions, unselected join keys, and empty formulas.
"""
from typing import Dict, Any, List, Tuple


def validate_node_config(node_type: str, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a node configuration dictionary based on its tool type.
    Returns (is_valid, list_of_warning_messages).
    """
    if not isinstance(config, dict):
        config = {}

    warnings = []

    if node_type == "input_data":
        file_name = config.get("file_name") or config.get("file_path") or config.get("filename")
        if not file_name:
            warnings.append("No data file selected. Please choose or upload a CSV or Excel file.")

    elif node_type == "text_input":
        text = config.get("text", "")
        raw_text = config.get("raw_text", "")
        data = config.get("data", [])
        columns = config.get("columns", [])
        has_grid_data = bool(columns and data and any(any(str(c).strip() for c in row) for row in data if isinstance(row, list)))
        if not text.strip() and not raw_text.strip() and not has_grid_data:
            warnings.append("No text data entered. Provide CSV/tabular text data.")

    elif node_type == "filter":
        mode = config.get("mode", "basic")
        if mode == "custom":
            expr = config.get("expression", "")
            if not expr or not str(expr).strip():
                warnings.append("No filter expression configured.")
        else:
            conditions = config.get("conditions")
            if isinstance(conditions, list):
                if len(conditions) == 0:
                    warnings.append("No filter conditions configured. Add at least one condition.")
                else:
                    for i, cond in enumerate(conditions):
                        if not isinstance(cond, dict):
                            continue
                        col = cond.get("column")
                        if not col:
                            warnings.append(f"Condition #{i+1}: No filter column selected.")
                        op = cond.get("operator", "==")
                        unary_ops = {"is_null", "is_not_null", "is_empty", "is_not_empty"}
                        if op not in unary_ops:
                            val = cond.get("value")
                            if val is None or str(val).strip() == "":
                                warnings.append(f"Condition #{i+1}: Comparison value is missing for operator '{op}'.")
            else:
                col = config.get("column")
                if not col:
                    warnings.append("No filter column selected.")
                op = config.get("operator", "==")
                unary_ops = {"is_null", "is_not_null", "is_empty", "is_not_empty"}
                if op not in unary_ops:
                    val = config.get("value")
                    if val is None or str(val).strip() == "":
                        warnings.append(f"Comparison value is missing for operator '{op}'.")

    elif node_type == "formula":
        formulas = config.get("formulas", [])
        expressions = config.get("expressions", [])
        valid_formulas = [
            f for f in formulas
            if isinstance(f, dict) and f.get("output_field") and str(f.get("expression", "")).strip()
        ]
        valid_exprs = [
            e for e in expressions
            if isinstance(e, dict) and e.get("column") and str(e.get("expression", "")).strip()
        ]
        if not valid_formulas and not valid_exprs:
            warnings.append("No formula expression configured. Specify target column and formula.")

    elif node_type == "multi_row_formula":
        expr = config.get("expression")
        if not expr or not str(expr).strip():
            warnings.append("No formula expression configured for Multi-Row Formula.")
        target = config.get("output_field")
        if not target or not str(target).strip():
            warnings.append("No output field specified for Multi-Row Formula.")

    elif node_type == "multi_field_formula":
        expr = config.get("expression")
        if not expr or not str(expr).strip():
            warnings.append("No formula expression configured for Multi-Field Formula.")

    elif node_type == "select":
        columns = config.get("columns", [])
        fields = config.get("fields", [])
        if columns and isinstance(columns, list):
            selected = [c for c in columns if isinstance(c, dict) and c.get("selected", True)]
            if len(selected) == 0:
                warnings.append("All output columns are deselected.")
        elif fields and isinstance(fields, list):
            selected = [f for f in fields if isinstance(f, dict) and f.get("keep", True)]
            if len(selected) == 0:
                warnings.append("All output columns are deselected.")

    elif node_type == "sort":
        sort_by = config.get("sort_by", [])
        rules = config.get("rules", [])
        col = config.get("column")
        valid_sort_by = [s for s in sort_by if isinstance(s, dict) and s.get("column")]
        valid_rules = [r for r in rules if isinstance(r, dict) and r.get("column")]
        if not valid_sort_by and not valid_rules and not col:
            warnings.append("No sort column specified.")

    elif node_type == "summarize":
        actions = config.get("actions", [])
        valid_actions = [a for a in actions if isinstance(a, dict) and a.get("field") and a.get("action")]
        if not valid_actions:
            warnings.append("No summary actions configured. Add at least one aggregation or group by.")

    elif node_type == "join":
        join_mode = config.get("join_mode", "specific_fields")
        if join_mode != "record_position":
            join_keys = config.get("join_keys", [])
            valid_keys = [
                k for k in join_keys
                if isinstance(k, dict) and k.get("left_key") and k.get("right_key")
            ]
            left_key = config.get("left_key") or config.get("left_field")
            right_key = config.get("right_key") or config.get("right_field")
            if not valid_keys and (not left_key or not right_key):
                warnings.append("Both Left and Right join key columns must be specified.")

    elif node_type == "join_multiple":
        join_mode = config.get("join_mode", "specific_fields")
        if join_mode != "record_position":
            join_keys = config.get("join_keys", [])
            if not join_keys and "input_keys" not in config:
                warnings.append("No join keys configured. Select key fields for connected inputs.")

    elif node_type == "find_replace":
        find_field = config.get("find_field")
        action = config.get("action", "replace")
        replace_field = config.get("replace_field") or config.get("replace_with_field")
        append_fields = config.get("append_fields", [])
        if not find_field:
            warnings.append("Find target field must be selected.")
        elif action == "append":
            if not append_fields:
                warnings.append("At least one field to append must be selected.")
        elif not replace_field:
            warnings.append("Replace target field must be selected.")

    elif node_type == "unique":
        columns = config.get("columns", [])
        if not columns or len(columns) == 0:
            warnings.append("No deduplication columns selected.")

    elif node_type == "sample":
        sample_type = config.get("sample_type", "first_n")
        if sample_type == "percent":
            pct = config.get("percent", 0)
            try:
                if float(pct) <= 0 or float(pct) > 100:
                    warnings.append("Sample percentage must be between 1 and 100.")
            except (ValueError, TypeError):
                warnings.append("Invalid sample percentage value.")
        else:
            n = config.get("n_records", config.get("n", 0))
            try:
                if int(n) <= 0:
                    warnings.append("Sample size must be greater than 0.")
            except (ValueError, TypeError):
                warnings.append("Invalid sample size value.")

    elif node_type == "transpose":
        data_fields = config.get("data_fields") or config.get("data_columns") or []
        if not data_fields or len(data_fields) == 0:
            warnings.append("At least one data field must be selected for transposing.")

    elif node_type == "crosstab":
        header_field = config.get("header_field")
        data_field = config.get("data_field") or config.get("value_field")
        if not header_field or not data_field:
            warnings.append("Both Header column and Data value column must be selected.")

    elif node_type == "text_to_columns":
        col = config.get("column")
        delim = config.get("delimiters") or config.get("delimiter")
        if not col or not delim:
            warnings.append("Target column and delimiter must be specified.")

    elif node_type == "output_data":
        file_name = config.get("file_name") or config.get("filename")
        if not file_name:
            warnings.append("Output file name must be specified.")

    # tool_container, comment, union, clean, record_id are valid by default
    is_valid = len(warnings) == 0
    return is_valid, warnings
