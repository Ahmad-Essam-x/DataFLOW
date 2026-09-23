import pytest
import pandas as pd
import numpy as np

from backend.engine.nodes.preparation import MultiRowFormulaNode, MultiFieldFormulaNode
from backend.engine.sql_compiler.dialects import get_dialect
from backend.engine.sql_compiler.node_transpilers import (
    transpile_multi_row_formula,
    transpile_multi_field_formula
)


# ======================================================================
# Multi-Row Formula Tests
# ======================================================================

def test_multi_row_running_total():
    df = pd.DataFrame({
        "ID": [1, 2, 3, 4],
        "Sales": [100, 200, 150, 50]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "RunningTotal",
        "expression": "[Row-1:RunningTotal] + [Sales]",
        "output_type": "integer"
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["RunningTotal"]) == [100, 300, 450, 500]


def test_multi_row_running_total_grouped():
    df = pd.DataFrame({
        "Region": ["East", "East", "West", "West"],
        "Sales": [10, 20, 100, 200]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "RegionTotal",
        "expression": "[Row-1:RegionTotal] + [Sales]",
        "group_by_fields": ["Region"],
        "output_type": "integer"
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["RegionTotal"]) == [10, 30, 100, 300]


def test_multi_row_lag_difference():
    df = pd.DataFrame({
        "Month": [1, 2, 3, 4],
        "Revenue": [100.0, 120.0, 110.0, 150.0]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "DiffVsPrior",
        "expression": "[Revenue] - [Row-1:Revenue]",
        "values_for_rows_not_exist": "null"
    })
    res = node.execute({"I": df}, {})["O"]
    assert pd.isna(res["DiffVsPrior"].iloc[0])
    assert res["DiffVsPrior"].iloc[1] == 20.0
    assert res["DiffVsPrior"].iloc[2] == -10.0
    assert res["DiffVsPrior"].iloc[3] == 40.0


def test_multi_row_lag_difference_zero_boundary():
    df = pd.DataFrame({
        "Revenue": [100.0, 120.0]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "DiffVsPrior",
        "expression": "[Revenue] - [Row-1:Revenue]",
        "values_for_rows_not_exist": "zero_or_empty"
    })
    res = node.execute({"I": df}, {})["O"]
    assert res["DiffVsPrior"].iloc[0] == 100.0
    assert res["DiffVsPrior"].iloc[1] == 20.0


def test_multi_row_sequential_id():
    df = pd.DataFrame({
        "Dept": ["Sales", "Sales", "HR", "HR", "HR"],
        "Name": ["Alice", "Bob", "Charlie", "David", "Eve"]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "SeqID",
        "expression": "[Row-1:SeqID] + 1",
        "group_by_fields": ["Dept"]
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["SeqID"]) == [1, 2, 1, 2, 3]


def test_multi_row_fill_down():
    df = pd.DataFrame({
        "Category": ["Electronics", None, None, "Clothing", None]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "Category",
        "is_new_field": False,
        "expression": "IF ISNULL([Category]) THEN [Row-1:Category] ELSE [Category] ENDIF"
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["Category"]) == ["Electronics", "Electronics", "Electronics", "Clothing", "Clothing"]


def test_multi_row_lead_value():
    df = pd.DataFrame({
        "Step": [1, 2, 3],
        "Value": [10, 20, 30]
    })
    node = MultiRowFormulaNode("node_test", {
        "output_field": "NextValue",
        "expression": "[Row+1:Value]",
        "values_for_rows_not_exist": "null"
    })
    res = node.execute({"I": df}, {})["O"]
    assert res["NextValue"].iloc[0] == 20
    assert res["NextValue"].iloc[1] == 30
    assert pd.isna(res["NextValue"].iloc[2])


# ======================================================================
# Multi-Field Formula Tests
# ======================================================================

def test_multi_field_trim_strings():
    df = pd.DataFrame({
        "ColA": ["  apple ", "banana  "],
        "ColB": [" cherry", "date "],
        "Num": [1, 2]
    })
    node = MultiFieldFormulaNode("node_test", {
        "selected_fields": ["ColA", "ColB"],
        "output_mode": "update",
        "expression": "TRIM(_CurrentField_)"
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["ColA"]) == ["apple", "banana"]
    assert list(res["ColB"]) == ["cherry", "date"]
    assert list(res["Num"]) == [1, 2]


def test_multi_field_uppercase_all():
    df = pd.DataFrame({
        "First": ["alice", "bob"],
        "Last": ["smith", "jones"]
    })
    node = MultiFieldFormulaNode("node_test", {
        "selected_fields": ["First", "Last"],
        "output_mode": "update",
        "expression": "UPPER(_CurrentField_)"
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["First"]) == ["ALICE", "BOB"]
    assert list(res["Last"]) == ["SMITH", "JONES"]


def test_multi_field_fill_nulls_zero_and_create_new():
    df = pd.DataFrame({
        "Revenue": [100.0, None, 300.0],
        "Cost": [50.0, 75.0, None]
    })
    node = MultiFieldFormulaNode("node_test", {
        "selected_fields": ["Revenue", "Cost"],
        "output_mode": "create_new",
        "output_prefix": "Clean_",
        "output_suffix": "",
        "expression": "IFNULL(_CurrentField_, 0)"
    })
    res = node.execute({"I": df}, {})["O"]
    assert "Clean_Revenue" in res.columns
    assert "Clean_Cost" in res.columns
    assert list(res["Clean_Revenue"]) == [100.0, 0.0, 300.0]
    assert list(res["Clean_Cost"]) == [50.0, 75.0, 0.0]
    assert pd.isna(res["Revenue"].iloc[1])


def test_multi_field_type_filter_numeric():
    df = pd.DataFrame({
        "Text": ["a", "b"],
        "Val1": [1.5, 2.5],
        "Val2": [10.2, 20.8]
    })
    node = MultiFieldFormulaNode("node_test", {
        "field_type_filter": "numeric",
        "output_mode": "update",
        "output_type": "integer",
        "expression": "ROUND(_CurrentField_, 0)"
    })
    res = node.execute({"I": df}, {})["O"]
    assert list(res["Text"]) == ["a", "b"]
    assert list(res["Val1"]) in ([2, 2], [2, 3])


# ======================================================================
# SQL Transpilation Tests
# ======================================================================

def test_sql_transpile_multi_row_running_total():
    dialect = get_dialect("duckdb")
    node = {
        "id": "node_mr_1",
        "config": {
            "output_field": "CumSales",
            "expression": "[Row-1:CumSales] + [Sales]",
            "group_by_fields": ["Region"],
            "order_by_fields": ["Date"]
        }
    }
    sql = transpile_multi_row_formula(node, {"I": "cte_in"}, dialect, {})["O"]
    assert 'SUM("Sales") OVER (PARTITION BY "Region" ORDER BY "Date" ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS "CumSales"' in sql


def test_sql_transpile_multi_row_lag():
    dialect = get_dialect("duckdb")
    node = {
        "id": "node_mr_2",
        "config": {
            "output_field": "Growth",
            "expression": "[Sales] - [Row-1:Sales]",
            "order_by_fields": ["Date"]
        }
    }
    sql = transpile_multi_row_formula(node, {"I": "cte_in"}, dialect, {})["O"]
    assert 'LAG("Sales", 1) OVER (ORDER BY "Date")' in sql
    assert 'AS "Growth"' in sql


def test_sql_transpile_multi_field():
    dialect = get_dialect("duckdb")
    node = {
        "id": "node_mf_1",
        "config": {
            "selected_fields": ["ColA", "ColB"],
            "output_mode": "create_new",
            "output_prefix": "Trimmed_",
            "expression": "TRIM(_CurrentField_)"
        }
    }
    sql = transpile_multi_field_formula(node, {"I": "cte_in"}, dialect, {})["O"]
    assert 'TRIM("ColA") AS "Trimmed_ColA"' in sql
    assert 'TRIM("ColB") AS "Trimmed_ColB"' in sql
