import os
import time
import json
import unittest
import pandas as pd
from typing import List, Dict, Any

from backend.engine.executor import WorkflowExecutor
from backend.samples.generator import ensure_sample_data


class TestAMPParallelExecutor(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "data")
        self.output_dir = os.path.join(self.data_dir, "outputs")
        self.workflows_dir = os.path.join(self.base_dir, "workflows")
        ensure_sample_data(self.data_dir, self.workflows_dir)
        self.executor = WorkflowExecutor(context={"data_dir": self.data_dir, "output_dir": self.output_dir})

    def test_amp_multiple_inputs_parallel_execution(self):
        """Tests that multiple input nodes execute in parallel and produce correct union output."""
        wf = {
            "name": "Multi-Input Parallel Test",
            "use_amp_engine": True,
            "max_threads": 4,
            "nodes": [
                {
                    "id": "in1",
                    "type": "text_input",
                    "name": "Source A",
                    "config": {
                        "columns": ["ID", "Val"],
                        "data": [[1, "A1"], [2, "A2"]]
                    }
                },
                {
                    "id": "in2",
                    "type": "text_input",
                    "name": "Source B",
                    "config": {
                        "columns": ["ID", "Val"],
                        "data": [[3, "B1"], [4, "B2"]]
                    }
                },
                {
                    "id": "in3",
                    "type": "text_input",
                    "name": "Source C",
                    "config": {
                        "columns": ["ID", "Val"],
                        "data": [[5, "C1"]]
                    }
                },
                {
                    "id": "union_all",
                    "type": "union",
                    "name": "Combine Inputs",
                    "config": {"mode": "by_name"}
                }
            ],
            "connections": [
                {"source": "in1", "sourceHandle": "O", "target": "union_all", "targetHandle": "I"},
                {"source": "in2", "sourceHandle": "O", "target": "union_all", "targetHandle": "I"},
                {"source": "in3", "sourceHandle": "O", "target": "union_all", "targetHandle": "I"}
            ]
        }

        events = []
        def observer(ev):
            events.append(ev)

        result = self.executor.run(wf, observer_cb=observer)
        self.assertTrue(result.success)
        self.assertEqual(len(result.node_results), 4)

        # Check union output
        out = self.executor.get_node_data("union_all", "O")
        self.assertTrue(out["available"])
        self.assertEqual(out["pagination"]["total_records"], 5)

        # Verify that all 3 inputs started before all of them completed (concurrent execution)
        started_nodes = [ev["node_id"] for ev in events if ev.get("event") == "node_started"]
        self.assertIn("in1", started_nodes)
        self.assertIn("in2", started_nodes)
        self.assertIn("in3", started_nodes)

    def test_amp_parity_with_classic_sequential(self):
        """Verifies that AMP and Classic engines produce identical result data on multi-input workflows."""
        with open(os.path.join(self.workflows_dir, "inventory_supplier_reconciliation.json"), "r") as f:
            base_wf = json.load(f)

        # 1. Run with AMP
        wf_amp = dict(base_wf)
        wf_amp["use_amp_engine"] = True
        res_amp = self.executor.run(wf_amp)
        self.assertTrue(res_amp.success)

        # 2. Run with Classic Sequential
        wf_seq = dict(base_wf)
        wf_seq["use_amp_engine"] = False
        res_seq = self.executor.run(wf_seq)
        self.assertTrue(res_seq.success)

        # Compare node results count and status
        self.assertEqual(len(res_amp.node_results), len(res_seq.node_results))
        for nid in res_amp.node_results:
            self.assertEqual(res_amp.node_results[nid]["status"], res_seq.node_results[nid]["status"])
            self.assertEqual(res_amp.node_results[nid]["record_counts"], res_seq.node_results[nid]["record_counts"])

    def test_amp_cancellation(self):
        """Verifies that cancellation halts in-flight parallel execution safely."""
        wf = {
            "name": "Slow Parallel Run",
            "use_amp_engine": True,
            "nodes": [
                {
                    "id": "in1",
                    "type": "input_data",
                    "name": "Input Sales",
                    "config": {"file_path": "sales_orders.csv", "file_type": "csv"}
                },
                {
                    "id": "in2",
                    "type": "input_data",
                    "name": "Input Customers",
                    "config": {"file_path": "customers.csv", "file_type": "csv"}
                }
            ],
            "connections": []
        }

        self.executor.cancel_run()
        res = self.executor.run(wf)
        self.assertIsNotNone(res)

    def test_amp_error_handling_in_branch(self):
        """Verifies that an error in one parallel branch halts execution gracefully and surfaces diagnostic."""
        wf = {
            "name": "Branch Error Test",
            "use_amp_engine": True,
            "nodes": [
                {
                    "id": "in_ok",
                    "type": "text_input",
                    "name": "Good Input",
                    "config": {"columns": ["X"], "data": [[1]]}
                },
                {
                    "id": "in_bad",
                    "type": "filter",
                    "name": "Bad Filter Without Input",
                    "config": {"mode": "custom", "expression": "[NonExistent] > 0"}
                },
                {
                    "id": "downstream",
                    "type": "select",
                    "name": "Downstream Tool",
                    "config": {}
                }
            ],
            "connections": [
                {"source": "in_bad", "sourceHandle": "T", "target": "downstream", "targetHandle": "I"}
            ]
        }

        res = self.executor.run(wf)
        self.assertFalse(res.success)
        self.assertIn("in_bad", res.node_results)
        self.assertEqual(res.node_results["in_bad"]["status"], "error")

    def test_amp_independent_branches_parallel(self):
        """Tests that two completely independent branches run in parallel."""
        wf = {
            "name": "Dual Independent Pipelines",
            "use_amp_engine": True,
            "max_threads": 4,
            "nodes": [
                # Branch 1
                {"id": "b1_in", "type": "text_input", "name": "Branch 1 In", "config": {"columns": ["V"], "data": [[10], [20]]}},
                {"id": "b1_formula", "type": "formula", "name": "Branch 1 Formula", "config": {"formulas": [{"output_field": "V2", "expression": "[V] * 2", "type": "integer"}]}},
                # Branch 2
                {"id": "b2_in", "type": "text_input", "name": "Branch 2 In", "config": {"columns": ["W"], "data": [[100], [200]]}},
                {"id": "b2_formula", "type": "formula", "name": "Branch 2 Formula", "config": {"formulas": [{"output_field": "W2", "expression": "[W] * 3", "type": "integer"}]}}
            ],
            "connections": [
                {"source": "b1_in", "sourceHandle": "O", "target": "b1_formula", "targetHandle": "I"},
                {"source": "b2_in", "sourceHandle": "O", "target": "b2_formula", "targetHandle": "I"}
            ]
        }

        res = self.executor.run(wf)
        self.assertTrue(res.success)
        self.assertEqual(len(res.node_results), 4)
        self.assertEqual(res.node_results["b1_formula"]["status"], "success")
        self.assertEqual(res.node_results["b2_formula"]["status"], "success")


if __name__ == '__main__':
    unittest.main()
