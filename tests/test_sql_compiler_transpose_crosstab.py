"""
Tests for Transpose, CrossTab, FindReplace, and JoinMultiple SQL Transpilation.
Verifies dialect-specific syntax (ANSI, DuckDB, Snowflake) and tests live SQL execution in SQLite.
"""
import sqlite3
import pandas as pd
import pytest

from backend.engine.sql_compiler import (
    compile_workflow_to_sql,
    get_dialect,
)
from backend.engine.executor import WorkflowExecutor


def test_transpose_ansi_sql_transpilation():
    """Verifies that Transpose tool compiles to ANSI SQL UNION ALL unpivot."""
    wf = {
        "name": "Transpose Pipeline",
        "nodes": [
            {
                "id": "n_data",
                "type": "text_input",
                "name": "Scores",
                "config": {
                    "columns": ["Student", "Subject", "Q1", "Q2", "Q3"],
                    "data": [
                        ["Alice", "Math", 90, 85, 95],
                        ["Bob", "Science", 80, 75, 88],
                    ]
                }
            },
            {
                "id": "n_trans",
                "type": "transpose",
                "name": "Unpivot Quarters",
                "config": {
                    "key_columns": ["Student", "Subject"],
                    "data_columns": ["Q1", "Q2", "Q3"],
                    "name_column": "Quarter",
                    "value_column": "Score"
                }
            }
        ],
        "connections": [
            {"source": "n_data", "target": "n_trans", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="ansi")
    assert res["success"] is True
    sql = res["sql"]

    assert "UNION ALL" in sql
    assert "'Q1' AS \"Quarter\"" in sql
    assert "\"Q1\" AS \"Score\"" in sql
    assert "\"Student\"" in sql
    assert "\"Subject\"" in sql


def test_transpose_live_sqlite_execution():
    """Verifies live SQL execution of Transpose unpivot in SQLite."""
    wf = {
        "name": "Transpose Live Test",
        "nodes": [
            {
                "id": "n_data",
                "type": "text_input",
                "name": "Sales",
                "config": {
                    "columns": ["Region", "Jan", "Feb"],
                    "data": [
                        ["East", 100, 150],
                        ["West", 200, 250],
                    ]
                }
            },
            {
                "id": "n_trans",
                "type": "transpose",
                "name": "Unpivot Months",
                "config": {
                    "key_columns": ["Region"],
                    "data_columns": ["Jan", "Feb"],
                    "name_column": "Month",
                    "value_column": "Revenue"
                }
            }
        ],
        "connections": [
            {"source": "n_data", "target": "n_trans", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="sqlite")
    assert res["success"] is True
    sql = res["sql"]

    # Execute in SQLite memory DB
    conn = sqlite3.connect(":memory:")
    sql_body = sql[sql.find("WITH"):] if "WITH" in sql else sql
    df = pd.read_sql_query(sql_body, conn)
    conn.close()

    assert len(df) == 4
    assert list(df.columns) == ["Region", "Month", "Revenue"]
    assert set(df["Month"]) == {"Jan", "Feb"}
    assert set(df["Region"]) == {"East", "West"}


def test_crosstab_ansi_sql_transpilation():
    """Verifies that CrossTab tool compiles to conditional aggregation in ANSI SQL."""
    wf = {
        "name": "CrossTab Pipeline",
        "nodes": [
            {
                "id": "n_data",
                "type": "text_input",
                "name": "Sales Records",
                "config": {
                    "columns": ["Region", "Category", "Amount"],
                    "data": [
                        ["North", "Electronics", 500],
                        ["North", "Furniture", 300],
                        ["South", "Electronics", 700],
                        ["South", "Furniture", 200],
                    ]
                }
            },
            {
                "id": "n_pivot",
                "type": "crosstab",
                "name": "Pivot Category Matrix",
                "config": {
                    "group_by": ["Region"],
                    "header_field": "Category",
                    "value_field": "Amount",
                    "agg_func": "sum"
                }
            }
        ],
        "connections": [
            {"source": "n_data", "target": "n_pivot", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="ansi")
    assert res["success"] is True
    sql = res["sql"]

    assert "GROUP BY \"Region\"" in sql
    assert "SUM(CASE WHEN \"Category\" = 'Electronics' THEN \"Amount\" END) AS \"Electronics\"" in sql
    assert "SUM(CASE WHEN \"Category\" = 'Furniture' THEN \"Amount\" END) AS \"Furniture\"" in sql


def test_crosstab_live_sqlite_execution():
    """Verifies live SQL execution of CrossTab pivot in SQLite."""
    wf = {
        "name": "CrossTab Live Test",
        "nodes": [
            {
                "id": "n_data",
                "type": "text_input",
                "name": "Survey",
                "config": {
                    "columns": ["Department", "Metric", "Score"],
                    "data": [
                        ["HR", "Satisfaction", 88],
                        ["HR", "Efficiency", 92],
                        ["IT", "Satisfaction", 78],
                        ["IT", "Efficiency", 95],
                    ]
                }
            },
            {
                "id": "n_pivot",
                "type": "crosstab",
                "name": "Pivot Scores",
                "config": {
                    "group_by": ["Department"],
                    "header_field": "Metric",
                    "value_field": "Score",
                    "agg_func": "mean"
                }
            }
        ],
        "connections": [
            {"source": "n_data", "target": "n_pivot", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="sqlite")
    assert res["success"] is True
    sql = res["sql"]

    conn = sqlite3.connect(":memory:")
    sql_body = sql[sql.find("WITH"):] if "WITH" in sql else sql
    df = pd.read_sql_query(sql_body, conn)
    conn.close()

    assert len(df) == 2
    assert "Department" in df.columns
    assert "Satisfaction" in df.columns
    assert "Efficiency" in df.columns
    hr_row = df[df["Department"] == "HR"].iloc[0]
    assert hr_row["Satisfaction"] == 88.0
    assert hr_row["Efficiency"] == 92.0


def test_find_replace_sql_transpilation_and_execution():
    """Verifies FindReplace SQL transpilation using find_value_field and live execution."""
    wf = {
        "name": "Find Replace Pipeline",
        "nodes": [
            {
                "id": "n_main",
                "type": "text_input",
                "name": "Main Data",
                "config": {
                    "columns": ["ID", "Code", "Value"],
                    "data": [
                        [1, "C1", 100],
                        [2, "C2", 200],
                        [3, "C9", 300],
                    ]
                }
            },
            {
                "id": "n_dict",
                "type": "text_input",
                "name": "Dictionary",
                "config": {
                    "columns": ["RefCode", "FriendlyName"],
                    "data": [
                        ["C1", "Alpha"],
                        ["C2", "Beta"],
                    ]
                }
            },
            {
                "id": "n_fr",
                "type": "find_replace",
                "name": "Map Friendly Names",
                "config": {
                    "find_field": "Code",
                    "find_value_field": "RefCode",
                    "replace_with_field": "FriendlyName",
                    "action": "replace",
                    "case_sensitive": False
                }
            }
        ],
        "connections": [
            {"source": "n_main", "target": "n_fr", "sourceHandle": "O", "targetHandle": "F"},
            {"source": "n_dict", "target": "n_fr", "sourceHandle": "O", "targetHandle": "R"},
        ]
    }

    res = compile_workflow_to_sql(wf, dialect="sqlite")
    assert res["success"] is True
    sql = res["sql"]

    assert "LEFT JOIN" in sql
    assert "COALESCE(" in sql

    conn = sqlite3.connect(":memory:")
    sql_body = sql[sql.find("WITH"):] if "WITH" in sql else sql
    df = pd.read_sql_query(sql_body, conn)
    conn.close()

    assert len(df) == 3
    # Rows 1 and 2 should have Code replaced by Alpha and Beta, Row 3 remains C9
    row1 = df[df["ID"] == 1].iloc[0]
    row2 = df[df["ID"] == 2].iloc[0]
    row3 = df[df["ID"] == 3].iloc[0]
    assert row1["Code"] == "Alpha"
    assert row2["Code"] == "Beta"
    assert row3["Code"] == "C9"


def test_marketing_attribution_template_full_pipeline_compiles():
    """Tests that the full Marketing Attribution & Survey Matrix template compiles to proper SQL."""
    import json
    with open("workflows/templates/marketing_campaign_attribution.json", "r", encoding="utf-8") as f:
        wf = json.load(f)

    res = compile_workflow_to_sql(wf, dialect="ansi")
    assert res["success"] is True
    sql = res["sql"]

    # Ensure none of the nodes fell back to useless pass-throughs
    assert "cte_replace_campaign_codes AS (" in sql
    assert "LEFT JOIN cte_campaign_dictionary" in sql

    assert "cte_unpivot_quarterly_scores AS (" in sql
    assert "UNION ALL" in sql
    assert "'Q1' AS \"Quarter\"" in sql

    assert "cte_pivot_to_regional_matrix AS (" in sql
    assert "GROUP BY \"Region\"" in sql
    assert "Summer_Brand_Lift" in sql
    assert "Winter_Holiday_Blitz" in sql
