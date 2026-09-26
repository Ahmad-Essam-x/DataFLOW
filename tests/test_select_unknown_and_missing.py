import pandas as pd
import pytest
from backend.engine.nodes.preparation import SelectNode
from backend.engine.nodes.join import JoinNode, AppendFieldsNode, JoinMultipleNode

def test_select_unknown_enabled():
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [10.5, 20.5, 30.5]
    })
    # Configure A, but leave B and C unconfigured; select_unknown=True (default)
    config = {
        "fields": [
            {"original": "A", "rename": "A_renamed", "keep": True},
            {"original": "*Unknown", "keep": True}
        ],
        "select_unknown": True
    }
    node = SelectNode("sel1", config)
    res = node.execute({"I": df}, {})
    out = res["O"]
    assert "A_renamed" in out.columns
    assert "B" in out.columns
    assert "C" in out.columns
    assert list(out.columns) == ["A_renamed", "B", "C"]

def test_select_unknown_disabled():
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"],
        "C": [10.5, 20.5, 30.5]
    })
    # Configure A, uncheck *Unknown
    config = {
        "fields": [
            {"original": "A", "rename": "A_only", "keep": True},
            {"original": "*Unknown", "keep": False}
        ],
        "select_unknown": False
    }
    node = SelectNode("sel2", config)
    res = node.execute({"I": df}, {})
    out = res["O"]
    assert list(out.columns) == ["A_only"]
    assert "B" not in out.columns
    assert "C" not in out.columns

def test_select_missing_column_graceful():
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["x", "y", "z"]
    })
    # Config has "OldCol" which is missing upstream
    config = {
        "fields": [
            {"original": "OldCol", "rename": "OldCol_Renamed", "keep": True},
            {"original": "A", "rename": "A", "keep": True},
            {"original": "*Unknown", "keep": True}
        ],
        "select_unknown": True
    }
    node = SelectNode("sel3", config)
    res = node.execute({"I": df}, {})
    out = res["O"]
    # Does not crash, A and B are present, OldCol is skipped
    assert "A" in out.columns
    assert "B" in out.columns
    assert "OldCol" not in out.columns
    assert "OldCol_Renamed" not in out.columns

def test_join_select_unknown():
    left = pd.DataFrame({"ID": [1, 2], "Name": ["Alice", "Bob"], "ExtraL": ["L1", "L2"]})
    right = pd.DataFrame({"ID": [1, 2], "Score": [90, 85], "ExtraR": ["R1", "R2"]})

    # select_unknown = False: only configured fields should appear
    cfg_no_unknown = {
        "join_keys": [{"left_key": "ID", "right_key": "ID"}],
        "select_fields": [
            {"field": "ID", "source": "L", "selected": True},
            {"field": "Name", "source": "L", "selected": True},
            {"field": "*Unknown", "selected": False}
        ],
        "select_unknown": False
    }
    node = JoinNode("j1", cfg_no_unknown)
    res = node.execute({"L": left, "R": right}, {})
    out = res["J"]
    assert list(out.columns) == ["ID", "Name"]
    assert "ExtraL" not in out.columns
    assert "Score" not in out.columns
    assert "ExtraR" not in out.columns

    # select_unknown = True: unlisted fields should appear
    cfg_with_unknown = {
        "join_keys": [{"left_key": "ID", "right_key": "ID"}],
        "select_fields": [
            {"field": "ID", "source": "L", "selected": True},
            {"field": "Name", "source": "L", "selected": True},
            {"field": "*Unknown", "selected": True}
        ],
        "select_unknown": True
    }
    node2 = JoinNode("j2", cfg_with_unknown)
    res2 = node2.execute({"L": left, "R": right}, {})
    out2 = res2["J"]
    assert "ID" in out2.columns
    assert "Name" in out2.columns
    assert "ExtraL" in out2.columns
    assert "Score" in out2.columns
    assert "ExtraR" in out2.columns

def test_join_missing_columns_graceful():
    left = pd.DataFrame({"ID": [1, 2], "Name": ["Alice", "Bob"]})
    right = pd.DataFrame({"ID": [1, 2], "Score": [90, 85]})

    # select_fields contains a purged column
    cfg = {
        "join_keys": [{"left_key": "ID", "right_key": "ID"}],
        "select_fields": [
            {"field": "PurgedCol", "source": "L", "selected": True},
            {"field": "ID", "source": "L", "selected": True},
            {"field": "Score", "source": "R", "selected": True},
            {"field": "*Unknown", "selected": False}
        ],
        "select_unknown": False
    }
    node = JoinNode("j3", cfg)
    res = node.execute({"L": left, "R": right}, {})
    out = res["J"]
    assert "PurgedCol" not in out.columns
    assert "ID" in out.columns
    assert "Score" in out.columns

def test_append_fields_unknown():
    target = pd.DataFrame({"T1": [1, 2], "UnlistedT": ["a", "b"]})
    source = pd.DataFrame({"S1": [10, 20], "UnlistedS": ["x", "y"]})

    # select_unknown = False
    cfg = {
        "cartesian_mode": "allow_all",
        "select_fields": [
            {"field": "T1", "source": "T", "selected": True},
            {"field": "S1", "source": "S", "selected": True},
            {"field": "*Unknown", "selected": False}
        ],
        "select_unknown": False
    }
    node = AppendFieldsNode("af1", cfg)
    res = node.execute({"T": target, "S": source}, {})
    out = res["O"]
    assert list(out.columns) == ["T1", "S1"]
    assert "UnlistedT" not in out.columns
    assert "UnlistedS" not in out.columns

def test_join_multiple_unknown():
    df1 = pd.DataFrame({"ID": [1, 2], "Val1": [10, 20], "Extra1": ["e1", "e2"]})
    df2 = pd.DataFrame({"ID": [1, 2], "Val2": [100, 200], "Extra2": ["e3", "e4"]})

    cfg = {
        "join_mode": "specific_fields",
        "join_keys": [{"1": "ID", "2": "ID"}],
        "select_fields": [
            {"field": "ID", "source": 1, "selected": True},
            {"field": "Val1", "source": 1, "selected": True},
            {"field": "*Unknown", "selected": False}
        ],
        "select_unknown": False
    }
    node = JoinMultipleNode("jm1", cfg)
    res = node.execute({"I": [df1, df2]}, {})
    out = res["J"]
    assert list(out.columns) == ["ID", "Val1"]
    assert "Val2" not in out.columns
    assert "Extra1" not in out.columns
