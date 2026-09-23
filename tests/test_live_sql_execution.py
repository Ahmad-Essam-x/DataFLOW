"""
Live SQL Execution Engine Verification Test Suite.
Verifies semantic and data parity between Python/Pandas WorkflowExecutor
and compiled SQL Common Table Expressions (CTEs) executed against a live SQL engine (in-memory SQLite).
"""
import sqlite3
import pandas as pd
import numpy as np
import pytest

from backend.engine.sql_compiler import compile_workflow_to_sql
from backend.engine.executor import WorkflowExecutor


def _run_and_compare_sql(wf: dict):
    """
    Executes a workflow in the Python engine and compiles it to SQLite SQL.
    Executes the generated SQL in SQLite and verifies that the resulting DataFrame matches the Python engine output.
    """
    # 1. Run in Python engine
    executor = WorkflowExecutor()
    exec_res = executor.run(wf)
    assert exec_res.success is True, f"Python engine execution failed: {exec_res.error}"

    # Find the terminal leaf node
    all_sources = {c["source"] for c in wf.get("connections", [])}
    all_targets = {c["target"] for c in wf.get("connections", [])}
    leaf_ids = all_targets - all_sources
    if not leaf_ids:
        leaf_ids = {wf["nodes"][-1]["id"]}
    leaf_id = list(leaf_ids)[0]

    leaf_port = "O"
    leaf_node = next(n for n in wf["nodes"] if n["id"] == leaf_id)
    if leaf_node["type"] == "filter":
        leaf_port = "T"
    elif leaf_node["type"] == "join":
        leaf_port = "J"

    engine_df = executor.data_cache[leaf_id][leaf_port]

    # 2. Compile to SQLite SQL
    sql_res = compile_workflow_to_sql(wf, dialect="sqlite")
    assert sql_res["success"] is True, f"SQL compilation failed: {sql_res.get('error')}"
    sql_text = sql_res["sql"]

    # 3. Execute in SQLite
    conn = sqlite3.connect(":memory:")
    # Extract WITH ... body
    sql_body = sql_text[sql_text.find("WITH"):] if "WITH" in sql_text else sql_text
    sql_df = pd.read_sql_query(sql_body, conn)
    conn.close()

    # 4. Compare Engine DF vs SQL DF
    assert len(sql_df) == len(engine_df), f"Row count mismatch: SQL had {len(sql_df)}, Engine had {len(engine_df)}"
    assert list(sql_df.columns) == list(engine_df.columns), f"Columns mismatch: SQL {list(sql_df.columns)} vs Engine {list(engine_df.columns)}"

    # Normalize values for loose comparison across SQLite vs Pandas numeric types
    for col in sql_df.columns:
        if pd.api.types.is_numeric_dtype(sql_df[col]) and pd.api.types.is_numeric_dtype(engine_df[col]):
            np.testing.assert_allclose(
                sql_df[col].fillna(0).values,
                engine_df[col].fillna(0).values,
                rtol=1e-4,
                err_msg=f"Values differ in column '{col}'"
            )
        else:
            s1 = sql_df[col].astype(str).fillna("").values
            s2 = engine_df[col].astype(str).fillna("").values
            assert list(s1) == list(s2), f"String content differs in column '{col}'"

    return sql_df, engine_df


