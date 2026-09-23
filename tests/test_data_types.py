import unittest
import pandas as pd
import numpy as np

from backend.engine.nodes.base import infer_alteryx_type, map_alteryx_to_category
from backend.engine.nodes.preparation import SelectNode, AutoFieldNode
from backend.engine.executor import WorkflowExecutor


class TestAlteryxDataTypes(unittest.TestCase):
    def test_infer_alteryx_type_strings(self):
        # Raw string series
        s = pd.Series(["Apple", "Banana", "Cherry"], dtype="object")
        self.assertEqual(infer_alteryx_type(s), "String")
        self.assertNotEqual(infer_alteryx_type(s), "object")

    def test_infer_alteryx_type_numerics(self):
        s_int = pd.Series([10, 20, 30], dtype="int64")
        self.assertEqual(infer_alteryx_type(s_int), "Int64")

        s_float = pd.Series([10.5, 20.2, 30.1], dtype="float64")
        self.assertEqual(infer_alteryx_type(s_float), "Double")

    def test_infer_alteryx_type_from_object_numbers(self):
        # Object column containing integer strings
        s_obj_num = pd.Series(["100", "200", "300"], dtype="object")
        self.assertIn(infer_alteryx_type(s_obj_num), ("Int16", "Int32", "Int64"))

        # Object column containing float strings
        s_obj_flt = pd.Series(["100.5", "200.2", "300.9"], dtype="object")
        self.assertEqual(infer_alteryx_type(s_obj_flt), "Double")

    def test_infer_alteryx_type_dates(self):
        # Explicit datetime
        s_dt = pd.to_datetime(pd.Series(["2024-01-01", "2024-02-01"]))
        self.assertIn(infer_alteryx_type(s_dt), ("Date", "DateTime"))

        # Object column containing dates
        s_date_str = pd.Series(["2024-05-01", "2024-05-02", "2024-05-03"], dtype="object")
        self.assertEqual(infer_alteryx_type(s_date_str), "Date")

    def test_infer_alteryx_type_booleans(self):
        s_bool = pd.Series([True, False, True], dtype="bool")
        self.assertEqual(infer_alteryx_type(s_bool), "Bool")

        s_bool_str = pd.Series(["True", "False", "true", "false"], dtype="object")
        self.assertEqual(infer_alteryx_type(s_bool_str), "Bool")

    def test_map_alteryx_to_category(self):
        self.assertEqual(map_alteryx_to_category("Int64"), "numeric")
        self.assertEqual(map_alteryx_to_category("Double"), "numeric")
        self.assertEqual(map_alteryx_to_category("Date"), "datetime")
        self.assertEqual(map_alteryx_to_category("DateTime"), "datetime")
        self.assertEqual(map_alteryx_to_category("Bool"), "boolean")
        self.assertEqual(map_alteryx_to_category("String"), "string")


class TestSelectNodeCasting(unittest.TestCase):
    def test_select_cast_currency_and_commas(self):
        df = pd.DataFrame({
            "Price": ["$1,200.50", "$3,450.00", "$99.99"],
            "Qty": ["1,000", "2,500", "500"]
        })
        node = SelectNode("sel1", {
            "fields": [
                {"original": "Price", "keep": True, "type": "double"},
                {"original": "Qty", "keep": True, "type": "int64"}
            ]
        })
        res = node.execute({"I": df}, {})["O"]
        self.assertEqual(res["Price"].iloc[0], 1200.50)
        self.assertEqual(res["Qty"].iloc[0], 1000)

    def test_select_cast_nullable_integers(self):
        # Null values should not turn into 0
        df = pd.DataFrame({
            "Val": ["10", None, "30"]
        })
        node = SelectNode("sel2", {
            "fields": [
                {"original": "Val", "keep": True, "type": "int64"}
            ]
        })
        res = node.execute({"I": df}, {})["O"]
        self.assertEqual(res["Val"].iloc[0], 10)
        self.assertTrue(pd.isna(res["Val"].iloc[1]))

    def test_select_cast_booleans(self):
        df = pd.DataFrame({
            "Flag": ["yes", "no", "true", "false", "1", "0"]
        })
        node = SelectNode("sel3", {
            "fields": [
                {"original": "Flag", "keep": True, "type": "bool"}
            ]
        })
        res = node.execute({"I": df}, {})["O"]
        self.assertTrue(res["Flag"].iloc[0])
        self.assertFalse(res["Flag"].iloc[1])


class TestAutoFieldNode(unittest.TestCase):
    def test_auto_field_conversion(self):
        df = pd.DataFrame({
            "StrCol": ["Red", "Green", "Blue"],
            "IntCol": ["10", "20", "30"],
            "FloatCol": ["10.5", "20.75", "30.1"],
            "DateCol": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "BoolCol": ["true", "false", "true"]
        })
        node = AutoFieldNode("af1", {})
        res = node.execute({"I": df}, {})["O"]

        # IntCol should become numeric
        self.assertTrue(pd.api.types.is_numeric_dtype(res["IntCol"]))
        # FloatCol should become numeric
        self.assertTrue(pd.api.types.is_numeric_dtype(res["FloatCol"]))
        # StrCol should remain string
        self.assertEqual(res["StrCol"].iloc[0], "Red")
        # BoolCol should be boolean
        self.assertTrue(pd.api.types.is_bool_dtype(res["BoolCol"]))


class TestExecutorDataTypes(unittest.TestCase):
    def test_get_node_data_no_object_dtype(self):
        executor = WorkflowExecutor()
        df = pd.DataFrame({
            "Text": ["Hello", "World"],
            "Number": [1, 2],
            "Date": ["2024-01-01", "2024-01-02"]
        })
        executor.data_cache["test_node"] = {"O": df}

        node_data = executor.get_node_data("test_node", port="O")
        self.assertTrue(node_data["available"])

        dtypes = {c["name"]: c["dtype"] for c in node_data["columns"]}
        # Verify 'object' is nowhere in the dtypes!
        for col_name, dt in dtypes.items():
            self.assertNotEqual(dt, "object", f"Column '{col_name}' returned 'object' dtype!")

        self.assertEqual(dtypes["Text"], "String")
        self.assertIn(dtypes["Number"], ("Int64", "Int32", "Int16"))
        self.assertEqual(dtypes["Date"], "Date")


if __name__ == "__main__":
    unittest.main()
