import unittest
import pandas as pd
import numpy as np
from backend.engine.nodes.join import JoinNode
from backend.engine.nodes.base import NodeExecutionError

class TestJoinToolAdvanced(unittest.TestCase):
    def setUp(self):
        self.context = {}

    def test_basic_join_outputs_both_tables(self):
        # Left table
        df_left = pd.DataFrame({
            "CustomerID": [1, 2, 3, 4],
            "CustomerName": ["Alice", "Bob", "Charlie", "David"],
            "Region": ["East", "West", "North", "South"]
        })
        # Right table
        df_right = pd.DataFrame({
            "CustomerID": [2, 3, 5],
            "Spend": [250.0, 430.5, 120.0],
            "Tier": ["Gold", "Platinum", "Silver"]
        })

        node = JoinNode("j1", {
            "join_keys": [{"left_key": "CustomerID", "right_key": "CustomerID"}]
        })
        res = node.execute({"L": df_left, "R": df_right}, self.context)

        self.assertIn("J", res)
        self.assertIn("L", res)
        self.assertIn("R", res)

        j_df = res["J"]
        l_df = res["L"]
        r_df = res["R"]

        # 2 matched records (CustomerID 2, 3)
        self.assertEqual(len(j_df), 2)
        # J contains columns from BOTH tables
        self.assertIn("CustomerID", j_df.columns)
        self.assertIn("CustomerName", j_df.columns)
        self.assertIn("Region", j_df.columns)
        self.assertIn("Right_CustomerID", j_df.columns)  # Colliding key prefixed
        self.assertIn("Spend", j_df.columns)
        self.assertIn("Tier", j_df.columns)

        # L contains unmatched left records (CustomerID 1, 4) with original Left schema
        self.assertEqual(len(l_df), 2)
        self.assertListEqual(list(l_df.columns), ["CustomerID", "CustomerName", "Region"])
        self.assertSetEqual(set(l_df["CustomerID"].tolist()), {1, 4})

        # R contains unmatched right records (CustomerID 5) with original Right schema
        self.assertEqual(len(r_df), 1)
        self.assertListEqual(list(r_df.columns), ["CustomerID", "Spend", "Tier"])
        self.assertEqual(r_df.iloc[0]["CustomerID"], 5)

    def test_collision_prefixing(self):
        df_l = pd.DataFrame({
            "ID": [10, 20],
            "Status": ["Active", "Pending"],
            "Value": [100, 200]
        })
        df_r = pd.DataFrame({
            "ID": [10, 20],
            "Status": ["Verified", "Unverified"],
            "Extra": ["X", "Y"]
        })

        node = JoinNode("j2", {
            "join_keys": [{"left_key": "ID", "right_key": "ID"}]
        })
        res = node.execute({"L": df_l, "R": df_r}, self.context)
        j_df = res["J"]

        # Colliding columns ID and Status from Right must be prefixed with Right_
        self.assertIn("ID", j_df.columns)
        self.assertIn("Right_ID", j_df.columns)
        self.assertIn("Status", j_df.columns)
        self.assertIn("Right_Status", j_df.columns)
        self.assertIn("Value", j_df.columns)
        self.assertIn("Extra", j_df.columns)

    def test_embedded_select_deselect_rename_reorder_typecast(self):
        df_l = pd.DataFrame({
            "ID": [1, 2],
            "Code": ["100", "200"],
            "ActiveStr": ["true", "false"]
        })
        df_r = pd.DataFrame({
            "ID": [1, 2],
            "Amount": ["50.5", "100.25"],
            "Notes": ["note1", "note2"]
        })

        # Embedded select:
        # - Deselect Right_ID and Notes
        # - Rename Code -> AccountCode
        # - Reorder: Amount first, then ID, then AccountCode, then ActiveStr
        # - Cast Code to int, Amount to float, ActiveStr to bool
        select_fields = [
            {"field": "Amount", "selected": True, "type": "float"},
            {"field": "ID", "selected": True, "type": "int64"},
            {"field": "Right_ID", "selected": False},
            {"field": "Code", "selected": True, "rename": "AccountCode", "type": "int64"},
            {"field": "ActiveStr", "selected": True, "type": "bool"},
            {"field": "Notes", "selected": False}
        ]

        node = JoinNode("j3", {
            "join_keys": [{"left_key": "ID", "right_key": "ID"}],
            "select_fields": select_fields
        })
        res = node.execute({"L": df_l, "R": df_r}, self.context)
        j_df = res["J"]

        # Check column order and renames
        expected_cols = ["Amount", "ID", "AccountCode", "ActiveStr"]
        self.assertListEqual(list(j_df.columns), expected_cols)
        self.assertNotIn("Right_ID", j_df.columns)
        self.assertNotIn("Notes", j_df.columns)

        # Check type casts
        self.assertTrue(pd.api.types.is_float_dtype(j_df["Amount"]))
        self.assertTrue(pd.api.types.is_integer_dtype(j_df["ID"]) or pd.api.types.is_int64_dtype(j_df["ID"]))
        self.assertTrue(pd.api.types.is_integer_dtype(j_df["AccountCode"]))
        self.assertTrue(pd.api.types.is_bool_dtype(j_df["ActiveStr"]))
        self.assertEqual(j_df.iloc[0]["ActiveStr"], True)
        self.assertEqual(j_df.iloc[1]["ActiveStr"], False)

    def test_composite_multi_key_join(self):
        df_l = pd.DataFrame({
            "Company": ["Acme", "Acme", "Beta"],
            "Branch": [1, 2, 1],
            "Revenue": [1000, 2000, 3000]
        })
        df_r = pd.DataFrame({
            "Company": ["Acme", "Acme", "Beta"],
            "Branch": [2, 3, 1],
            "Cost": [500, 700, 800]
        })

        node = JoinNode("j4", {
            "join_keys": [
                {"left_key": "Company", "right_key": "Company"},
                {"left_key": "Branch", "right_key": "Branch"}
            ]
        })
        res = node.execute({"L": df_l, "R": df_r}, self.context)
        j_df = res["J"]
        l_df = res["L"]
        r_df = res["R"]

        # Acme-2 and Beta-1 match
        self.assertEqual(len(j_df), 2)
        # Acme-1 in Left only
        self.assertEqual(len(l_df), 1)
        self.assertEqual(l_df.iloc[0]["Company"], "Acme")
        self.assertEqual(l_df.iloc[0]["Branch"], 1)
        # Acme-3 in Right only
        self.assertEqual(len(r_df), 1)
        self.assertEqual(r_df.iloc[0]["Company"], "Acme")
        self.assertEqual(r_df.iloc[0]["Branch"], 3)

    def test_case_insensitive_and_whitespace_trimming(self):
        df_l = pd.DataFrame({
            "Key": [" ALPHA ", "Beta", "GAMMA"],
            "L_Val": [1, 2, 3]
        })
        df_r = pd.DataFrame({
            "Key": ["alpha", " BETA  ", "Delta"],
            "R_Val": [10, 20, 30]
        })

        node = JoinNode("j5", {
            "join_keys": [{"left_key": "Key", "right_key": "Key"}],
            "ignore_case": True
        })
        res = node.execute({"L": df_l, "R": df_r}, self.context)
        j_df = res["J"]
        l_df = res["L"]
        r_df = res["R"]

        self.assertEqual(len(j_df), 2)  # ALPHA/alpha and Beta/BETA match
        self.assertEqual(len(l_df), 1)  # GAMMA unjoined
        self.assertEqual(len(r_df), 1)  # Delta unjoined

    def test_null_keys_do_not_match(self):
        df_l = pd.DataFrame({
            "Key": [None, np.nan, "ValidKey"],
            "Val_L": [1, 2, 3]
        })
        df_r = pd.DataFrame({
            "Key": [None, np.nan, "ValidKey"],
            "Val_R": [10, 20, 30]
        })

        node = JoinNode("j6", {
            "join_keys": [{"left_key": "Key", "right_key": "Key"}]
        })
        res = node.execute({"L": df_l, "R": df_r}, self.context)
        j_df = res["J"]
        l_df = res["L"]
        r_df = res["R"]

        # Only ValidKey matches! Nulls must never match each other (null != null)
        self.assertEqual(len(j_df), 1)
        self.assertEqual(j_df.iloc[0]["Key"], "ValidKey")
        # 2 null rows unjoined on Left
        self.assertEqual(len(l_df), 2)
        # 2 null rows unjoined on Right
        self.assertEqual(len(r_df), 2)

    def test_missing_inputs_and_keys_errors(self):
        node = JoinNode("j7", {"join_keys": [{"left_key": "A", "right_key": "A"}]})
        
        # Missing Left
        with self.assertRaises(NodeExecutionError):
            node.execute({"R": pd.DataFrame({"A": [1]})}, self.context)

        # Missing Right
        with self.assertRaises(NodeExecutionError):
            node.execute({"L": pd.DataFrame({"A": [1]})}, self.context)

        # No join keys configured
        node_no_keys = JoinNode("j8", {"join_keys": []})
        with self.assertRaises(NodeExecutionError):
            node_no_keys.execute({"L": pd.DataFrame({"A": [1]}), "R": pd.DataFrame({"A": [1]})}, self.context)

        # Key not in columns
        node_bad_keys = JoinNode("j9", {"join_keys": [{"left_key": "NonExistent", "right_key": "A"}]})
        with self.assertRaises(NodeExecutionError):
            node_bad_keys.execute({"L": pd.DataFrame({"A": [1]}), "R": pd.DataFrame({"A": [1]})}, self.context)

if __name__ == "__main__":
    unittest.main()