# ----------------------------------------------------------------------
# 1. Formula & Arithmetic Pipeline Parity
# ----------------------------------------------------------------------
def test_live_sql_formula_and_arithmetic_parity():
    seed_records = [
        {"EmpID": 101, "Salary": 50000, "Bonus": 5000, "Active": 1},
        {"EmpID": 102, "Salary": 85000, "Bonus": 10000, "Active": 1},
        {"EmpID": 103, "Salary": 120000, "Bonus": 20000, "Active": 0},
        {"EmpID": 104, "Salary": 40000, "Bonus": 2000, "Active": 1},
    ]

    wf = {
        "name": "Live Formula Test",
        "nodes": [
            {
                "id": "n_src",
                "type": "text_input",
                "name": "Employees",
                "config": {"data": seed_records}
            },
            {
                "id": "n_formula",
                "type": "formula",
                "name": "Compute Total Comp",
                "config": {
                    "expressions": [
                        {"field": "Total_Comp", "expression": "[Salary] + [Bonus]", "type": "int64"},
                        {"field": "Eligible", "expression": 'IIF([Salary] > 60000 AND [Active] == 1, 1, 0)', "type": "int32"}
                    ]
                }
            },
            {
                "id": "n_sort",
                "type": "sort",
                "name": "Sort By Comp",
                "config": {
                    "sort_fields": [{"field": "Total_Comp", "order": "desc"}]
                }
            }
        ],
        "connections": [
            {"source": "n_src", "target": "n_formula", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n_formula", "target": "n_sort", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    _run_and_compare_sql(wf)


# ----------------------------------------------------------------------
# 2. Filter & Selection Pipeline Parity
# ----------------------------------------------------------------------
def test_live_sql_filter_and_select_parity():
    seed_records = [
        {"ID": 1, "Category": "Hardware", "Price": 250.0, "Quantity": 10},
        {"ID": 2, "Category": "Software", "Price": 50.0, "Quantity": 100},
        {"ID": 3, "Category": "Hardware", "Price": 15.0, "Quantity": 500},
        {"ID": 4, "Category": "Services", "Price": 1200.0, "Quantity": 5},
    ]

    wf = {
        "name": "Filter and Select Pipeline",
        "nodes": [
            {
                "id": "n_in",
                "type": "text_input",
                "name": "Products",
                "config": {"data": seed_records}
            },
            {
                "id": "n_filter",
                "type": "filter",
                "name": "Price Filter",
                "config": {
                    "mode": "custom",
                    "expression": "[Price] >= 50.0 AND [Category] != 'Services'"
                }
            },
            {
                "id": "n_select",
                "type": "select",
                "name": "Rename and Project",
                "config": {
                    "fields": [
                        {"name": "ID", "selected": True},
                        {"name": "Category", "selected": True, "rename": "Product_Category"},
                        {"name": "Price", "selected": True, "rename": "Unit_Price"},
                        {"name": "Quantity", "selected": False}
                    ]
                }
            }
        ],
        "connections": [
            {"source": "n_in", "target": "n_filter", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n_filter", "target": "n_select", "sourceHandle": "T", "targetHandle": "I"}
        ]
    }

    _run_and_compare_sql(wf)


# ----------------------------------------------------------------------
# 3. Aggregation (Summarize) with GroupBy & Counts
# ----------------------------------------------------------------------
def test_live_sql_summarize_group_by_parity():
    seed_records = [
        {"Region": "North", "Sales": 1000, "Returns": 50},
        {"Region": "North", "Sales": 1500, "Returns": 30},
        {"Region": "South", "Sales": 2000, "Returns": 100},
        {"Region": "South", "Sales": 3000, "Returns": 150},
        {"Region": "East", "Sales": 800, "Returns": 10},
    ]

    wf = {
        "name": "Regional Summary",
        "nodes": [
            {
                "id": "n_in",
                "type": "text_input",
                "name": "Regional Sales",
                "config": {"data": seed_records}
            },
            {
                "id": "n_sum",
                "type": "summarize",
                "name": "Group by Region",
                "config": {
                    "actions": [
                        {"field": "Region", "action": "GroupBy"},
                        {"field": "Sales", "action": "Sum", "output_name": "Total_Sales"},
                        {"field": "Sales", "action": "Count", "output_name": "Transaction_Count"},
                        {"field": "Returns", "action": "Sum", "output_name": "Total_Returns"}
                    ]
                }
            },
            {
                "id": "n_sort",
                "type": "sort",
                "name": "Order By Sales",
                "config": {
                    "sort_fields": [{"field": "Total_Sales", "order": "desc"}]
                }
            }
        ],
        "connections": [
            {"source": "n_in", "target": "n_sum", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n_sum", "target": "n_sort", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    _run_and_compare_sql(wf)


# ----------------------------------------------------------------------
# 4. Multi-Stream Join Parity (Inner Join J stream)
# ----------------------------------------------------------------------
def test_live_sql_inner_join_parity():
    orders = [
        {"OrderID": 1, "CustomerID": 101, "Amount": 150},
        {"OrderID": 2, "CustomerID": 102, "Amount": 300},
        {"OrderID": 3, "CustomerID": 103, "Amount": 450},
    ]
    customers = [
        {"CustomerID": 101, "CustomerName": "Alice", "Tier": "Gold"},
        {"CustomerID": 102, "CustomerName": "Bob", "Tier": "Silver"},
        {"CustomerID": 105, "CustomerName": "Charlie", "Tier": "Bronze"},
    ]

    wf = {
        "name": "Order Customer Join",
        "nodes": [
            {"id": "n_ord", "type": "text_input", "name": "Orders", "config": {"data": orders}},
            {"id": "n_cust", "type": "text_input", "name": "Customers", "config": {"data": customers}},
            {
                "id": "n_join",
                "type": "join",
                "name": "Join on CustID",
                "config": {
                    "join_type": "inner",
                    "left_keys": ["CustomerID"],
                    "right_keys": ["CustomerID"]
                }
            },
            {
                "id": "n_select",
                "type": "select",
                "name": "Project Clean Columns",
                "config": {
                    "fields": [
                        {"name": "OrderID", "selected": True},
                        {"name": "CustomerID", "selected": True},
                        {"name": "Amount", "selected": True},
                        {"name": "CustomerName", "selected": True},
                        {"name": "Tier", "selected": True}
                    ]
                }
            },
            {
                "id": "n_sort",
                "type": "sort",
                "name": "Order by ID",
                "config": {
                    "sort_fields": [{"field": "OrderID", "order": "asc"}]
                }
            }
        ],
        "connections": [
            {"source": "n_ord", "target": "n_join", "sourceHandle": "O", "targetHandle": "L"},
            {"source": "n_cust", "target": "n_join", "sourceHandle": "O", "targetHandle": "R"},
            {"source": "n_join", "target": "n_select", "sourceHandle": "J", "targetHandle": "I"},
            {"source": "n_select", "target": "n_sort", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    _run_and_compare_sql(wf)
