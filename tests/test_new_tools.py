"""
Unit tests for the 3 new Alteryx tools:
- Text To Columns (TextToColumnsNode)
- Append Fields (AppendFieldsNode)
- DateTime (DateTimeNode)
"""
import unittest
import pandas as pd
import numpy as np

from backend.engine.node_registry import (
    NODE_REGISTRY, TOOL_METADATA, NodeExecutionError,
    TextToColumnsNode, AppendFieldsNode, DateTimeNode
)
from backend.engine.error_diagnostics import diagnose_error


class TestTextToColumns(unittest.TestCase):
    def setUp(self):
        self.context = {}

    def test_basic_split_to_columns(self):
        df = pd.DataFrame({"Full_Name": ["John,Doe", "Jane,Smith,Jr.", "Alice,W"]})
        node = TextToColumnsNode("ttc1", {
            "column": "Full_Name",
            "delimiters": ",",
            "num_columns": 2,
            "split_type": "columns",
            "extra_characters": "last"
        })
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertIn("Full_Name1", out.columns)
        self.assertIn("Full_Name2", out.columns)
        self.assertEqual(out.iloc[0]["Full_Name1"], "John")
        self.assertEqual(out.iloc[0]["Full_Name2"], "Doe")
        # Row 1 has extra characters 'Smith,Jr.', should be left in last column
        self.assertEqual(out.iloc[1]["Full_Name2"], "Smith,Jr.")

    def test_drop_extra_characters(self):
        df = pd.DataFrame({"Data": ["A,B,C,D"]})
        node = TextToColumnsNode("ttc2", {
            "column": "Data",
            "delimiters": ",",
            "num_columns": 2,
            "split_type": "columns",
            "extra_characters": "drop"
        })
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertEqual(out.iloc[0]["Data1"], "A")
        self.assertEqual(out.iloc[0]["Data2"], "B")

    def test_error_extra_characters(self):
        df = pd.DataFrame({"Data": ["A,B,C"]})
        node = TextToColumnsNode("ttc3", {
            "column": "Data",
            "delimiters": ",",
            "num_columns": 2,
            "split_type": "columns",
            "extra_characters": "error"
        })
        with self.assertRaises(NodeExecutionError) as ctx:
            node.execute({"I": df}, self.context)
        self.assertIn("Extra characters", str(ctx.exception))

    def test_quote_aware_split(self):
        df = pd.DataFrame({"Data": ['"San Francisco, CA",USA,94105']})
        node = TextToColumnsNode("ttc4", {
            "column": "Data",
            "delimiters": ",",
            "num_columns": 3,
            "ignore_quotes": True
        })
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertEqual(out.iloc[0]["Data1"], "San Francisco, CA")
        self.assertEqual(out.iloc[0]["Data2"], "USA")
        self.assertEqual(out.iloc[0]["Data3"], "94105")

    def test_split_to_rows(self):
        df = pd.DataFrame({
            "ID": [1, 2],
            "Tags": ["red,blue,green", "yellow,black"]
        })
        node = TextToColumnsNode("ttc5", {
            "column": "Tags",
            "delimiters": ",",
            "split_type": "rows"
        })
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertEqual(len(out), 5)
        self.assertEqual(out["Tags"].tolist(), ["red", "blue", "green", "yellow", "black"])
        self.assertEqual(out["ID"].tolist(), [1, 1, 1, 2, 2])

    def test_custom_root_name(self):
        df = pd.DataFrame({"Code": ["X-123", "Y-456"]})
        node = TextToColumnsNode("ttc6", {
            "column": "Code",
            "delimiters": "-",
            "num_columns": 2,
            "root_name": "Part"
        })
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertIn("Part1", out.columns)
        self.assertIn("Part2", out.columns)
        self.assertEqual(out.iloc[0]["Part1"], "X")
        self.assertEqual(out.iloc[0]["Part2"], "123")


