"""
Tests for Select Tool, Join Tool, and Unique Tool configuration capabilities:
1. Column reordering via configuration (drag-and-drop parity).
2. Join tool Select/Deselect All Left and Select/Deselect All Right.
3. Unique tool Select All columns deduplication.
"""
import pandas as pd
import pytest

from backend.engine.nodes.preparation import SelectNode, UniqueNode
from backend.engine.nodes.join import JoinNode, JoinMultipleNode
from backend.engine.executor import WorkflowExecutor


def test_select_node_column_reordering():
    """Verify that reordering fields in SelectNode configuration alters the output column order."""
    df = pd.DataFrame({
        "Col_A": [1, 2, 3],
        "Col_B": ["x", "y", "z"],
        "Col_C": [10.5, 20.5, 30.5],
        "Col_D": [True, False, True]
    })

    # User dragged Col_C to position 0, Col_D to position 1, Col_A to position 2, Col_B to position 3
    node = SelectNode("sel_1", {
        "fields": [
            {"original": "Col_C", "keep": True, "rename": "Col_C", "type": "none"},
            {"original": "Col_D", "keep": True, "rename": "Col_D", "type": "none"},
            {"original": "Col_A", "keep": True, "rename": "Col_A", "type": "none"},
            {"original": "Col_B", "keep": True, "rename": "Col_B", "type": "none"}
        ]
    })

    out = node.execute({"I": df}, {})
    res_df = out["O"]

    assert list(res_df.columns) == ["Col_C", "Col_D", "Col_A", "Col_B"]
    assert len(res_df) == 3


def test_select_node_reorder_with_drops_and_renames():
    """Verify reordering combined with field drops and renames."""
    df = pd.DataFrame({
        "ID": [1, 2],
        "FirstName": ["John", "Jane"],
        "LastName": ["Doe", "Smith"],
        "Age": [30, 25]
    })

    # Drag LastName first and rename to Surname, drop Age, keep ID last
    node = SelectNode("sel_2", {
        "fields": [
            {"original": "LastName", "keep": True, "rename": "Surname", "type": "none"},
            {"original": "FirstName", "keep": True, "rename": "FirstName", "type": "none"},
            {"original": "Age", "keep": False, "rename": "Age", "type": "none"},
            {"original": "ID", "keep": True, "rename": "User_ID", "type": "none"}
        ]
    })

    out = node.execute({"I": df}, {})
    res_df = out["O"]

    assert list(res_df.columns) == ["Surname", "FirstName", "User_ID"]
    assert res_df.iloc[0]["Surname"] == "Doe"


def test_join_node_reordering_embedded_select():
    """Verify that reordering columns in JoinNode embedded select puts Right column before Left."""
    df_l = pd.DataFrame({"ID": [1, 2], "LeftVal": ["L1", "L2"]})
    df_r = pd.DataFrame({"ID": [1, 2], "RightVal": ["R1", "R2"]})

    # Drag RightVal before LeftVal
    node = JoinNode("join_reorder", {
        "join_keys": [{"left_key": "ID", "right_key": "ID"}],
        "select_fields": [
            {"field": "RightVal", "source": "R", "selected": True, "rename": "RightVal"},
            {"field": "ID", "source": "L", "selected": True, "rename": "ID"},
            {"field": "LeftVal", "source": "L", "selected": True, "rename": "LeftVal"}
        ]
    })

    out = node.execute({"L": df_l, "R": df_r}, {})
    j_df = out["J"]

    assert list(j_df.columns) == ["RightVal", "ID", "LeftVal"]
    assert j_df.iloc[0]["RightVal"] == "R1"
    assert j_df.iloc[0]["LeftVal"] == "L1"


def test_join_node_deselect_all_right():
    """Verify deselecting all Right columns outputs only Left schema in Joined (J)."""
    df_l = pd.DataFrame({"ID": [1, 2], "LeftCol1": ["A", "B"], "LeftCol2": [10, 20]})
    df_r = pd.DataFrame({"ID": [1, 2], "RightCol1": ["X", "Y"], "RightCol2": [100, 200]})

    # Simulate 'Deselect All Right' button click: all R fields have selected=False
    node = JoinNode("join_desel_r", {
        "join_keys": [{"left_key": "ID", "right_key": "ID"}],
        "select_fields": [
            {"field": "ID", "source": "L", "selected": True, "rename": "ID"},
            {"field": "LeftCol1", "source": "L", "selected": True, "rename": "LeftCol1"},
            {"field": "LeftCol2", "source": "L", "selected": True, "rename": "LeftCol2"},
            {"field": "RightCol1", "source": "R", "selected": False, "rename": "RightCol1"},
            {"field": "RightCol2", "source": "R", "selected": False, "rename": "RightCol2"}
        ]
    })

    out = node.execute({"L": df_l, "R": df_r}, {})
    j_df = out["J"]

    assert list(j_df.columns) == ["ID", "LeftCol1", "LeftCol2"]
    assert "RightCol1" not in j_df.columns
    assert "RightCol2" not in j_df.columns


