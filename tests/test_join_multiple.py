"""
Comprehensive tests for Alteryx-parity Join Multiple (Multi-Join) Node
"""
import pandas as pd
import numpy as np
import pytest

from backend.engine.nodes.join import JoinMultipleNode
from backend.engine.nodes.base import NodeExecutionError
from backend.engine.executor import WorkflowExecutor


def test_join_multiple_two_tables_inner():
    """Test 2-table join with join_all_only=True (Inner Join)"""
    df1 = pd.DataFrame({"ID": [1, 2, 3], "Name": ["Alice", "Bob", "Charlie"]})
    df2 = pd.DataFrame({"ID": [2, 3, 4], "Score": [85, 90, 95]})

    node = JoinMultipleNode("node_jm", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "ID", "2": "ID"}]
    })

    out = node.execute({"I": [df1, df2]}, {})
    res = out["J"]

    assert len(res) == 2
    assert set(res["ID"]) == {2, 3}
    assert "Score" in res.columns
    assert "Name" in res.columns
    # Check column_sources attrs
    sources = res.attrs.get("column_sources", {})
    assert sources["ID"] == 1
    assert sources["Name"] == 1
    assert sources["Score"] == 2


def test_join_multiple_two_tables_outer():
    """Test 2-table join with join_all_only=False (Full Outer Join)"""
    df1 = pd.DataFrame({"ID": [1, 2, 3], "Name": ["Alice", "Bob", "Charlie"]})
    df2 = pd.DataFrame({"ID": [2, 3, 4], "Score": [85, 90, 95]})

    node = JoinMultipleNode("node_jm", {
        "join_mode": "specific_fields",
        "join_all_only": False,
        "join_keys": [{"1": "ID", "2": "ID"}]
    })

    out = node.execute({"I": [df1, df2]}, {})
    res = out["J"]

    # Full outer join keeps 1, 2, 3, 4
    assert len(res) == 4
    assert "Input2_ID" in res.columns
    # Table 1 ID has 1, 2, 3 and NaN for 4
    # Table 2 Input2_ID has NaN for 1 and 2, 3, 4
    row4 = res[res["Input2_ID"] == 4].iloc[0]
    assert pd.isna(row4["Name"])
    assert row4["Score"] == 95


def test_join_multiple_three_tables_inner():
    """Test 3-table join with join_all_only=True (Inner Join across all 3)"""
    df1 = pd.DataFrame({"CustID": [101, 102, 103], "Dept": ["HR", "IT", "Sales"]})
    df2 = pd.DataFrame({"CustID": [102, 103, 104], "Salary": [60000, 75000, 80000]})
    df3 = pd.DataFrame({"CustID": [103, 104, 105], "Bonus": [5000, 6000, 7000]})

    node = JoinMultipleNode("node_jm", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "CustID", "2": "CustID", "3": "CustID"}]
    })

    out = node.execute({"I": [df1, df2, df3]}, {})
    res = out["J"]

    # Only 103 is present in all 3 tables
    assert len(res) == 1
    row = res.iloc[0]
    assert row["CustID"] == 103
    assert row["Dept"] == "Sales"
    assert row["Salary"] == 75000
    assert row["Bonus"] == 5000


def test_join_multiple_three_tables_outer():
    """Test 3-table join with join_all_only=False (Full Outer Join across all 3)"""
    df1 = pd.DataFrame({"CustID": [1, 2], "V1": ["A1", "A2"]})
    df2 = pd.DataFrame({"CustID": [2, 3], "V2": ["B2", "B3"]})
    df3 = pd.DataFrame({"CustID": [2, 4], "V3": ["C2", "C4"]})

    node = JoinMultipleNode("node_jm", {
        "join_mode": "specific_fields",
        "join_all_only": False,
        "join_keys": [{"1": "CustID", "2": "CustID", "3": "CustID"}]
    })

    out = node.execute({"I": [df1, df2, df3]}, {})
    res = out["J"]

    # All unique keys: 1, 2, 3, 4 -> 4 rows total
    assert len(res) == 4
    assert "V1" in res.columns
    assert "V2" in res.columns
    assert "V3" in res.columns


def test_join_multiple_four_tables():
    """Test 4-table join simultaneously"""
    d1 = pd.DataFrame({"k": [1, 2], "a": ["a1", "a2"]})
    d2 = pd.DataFrame({"k": [1, 2], "b": ["b1", "b2"]})
    d3 = pd.DataFrame({"k": [1, 2], "c": ["c1", "c2"]})
    d4 = pd.DataFrame({"k": [1, 2], "d": ["d1", "d2"]})

    node = JoinMultipleNode("node_jm4", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "k", "2": "k", "3": "k", "4": "k"}]
    })

    out = node.execute({"I": [d1, d2, d3, d4]}, {})
    res = out["J"]
    assert len(res) == 2
    assert set(["k", "a", "b", "c", "d"]).issubset(set(res.columns))