class TestAppendFields(unittest.TestCase):
    def setUp(self):
        self.context = {}

    def test_basic_cartesian_join(self):
        t_df = pd.DataFrame({"TargetID": [1, 2], "Name": ["Alpha", "Beta"]})
        s_df = pd.DataFrame({"Param": ["P1", "P2", "P3"]})

        node = AppendFieldsNode("af1", {})
        res = node.execute({"T": t_df, "S": s_df}, self.context)
        out = res["O"]
        self.assertEqual(len(out), 6)  # 2 * 3 = 6
        self.assertIn("TargetID", out.columns)
        self.assertIn("Param", out.columns)

    def test_collision_renaming(self):
        t_df = pd.DataFrame({"ID": [1, 2], "Status": ["Active", "Pending"]})
        s_df = pd.DataFrame({"ID": [99], "Status": ["Global"]})

        node = AppendFieldsNode("af2", {"source_prefix": "Source_"})
        res = node.execute({"T": t_df, "S": s_df}, self.context)
        out = res["O"]
        self.assertIn("ID", out.columns)
        self.assertIn("Source_ID", out.columns)
        self.assertIn("Status", out.columns)
        self.assertIn("Source_Status", out.columns)
        self.assertEqual(out.iloc[0]["Source_ID"], 99)

    def test_cartesian_limit_16(self):
        t_df = pd.DataFrame({"ID": [1, 2]})
        s_df = pd.DataFrame({"Val": range(20)})  # 20 records > 16

        node_err = AppendFieldsNode("af3", {"cartesian_mode": "error_16"})
        with self.assertRaises(NodeExecutionError) as ctx:
            node_err.execute({"T": t_df, "S": s_df}, self.context)
        self.assertIn("exceeding the limit of 16 records", str(ctx.exception))

        # With allow_all, it succeeds
        node_allow = AppendFieldsNode("af4", {"cartesian_mode": "allow_all"})
        res = node_allow.execute({"T": t_df, "S": s_df}, self.context)
        out = res["O"]
        self.assertEqual(len(out), 40)

    def test_select_and_rename_fields(self):
        t_df = pd.DataFrame({"A": [1], "B": [2]})
        s_df = pd.DataFrame({"C": [3], "D": [4]})

        node = AppendFieldsNode("af5", {
            "select_fields": [
                {"field": "A", "selected": True, "rename": "A_Renamed"},
                {"field": "B", "selected": False},
                {"field": "C", "selected": True, "rename": "C"},
                {"field": "D", "selected": False}
            ]
        })
        res = node.execute({"T": t_df, "S": s_df}, self.context)
        out = res["O"]
        self.assertEqual(list(out.columns), ["A_Renamed", "C"])


class TestDateTime(unittest.TestCase):
    def setUp(self):
        self.context = {}

    def test_string_to_date_iso(self):
        df = pd.DataFrame({"RawDate": ["2026-09-11", "2025-01-01"]})
        node = DateTimeNode("dt1", {
            "column": "RawDate",
            "conversion_type": "string_to_date",
            "format_template": "yyyy-MM-dd"
        })
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertIn("RawDate_DateTime", out.columns)
        self.assertEqual(out.iloc[0]["RawDate_DateTime"], "2026-09-11")

    def test_string_to_date_presets(self):
        # MM/dd/yyyy
        df = pd.DataFrame({"DateUS": ["09/11/2026", "12/25/2025"]})
        node = DateTimeNode("dt2", {
            "column": "DateUS",
            "conversion_type": "string_to_date",
            "format_template": "MM/dd/yyyy"
        })
        out = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(out.iloc[0]["DateUS_DateTime"], "2026-09-11")

        # dd-Mon-yyyy
        df2 = pd.DataFrame({"DateMon": ["11-Sep-2026"]})
        node2 = DateTimeNode("dt3", {
            "column": "DateMon",
            "conversion_type": "string_to_date",
            "format_template": "dd-Mon-yyyy"
        })
        out2 = node2.execute({"I": df2}, self.context)["O"]
        self.assertEqual(out2.iloc[0]["DateMon_DateTime"], "2026-09-11")

    def test_date_to_string(self):
        df = pd.DataFrame({"Date": ["2026-09-11"]})
        node = DateTimeNode("dt4", {
            "column": "Date",
            "conversion_type": "date_to_string",
            "format_template": "Month dd, yyyy"
        })
        out = node.execute({"I": df}, self.context)["O"]
        self.assertIn("Date_String", out.columns)
        self.assertEqual(out.iloc[0]["Date_String"], "September 11, 2026")

    def test_custom_format(self):
        df = pd.DataFrame({"Custom": ["26-09-11"]})
        node = DateTimeNode("dt5", {
            "column": "Custom",
            "conversion_type": "string_to_date",
            "format_template": "custom",
            "custom_format": "yy-MM-dd"
        })
        out = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(out.iloc[0]["Custom_DateTime"], "2026-09-11")


class TestNewToolsDiagnostics(unittest.TestCase):
    def test_cartesian_limit_diagnostic(self):
        err = NodeExecutionError("Append Fields: The Source input contains 20 records, exceeding the limit of 16 records.")
        diag = diagnose_error(err, {"id": "n1", "name": "Append Fields", "type": "append_fields"})
        self.assertEqual(diag.error_code, "CARTESIAN_SAFETY_LIMIT")
        self.assertIn("16 Record Limit", diag.title)

    def test_missing_input_diagnostic(self):
        err = NodeExecutionError("Append Fields: 'T' (Target) input is not connected.")
        diag = diagnose_error(err, {"id": "n1", "name": "Append Fields", "type": "append_fields"})
        self.assertEqual(diag.error_code, "MISSING_CONNECTION")
        self.assertIn("Target ('T')", diag.title)


if __name__ == '__main__':
    unittest.main()
