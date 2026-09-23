"""
Node-Level SQL Transpilers for Antigravity DataFlow.
Transforms each node in the workflow DAG into SQL query expressions for its output ports.
"""
import os
import re
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.engine.sql_compiler.dialects import SQLDialect
from backend.engine.sql_compiler.formula_transpiler import transpile_expression


class NodeTranspileError(Exception):
    pass


def transpile_input_data(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles InputDataNode to a SQL table/view or file reader query."""
    node_id = node.get("id", "")
    config = node.get("config", {})
    filepath = config.get("filepath") or config.get("file_name") or ""
    table_mappings = context.get("table_mappings", {})

    # 1. Custom table mapping override (by node_id or by filename)
    base_name = os.path.splitext(os.path.basename(filepath))[0] if filepath else ""
    mapped_name = table_mappings.get(node_id) or table_mappings.get(filepath) or table_mappings.get(base_name)

    if mapped_name:
        return {"O": f"SELECT * FROM {mapped_name}"}

    # 2. DuckDB native CSV/Parquet reader if available
    if dialect.supports_read_csv and filepath and filepath.lower().endswith((".csv", ".tsv")):
        clean_path = filepath.replace("\\", "/")
        return {"O": f"SELECT * FROM read_csv_auto('{clean_path}')"}

    # 3. Default: sanitize filename to table identifier or placeholder
    table_ident = dialect.quote_identifier(base_name if base_name else f"table_{node_id}")
    comment = f" /* Source: {os.path.basename(filepath)} */" if filepath else ""
    return {"O": f"SELECT * FROM {table_ident}{comment}"}


def transpile_text_input(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles TextInputNode into an inline UNION ALL query or VALUES clause."""
    config = node.get("config", {})
    data = config.get("data", [])

    if not data or not isinstance(data, list):
        return {"O": "SELECT 1 AS empty_stream WHERE 1=0"}

    # Determine columns from first record
    first = data[0]
    if isinstance(first, dict):
        cols = list(first.keys())
        rows = [[row.get(c) for c in cols] for row in data]
    elif isinstance(first, list):
        cols = [f"Field_{i+1}" for i in range(len(first))]
        rows = data
    else:
        return {"O": "SELECT 1 AS empty_stream WHERE 1=0"}

    select_statements = []
    for idx, row in enumerate(rows):
        projections = []
        for c, val in zip(cols, row):
            val_sql = dialect.quote_literal(val)
            if idx == 0:
                projections.append(f"{val_sql} AS {dialect.quote_identifier(c)}")
            else:
                projections.append(val_sql)
        select_statements.append(f"SELECT {', '.join(projections)}")

    query = "\nUNION ALL\n".join(select_statements)
    return {"O": query}


def transpile_select(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles SelectNode (projections, renames, type casts, drops)."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Select tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    fields = config.get("fields") or config.get("columns") or []

    if not fields:
        return {"O": f"SELECT * FROM {upstream}"}

    projections = []
    has_deselected = False

    for item in fields:
        selected = item.get("selected", True)
        if not selected:
            has_deselected = True
            continue

        orig = item.get("name") or item.get("field")
        if not orig:
            continue

        rename = str(item.get("rename") or "").strip()
        new_type = str(item.get("type") or "").strip().lower()
        orig_quoted = dialect.quote_identifier(orig)
        out_col = rename if rename else orig
        out_quoted = dialect.quote_identifier(out_col)

        # Handle type casting if specified
        if new_type and new_type not in ("none", "keep", "original"):
            cast_sql = dialect.cast_type(orig, new_type, safe=True)
            projections.append(f"{cast_sql} AS {out_quoted}")
        elif rename and rename != orig:
            projections.append(f"{orig_quoted} AS {out_quoted}")
        else:
            projections.append(orig_quoted)

    if not projections:
        if has_deselected:
            return {"O": f"SELECT 1 AS empty_stream WHERE 1=0"}
        return {"O": f"SELECT * FROM {upstream}"}

    return {"O": f"SELECT\n  {',\n  '.join(projections)}\nFROM {upstream}"}


def transpile_auto_field(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles AutoFieldNode. In SQL, maps to clean passthrough."""
    upstream = input_sources.get("I")
    return {"O": f"SELECT * FROM {upstream}"}


def transpile_filter(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles FilterNode into True ('T') and False ('F') CTE queries."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Filter tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    mode = str(config.get("mode", "basic")).lower().strip()

    if mode in ("custom", "expression", "formula"):
        expr = config.get("expression", "").strip()
        if not expr:
            cond_sql = "1=1"
        else:
            cond_sql = transpile_expression(expr, dialect)
    else:
        # Basic mode
        conditions = config.get("conditions", [])
        if not conditions:
            cond_sql = "1=1"
        else:
            cond_parts = []
            for cond in conditions:
                col = cond.get("column")
                if not col:
                    continue
                op = str(cond.get("operator", "==")).lower().strip()
                val = cond.get("value", "")
                val_max = cond.get("value_max", "")
                quoted_col = dialect.quote_identifier(col)

                if op == "is_null":
                    cond_parts.append(f"({quoted_col} IS NULL)")
                elif op in ("not_null", "is_not_null"):
                    cond_parts.append(f"({quoted_col} IS NOT NULL)")
                elif op == "is_empty":
                    cond_parts.append(f"({quoted_col} IS NULL OR TRIM(CAST({quoted_col} AS VARCHAR)) = '')")
                elif op in ("not_empty", "is_not_empty"):
                    cond_parts.append(f"({quoted_col} IS NOT NULL AND TRIM(CAST({quoted_col} AS VARCHAR)) != '')")
                elif op in ("==", "=", "equals"):
                    cond_parts.append(f"({quoted_col} = {dialect.quote_literal(val)})")
                elif op in ("!=", "<>", "not_equals"):
                    cond_parts.append(f"({quoted_col} != {dialect.quote_literal(val)})")
                elif op in (">", "greater_than"):
                    cond_parts.append(f"({quoted_col} > {dialect.quote_literal(val)})")
                elif op in (">=", "greater_than_or_equal"):
                    cond_parts.append(f"({quoted_col} >= {dialect.quote_literal(val)})")
                elif op in ("<", "less_than"):
                    cond_parts.append(f"({quoted_col} < {dialect.quote_literal(val)})")
                elif op in ("<=", "less_than_or_equal"):
                    cond_parts.append(f"({quoted_col} <= {dialect.quote_literal(val)})")
                elif op == "between":
                    cond_parts.append(f"({quoted_col} BETWEEN {dialect.quote_literal(val)} AND {dialect.quote_literal(val_max)})")
                elif op in ("in", "not_in"):
                    items = [x.strip() for x in str(val).split(",") if x.strip()]
                    quoted_items = [dialect.quote_literal(it) for it in items]
                    in_op = "IN" if op == "in" else "NOT IN"
                    cond_parts.append(f"({quoted_col} {in_op} ({', '.join(quoted_items)}))")
                elif op in ("contains",):
                    if dialect.supports_ilike:
                        cond_parts.append(f"({quoted_col} ILIKE '%' || {dialect.quote_literal(val)} || '%')")
                    else:
                        cond_parts.append(f"(LOWER({quoted_col}) LIKE '%' || LOWER({dialect.quote_literal(val)}) || '%')")
                else:
                    cond_parts.append(f"({quoted_col} = {dialect.quote_literal(val)})")

            logical_op = f" {config.get('logical_op', 'AND').upper()} "
            cond_sql = logical_op.join(cond_parts) if cond_parts else "1=1"

    t_query = f"SELECT * FROM {upstream}\nWHERE {cond_sql}"
    f_query = f"SELECT * FROM {upstream}\nWHERE NOT ({cond_sql}) OR ({cond_sql}) IS NULL"

    return {"T": t_query, "F": f_query}


def transpile_formula(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles FormulaNode with expression AST transpilation."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Formula tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    formulas = config.get("formulas") or config.get("expressions") or []

    if not formulas:
        return {"O": f"SELECT * FROM {upstream}"}

    formula_projections = []
    for item in formulas:
        col = item.get("output_field") or item.get("field") or item.get("column") or ""
        expr = item.get("expression") or ""
        if not col or not expr:
            continue

        expr_sql = transpile_expression(expr, dialect)
        out_type = str(item.get("type") or "").strip().lower()
        quoted_col = dialect.quote_identifier(col)

        if out_type and out_type not in ("none", "keep"):
            cast_sql = f"CAST({expr_sql} AS {dialect.map_type(out_type)})"
            formula_projections.append(f"{cast_sql} AS {quoted_col}")
        else:
            formula_projections.append(f"{expr_sql} AS {quoted_col}")

    if not formula_projections:
        return {"O": f"SELECT * FROM {upstream}"}

    # Use SELECT *, expr1 AS col1, expr2 AS col2 FROM upstream
    return {"O": f"SELECT\n  *,\n  {',\n  '.join(formula_projections)}\nFROM {upstream}"}


def transpile_sort(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles SortNode to ORDER BY clause."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Sort tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    sort_fields = config.get("sort_fields") or config.get("fields") or []

    if not sort_fields:
        return {"O": f"SELECT * FROM {upstream}"}

    order_clauses = []
    for item in sort_fields:
        field = item.get("field") or item.get("column")
        if not field:
            continue
        direction = "DESC" if str(item.get("order", "asc")).lower() == "desc" else "ASC"
        order_clauses.append(f"{dialect.quote_identifier(field)} {direction}")

    if not order_clauses:
        return {"O": f"SELECT * FROM {upstream}"}

    return {"O": f"SELECT * FROM {upstream}\nORDER BY {', '.join(order_clauses)}"}


def transpile_clean(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles CleanNode to SQL string trimming, null handling, and casing."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Clean tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    target_cols = config.get("fields") or config.get("columns") or []
    trim_ws = bool(config.get("trim_whitespace", True))
    rep_null_str = bool(config.get("replace_nulls_string", False))
    rep_null_num = bool(config.get("replace_nulls_numeric", False))
    case_op = str(config.get("case_mode") or config.get("case_transformation", "none")).lower()

    if not target_cols:
        return {"O": f"SELECT * FROM {upstream}"}

    projections = ["*"]
    for col in target_cols:
        quoted = dialect.quote_identifier(col)
        expr = quoted

        if rep_null_str:
            expr = f"COALESCE({expr}, '')"
        elif rep_null_num:
            expr = f"COALESCE({expr}, 0)"

        if trim_ws:
            expr = f"TRIM({expr})"

        if case_op == "upper":
            expr = f"UPPER({expr})"
        elif case_op == "lower":
            expr = f"LOWER({expr})"

        if expr != quoted:
            projections.append(f"{expr} AS {quoted}")

    return {"O": f"SELECT\n  {',\n  '.join(projections)}\nFROM {upstream}"}


def transpile_unique(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles UniqueNode into Unique ('U') and Duplicate ('D') output CTEs."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Unique tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    cols = config.get("columns") or config.get("fields") or []

    partition_expr = dialect.row_number_expr(partition_by=cols)

    # Subquery with window function
    u_query = (
        f"SELECT * FROM (\n"
        f"  SELECT *,\n"
        f"    {partition_expr} AS _rn\n"
        f"  FROM {upstream}\n"
        f") t WHERE _rn = 1"
    )
    d_query = (
        f"SELECT * FROM (\n"
        f"  SELECT *,\n"
        f"    {partition_expr} AS _rn\n"
        f"  FROM {upstream}\n"
        f") t WHERE _rn > 1"
    )

    return {"U": u_query, "D": d_query}


def transpile_sample(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles SampleNode to LIMIT / OFFSET or TOP N."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Sample tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    sample_type = config.get("sample_type", "first_n")
    n_records = int(config.get("n_records", 100))

    if sample_type == "first_n":
        return {"O": f"SELECT * FROM {upstream}\n{dialect.limit_clause(n_records)}"}
    elif sample_type == "percent":
        pct = float(config.get("percent", 10.0))
        # Dialect random sample or limit
        return {"O": f"SELECT * FROM {upstream}\nWHERE RANDOM() <= {pct / 100.0}"}
    elif sample_type == "last_n":
        return {"O": f"SELECT * FROM {upstream}\nORDER BY (SELECT NULL) DESC\n{dialect.limit_clause(n_records)}"}

    return {"O": f"SELECT * FROM {upstream}\n{dialect.limit_clause(n_records)}"}


def transpile_record_id(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles RecordIDNode using ROW_NUMBER() OVER ()."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Record ID tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    col_name = config.get("column_name", "RecordID") or "RecordID"
    start_val = int(config.get("start_value", 1))
    group_by = config.get("group_by", [])
    if isinstance(group_by, str) and group_by:
        group_by = [group_by]

    row_num_expr = dialect.row_number_expr(partition_by=group_by if group_by else None)
    offset = start_val - 1
    id_calc = f"({row_num_expr} + {offset})" if offset != 0 else row_num_expr
    quoted_col = dialect.quote_identifier(col_name)

    return {"O": f"SELECT\n  {id_calc} AS {quoted_col},\n  *\nFROM {upstream}"}


def transpile_join(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """
    Transpiles JoinNode with multi-port routing:
    - J: INNER JOIN (Joined records)
    - L: LEFT JOIN anti (Unmatched left records)
    - R: RIGHT JOIN anti (Unmatched right records)
    """
    left_upstream = input_sources.get("L")
    right_upstream = input_sources.get("R")

    if not left_upstream or not right_upstream:
        raise NodeTranspileError(f"Join tool ({node.get('id')}) requires both 'L' and 'R' inputs.")

    config = node.get("config", {})
    join_keys = config.get("join_keys", [])
    if not join_keys:
        lks = config.get("left_keys", [])
        rks = config.get("right_keys", [])
        if lks and rks:
            join_keys = [{"left_key": l, "right_key": r} for l, r in zip(lks, rks)]

    on_clauses = []
    l_key_cols = []
    r_key_cols = []

    for pair in join_keys:
        lk = pair.get("left_key")
        rk = pair.get("right_key")
        if lk and rk:
            l_quoted = f"l.{dialect.quote_identifier(lk)}"
            r_quoted = f"r.{dialect.quote_identifier(rk)}"
            on_clauses.append(f"{l_quoted} = {r_quoted}")
            l_key_cols.append(l_quoted)
            r_key_cols.append(r_quoted)

    on_sql = " AND ".join(on_clauses) if on_clauses else "1=1"

    # 1. Joined (J) Output
    j_query = (
        f"SELECT\n"
        f"  l.*,\n"
        f"  r.*\n"
        f"FROM {left_upstream} l\n"
        f"INNER JOIN {right_upstream} r ON {on_sql}"
    )

    # 2. Left Unmatched (L) Output
    r_null_check = f"{r_key_cols[0]} IS NULL" if r_key_cols else "1=0"
    l_query = (
        f"SELECT\n"
        f"  l.*\n"
        f"FROM {left_upstream} l\n"
        f"LEFT JOIN {right_upstream} r ON {on_sql}\n"
        f"WHERE {r_null_check}"
    )

    # 3. Right Unmatched (R) Output
    l_null_check = f"{l_key_cols[0]} IS NULL" if l_key_cols else "1=0"
    r_query = (
        f"SELECT\n"
        f"  r.*\n"
        f"FROM {right_upstream} r\n"
        f"LEFT JOIN {left_upstream} l ON {on_sql}\n"
        f"WHERE {l_null_check}"
    )

    return {"J": j_query, "L": l_query, "R": r_query}


def transpile_union(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles UnionNode stacking multiple input streams."""
    upstreams = input_sources.get("I", [])
    if isinstance(upstreams, str):
        upstreams = [upstreams]

    if not upstreams:
        raise NodeTranspileError(f"Union tool ({node.get('id')}) has no incoming streams.")

    config = node.get("config", {})
    union_type = "UNION DISTINCT" if str(config.get("union_type", "all")).lower() == "distinct" else "UNION ALL"

    selects = [f"SELECT * FROM {src}" for src in upstreams]
    query = f"\n{union_type}\n".join(selects)
    return {"O": query}


def transpile_append_fields(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles AppendFieldsNode to Cartesian CROSS JOIN."""
    target_src = input_sources.get("T")
    source_src = input_sources.get("S")

    if not target_src or not source_src:
        raise NodeTranspileError(f"Append Fields tool ({node.get('id')}) requires Target ('T') and Source ('S') inputs.")

    query = f"SELECT * FROM {target_src}\nCROSS JOIN {source_src}"
    return {"O": query}


def transpile_find_replace(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles FindReplaceNode into a LEFT JOIN with reference replacement."""
    find_src = input_sources.get("F")
    replace_src = input_sources.get("R")

    if not find_src or not replace_src:
        raise NodeTranspileError(f"Find Replace tool ({node.get('id')}) requires Find ('F') and Replace ('R') inputs.")

    config = node.get("config", {})
    f_field = config.get("find_field", "")
    r_field = config.get("replace_field", "")
    replace_with = config.get("replace_with_field", "")

    if not f_field or not r_field or not replace_with:
        return {"O": f"SELECT * FROM {find_src}"}

    f_quoted = dialect.quote_identifier(f_field)
    r_quoted = dialect.quote_identifier(r_field)
    w_quoted = dialect.quote_identifier(replace_with)

    query = (
        f"SELECT\n"
        f"  f.*,\n"
        f"  COALESCE(r.{w_quoted}, f.{f_quoted}) AS {f_quoted}_replaced\n"
        f"FROM {find_src} f\n"
        f"LEFT JOIN {replace_src} r ON f.{f_quoted} = r.{r_quoted}"
    )
    return {"O": query}


def transpile_summarize(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles SummarizeNode to GROUP BY with aggregate functions."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Summarize tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    actions = config.get("actions", [])

    if not actions:
        return {"O": f"SELECT * FROM {upstream}"}

    group_by_cols = []
    agg_projections = []

    for act in actions:
        field = act.get("field")
        if not field:
            continue

        action_type = str(act.get("action", "GroupBy")).lower()
        custom_out = str(act.get("output_name") or "").strip()
        quoted_field = dialect.quote_identifier(field)

        if action_type == "groupby":
            out_name = custom_out or field
            group_by_cols.append(quoted_field)
            agg_projections.append(f"{quoted_field} AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("sum",):
            out_name = custom_out or f"Sum_{field}"
            agg_projections.append(f"SUM({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("mean", "average", "avg"):
            out_name = custom_out or f"Avg_{field}"
            agg_projections.append(f"AVG({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type == "min":
            out_name = custom_out or f"Min_{field}"
            agg_projections.append(f"MIN({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type == "max":
            out_name = custom_out or f"Max_{field}"
            agg_projections.append(f"MAX({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type == "count":
            out_name = custom_out or f"Count_{field}"
            agg_projections.append(f"COUNT({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("countdistinct", "count_distinct"):
            out_name = custom_out or f"Distinct_{field}"
            agg_projections.append(f"COUNT(DISTINCT {quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("countnull", "count_null"):
            out_name = custom_out or f"Nulls_{field}"
            agg_projections.append(f"COUNT(CASE WHEN {quoted_field} IS NULL THEN 1 END) AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("countnonnull", "count_non_null"):
            out_name = custom_out or f"NonNulls_{field}"
            agg_projections.append(f"COUNT({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("stddev", "std_dev"):
            out_name = custom_out or f"StdDev_{field}"
            fn = "STDDEV_SAMP" if dialect.name in ("postgres", "snowflake", "duckdb") else "STDDEV"
            agg_projections.append(f"{fn}({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        elif action_type in ("variance", "var"):
            out_name = custom_out or f"Variance_{field}"
            fn = "VAR_SAMP" if dialect.name in ("postgres", "snowflake", "duckdb") else "VARIANCE"
            agg_projections.append(f"{fn}({quoted_field}) AS {dialect.quote_identifier(out_name)}")
        else:
            out_name = custom_out or f"{action_type}_{field}"
            agg_projections.append(f"MAX({quoted_field}) AS {dialect.quote_identifier(out_name)}")

    if not agg_projections:
        return {"O": f"SELECT * FROM {upstream}"}

    query = f"SELECT\n  {',\n  '.join(agg_projections)}\nFROM {upstream}"
    if group_by_cols:
        query += f"\nGROUP BY {', '.join(group_by_cols)}"

    return {"O": query}


def transpile_text_to_columns(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles TextToColumnsNode using SPLIT_PART."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Text to Columns tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    field = config.get("field", "")
    delim = config.get("delimiter", ",")
    num_cols = int(config.get("num_columns", 2))

    if not field or num_cols < 1:
        return {"O": f"SELECT * FROM {upstream}"}

    quoted_field = dialect.quote_identifier(field)
    projections = ["*"]

    for i in range(1, num_cols + 1):
        col_out = dialect.quote_identifier(f"{field}_{i}")
        if dialect.name == "sqlite":
            # SQLite doesn't have SPLIT_PART, fallback to substr
            projections.append(f"{quoted_field} AS {col_out}")
        else:
            projections.append(f"SPLIT_PART({quoted_field}, '{delim}', {i}) AS {col_out}")

    return {"O": f"SELECT\n  {',\n  '.join(projections)}\nFROM {upstream}"}


def transpile_date_time(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles DateTimeNode."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"DateTime tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    field = config.get("field", "")
    out_field = config.get("output_field") or f"{field}_Date"

    if not field:
        return {"O": f"SELECT * FROM {upstream}"}

    quoted_field = dialect.quote_identifier(field)
    quoted_out = dialect.quote_identifier(out_field)
    cast_sql = dialect.cast_type(field, "datetime", safe=True)

    return {"O": f"SELECT\n  *,\n  {cast_sql} AS {quoted_out}\nFROM {upstream}"}


def transpile_output_data(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles OutputDataNode (terminal passthrough)."""
    upstream = input_sources.get("I")
    if not upstream:
        return {"O": "SELECT 1 AS empty_stream WHERE 1=0"}
    return {"O": f"SELECT * FROM {upstream}"}


def transpile_passthrough(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Default fallback passthrough transpiler."""
    upstream = input_sources.get("I")
    if upstream:
        return {"O": f"SELECT * FROM {upstream}"}
    return {"O": "SELECT 1 AS placeholder"}


def transpile_multi_row_formula(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles MultiRowFormulaNode into SQL window functions (LAG, LEAD, SUM OVER, etc.)."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Multi-Row Formula tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    output_field = str(config.get("output_field", "")).strip() or "New_Field"
    expr = str(config.get("expression", "")).strip()

    if not expr:
        return {"O": f"SELECT * FROM {upstream}"}

    group_by = config.get("group_by_fields") or config.get("group_by", [])
    if isinstance(group_by, str) and group_by:
        group_by = [group_by]
    order_by = config.get("order_by_fields") or []
    if isinstance(order_by, str) and order_by:
        order_by = [order_by]

    partition_clause = f"PARTITION BY {', '.join([dialect.quote_identifier(c) for c in group_by])}" if group_by else ""
    order_clause = f"ORDER BY {', '.join([dialect.quote_identifier(c) for c in order_by])}" if order_by else ""

    norm_upper = expr.upper().replace(" ", "")

    # Sequential ID: [Row-1:Output] + 1
    if norm_upper in (f"[ROW-1:{output_field.upper()}]+1", f"1+[ROW-1:{output_field.upper()}]"):
        row_num_spec = f"({partition_clause} {order_clause or 'ORDER BY (SELECT NULL)'})".strip()
        proj = f"ROW_NUMBER() OVER ({row_num_spec}) AS {dialect.quote_identifier(output_field)}"
        return {"O": f"SELECT\n  *,\n  {proj}\nFROM {upstream}"}

    # Running Total: [Row-1:Output] + [Col]
    sum_match = re.match(rf"^\[ROW-1:{re.escape(output_field.upper())}\]\+\[([^\]]+)\]$", norm_upper)
    if not sum_match:
        sum_match = re.match(rf"^\[([^\]]+)\]\+\[ROW-1:{re.escape(output_field.upper())}\]$", norm_upper)
    if sum_match:
        col_cand = sum_match.group(1)
        # Find original case in expr if possible
        m_col = re.search(rf"\[\s*({re.escape(col_cand)})\s*\]", expr, flags=re.IGNORECASE)
        orig_col = m_col.group(1) if m_col else col_cand
        sum_spec = f"{partition_clause} {order_clause or 'ORDER BY (SELECT NULL)'} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW".strip()
        proj = f"SUM({dialect.quote_identifier(orig_col)}) OVER ({sum_spec}) AS {dialect.quote_identifier(output_field)}"
        return {"O": f"SELECT\n  *,\n  {proj}\nFROM {upstream}"}

    # General expression: replace [Row[+-]N:Col] with window call
    def _clean_token(m):
        offset_sign = m.group(1).replace(" ", "")
        col = m.group(2).strip()
        offset_num = int(offset_sign)
        if offset_num == 0:
            return f"[{col}]"
        sign_char = "+" if offset_num > 0 else ""
        return f"[Row{sign_char}{offset_num}:{col}]"

    clean_expr = re.sub(r"\[\s*Row\s*([+-]?\s*\d+)\s*:\s*([^\]]+)\s*\]", _clean_token, expr, flags=re.IGNORECASE)
    row_refs = re.findall(r"\[Row([+-]\d+):([^\]]+)\]", clean_expr)

    win_sub_map = {}
    subbed_expr = clean_expr

    for idx, (offset_str, col_name) in enumerate(row_refs):
        offset = int(offset_str)
        token = f"[Row{'+' if offset > 0 else ''}{offset}:{col_name}]"
        placeholder = f"__mr_win_var_{idx}__"
        subbed_expr = subbed_expr.replace(token, f"[{placeholder}]")

        win_order = order_clause or "ORDER BY (SELECT NULL)"
        full_win = f"{partition_clause} {win_order}".strip()
        if offset < 0:
            fn_call = f"LAG({dialect.quote_identifier(col_name)}, {-offset}) OVER ({full_win})"
        else:
            fn_call = f"LEAD({dialect.quote_identifier(col_name)}, {offset}) OVER ({full_win})"
        win_sub_map[dialect.quote_identifier(placeholder)] = fn_call

    sql_expr = transpile_expression(subbed_expr, dialect)
    for placeholder_quoted, win_call in win_sub_map.items():
        sql_expr = sql_expr.replace(placeholder_quoted, win_call)

    out_type = str(config.get("output_type") or "").strip().lower()
    quoted_col = dialect.quote_identifier(output_field)
    if out_type and out_type not in ("none", "keep"):
        cast_sql = f"CAST({sql_expr} AS {dialect.map_type(out_type)})"
        proj = f"{cast_sql} AS {quoted_col}"
    else:
        proj = f"{sql_expr} AS {quoted_col}"

    return {"O": f"SELECT\n  *,\n  {proj}\nFROM {upstream}"}


def transpile_multi_field_formula(
    node: Dict[str, Any],
    input_sources: Dict[str, Any],
    dialect: SQLDialect,
    context: Dict[str, Any]
) -> Dict[str, str]:
    """Transpiles MultiFieldFormulaNode across selected fields into SQL projections."""
    upstream = input_sources.get("I")
    if not upstream:
        raise NodeTranspileError(f"Multi-Field Formula tool ({node.get('id')}) has no incoming input.")

    config = node.get("config", {})
    selected_fields = config.get("selected_fields") or config.get("fields") or []
    output_mode = str(config.get("output_mode", "update")).strip().lower()
    output_prefix = str(config.get("output_prefix", "") or "")
    output_suffix = str(config.get("output_suffix", "") or "")
    output_type = str(config.get("output_type", "none")).strip().lower()
    expr = str(config.get("expression", "")).strip()

    if not expr or not selected_fields:
        return {"O": f"SELECT * FROM {upstream}"}

    projections = []
    for col in selected_fields:
        parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', expr)
        for i in range(0, len(parts), 2):
            chunk = parts[i]
            chunk = re.sub(r'\[\s*_CurrentField_\s*\]', f'[{col}]', chunk, flags=re.IGNORECASE)
            chunk = re.sub(r'\b_CurrentField_\b', f'[{col}]', chunk, flags=re.IGNORECASE)
            chunk = re.sub(r'\[\s*_CurrentFieldName_\s*\]', f'"{col}"', chunk, flags=re.IGNORECASE)
            chunk = re.sub(r'\b_CurrentFieldName_\b', f'"{col}"', chunk, flags=re.IGNORECASE)
            parts[i] = chunk
        col_expr = "".join(parts)

        col_sql = transpile_expression(col_expr, dialect)
        if output_type and output_type not in ("none", "keep"):
            col_sql = f"CAST({col_sql} AS {dialect.map_type(output_type)})"

        if output_mode == "create_new":
            out_alias = f"{output_prefix}{col}{output_suffix}"
        else:
            out_alias = col

        projections.append(f"{col_sql} AS {dialect.quote_identifier(out_alias)}")

    return {"O": f"SELECT\n  *,\n  {',\n  '.join(projections)}\nFROM {upstream}"}


NODE_TRANSPILER_REGISTRY = {
    "input_data": transpile_input_data,
    "text_input": transpile_text_input,
    "output_data": transpile_output_data,
    "browse": transpile_passthrough,
    "select": transpile_select,
    "auto_field": transpile_auto_field,
    "filter": transpile_filter,
    "formula": transpile_formula,
    "multi_row_formula": transpile_multi_row_formula,
    "multi_field_formula": transpile_multi_field_formula,
    "sort": transpile_sort,
    "clean": transpile_clean,
    "unique": transpile_unique,
    "sample": transpile_sample,
    "record_id": transpile_record_id,
    "join": transpile_join,
    "union": transpile_union,
    "append_fields": transpile_append_fields,
    "find_replace": transpile_find_replace,
    "summarize": transpile_summarize,
    "text_to_columns": transpile_text_to_columns,
    "date_time": transpile_date_time,
}


def get_node_transpiler(node_type: str):
    """Returns the transpiler function for the given node type or default passthrough."""
    return NODE_TRANSPILER_REGISTRY.get(str(node_type).lower(), transpile_passthrough)

