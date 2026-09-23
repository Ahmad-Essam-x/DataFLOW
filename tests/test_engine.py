"""
Comprehensive unit tests for the visual ETL execution engine and node processors.
"""
import os
import unittest
import pandas as pd
import numpy as np

from backend.engine.dag import DAG, WorkflowValidationError
from backend.engine.node_registry import (
    InputDataNode, OutputDataNode, SelectNode, FilterNode,
    FormulaNode, SortNode, CleanNode, UniqueNode,
    SummarizeNode, JoinNode, UnionNode
)
from backend.engine.executor import WorkflowExecutor
from backend.samples.generator import ensure_sample_data


class TestDAG(unittest.TestCase):
    def test_valid_dag(self):
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        connections = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"}
        ]
        dag = DAG(nodes, connections)
        self.assertFalse(dag.detect_cycles())
        order = dag.topological_sort()
        self.assertEqual(order, ["A", "B", "C"])

    def test_cycle_detection(self):
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        connections = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
            {"source": "C", "target": "A"}
        ]
        dag = DAG(nodes, connections)
        self.assertTrue(dag.detect_cycles())
        with self.assertRaises(WorkflowValidationError):
            dag.topological_sort()


class TestNodeProcessors(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "data")
        self.workflows_dir = os.path.join(self.base_dir, "workflows")
        ensure_sample_data(self.data_dir, self.workflows_dir)
        self.context = {"data_dir": self.data_dir, "output_dir": os.path.join(self.data_dir, "outputs")}

    def test_input_data_csv(self):
        node = InputDataNode("in1", {"file_path": "customers.csv", "file_type": "csv"})
        res = node.execute({}, self.context)
        self.assertIn("O", res)
        df = res["O"]
        self.assertEqual(len(df), 1000)
        self.assertIn("CustomerID", df.columns)
        self.assertIn("CustomerName", df.columns)

    def test_input_data_excel(self):
        node = InputDataNode("in2", {"file_path": "orders.xlsx", "file_type": "excel"})
        res = node.execute({}, self.context)
        self.assertIn("O", res)
        df = res["O"]
        self.assertEqual(len(df), 2500)
        self.assertIn("OrderID", df.columns)
        self.assertIn("Quantity", df.columns)

    def test_select_node(self):
        df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"], "C": [10.5, 20.5]})
        config = {
            "fields": [
                {"original": "A", "keep": True, "rename": "Alpha", "type": "string"},
                {"original": "B", "keep": False},
                {"original": "C", "keep": True, "rename": "Gamma", "type": "float"}
            ]
        }
        node = SelectNode("sel", config)
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertListEqual(list(out.columns), ["Alpha", "Gamma"])
        self.assertEqual(out["Alpha"].iloc[0], "1")

    def test_filter_node(self):
        df = pd.DataFrame({"Val": [10, 50, 80, 20], "Cat": ["A", "B", "A", "B"]})
        config = {
            "mode": "basic",
            "logical_op": "AND",
            "conditions": [
                {"column": "Val", "operator": ">=", "value": "50"},
                {"column": "Cat", "operator": "==", "value": "A"}
            ]
        }
        node = FilterNode("flt", config)
        res = node.execute({"I": df}, self.context)
        self.assertIn("T", res)
        self.assertIn("F", res)
        self.assertEqual(len(res["T"]), 1)
        self.assertEqual(len(res["F"]), 3)
        self.assertEqual(res["T"].iloc[0]["Val"], 80)

    def test_formula_node(self):
        df = pd.DataFrame({"Price": [100.0, 50.0], "Qty": [2, 4], "Disc": [0.1, 0.0], "Name": ["  alice  ", "BOB"]})
        config = {
            "formulas": [
                {"output_field": "Total", "expression": "[Price] * [Qty] * (1 - [Disc])"},
                {"output_field": "CleanName", "expression": "UPPER(TRIM([Name]))"},
                {"output_field": "Tier", "expression": "IF([Total] > 150, 'High', 'Standard')"}
            ]
        }
        node = FormulaNode("form", config)
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertAlmostEqual(out["Total"].iloc[0], 180.0)
        self.assertAlmostEqual(out["Total"].iloc[1], 200.0)
        self.assertEqual(out["CleanName"].iloc[0], "ALICE")
        self.assertEqual(out["Tier"].iloc[0], "High")

    def test_sort_node(self):
        df = pd.DataFrame({"Group": ["B", "A", "B", "A"], "Num": [10, 20, 5, 30]})
        config = {
            "sort_by": [
                {"column": "Group", "ascending": True},
                {"column": "Num", "ascending": False}
            ]
        }
        node = SortNode("sort", config)
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertEqual(list(out["Num"]), [30, 20, 10, 5])

    def test_clean_node(self):
        df = pd.DataFrame({"City": ["  new york  ", "Chicago", np.nan], "Val": [10.0, np.nan, 30.0]})
        config = {
            "columns": ["City", "Val"],
            "trim_whitespace": True,
            "case_transformation": "upper",
            "null_strategy": "mean"
        }
        node = CleanNode("clean", config)
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertEqual(out["City"].iloc[0], "NEW YORK")
        # Val mean is (10 + 30) / 2 = 20
        self.assertEqual(out["Val"].iloc[1], 20.0)

    def test_unique_node(self):
        df = pd.DataFrame({"Key": ["A", "B", "A", "C"], "Val": [1, 2, 3, 4]})
        config = {"columns": ["Key"]}
        node = UniqueNode("uniq", config)
        res = node.execute({"I": df}, self.context)
        self.assertEqual(len(res["U"]), 3)
        self.assertEqual(len(res["D"]), 1)
        self.assertEqual(res["D"].iloc[0]["Val"], 3)

    def test_summarize_node(self):
        df = pd.DataFrame({
            "Dept": ["Sales", "Sales", "IT", "IT"],
            "Salary": [50000, 70000, 80000, 90000],
            "EmpID": ["E1", "E2", "E3", "E4"]
        })
        config = {
            "actions": [
                {"field": "Dept", "action": "GroupBy", "output_name": "Department"},
                {"field": "Salary", "action": "Sum", "output_name": "TotalSalary"},
                {"field": "Salary", "action": "Mean", "output_name": "AvgSalary"},
                {"field": "EmpID", "action": "Count", "output_name": "Headcount"}
            ]
        }
        node = SummarizeNode("sum", config)
        res = node.execute({"I": df}, self.context)
        out = res["O"]
        self.assertEqual(len(out), 2)
        sales_row = out[out["Department"] == "Sales"].iloc[0]
        self.assertEqual(sales_row["TotalSalary"], 120000)
        self.assertEqual(sales_row["AvgSalary"], 60000)
        self.assertEqual(sales_row["Headcount"], 2)

    def test_join_node_3_outputs(self):
        left = pd.DataFrame({"ID": ["1", "2", "3"], "LVal": ["L1", "L2", "L3"]})
        right = pd.DataFrame({"ID": ["2", "3", "4"], "RVal": ["R2", "R3", "R4"]})
        config = {
            "join_keys": [{"left_key": "ID", "right_key": "ID"}]
        }
        node = JoinNode("jn", config)
        res = node.execute({"L": left, "R": right}, self.context)
        self.assertIn("J", res)
        self.assertIn("L", res)
        self.assertIn("R", res)
        # J should have 2 and 3
        self.assertEqual(len(res["J"]), 2)
        # L should have 1
        self.assertEqual(len(res["L"]), 1)
        self.assertEqual(res["L"].iloc[0]["ID"], "1")
        # R should have 4
        self.assertEqual(len(res["R"]), 1)
        self.assertEqual(res["R"].iloc[0]["ID"], "4")

    def test_union_node(self):
        df1 = pd.DataFrame({"A": [1, 2], "B": ["X", "Y"]})
        df2 = pd.DataFrame({"A": [3, 4], "B": ["Z", "W"]})
        node = UnionNode("un", {"mode": "by_name"})
        res = node.execute({"I": [df1, df2]}, self.context)
        out = res["O"]
        self.assertEqual(len(out), 4)


class TestWorkflowExecutor(unittest.TestCase):
    def test_full_pipeline_run(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        workflows_dir = os.path.join(base_dir, "workflows")
        ensure_sample_data(data_dir, workflows_dir)

        import json
        with open(os.path.join(workflows_dir, "sales_customer_enrichment.json"), "r") as f:
            wf = json.load(f)

        executor = WorkflowExecutor(context={"data_dir": data_dir, "output_dir": os.path.join(data_dir, "outputs")})
        res = executor.run(wf)
        self.assertTrue(res.success)
        self.assertIn("node_sort_1", res.node_results)
        self.assertEqual(res.node_results["node_sort_1"]["status"], "success")

        # Test pagination
        page_data = executor.get_node_data("node_sort_1", "O", page=1, page_size=10)
        self.assertTrue(page_data["available"])
        self.assertGreater(len(page_data["records"]), 0)

        # Test profiling
        profile = executor.get_node_profiling("node_sort_1", "O")
        self.assertTrue(profile["available"])
        self.assertGreater(len(profile["columns"]), 0)


if __name__ == "__main__":
    unittest.main()