def test_join_node_deselect_all_left():
    """Verify deselecting all Left columns outputs only Right schema in Joined (J)."""
    df_l = pd.DataFrame({"ID": [1, 2], "LeftCol": ["A", "B"]})
    df_r = pd.DataFrame({"ID": [1, 2], "RightCol": ["X", "Y"], "RightExtra": [9, 8]})

    # Simulate 'Deselect All Left' button click: all L fields have selected=False
    node = JoinNode("join_desel_l", {
        "join_keys": [{"left_key": "ID", "right_key": "ID"}],
        "select_fields": [
            {"field": "ID", "source": "L", "selected": False, "rename": "ID"},
            {"field": "LeftCol", "source": "L", "selected": False, "rename": "LeftCol"},
            {"field": "RightCol", "source": "R", "selected": True, "rename": "RightCol"},
            {"field": "RightExtra", "source": "R", "selected": True, "rename": "RightExtra"}
        ]
    })

    out = node.execute({"L": df_l, "R": df_r}, {})
    j_df = out["J"]

    assert list(j_df.columns) == ["RightCol", "RightExtra"]
    assert "LeftCol" not in j_df.columns


def test_join_multiple_reordering():
    """Verify JoinMultipleNode honors reordered select_fields."""
    df1 = pd.DataFrame({"k": [1, 2], "A": ["a1", "a2"]})
    df2 = pd.DataFrame({"k": [1, 2], "B": ["b1", "b2"]})
    df3 = pd.DataFrame({"k": [1, 2], "C": ["c1", "c2"]})

    # Drag C first, then B, then A
    node = JoinMultipleNode("jm_reorder", {
        "join_mode": "specific_fields",
        "join_all_only": True,
        "join_keys": [{"1": "k", "2": "k", "3": "k"}],
        "select_fields": [
            {"field": "C", "source": 3, "selected": True, "rename": "C"},
            {"field": "B", "source": 2, "selected": True, "rename": "B"},
            {"field": "A", "source": 1, "selected": True, "rename": "A"}
        ]
    })

    out = node.execute({"I": [df1, df2, df3]}, {})
    j_df = out["J"]

    assert list(j_df.columns) == ["C", "B", "A"]


def test_unique_node_select_all_columns():
    """Verify UniqueNode when all columns are selected vs subset."""
    df = pd.DataFrame({
        "City": ["NYC", "NYC", "NYC", "LA"],
        "Dept": ["HR", "HR", "Sales", "Sales"],
        "Year": [2025, 2025, 2025, 2025]
    })

    # Case 1: Deduplicate on only City (2 unique cities: NYC, LA)
    node_subset = UniqueNode("u_sub", {"columns": ["City"]})
    out_sub = node_subset.execute({"I": df}, {})
    assert len(out_sub["U"]) == 2
    assert len(out_sub["D"]) == 2

    # Case 2: 'Select All Columns' clicked -> columns = ["City", "Dept", "Year"]
    # Row 0: NYC, HR, 2025 -> Unique
    # Row 1: NYC, HR, 2025 -> Duplicate
    # Row 2: NYC, Sales, 2025 -> Unique
    # Row 3: LA, Sales, 2025 -> Unique
    node_all = UniqueNode("u_all", {"columns": ["City", "Dept", "Year"]})
    out_all = node_all.execute({"I": df}, {})
    assert len(out_all["U"]) == 3
    assert len(out_all["D"]) == 1
    assert out_all["D"].iloc[0]["City"] == "NYC"
    assert out_all["D"].iloc[0]["Dept"] == "HR"


def test_pipeline_execution_with_reordered_select_and_unique():
    """Verify complete pipeline execution in WorkflowExecutor."""
    workflow = {
        "nodes": [
            {
                "id": "t1",
                "type": "text_input",
                "name": "Input",
                "config": {
                    "columns": ["Col1", "Col2", "Col3"],
                    "data": [
                        ["Z", "10", "A"],
                        ["Z", "10", "A"],
                        ["Y", "20", "B"]
                    ]
                }
            },
            {
                "id": "sel1",
                "type": "select",
                "name": "Select Reorder",
                "config": {
                    "fields": [
                        {"original": "Col3", "keep": True, "rename": "ReorderedCol3", "type": "none"},
                        {"original": "Col1", "keep": True, "rename": "ReorderedCol1", "type": "none"}
                    ]
                }
            },
            {
                "id": "uniq1",
                "type": "unique",
                "name": "Unique All",
                "config": {
                    "columns": ["ReorderedCol3", "ReorderedCol1"]
                }
            }
        ],
        "connections": [
            {"source": "t1", "target": "sel1", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "sel1", "target": "uniq1", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    executor = WorkflowExecutor()
    result = executor.run(workflow)

    assert result.success is True

    # Check select output schema
    sel_data = executor.get_node_data("sel1", "O")
    assert [c["name"] for c in sel_data["columns"]] == ["ReorderedCol3", "ReorderedCol1"]

    # Check unique output
    u_data = executor.get_node_data("uniq1", "U")
    assert u_data["pagination"]["total_records"] == 2
    d_data = executor.get_node_data("uniq1", "D")
    assert d_data["pagination"]["total_records"] == 1
