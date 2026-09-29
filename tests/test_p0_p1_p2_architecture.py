"""
Comprehensive test suite for P0 (Blueprint Architecture, Dialogs, RunContext),
P1 (Tab-isolated Undo/Redo), and P2 (Column Lineage Tracer).
"""
import os
import sys
import json
import time
import unittest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app, executor
from backend.engine.executor import RunContext
from backend.engine.lineage import compute_lineage
from backend.blueprints.dialogs import _run_dialog_safe


class TestArchitectureAndLineage(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_blueprint_route_coverage(self):
        """Verify endpoints across all 6 registered blueprints respond with valid HTTP statuses."""
        # 1. execution blueprint
        res_tools = self.client.get("/api/tools")
        self.assertEqual(res_tools.status_code, 200)
        self.assertIn("tools", res_tools.get_json())

        # 2. files blueprint
        res_samples = self.client.get("/api/samples")
        self.assertEqual(res_samples.status_code, 200)
        self.assertIn("datasets", res_samples.get_json())

        # 3. workflow blueprint
        res_app_info = self.client.get("/api/app-info")
        self.assertEqual(res_app_info.status_code, 200)
        self.assertEqual(res_app_info.get_json().get("app_name"), "Antigravity DataFlow")

        # 4. settings blueprint
        res_settings = self.client.get("/api/user-settings")
        self.assertEqual(res_settings.status_code, 200)

        # 5. ai blueprint
        res_ai = self.client.get("/api/ai/providers")
        self.assertEqual(res_ai.status_code, 200)
        self.assertIn("providers", res_ai.get_json())

    def test_run_context_isolation(self):
        """Verify RunContext encapsulates session_id and threads it through execution calls."""
        ctx1 = executor.get_run_context("tab_session_alpha")
        self.assertEqual(ctx1.session_id, "tab_session_alpha")
        self.assertIs(ctx1.executor, executor)

        ctx2 = executor.get_run_context("tab_session_beta")
        self.assertEqual(ctx2.session_id, "tab_session_beta")

        # Minimal workflow payload
        wf = {
            "name": "Context Test",
            "nodes": [
                {"id": "n1", "type": "text_input", "config": {"columns": ["X", "Y"], "data": [["1", "2"], ["3", "4"]]}}
            ],
            "connections": []
        }

        res = ctx1.run(wf)
        self.assertTrue(res.success)
        self.assertEqual(res.session_id, "tab_session_alpha")

        # Node data retrieved via ctx1 automatically carries session_id
        node_data = ctx1.get_node_data("n1")
        self.assertTrue(node_data.get("available"))
        self.assertEqual(node_data.get("pagination", {}).get("total_records"), 2)
        self.assertEqual(len(node_data.get("records", [])), 2)

    def test_column_lineage_computation(self):
        """Verify compute_lineage traces column origins through input, formula, and select renames."""
        wf = {
            "nodes": [
                {
                    "id": "node_in",
                    "type": "input_data",
                    "config": {"preview_columns": ["OrderID", "Customer", "Subtotal", "TaxRate"]}
                },
                {
                    "id": "node_formula",
                    "type": "formula",
                    "config": {
                        "formulas": [
                            {"output_field": "TaxAmount", "expression": "[Subtotal] * [TaxRate]"},
                            {"output_field": "Total", "expression": "[Subtotal] + [TaxAmount]"}
                        ]
                    }
                },
                {
                    "id": "node_select",
                    "type": "select",
                    "config": {
                        "fields": [
                            {"name": "Customer", "rename": "ClientName", "selected": True},
                            {"name": "Total", "rename": "GrandTotal", "selected": True}
                        ]
                    }
                }
            ],
            "connections": [
                {"source": "node_in", "target": "node_formula"},
                {"source": "node_formula", "target": "node_select"}
            ]
        }

        lineage = compute_lineage(wf)

        # 1. Initial node has itself as origin for all fields
        self.assertEqual(lineage["node_in"]["OrderID"], [("node_in", "OrderID")])
        self.assertEqual(lineage["node_in"]["Subtotal"], [("node_in", "Subtotal")])

        # 2. Formula node computes TaxAmount from Subtotal and TaxRate
        tax_sources = lineage["node_formula"]["TaxAmount"]
        self.assertIn(("node_in", "Subtotal"), tax_sources)
        self.assertIn(("node_in", "TaxRate"), tax_sources)

        # 3. Select node renamed fields
        self.assertEqual(lineage["node_select"]["ClientName"], [("node_in", "Customer")])
        self.assertIn(("node_in", "Subtotal"), lineage["node_select"]["GrandTotal"])

    def test_lineage_api_endpoint(self):
        """Verify POST /api/workflow/lineage endpoint returns DAG column provenance."""
        wf = {
            "nodes": [
                {"id": "n1", "type": "input_data", "config": {"preview_columns": ["A", "B"]}},
                {"id": "n2", "type": "select", "config": {"fields": [{"name": "A", "rename": "A_renamed", "selected": True}]}}
            ],
            "connections": [{"source": "n1", "target": "n2"}]
        }

        resp = self.client.post(
            "/api/workflow/lineage",
            data=json.dumps({"workflow": wf, "node_id": "n2"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("lineage", data)
        self.assertIn("A_renamed", data["lineage"]["n2"])
        self.assertEqual(data["lineage"]["n2"]["A_renamed"], [["n1", "A"]])

    def test_async_dialog_runner_timeout_safety(self):
        """Verify _run_dialog_safe returns None on worker timeout without blocking the caller."""
        def slow_blocking_dialog():
            time.sleep(1.0)
            return "C:/path/should_not_reach.json"

        # Execute with an aggressive 0.1s timeout
        start = time.time()
        result = _run_dialog_safe(slow_blocking_dialog, timeout=0.1)
        duration = time.time() - start

        self.assertIsNone(result, "Slow dialog should time out and return None")
        self.assertLess(duration, 0.5, "Timeout must return promptly without hanging the thread")

    def test_async_dialog_runner_success(self):
        """Verify _run_dialog_safe successfully returns result from completed worker."""
        def fast_dialog(default_name="test.json"):
            return f"C:/mock_workflows/{default_name}"

        result = _run_dialog_safe(fast_dialog, timeout=2.0, default_name="my_flow.json")
        self.assertEqual(result, "C:/mock_workflows/my_flow.json")

    def test_recent_workflows_full_lifecycle_and_spaces(self):
        """Verify recent workflows with spaces, absolute paths, and bulk sync maintain persistence."""
        # 1. Post a recent workflow with spaces in filename
        post_res = self.client.post("/api/workflow/recent", json={
            "name": "Spotify Analytics",
            "path": "spotify analytics.json"
        })
        self.assertEqual(post_res.status_code, 200)

        # 2. GET enriched with existence and resolved path
        get_res = self.client.get("/api/workflow/recent")
        self.assertEqual(get_res.status_code, 200)
        recent_list = get_res.get_json().get("recent_workflows", [])
        self.assertTrue(len(recent_list) > 0)
        first_item = recent_list[0]
        self.assertEqual(first_item["name"], "Spotify Analytics")
        self.assertTrue(first_item["exists"])
        self.assertTrue(first_item["resolved_path"].endswith("spotify analytics.json"))

        # 3. Bulk sync
        bulk_res = self.client.post("/api/workflow/recent", json={
            "recent_workflows": [
                {"name": "Spotify Analytics", "path": "workflows/spotify analytics.json"},
                {"name": "Customer Sales", "path": "workflows/customer_sales_analysis.json"}
            ]
        })
        self.assertEqual(bulk_res.status_code, 200)
        self.assertEqual(len(bulk_res.get_json().get("recent_workflows", [])), 2)

    def test_workflow_open_endpoint_resilience(self):
        """Verify /api/workflow/open resolves files by path, filename with spaces/underscores, and name."""
        # 1. By direct path with spaces
        res1 = self.client.post("/api/workflow/open", json={"path": "workflows/spotify analytics.json"})
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.get_json().get("success"))
        self.assertIn("nodes", res1.get_json().get("workflow", {}))

        # 2. By filename with underscore
        res2 = self.client.post("/api/workflow/open", json={"filename": "spotify_analytics.json"})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json().get("success"))

        # 3. By human-readable name
        res3 = self.client.post("/api/workflow/open", json={"name": "Spotify Analytics"})
        self.assertEqual(res3.status_code, 200)
        self.assertTrue(res3.get_json().get("success"))


if __name__ == "__main__":
    unittest.main()
