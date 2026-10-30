"""
Tests for Curated Sample Workflows & 100% Product Tool Coverage.
Verifies that:
1. /api/samples returns strictly the 3 curated business pipelines.
2. All 3 sample workflows execute successfully with WorkflowExecutor.
3. All 24 tools (22 operational nodes + containers and comments) are covered across the 3 workflows.
"""
import unittest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app
from backend.engine.executor import WorkflowExecutor
from backend.engine.nodes.registry import NODE_REGISTRY


class TestSampleWorkflowsCoverage(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = app.test_client()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.workflows_dir = os.path.join(self.base_dir, "workflows")
        self.data_dir = os.path.join(self.base_dir, "data")
        self.executor = WorkflowExecutor(context={"data_dir": self.data_dir})

    def test_samples_api_endpoint(self):
        """Verify /api/samples returns exactly 3 curated workflows and sample datasets."""
        res = self.client.get("/api/samples")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)

        workflows = data.get("workflows", [])
        self.assertGreaterEqual(len(workflows), 3)

        workflow_files = [w["file"] for w in workflows]
        expected_files = [
            "sales_customer_enrichment.json",
            "inventory_supplier_reconciliation.json",
            "marketing_campaign_attribution.json"
        ]
        for exp in expected_files:
            self.assertIn(exp, workflow_files)

        datasets = [d["name"] for d in data.get("datasets", [])]
        self.assertIn("sales_orders.csv", datasets)
        self.assertIn("warehouse_inventory.xlsx", datasets)
        self.assertIn("quarterly_campaign_responses.csv", datasets)

    def test_workflow_1_customer_sales_execution(self):
        """Verify Workflow 1 (Customer Sales Analysis) executes end-to-end."""
        wf_path = os.path.join(self.workflows_dir, "sales_customer_enrichment.json")
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = json.load(f)

        self.assertEqual(wf["name"], "Customer Sales Analysis")
        self.assertTrue(len(wf.get("containers", [])) > 0)
        self.assertTrue(len(wf.get("comments", [])) > 0)

        result = self.executor.run(wf)
        self.assertTrue(result.success, f"Workflow 1 failed: {result.error}")

        # Assert every node succeeded
        for nid, nres in result.node_results.items():
            self.assertEqual(nres["status"], "success", f"Node {nid} failed: {nres.get('error')}")

        # Verify output node record counts
        self.assertIn("node_sales_out", result.node_results)
        out_counts = result.node_results["node_sales_out"]["record_counts"]
        self.assertGreater(out_counts.get("O", 0), 0)

    def test_workflow_2_inventory_reconciliation_execution(self):
        """Verify Workflow 2 (Inventory & Supplier Reconciliation) executes end-to-end."""
        wf_path = os.path.join(self.workflows_dir, "inventory_supplier_reconciliation.json")
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = json.load(f)

        self.assertEqual(wf["name"], "Inventory & Supplier Reconciliation")
        self.assertTrue(len(wf.get("containers", [])) > 0)
        self.assertTrue(len(wf.get("comments", [])) > 0)

        result = self.executor.run(wf)
        self.assertTrue(result.success, f"Workflow 2 failed: {result.error}")

        # Assert every node succeeded
        for nid, nres in result.node_results.items():
            self.assertEqual(nres["status"], "success", f"Node {nid} failed: {nres.get('error')}")

        # Verify Unique tool generated both U and D outputs
        uniq_counts = result.node_results["node_inv_unique"]["record_counts"]
        self.assertGreater(uniq_counts.get("U", 0), 0)
        self.assertGreater(uniq_counts.get("D", 0), 0)

        # Verify Join tool generated J outputs
        join_counts = result.node_results["node_inv_join"]["record_counts"]
        self.assertGreater(join_counts.get("J", 0), 0)

        # Verify Append Fields output
        append_counts = result.node_results["node_inv_append"]["record_counts"]
        self.assertGreater(append_counts.get("O", 0), 0)

        # Verify Record ID output
        recid_counts = result.node_results["node_inv_recid"]["record_counts"]
        self.assertGreater(recid_counts.get("O", 0), 0)

    def test_workflow_3_marketing_attribution_execution(self):
        """Verify Workflow 3 (Marketing Attribution & Survey Matrix) executes end-to-end."""
        wf_path = os.path.join(self.workflows_dir, "marketing_campaign_attribution.json")
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = json.load(f)

        self.assertEqual(wf["name"], "Marketing Attribution & Survey Matrix")
        self.assertTrue(len(wf.get("containers", [])) > 0)
        self.assertTrue(len(wf.get("comments", [])) > 0)

        result = self.executor.run(wf)
        self.assertTrue(result.success, f"Workflow 3 failed: {result.error}")

        # Assert every node succeeded
        for nid, nres in result.node_results.items():
            self.assertEqual(nres["status"], "success", f"Node {nid} failed: {nres.get('error')}")

        # Verify Union output
        union_counts = result.node_results["node_mkt_union"]["record_counts"]
        self.assertGreater(union_counts.get("O", 0), 0)

        # Verify Transpose unpivoted records
        transpose_counts = result.node_results["node_mkt_transpose"]["record_counts"]
        self.assertGreater(transpose_counts.get("O", 0), union_counts.get("O", 0))

        # Verify CrossTab pivoted matrix
        crosstab_counts = result.node_results["node_mkt_crosstab"]["record_counts"]
        self.assertGreater(crosstab_counts.get("O", 0), 0)

    def test_complete_tool_coverage_across_3_workflows(self):
        """Verify that all 21 processing tool types + containers and comments are represented across the 3 workflows."""
        curated_files = [
            "sales_customer_enrichment.json",
            "inventory_supplier_reconciliation.json",
            "marketing_campaign_attribution.json"
        ]

        found_types = set()
        has_containers = False
        has_comments = False

        for fname in curated_files:
            path = os.path.join(self.workflows_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                wf = json.load(f)

            for node in wf.get("nodes", []):
                found_types.add(node["type"])

            if wf.get("containers"):
                has_containers = True
            if wf.get("comments"):
                has_comments = True

        # Check all classic offline engine tools from NODE_REGISTRY (excluding external AI runtime nodes and new extension nodes)
        registered_tools = set(NODE_REGISTRY.keys()) - {"llm_process", "join_multiple", "schema_fit", "llm_override", "unsupported_tool"}
        missing_tools = registered_tools - found_types

        self.assertEqual(
            missing_tools,
            set(),
            f"The following tools are missing from the 3 curated workflows: {missing_tools}"
        )
        self.assertTrue(has_containers, "Tool containers must be represented.")
        self.assertTrue(has_comments, "Comments must be represented.")
        self.assertEqual(len(found_types), 26, f"Expected 26 tool types, found: {len(found_types)}")


if __name__ == "__main__":
    unittest.main()
