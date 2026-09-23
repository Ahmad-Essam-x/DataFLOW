"""
Unit and Integration Tests for Antigravity DataFlow SQL Compiler & Execution Parity.
"""
import sqlite3
import pandas as pd
import pytest

from backend.engine.sql_compiler import (
    SQLDialect,
    SnowflakeDialect,
    PostgresDialect,
    BigQueryDialect,
    DuckDBDialect,
    SQLiteDialect,
    get_dialect,
    transpile_expression,
    compile_workflow_to_sql
)
from backend.engine.executor import WorkflowExecutor


# ----------------------------------------------------------------------
# 1. Formula AST Transpiler Tests
# ----------------------------------------------------------------------

def test_transpile_bracketed_columns():
    sql = transpile_expression("[First Name] + ' ' + [Last Name]")
    assert '"First Name"' in sql
    assert '"Last Name"' in sql


def test_transpile_conditionals_if_then_else():
    expr = 'IF [Score] >= 90 THEN "A" ELSEIF [Score] >= 80 THEN "B" ELSE "C" ENDIF'
    sql = transpile_expression(expr)
    assert "CASE" in sql
    assert 'WHEN ("Score" >= 90) THEN \'A\'' in sql
    assert 'WHEN ("Score" >= 80) THEN \'B\'' in sql
    assert "ELSE 'C' END" in sql


def test_transpile_iif():
    expr = 'IIF([Status] == "Active", 1, 0)'
    sql = transpile_expression(expr)
    assert 'WHEN ("Status" = \'Active\') THEN 1 ELSE 0 END' in sql


def test_transpile_string_functions():
    sql_trim = transpile_expression("Trim([City])")
    assert 'TRIM("City")' in sql_trim

    sql_upper = transpile_expression("UpperCase([State])")
    assert 'UPPER("State")' in sql_upper

    sql_lower = transpile_expression("LowerCase([Country])")
    assert 'LOWER("Country")' in sql_lower

    sql_len = transpile_expression("Length([Zip])")
    assert 'LENGTH("Zip")' in sql_len


def test_transpile_null_checks():
    sql_null = transpile_expression("IsNull([Email])")
    assert '("Email" IS NULL)' in sql_null

    sql_notnull = transpile_expression("NotNull([Email])")
    assert '("Email" IS NOT NULL)' in sql_notnull

    sql_empty = transpile_expression("IsEmpty([Phone])")
    assert '("Phone" IS NULL OR' in sql_empty


def test_transpile_math_functions():
    sql_round = transpile_expression("Round([Price], 2)")
    assert 'ROUND("Price", 2)' in sql_round

    sql_abs = transpile_expression("Abs([Delta])")
    assert 'ABS("Delta")' in sql_abs


def test_transpile_conversions():
    sql_num = transpile_expression("ToNumber([StringVal])")
    assert 'CAST("StringVal" AS NUMERIC)' in sql_num

    sql_str = transpile_expression("ToString([IntVal])")
    assert 'CAST("IntVal" AS VARCHAR)' in sql_str


# ----------------------------------------------------------------------
# 2. Dialect Specific Syntax Tests
# ----------------------------------------------------------------------

def test_bigquery_backtick_identifiers():
    bq = get_dialect("bigquery")
    sql = transpile_expression("[User Name] == 'Admin'", dialect=bq)
    assert '`User Name`' in sql


def test_snowflake_functions():
    sf = get_dialect("snowflake")
    sql = transpile_expression("DateTimeNow()", dialect=sf)
    assert "CURRENT_TIMESTAMP()" in sql


def test_postgres_concat():
    pg = get_dialect("postgres")
    sql = transpile_expression("Concat([A], [B], [C])", dialect=pg)
    assert '"A" || "B" || "C"' in sql


# ----------------------------------------------------------------------
# 3. Node Transpilation & Compiler Tests
# ----------------------------------------------------------------------

