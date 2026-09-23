import os
import sys
import unittest
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.engine.nodes.preparation import FilterNode


class TestFilterNodeAdvanced(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "OrderID": ["ORD-101", "ORD-102", "ORD-103", "ORD-104", "ORD-105", "ORD-106"],
            "Customer": ["Acme Corp", "Tech Innovators Inc", "Global Logistics", "Acme Retail", None, "   "],
            "Region": ["East", "West", "East", "Central", "North", "South"],
            "Sales": [1500.0, 250.0, 800.0, 3200.0, 45.0, 600.0],
            "Quantity": [10, 2, 8, 25, 1, 5],
            "OrderDate": ["2024-01-15", "2024-02-20", "2024-03-10", "2024-04-05", "2024-05-12", "2024-06-18"],
            "PostalCode": ["10001", "90210", "07001", "60601", "ABCDE", "30301"],
            "IsPriority": [True, False, True, False, False, True]
        })

    def test_basic_numeric_operators(self):
        # Greater than
        node = FilterNode("flt_1", {
            "mode": "basic",
            "conditions": [{"column": "Sales", "operator": ">", "value": "1000"}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(len(res["T"]), 2)
        self.assertEqual(len(res["F"]), 4)
        self.assertEqual(len(res["T"]) + len(res["F"]), len(self.df))

        # Between
        node = FilterNode("flt_btw", {
            "mode": "basic",
            "conditions": [{"column": "Sales", "operator": "between", "value": "200", "value_max": "1000"}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(set(res["T"]["OrderID"]), {"ORD-102", "ORD-103", "ORD-106"})

        # In list
        node = FilterNode("flt_in", {
            "mode": "basic",
            "conditions": [{"column": "Quantity", "operator": "in", "value": "2, 10, 25"}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(len(res["T"]), 3)

    def test_basic_string_operators(self):
        # Contains (case-insensitive)
        node = FilterNode("flt_str", {
            "mode": "basic",
            "conditions": [{"column": "Customer", "operator": "contains", "value": "acme", "ignore_case": True}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(len(res["T"]), 2)

        # Starts with
        node = FilterNode("flt_sw", {
            "mode": "basic",
            "conditions": [{"column": "OrderID", "operator": "starts_with", "value": "ORD-10", "ignore_case": True}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(len(res["T"]), 6)

        # Regex match: 5 digits postal code
        node = FilterNode("flt_rx", {
            "mode": "basic",
            "conditions": [{"column": "PostalCode", "operator": "regex_match", "value": r"^\d{5}$"}]
        })
        res = node.execute({"I": self.df}, {})
        # 5 out of 6 have 5-digit postal code (ORD-105 is 'ABCDE')
        self.assertEqual(len(res["T"]), 5)
        self.assertEqual(list(res["F"]["OrderID"]), ["ORD-105"])

    def test_null_and_empty_operators(self):
        # is_null
        node = FilterNode("flt_null", {
            "mode": "basic",
            "conditions": [{"column": "Customer", "operator": "is_null"}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(list(res["T"]["OrderID"]), ["ORD-105"])

        # is_empty (catches None and whitespace)
        node = FilterNode("flt_empty", {
            "mode": "basic",
            "conditions": [{"column": "Customer", "operator": "is_empty"}]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(set(res["T"]["OrderID"]), {"ORD-105", "ORD-106"})

    def test_multi_condition_and_or(self):
        # Match ALL (AND)
        node = FilterNode("flt_and", {
            "mode": "basic",
            "logical_op": "AND",
            "conditions": [
                {"column": "Region", "operator": "==", "value": "East"},
                {"column": "Sales", "operator": ">", "value": "1000"}
            ]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(list(res["T"]["OrderID"]), ["ORD-101"])

        # Match ANY (OR)
        node = FilterNode("flt_or", {
            "mode": "basic",
            "logical_op": "OR",
            "conditions": [
                {"column": "Region", "operator": "==", "value": "West"},
                {"column": "Region", "operator": "==", "value": "South"}
            ]
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(set(res["T"]["OrderID"]), {"ORD-102", "ORD-106"})

    def test_custom_expression_mode(self):
        # Complex Alteryx AST expression with brackets, AND, OR
        expr = '[Sales] >= 800 AND ([Region] == "East" OR [Quantity] > 20)'
        node = FilterNode("flt_cust", {
            "mode": "custom",
            "expression": expr
        })
        res = node.execute({"I": self.df}, {})
        # ORD-101 (1500, East) -> True
        # ORD-103 (800, East) -> True
        # ORD-104 (3200, Qty 25) -> True
        self.assertEqual(set(res["T"]["OrderID"]), {"ORD-101", "ORD-103", "ORD-104"})
        self.assertEqual(set(res["F"]["OrderID"]), {"ORD-102", "ORD-105", "ORD-106"})

    def test_custom_expression_functions(self):
        # Using Contains, Regex_Match, Between
        expr = 'Contains([Customer], "Corp") OR REGEX_MATCH([PostalCode], "^90210$")'
        node = FilterNode("flt_fn", {
            "mode": "custom",
            "expression": expr
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(set(res["T"]["OrderID"]), {"ORD-101", "ORD-102"})

        # Between function
        expr_btw = 'Between([Quantity], 5, 15)'
        node_btw = FilterNode("flt_btw", {
            "mode": "custom",
            "expression": expr_btw
        })
        res_btw = node_btw.execute({"I": self.df}, {})
        # Qty: 10, 8, 5 -> ORD-101, ORD-103, ORD-106
        self.assertEqual(set(res_btw["T"]["OrderID"]), {"ORD-101", "ORD-103", "ORD-106"})

    def test_text_query_mode(self):
        # Natural search query: Region:East Sales>1000
        node = FilterNode("flt_q", {
            "mode": "text_query",
            "query": "Region:East Sales>1000"
        })
        res = node.execute({"I": self.df}, {})
        self.assertEqual(list(res["T"]["OrderID"]), ["ORD-101"])

        # Range query: Sales:200..1000
        node_range = FilterNode("flt_qr", {
            "mode": "text_query",
            "query": "Sales:200..1000"
        })
        res_range = node_range.execute({"I": self.df}, {})
        self.assertEqual(set(res_range["T"]["OrderID"]), {"ORD-102", "ORD-103", "ORD-106"})

        # List query: Region:East,South
        node_list = FilterNode("flt_ql", {
            "mode": "text_query",
            "query": "Region:East,South"
        })
        res_list = node_list.execute({"I": self.df}, {})
        self.assertEqual(set(res_list["T"]["OrderID"]), {"ORD-101", "ORD-103", "ORD-106"})

    def test_empty_dataframe(self):
        empty_df = pd.DataFrame(columns=self.df.columns)
        node = FilterNode("flt_emp", {
            "mode": "custom",
            "expression": "[Sales] > 100"
        })
        res = node.execute({"I": empty_df}, {})
        self.assertTrue(res["T"].empty)
        self.assertTrue(res["F"].empty)


if __name__ == "__main__":
    unittest.main()
