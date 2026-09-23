import unittest
import numpy as np
import pandas as pd
from backend.engine.nodes.preparation import CleanNode


class TestDataCleanAlteryxParity(unittest.TestCase):
    def setUp(self):
        self.context = {"data_dir": "data"}

    def test_selective_column_cleansing(self):
        """Only fields specified in 'columns' should be cleaned; others remain untouched."""
        df = pd.DataFrame({
            "CleanMe": ["  alpha  ", "  beta  "],
            "LeaveMe": ["  gamma  ", "  delta  "],
            "NumClean": [10.0, None],
            "NumLeave": [20.0, None]
        })
        node = CleanNode("clean_1", {
            "columns": ["CleanMe", "NumClean"],
            "trim_whitespace": True,
            "case_mode": "upper",
            "replace_nulls_numeric": True
        })
        out = node.execute({"I": df}, self.context)["O"]

        # CleanMe should be trimmed and uppercased
        self.assertEqual(out["CleanMe"].tolist(), ["ALPHA", "BETA"])
        # LeaveMe should retain its exact spaces and lower case
        self.assertEqual(out["LeaveMe"].tolist(), ["  gamma  ", "  delta  "])
        # NumClean null should be replaced with 0
        self.assertEqual(out["NumClean"].tolist(), [10.0, 0.0])
        # NumLeave null should still be NaN
        self.assertTrue(pd.isna(out["NumLeave"].iloc[1]))

    def test_default_all_columns_when_empty_columns_specified(self):
        """When columns is omitted or empty, all eligible columns are cleansed."""
        df = pd.DataFrame({
            "TextA": ["  apple  ", " banana "],
            "TextB": [" CARROT ", "date "]
        })
        node = CleanNode("clean_all", {
            "trim_whitespace": True,
            "case_mode": "lower"
        })
        out = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(out["TextA"].tolist(), ["apple", "banana"])
        self.assertEqual(out["TextB"].tolist(), ["carrot", "date"])

    def test_alteryx_null_replacements(self):
        """String nulls -> '', Numeric nulls -> 0."""
        df = pd.DataFrame({
            "Customer": ["Alice", None, np.nan, "Bob"],
            "Balance": [100.5, None, np.nan, 250.0]
        })
        node = CleanNode("clean_nulls", {
            "replace_nulls_string": True,
            "replace_nulls_numeric": True
        })
        out = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(out["Customer"].tolist(), ["Alice", "", "", "Bob"])
        self.assertEqual(out["Balance"].tolist(), [100.5, 0.0, 0.0, 250.0])

    def test_tabs_linebreaks_and_duplicate_whitespace(self):
        """Tabs, newlines, and multiple consecutive spaces collapse into single space."""
        df = pd.DataFrame({
            "MessyText": ["Hello \t \n  World  !  ", "Line1\r\nLine2\t\tEnd"]
        })
        node = CleanNode("clean_tabs", {
            "remove_tabs_linebreaks": True
        })
        out = node.execute({"I": df}, self.context)["O"]
        self.assertEqual(out["MessyText"].iloc[0], "Hello World !")
        self.assertEqual(out["MessyText"].iloc[1], "Line1 Line2 End")

    def test_character_removals_and_custom_chars(self):
        """Letters, numbers, punctuation, and custom symbols removal."""
        df = pd.DataFrame({
            "Raw": [
                "Price: $1,499.95 USD!",
                "SKU #99-AX (Euro: €45.00)"
            ]
        })
        # Test custom chars stripping e.g. currency signs
        node_custom = CleanNode("clean_custom", {
            "remove_custom_chars": "$€!#()"
        })
        out_custom = node_custom.execute({"I": df}, self.context)["O"]
        self.assertNotIn("$", out_custom["Raw"].iloc[0])
        self.assertNotIn("€", out_custom["Raw"].iloc[1])

        # Test numbers removal
        node_nums = CleanNode("clean_nums", {"remove_numbers": True})
        out_nums = node_nums.execute({"I": df}, self.context)["O"]
        self.assertEqual(out_nums["Raw"].iloc[0], "Price: $,. USD!")

        # Test letters removal
        node_letters = CleanNode("clean_letters", {"remove_letters": True})
        out_letters = node_letters.execute({"I": df}, self.context)["O"]
        self.assertEqual(out_letters["Raw"].iloc[0], ": $1,499.95 !")

    def test_case_transformations(self):
        df = pd.DataFrame({"Text": ["john DOE", "jane SMITH"]})
        
        # Upper
        node_up = CleanNode("c_up", {"case_mode": "upper"})
        self.assertEqual(node_up.execute({"I": df}, self.context)["O"]["Text"].tolist(), ["JOHN DOE", "JANE SMITH"])

        # Lower
        node_lo = CleanNode("c_lo", {"case_mode": "lower"})
        self.assertEqual(node_lo.execute({"I": df}, self.context)["O"]["Text"].tolist(), ["john doe", "jane smith"])

        # Title
        node_ti = CleanNode("c_ti", {"case_mode": "title"})
        self.assertEqual(node_ti.execute({"I": df}, self.context)["O"]["Text"].tolist(), ["John Doe", "Jane Smith"])

    def test_remove_empty_rows_and_columns(self):
        """Hygiene: Drops completely empty rows and completely empty columns."""
        df = pd.DataFrame({
            "ColA": ["A", "  ", None, "B"],
            "EmptyCol": [None, "", np.nan, "   "],
            "ColB": [1, np.nan, None, 2]
        })
        node = CleanNode("clean_hygiene", {
            "remove_empty_rows": True,
            "remove_empty_cols": True
        })
        out = node.execute({"I": df}, self.context)["O"]
        # EmptyCol should be removed entirely
        self.assertNotIn("EmptyCol", out.columns)
        self.assertEqual(list(out.columns), ["ColA", "ColB"])
        # The 2nd row (index 1: "  ", "", NaN) and 3rd row (index 2: None, NaN, None) are completely empty
        self.assertEqual(len(out), 2)
        self.assertEqual(out["ColA"].tolist(), ["A", "B"])

    def test_diagnostic_messages(self):
        """Execution generates human-readable summary diagnostics in messages."""
        df = pd.DataFrame({
            "Name": ["  alice  ", None, "  bob  "],
            "Age": [25.0, None, 30.0]
        })
        node = CleanNode("clean_diag", {
            "columns": ["Name", "Age"],
            "trim_whitespace": True,
            "case_mode": "upper",
            "replace_nulls_string": True,
            "replace_nulls_numeric": True
        })
        node.execute({"I": df}, self.context)
        self.assertTrue(len(node.messages) > 0)
        diag = " ".join(node.messages)
        self.assertIn("Replaced", diag)
        self.assertIn("Cleaned", diag)

    def test_backward_compatibility_statistical_null_strategies(self):
        """Legacy null_strategy options (mean, median, replace_value, drop_rows) continue to work."""
        df = pd.DataFrame({
            "Score": [10.0, np.nan, 30.0],
            "Tag": ["X", np.nan, "Z"]
        })
        # Mean
        node_mean = CleanNode("c_mean", {"columns": ["Score"], "null_strategy": "mean"})
        out_mean = node_mean.execute({"I": df}, self.context)["O"]
        self.assertEqual(out_mean["Score"].iloc[1], 20.0)

        # Replace Value
        node_rep = CleanNode("c_rep", {"columns": ["Tag"], "null_strategy": "replace_value", "null_replacement": "MISSING"})
        out_rep = node_rep.execute({"I": df}, self.context)["O"]
        self.assertEqual(out_rep["Tag"].iloc[1], "MISSING")


if __name__ == "__main__":
    unittest.main()
