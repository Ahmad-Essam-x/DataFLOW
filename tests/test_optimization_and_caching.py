"""
Tests for Optimization Features: Frozen Node Cache, Execution Cancellation,
and Node Configuration Validation Badges.
"""
import unittest
import time
import threading
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.engine.executor import WorkflowExecutor
from backend.engine.cache_manager import SessionRunCacheManager
from backend.engine.validation import validate_node_config
from backend.app import app


class TestNodeConfigValidation(unittest.TestCase):
    """Tests for validate_node_config()."""

    def test_input_data_missing_file(self):
        valid, warnings = validate_node_config("input_data", {})
        self.assertFalse(valid)
        self.assertEqual(len(warnings), 1)
        self.assertIn("No data file", warnings[0])

    def test_input_data_valid(self):
        valid, warnings = validate_node_config("input_data", {"file_name": "test.csv"})
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_filter_no_column(self):
        valid, warnings = validate_node_config("filter", {})
        self.assertFalse(valid)
        self.assertIn("No filter column", warnings[0])

    def test_filter_missing_value(self):
        valid, warnings = validate_node_config("filter", {"column": "Sales", "operator": "==", "value": ""})
        self.assertFalse(valid)
        self.assertIn("Comparison value", warnings[0])

    def test_filter_unary_operator_ok(self):
        valid, warnings = validate_node_config("filter", {"column": "Sales", "operator": "is_null"})
        self.assertTrue(valid)

    def test_filter_valid(self):
        valid, warnings = validate_node_config("filter", {"column": "Sales", "operator": ">=", "value": "100"})
        self.assertTrue(valid)

    def test_formula_empty(self):
        valid, warnings = validate_node_config("formula", {})
        self.assertFalse(valid)
        self.assertIn("No formula expression", warnings[0])

    def test_formula_valid(self):
        valid, warnings = validate_node_config("formula", {
            "expressions": [{"column": "Total", "expression": "[Qty] * [Price]"}]
        })
        self.assertTrue(valid)

    def test_sort_no_column(self):
        valid, warnings = validate_node_config("sort", {})
        self.assertFalse(valid)

    def test_sort_with_column(self):
        valid, warnings = validate_node_config("sort", {"column": "Revenue"})
        self.assertTrue(valid)

    def test_sort_with_rules(self):
        valid, warnings = validate_node_config("sort", {"rules": [{"column": "A"}]})
        self.assertTrue(valid)

    def test_summarize_no_actions(self):
        valid, warnings = validate_node_config("summarize", {})
        self.assertFalse(valid)

    def test_summarize_valid(self):
        valid, warnings = validate_node_config("summarize", {
            "actions": [{"field": "Amount", "action": "sum"}]
        })
        self.assertTrue(valid)

    def test_join_missing_keys(self):
        valid, warnings = validate_node_config("join", {"left_key": "ID"})
        self.assertFalse(valid)

    def test_join_valid(self):
        valid, warnings = validate_node_config("join", {"left_key": "ID", "right_key": "ID"})
        self.assertTrue(valid)

    def test_unique_no_columns(self):
        valid, warnings = validate_node_config("unique", {})
        self.assertFalse(valid)

    def test_unique_valid(self):
        valid, warnings = validate_node_config("unique", {"columns": ["Name"]})
        self.assertTrue(valid)

    def test_sample_zero(self):
        valid, warnings = validate_node_config("sample", {"n": 0})
        self.assertFalse(valid)

    def test_sample_valid(self):
        valid, warnings = validate_node_config("sample", {"n": 10})
        self.assertTrue(valid)

    def test_output_data_missing_filename(self):
        valid, warnings = validate_node_config("output_data", {})
        self.assertFalse(valid)

    def test_output_data_valid(self):
        valid, warnings = validate_node_config("output_data", {"file_name": "out.csv"})
        self.assertTrue(valid)

    def test_text_input_empty(self):
        valid, warnings = validate_node_config("text_input", {"text": ""})
        self.assertFalse(valid)

    def test_text_input_valid(self):
        valid, warnings = validate_node_config("text_input", {"text": "A,B\n1,2"})
        self.assertTrue(valid)

    def test_transpose_empty(self):
        valid, warnings = validate_node_config("transpose", {})
        self.assertFalse(valid)

    def test_crosstab_missing_fields(self):
        valid, warnings = validate_node_config("crosstab", {"header_field": "Region"})
        self.assertFalse(valid)

    def test_text_to_columns_missing(self):
        valid, warnings = validate_node_config("text_to_columns", {})
        self.assertFalse(valid)

    def test_text_to_columns_valid(self):
        valid, warnings = validate_node_config("text_to_columns", {"column": "Name", "delimiter": ","})
        self.assertTrue(valid)

    def test_modern_filter_conditions_valid(self):
        valid, warnings = validate_node_config("filter", {
            "mode": "basic",
            "conditions": [{"column": "Sales", "operator": ">", "value": "100"}]
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_modern_filter_custom_expression_valid(self):
        valid, warnings = validate_node_config("filter", {
            "mode": "custom",
            "expression": "[Sales] > 100"
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_modern_formula_valid(self):
        valid, warnings = validate_node_config("formula", {
            "formulas": [{"output_field": "Total", "expression": "[Qty] * [Price]"}]
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_modern_sort_by_valid(self):
        valid, warnings = validate_node_config("sort", {
            "sort_by": [{"column": "Customer", "ascending": True}]
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_modern_join_keys_valid(self):
        valid, warnings = validate_node_config("join", {
            "join_mode": "specific_fields",
            "join_keys": [{"left_key": "ID", "right_key": "CustID"}]
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_modern_join_record_position_valid(self):
        valid, warnings = validate_node_config("join", {
            "join_mode": "record_position"
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_modern_text_input_grid_valid(self):
        valid, warnings = validate_node_config("text_input", {
            "columns": ["Col1", "Col2"],
            "data": [["Val1", "Val2"]]
        })
        self.assertTrue(valid)
        self.assertEqual(len(warnings), 0)

    def test_union_always_valid(self):
        valid, warnings = validate_node_config("union", {})
        self.assertTrue(valid)

    def test_clean_always_valid(self):
        valid, warnings = validate_node_config("clean", {})
        self.assertTrue(valid)

    def test_record_id_always_valid(self):
        valid, warnings = validate_node_config("record_id", {})
        self.assertTrue(valid)

    def test_find_replace_missing(self):
        valid, warnings = validate_node_config("find_replace", {})
        self.assertFalse(valid)


class TestFrozenNodeCache(unittest.TestCase):
    """Tests for the frozen node caching mechanism in WorkflowExecutor."""

    def setUp(self):
        self.cache_manager = SessionRunCacheManager(max_runs=5, ttl_seconds=300)
        self.executor = WorkflowExecutor(context={
            "data_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
            "output_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "outputs"),
            "base_dir": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        }, cache_manager=self.cache_manager)

    def test_frozen_cache_starts_empty(self):
        self.assertEqual(len(self.executor.get_frozen_node_ids()), 0)

    def test_cache_and_clear_single_node(self):
        self.executor.frozen_node_cache["n1"] = {"O": pd.DataFrame({"x": [1, 2, 3]})}
        self.assertIn("n1", self.executor.get_frozen_node_ids())
        result = self.executor.clear_frozen_cache("n1")
        self.assertTrue(result)
        self.assertNotIn("n1", self.executor.get_frozen_node_ids())

    def test_clear_nonexistent_returns_false(self):
        result = self.executor.clear_frozen_cache("nonexistent_node")
        self.assertFalse(result)

    def test_clear_all_frozen_cache(self):
        self.executor.frozen_node_cache["n1"] = {"O": pd.DataFrame({"x": [1]})}
        self.executor.frozen_node_cache["n2"] = {"O": pd.DataFrame({"y": [2]})}
        self.assertEqual(len(self.executor.get_frozen_node_ids()), 2)
        result = self.executor.clear_frozen_cache()
        self.assertTrue(result)
        self.assertEqual(len(self.executor.get_frozen_node_ids()), 0)

    def test_cached_node_rerun_skips_upstream(self):
        """Test that a cached node loads from frozen cache and skips upstream."""
        workflow1 = {
            "nodes": [
                {"id": "inp1", "type": "input_data", "name": "Input",
                 "config": {"file_path": "customers.csv"}},
                {"id": "filt1", "type": "filter", "name": "Filter",
                 "config": {"column": "Region", "operator": "==", "value": "North"}}
            ],
            "connections": [
                {"source": "inp1", "sourceHandle": "O", "target": "filt1", "targetHandle": "I"}
            ]
        }
        result1 = self.executor.run(workflow1)
        self.assertTrue(result1.success, f"First run failed: {result1.error}")

        # Freeze the filter node
        if "filt1" in self.executor.data_cache:
            self.executor.frozen_node_cache["filt1"] = self.executor.data_cache["filt1"]

        workflow2 = {
            "nodes": [
                {"id": "inp1", "type": "input_data", "name": "Input",
                 "config": {"file_path": "customers.csv"}},
                {"id": "filt1", "type": "filter", "name": "Filter",
                 "config": {"column": "Region", "operator": "==", "value": "North"},
                 "is_cached": True}
            ],
            "connections": [
                {"source": "inp1", "sourceHandle": "O", "target": "filt1", "targetHandle": "I"}
            ],
            "cached_node_ids": ["filt1"]
        }
        start = time.time()
        result2 = self.executor.run(workflow2)
        elapsed = (time.time() - start) * 1000
        self.assertTrue(result2.success, f"Cached run failed: {result2.error}")

        filt_result = result2.node_results.get("filt1", {})
        self.assertEqual(filt_result.get("status"), "success")
        self.assertEqual(filt_result.get("duration_ms"), 0.0)


class TestExecutionCancellation(unittest.TestCase):
    """Tests for workflow execution cancellation."""

    def setUp(self):
        self.cache_manager = SessionRunCacheManager(max_runs=5, ttl_seconds=300)
        self.executor = WorkflowExecutor(context={
            "data_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
            "output_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "outputs"),
            "base_dir": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        }, cache_manager=self.cache_manager)

    def test_cancel_no_active_run(self):
        result = self.executor.cancel_run("nonexistent_run")
        self.assertFalse(result)

    def test_cancel_all_runs(self):
        token = threading.Event()
        self.executor._active_cancellations["test_run_123"] = token
        self.assertFalse(token.is_set())
        cancelled = self.executor.cancel_run()
        self.assertTrue(cancelled)
        self.assertTrue(token.is_set())

    def test_cancel_specific_run(self):
        token = threading.Event()
        self.executor._active_cancellations["run_abc"] = token
        cancelled = self.executor.cancel_run("run_abc")
        self.assertTrue(cancelled)
        self.assertTrue(token.is_set())


class TestCancelAndValidateEndpoints(unittest.TestCase):
    """Test the cancel and validate API endpoints."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_cancel_endpoint_no_run(self):
        resp = self.client.post("/api/cancel", json={"run_id": None})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])

    def test_cancel_with_run_id(self):
        resp = self.client.post("/api/cancel/nonexistent_id", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])

    def test_node_cache_status(self):
        resp = self.client.get("/api/node-cache/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("cached_node_ids", data)
        self.assertIsInstance(data["cached_node_ids"], list)

    def test_node_cache_clear(self):
        resp = self.client.post("/api/node-cache/clear", json={"node_id": "some_node"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])

    def test_validate_node_endpoint_valid(self):
        resp = self.client.post("/api/validate-node", json={
            "type": "input_data",
            "config": {"file_name": "test.csv"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["valid"])
        self.assertEqual(len(data["warnings"]), 0)

    def test_validate_node_endpoint_invalid(self):
        resp = self.client.post("/api/validate-node", json={
            "type": "input_data",
            "config": {}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["valid"])
        self.assertGreater(len(data["warnings"]), 0)

    def test_validate_filter_endpoint(self):
        resp = self.client.post("/api/validate-node", json={
            "type": "filter",
            "config": {"column": "Region", "operator": "==", "value": "North"}
        })
        data = resp.get_json()
        self.assertTrue(data["valid"])

    def test_validate_formula_endpoint(self):
        resp = self.client.post("/api/validate-node", json={
            "type": "formula",
            "config": {}
        })
        data = resp.get_json()
        self.assertFalse(data["valid"])


if __name__ == "__main__":
    unittest.main()