def test_join_multiple_composite_keys():
    """Test multi-key composite joining"""
    t1 = pd.DataFrame({
        "Country": ["USA", "USA", "UK"],
        "City": ["NYC", "LA", "London"],
        "Pop": [8.4, 3.9, 8.9]
    })
    t2 = pd.DataFrame({
        "Country": ["USA", "USA", "UK"],
        "City": ["NYC", "LA", "London"],
        "Area": [302, 468, 607]
    })
    t3 = pd.DataFrame({
        "Country": ["USA", "USA", "UK"],
        "City": ["NYC", "LA", "Manchester"],
        "HQ": [15, 8, 2]
    })

    node = JoinMultipleNode("jm_composite", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [
            {"1": "Country", "2": "Country", "3": "Country"},
            {"1": "City", "2": "City", "3": "City"}
        ]
    })

    out = node.execute({"I": [t1, t2, t3]}, {})
    res = out["J"]

    # NYC and LA match across all 3 (UK London does not match UK Manchester)
    assert len(res) == 2
    assert set(res["City"]) == {"NYC", "LA"}


def test_join_multiple_column_collisions():
    """Test column collision prefixing and origin tracking"""
    df1 = pd.DataFrame({"ID": [1], "Status": ["Active"], "Count": [10]})
    df2 = pd.DataFrame({"ID": [1], "Status": ["Pending"], "Count": [20]})
    df3 = pd.DataFrame({"ID": [1], "Status": ["Closed"], "Count": [30]})

    node = JoinMultipleNode("jm_collision", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "ID", "2": "ID", "3": "ID"}]
    })

    out = node.execute({"I": [df1, df2, df3]}, {})
    res = out["J"]

    assert "Status" in res.columns
    assert "Input2_Status" in res.columns
    assert "Input3_Status" in res.columns
    assert "Count" in res.columns
    assert "Input2_Count" in res.columns
    assert "Input3_Count" in res.columns

    sources = res.attrs["column_sources"]
    assert sources["Status"] == 1
    assert sources["Count"] == 1
    assert sources["Input2_Status"] == 2
    assert sources["Input2_Count"] == 2
    assert sources["Input3_Status"] == 3
    assert sources["Input3_Count"] == 3


def test_join_multiple_embedded_select():
    """Test embedded Select: keep, rename, type cast, reordering"""
    df1 = pd.DataFrame({"ID": [1, 2], "Name": ["Alpha", "Beta"]})
    df2 = pd.DataFrame({"ID": [1, 2], "Score": ["100", "200"]})

    node = JoinMultipleNode("jm_select", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "ID", "2": "ID"}],
        "select_fields": [
            {"field": "Name", "selected": True, "rename": "Item_Name"},
            {"field": "Score", "selected": True, "rename": "Numeric_Score", "type": "int64"},
            {"field": "ID", "selected": False},
            {"field": "Input2_ID", "selected": False}
        ]
    })

    out = node.execute({"I": [df1, df2]}, {})
    res = out["J"]

    assert list(res.columns) == ["Item_Name", "Numeric_Score"]
    assert pd.api.types.is_integer_dtype(res["Numeric_Score"])
    sources = res.attrs["column_sources"]
    assert sources["Item_Name"] == 1
    assert sources["Numeric_Score"] == 2


def test_join_multiple_record_position_inner():
    """Test Join by Record Position with join_all_only=True"""
    d1 = pd.DataFrame({"A": [1, 2, 3, 4]})
    d2 = pd.DataFrame({"B": ["x", "y", "z"]})
    d3 = pd.DataFrame({"C": [10.0, 20.0]})

    node = JoinMultipleNode("jm_pos_inner", {
        "join_mode": "record_position",
        "join_all_only": True
    })

    out = node.execute({"I": [d1, d2, d3]}, {})
    res = out["J"]

    # Shortest dataset is d3 with length 2
    assert len(res) == 2
    assert list(res["A"]) == [1, 2]
    assert list(res["B"]) == ["x", "y"]
    assert list(res["C"]) == [10.0, 20.0]


def test_join_multiple_record_position_outer():
    """Test Join by Record Position with join_all_only=False"""
    d1 = pd.DataFrame({"A": [1, 2, 3, 4]})
    d2 = pd.DataFrame({"B": ["x", "y", "z"]})
    d3 = pd.DataFrame({"C": [10.0, 20.0]})

    node = JoinMultipleNode("jm_pos_outer", {
        "join_mode": "record_position",
        "join_all_only": False
    })

    out = node.execute({"I": [d1, d2, d3]}, {})
    res = out["J"]

    # Longest dataset is d1 with length 4
    assert len(res) == 4
    assert list(res["A"]) == [1, 2, 3, 4]
    assert pd.isna(res.loc[3, "B"])
    assert pd.isna(res.loc[2, "C"])
    assert pd.isna(res.loc[3, "C"])


def test_join_multiple_relational_null_semantics():
    """Ensure null does NOT match null in join keys"""
    df1 = pd.DataFrame({"K": [1, None, 3], "V1": ["a", "b", "c"]})
    df2 = pd.DataFrame({"K": [1, None, 4], "V2": ["x", "y", "z"]})

    node = JoinMultipleNode("jm_nulls", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "K", "2": "K"}]
    })

    out = node.execute({"I": [df1, df2]}, {})
    res = out["J"]

    # In relational semantics, null != null, so only key 1 matches!
    assert len(res) == 1
    assert res.iloc[0]["K"] == 1