def test_linear_workflow_compilation():
    wf = {
        "name": "Linear Analytics",
        "nodes": [
            {
                "id": "node_input",
                "type": "text_input",
                "name": "Customers",
                "config": {
                    "data": [
                        {"ID": 1, "Name": "Alice", "Sales": 150},
                        {"ID": 2, "Name": "Bob", "Sales": 80}
                    ]
                }
            },
            {
                "id": "node_formula",
                "type": "formula",
                "name": "Bonus Calc",
                "config": {
                    "formulas": [
                        {"column": "Bonus", "expression": "[Sales] * 0.1"}
                    ]
                }
            },
            {
                "id": "node_sort",
                "type": "sort",
                "name": "Order By Sales",
                "config": {
                    "sort_fields": [{"field": "Sales", "order": "desc"}]
                }
            }
        ],
        "connections": [
            {"source": "node_input", "target": "node_formula", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "node_formula", "target": "node_sort", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="postgres")
    assert res["success"] is True
    sql = res["sql"]
    assert "WITH" in sql
    assert "cte_customers AS (" in sql
    assert "cte_bonus_calc AS (" in sql
    assert "cte_order_by_sales AS (" in sql
    assert 'ORDER BY "Sales" DESC' in sql
    assert "SELECT * FROM cte_order_by_sales;" in sql


def test_multi_port_filter_routing():
    wf = {
        "name": "Filter Branching",
        "nodes": [
            {
                "id": "in_1",
                "type": "text_input",
                "name": "Raw",
                "config": {"data": [{"Val": 10}, {"Val": 25}]}
            },
            {
                "id": "flt_1",
                "type": "filter",
                "name": "SplitVal",
                "config": {"mode": "custom", "expression": "[Val] > 20"}
            },
            {
                "id": "sort_true",
                "type": "sort",
                "name": "High Values",
                "config": {"sort_fields": [{"field": "Val", "order": "desc"}]}
            },
            {
                "id": "sort_false",
                "type": "sort",
                "name": "Low Values",
                "config": {"sort_fields": [{"field": "Val", "order": "asc"}]}
            }
        ],
        "connections": [
            {"source": "in_1", "target": "flt_1", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "flt_1", "target": "sort_true", "sourceHandle": "T", "targetHandle": "I"},
            {"source": "flt_1", "target": "sort_false", "sourceHandle": "F", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="snowflake")
    assert res["success"] is True
    sql = res["sql"]
    # Check that both T and F CTEs are generated
    assert "cte_splitval_t AS (" in sql
    assert "cte_splitval_f AS (" in sql
    # Check that downstream nodes select from the respective port CTE
    assert "FROM cte_splitval_t" in sql
    assert "FROM cte_splitval_f" in sql


def test_multi_port_join_and_summarize():
    wf = {
        "name": "Join Pipeline",
        "nodes": [
            {
                "id": "orders",
                "type": "text_input",
                "name": "Orders",
                "config": {"data": [{"OrderID": 101, "CustID": 1, "Amount": 50.0}]}
            },
            {
                "id": "customers",
                "type": "text_input",
                "name": "Customers",
                "config": {"data": [{"CustID": 1, "Region": "North"}]}
            },
            {
                "id": "join_tool",
                "type": "join",
                "name": "Match Orders",
                "config": {
                    "join_keys": [{"left_key": "CustID", "right_key": "CustID"}]
                }
            },
            {
                "id": "agg_tool",
                "type": "summarize",
                "name": "Summary",
                "config": {
                    "actions": [
                        {"field": "Region", "action": "GroupBy"},
                        {"field": "Amount", "action": "Sum", "output_name": "Total_Spend"}
                    ]
                }
            }
        ],
        "connections": [
            {"source": "orders", "target": "join_tool", "sourceHandle": "O", "targetHandle": "L"},
            {"source": "customers", "target": "join_tool", "sourceHandle": "O", "targetHandle": "R"},
            {"source": "join_tool", "target": "agg_tool", "sourceHandle": "J", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="ansi")
    assert res["success"] is True
    sql = res["sql"]
    assert "INNER JOIN cte_customers r" in sql
    assert "SUM(\"Amount\") AS \"Total_Spend\"" in sql
    assert "GROUP BY \"Region\"" in sql


# ----------------------------------------------------------------------
# 4. In-Memory Execution Parity Test (SQLite)
# ----------------------------------------------------------------------

def test_sql_execution_parity_with_engine():
    """
    Executes the same workflow via:
    1. Visual Python Executor (Pandas engine)
    2. In-memory SQLite database executing the transpiled SQL
    And asserts 100% record and value equality!
    """
    wf = {
        "name": "Parity Test Workflow",
        "nodes": [
            {
                "id": "node_input",
                "type": "text_input",
                "name": "Employees",
                "config": {
                    "data": [
                        {"Dept": "Engineering", "Salary": 120000},
                        {"Dept": "Engineering", "Salary": 140000},
                        {"Dept": "Sales", "Salary": 90000},
                        {"Dept": "Sales", "Salary": 110000},
                        {"Dept": "Marketing", "Salary": 75000}
                    ]
                }
            },
            {
                "id": "node_filter",
                "type": "filter",
                "name": "High Earners",
                "config": {
                    "mode": "custom",
                    "expression": "[Salary] >= 100000"
                }
            },
            {
                "id": "node_summarize",
                "type": "summarize",
                "name": "Dept Spend",
                "config": {
                    "actions": [
                        {"field": "Dept", "action": "GroupBy"},
                        {"field": "Salary", "action": "Sum", "output_name": "Total_High_Salary"},
                        {"field": "Salary", "action": "Count", "output_name": "Headcount"}
                    ]
                }
            },
            {
                "id": "node_sort",
                "type": "sort",
                "name": "Order By Spend",
                "config": {
                    "sort_fields": [{"field": "Total_High_Salary", "order": "desc"}]
                }
            }
        ],
        "connections": [
            {"source": "node_input", "target": "node_filter", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "node_filter", "target": "node_summarize", "sourceHandle": "T", "targetHandle": "I"},
            {"source": "node_summarize", "target": "node_sort", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    # 1. Run in Python engine
    executor = WorkflowExecutor()
    exec_res = executor.run(wf)
    assert exec_res.success is True
    engine_df = executor.data_cache["node_sort"]["O"]

    # 2. Compile to SQLite SQL
    sql_res = compile_workflow_to_sql(wf, dialect="sqlite")
    assert sql_res["success"] is True
    generated_sql = sql_res["sql"]

    # 3. Execute compiled SQL directly in in-memory SQLite
    conn = sqlite3.connect(":memory:")
    # Remove SQL header comment block for SQLite execute if needed, or pass full statement
    sql_body = generated_sql[generated_sql.find("WITH"):]
    sql_df = pd.read_sql_query(sql_body, conn)
    conn.close()

    # 4. Compare Engine DataFrame vs SQL DataFrame
    assert len(sql_df) == len(engine_df)
    assert list(sql_df.columns) == list(engine_df.columns)
    pd.testing.assert_frame_equal(sql_df.reset_index(drop=True), engine_df.reset_index(drop=True), check_dtype=False)


# ----------------------------------------------------------------------
# 5. REST API Integration Tests
# ----------------------------------------------------------------------

def test_api_to_sql_endpoints():
    from backend.app import app
    client = app.test_client()

    # GET dialects
    res = client.get("/api/workflow/sql-dialects")
    assert res.status_code == 200
    d_json = res.get_json()
    assert d_json["success"] is True
    ids = [d["id"] for d in d_json["dialects"]]
    assert "snowflake" in ids
    assert "postgres" in ids
    assert "duckdb" in ids

    # POST to-sql
    wf = {
        "name": "API Flow",
        "nodes": [
            {"id": "n1", "type": "input_data", "name": "Sales Raw", "config": {"filepath": "sales.csv"}},
            {"id": "n2", "type": "select", "name": "Select Fields", "config": {"fields": [{"name": "Amount", "selected": True}]}}
        ],
        "connections": [
            {"source": "n1", "target": "n2", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }
    post_res = client.post("/api/workflow/to-sql", json={"workflow": wf, "dialect": "snowflake"})
    assert post_res.status_code == 200
    post_json = post_res.get_json()
    assert post_json["success"] is True
    assert "cte_sales_raw" in post_json["sql"]
    assert "cte_select_fields" in post_json["sql"]

    # POST download
    dl_res = client.post("/api/workflow/to-sql/download", json={"sql": post_json["sql"], "filename": "test.sql"})
    assert dl_res.status_code == 200
    assert b"cte_sales_raw" in dl_res.data

