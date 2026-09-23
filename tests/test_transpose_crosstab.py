import unittest
import pandas as pd
import numpy as np

from backend.engine.nodes.transform import TransposeNode, CrossTabNode, sanitize_alteryx_header
from backend.engine.nodes.base import NodeExecutionError


class TestTransposeNode(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "ID": [1, 2, 3],
            "Name": ["Alice", "Bob", "Charlie"],
            "Q1": [100, 150, 200],
            "Q2": [110, 160, 210],
            "Q3": [120, 170, 220]
        })

    def test_basic_transpose(self):
        node = TransposeNode("transpose_1", {
            "key_columns": ["ID", "Name"],
            "data_columns": ["Q1", "Q2", "Q3"],
            "name_column": "Quarter",
            "value_column": "Revenue"
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]

        self.assertEqual(len(out_df), 9)
        self.assertIn("Quarter", out_df.columns)
        self.assertIn("Revenue", out_df.columns)
        self.assertIn("ID", out_df.columns)
        self.assertIn("Name", out_df.columns)
        self.assertListEqual(list(out_df["Quarter"].unique()), ["Q1", "Q2", "Q3"])

    def test_dynamic_data_columns(self):
        # When data_columns is empty, all non-key columns should be transposed
        node = TransposeNode("transpose_2", {
            "key_columns": ["ID", "Name"]
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]

        self.assertEqual(len(out_df), 9)
        self.assertIn("Name", out_df.columns)  # Key column preserved
        self.assertIn("Value", out_df.columns)

    def test_missing_columns_ignore(self):
        node = TransposeNode("transpose_3", {
            "key_columns": ["ID", "NonExistent"],
            "data_columns": ["Q1", "MissingCol"],
            "missing_columns_action": "ignore"
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]
        self.assertEqual(len(out_df), 3)

    def test_missing_columns_error(self):
        node = TransposeNode("transpose_4", {
            "key_columns": ["ID", "NonExistentKey"],
            "missing_columns_action": "error"
        })
        with self.assertRaises(NodeExecutionError):
            node.execute({"I": self.df}, {})

    def test_empty_dataframe(self):
        node = TransposeNode("transpose_5", {"key_columns": ["ID"]})
        empty_df = pd.DataFrame(columns=["ID", "Q1"])
        res = node.execute({"I": empty_df}, {})
        self.assertTrue(res["O"].empty)


class TestCrossTabNode(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "Region": ["North", "North", "South", "South", "North"],
            "Product": ["Widgets", "Gadgets", "Widgets", "Gadgets", "Widgets"],
            "Quarter": ["2024 Q1", "2024 Q1", "2024 Q2", "2024 Q2", "2024 Q2"],
            "Sales": [100, 200, 300, 400, 150]
        })

    def test_header_sanitization(self):
        self.assertEqual(sanitize_alteryx_header("2024 Q1"), "_2024_Q1")
        self.assertEqual(sanitize_alteryx_header("Sales ($)"), "Sales")
        self.assertEqual(sanitize_alteryx_header("Hello - World!"), "Hello_World")
        self.assertEqual(sanitize_alteryx_header(None), "Null")

    def test_basic_sum_crosstab(self):
        node = CrossTabNode("crosstab_1", {
            "group_by": ["Region"],
            "header_field": "Quarter",
            "value_field": "Sales",
            "agg_methods": ["sum"],
            "clean_headers": True
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]

        self.assertIn("Region", out_df.columns)
        self.assertIn("_2024_Q1", out_df.columns)
        self.assertIn("_2024_Q2", out_df.columns)
        # North 2024 Q1: 100 + 200 = 300
        north_q1 = out_df[out_df["Region"] == "North"]["_2024_Q1"].values[0]
        self.assertEqual(north_q1, 300)
        # North 2024 Q2: 150
        north_q2 = out_df[out_df["Region"] == "North"]["_2024_Q2"].values[0]
        self.assertEqual(north_q2, 150)

    def test_multi_method_crosstab(self):
        node = CrossTabNode("crosstab_2", {
            "group_by": ["Region"],
            "header_field": "Quarter",
            "value_field": "Sales",
            "agg_methods": ["sum", "count", "avg"],
            "clean_headers": True
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]

        # Prefixes should be added because multiple base methods were requested
        self.assertIn("Sum__2024_Q1", out_df.columns)
        self.assertIn("Count__2024_Q1", out_df.columns)
        self.assertIn("Avg__2024_Q1", out_df.columns)

    def test_concat_aggregation(self):
        df_text = pd.DataFrame({
            "Dept": ["Engineering", "Engineering", "Design"],
            "Role": ["Lead", "Developer", "Designer"],
            "Employee": ["Alice", "Bob", "Charlie"]
        })
        node = CrossTabNode("crosstab_concat", {
            "group_by": ["Dept"],
            "header_field": "Role",
            "value_field": "Employee",
            "agg_methods": ["concat"],
            "separator": " & ",
            "clean_headers": True
        })
        res = node.execute({"I": df_text}, {})
        out_df = res["O"]

        self.assertIn("Dept", out_df.columns)
        self.assertIn("Lead", out_df.columns)
        self.assertIn("Developer", out_df.columns)
        eng_dev = out_df[out_df["Dept"] == "Engineering"]["Developer"].values[0]
        self.assertEqual(eng_dev, "Bob")

    def test_total_row_and_column(self):
        node = CrossTabNode("crosstab_totals", {
            "group_by": ["Region"],
            "header_field": "Quarter",
            "value_field": "Sales",
            "agg_methods": ["sum", "total_row", "total_col"],
            "clean_headers": True
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]

        # Total column should exist
        self.assertIn("Total", out_df.columns)

        # Bottom row should be grand total
        bottom_row = out_df.iloc[-1]
        self.assertEqual(bottom_row["Region"], "Total")
        # Grand total of all sales: 100+200+300+400+150 = 1150
        self.assertEqual(bottom_row["Total"], 1150)

    def test_crosstab_without_group_by(self):
        # Pivoting without group by (single-row aggregation)
        node = CrossTabNode("crosstab_no_group", {
            "group_by": [],
            "header_field": "Quarter",
            "value_field": "Sales",
            "agg_methods": ["sum"],
            "clean_headers": True
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]
        self.assertEqual(len(out_df), 1)
        self.assertIn("_2024_Q1", out_df.columns)
        self.assertEqual(out_df["_2024_Q1"].values[0], 300)

    def test_legacy_agg_func_compatibility(self):
        node = CrossTabNode("crosstab_legacy", {
            "group_by": ["Region"],
            "header_field": "Quarter",
            "value_field": "Sales",
            "agg_func": "sum",
            "clean_headers": False
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]
        self.assertIn("2024 Q1", out_df.columns)

    def test_percentages(self):
        node = CrossTabNode("crosstab_pct", {
            "group_by": ["Region"],
            "header_field": "Quarter",
            "value_field": "Sales",
            "agg_methods": ["sum", "pct_row", "pct_col"],
            "clean_headers": True
        })
        res = node.execute({"I": self.df}, {})
        out_df = res["O"]
        self.assertIn("PctRow__2024_Q1", out_df.columns)
        self.assertIn("PctCol__2024_Q1", out_df.columns)

    def test_round_trip_transpose_crosstab(self):
        # 1. Start with wide data
        orig_df = pd.DataFrame({
            "Account": ["A100", "A200"],
            "Jan": [50, 80],
            "Feb": [60, 90]
        })
        # 2. Transpose (Unpivot) to tall
        transpose_node = TransposeNode("t_trip", {
            "key_columns": ["Account"],
            "data_columns": ["Jan", "Feb"],
            "name_column": "Month",
            "value_column": "Amount"
        })
        tall_res = transpose_node.execute({"I": orig_df}, {})["O"]
        self.assertEqual(len(tall_res), 4)

        # 3. CrossTab (Pivot) back to wide
        crosstab_node = CrossTabNode("ct_trip", {
            "group_by": ["Account"],
            "header_field": "Month",
            "value_field": "Amount",
            "agg_methods": ["sum"],
            "clean_headers": False
        })
        wide_res = crosstab_node.execute({"I": tall_res}, {})["O"]
        self.assertEqual(len(wide_res), 2)
        self.assertIn("Jan", wide_res.columns)
        self.assertIn("Feb", wide_res.columns)
        a100_jan = wide_res[wide_res["Account"] == "A100"]["Jan"].values[0]
        self.assertEqual(a100_jan, 50)


if __name__ == "__main__":
    unittest.main()