def test_join_multiple_ignore_case_and_trim():
    """Test ignore_case and string whitespace trimming"""
    df1 = pd.DataFrame({"Code": [" ABC ", "xyz"], "Val1": [1, 2]})
    df2 = pd.DataFrame({"Code": ["abc", "XYZ  "], "Val2": [10, 20]})

    node = JoinMultipleNode("jm_case", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "ignore_case": True,
        "join_keys": [{"1": "Code", "2": "Code"}]
    })

    out = node.execute({"I": [df1, df2]}, {})
    res = out["J"]

    assert len(res) == 2


def test_join_multiple_executor_pipeline_integration():
    """Test JoinMultipleNode through WorkflowExecutor with multiple upstream connections"""
    workflow = {
        "nodes": [
            {
                "id": "t1",
                "type": "text_input",
                "name": "Input 1",
                "config": {
                    "columns": ["EmpID", "FirstName"],
                    "data": [["E1", "John"], ["E2", "Jane"], ["E3", "Alex"]]
                }
            },
            {
                "id": "t2",
                "type": "text_input",
                "name": "Input 2",
                "config": {
                    "columns": ["EmpID", "Department"],
                    "data": [["E1", "Sales"], ["E2", "Engineering"], ["E4", "Marketing"]]
                }
            },
            {
                "id": "t3",
                "type": "text_input",
                "name": "Input 3",
                "config": {
                    "columns": ["EmpID", "Location"],
                    "data": [["E1", "NYC"], ["E2", "SF"], ["E5", "London"]]
                }
            },
            {
                "id": "jm_node",
                "type": "join_multiple",
                "name": "Join Multiple",
                "config": {
                    "join_mode": "specific_fields",
                    "join_all_only": False,
                    "join_keys": [{"1": "EmpID", "2": "EmpID", "3": "EmpID"}]
                }
            }
        ],
        "connections": [
            {"source": "t1", "target": "jm_node", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "t2", "target": "jm_node", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "t3", "target": "jm_node", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    executor = WorkflowExecutor()
    result = executor.run(workflow)

    assert result.success is True
    node_res = result.node_results["jm_node"]
    assert node_res["status"] == "success"
    assert node_res["record_counts"]["J"] == 5

    # Check node data retrieval
    data = executor.get_node_data("jm_node", "J")
    assert data["available"] is True
    assert "column_sources" in data
    sources = data["column_sources"]
    assert sources["EmpID"] == 1
    assert sources["FirstName"] == 1
    assert sources["Department"] == 2
    assert sources["Location"] == 3

    # Check columns list has source property
    for col in data["columns"]:
        if col["name"] in sources:
            assert col["source"] == sources[col["name"]]


def test_join_multiple_selection_by_specific_input_source():
    """Verify selecting a column from input 2 with same name as input 1 yields input 2's data."""
    df1 = pd.DataFrame({"id": [1], "platform": ["Platform_Input1"]})
    df2 = pd.DataFrame({"id": [1], "platform": ["Platform_Input2"]})

    # Select platform from input 2, drop platform from input 1
    sf = [
        {"field": "platform", "source": 2, "original": "platform", "selected": True, "rename": "platform"},
        {"field": "platform", "source": 1, "original": "platform", "selected": False, "rename": "platform"}
    ]
    node = JoinMultipleNode("jm_select_source", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "id", "2": "id"}],
        "select_fields": sf
    })
    res = node.execute({"I": [df1, df2]}, {})["J"]

    assert "platform" in res.columns
    assert res.iloc[0]["platform"] == "Platform_Input2"
    assert res.attrs.get("column_sources", {}).get("platform") == 2


def test_join_multiple_prevent_numeric_suffix_platform_2():
    """Verify that when duplicate column names exist in select_fields, Input{idx}_ prefix is used, NEVER _2."""
    df1 = pd.DataFrame({"id": [1], "platform": ["Val1"]})
    df2 = pd.DataFrame({"id": [1], "platform": ["Val2"]})

    # Both selected and named 'platform'
    sf = [
        {"field": "platform", "source": 1, "original": "platform", "selected": True, "rename": "platform"},
        {"field": "Input2_platform", "source": 2, "original": "platform", "selected": True, "rename": "platform"}
    ]
    node = JoinMultipleNode("jm_dedup", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "id", "2": "id"}],
        "select_fields": sf
    })
    res = node.execute({"I": [df1, df2]}, {})["J"]

    assert "platform_2" not in res.columns
    assert "platform" in res.columns
    assert "Input2_platform" in res.columns
    assert res.iloc[0]["platform"] == "Val1"
    assert res.iloc[0]["Input2_platform"] == "Val2"
    assert res.attrs.get("column_sources", {}).get("platform") == 1
    assert res.attrs.get("column_sources", {}).get("Input2_platform") == 2

