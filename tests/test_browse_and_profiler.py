"""
Tests for Browse Tool and Superior Data Profiler Engine.
Covers:
1. BrowseNode execution and passthrough semantics.
2. Dataset-level and column-level profiling metrics:
   - Automated Health Score & Letter Grade (A/B/C/D/F)
   - Quad-color quality breakdown (Valid, Whitespace, Anomalies, Missing)
   - Tukey's IQR and Z-score outlier detection
   - String hygiene and casing collisions ("Active" vs "ACTIVE")
   - Semantic pattern inference (Email, Phone, URL, UUID, IP)
   - Pairwise Pearson correlation matrix
3. Standalone Interactive HTML Quality Audit Report generation.
4. Flask API endpoints for profiling data and HTML report export.
"""
import unittest
import json
import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app
from backend.engine.nodes.io import BrowseNode
from backend.engine.profiler import compute_dataset_profile, generate_html_report
from backend.engine.executor import WorkflowExecutor


class TestBrowseAndProfiler(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = app.test_client()

    def test_browse_node_passthrough(self):
        """BrowseNode must pass input DataFrame unchanged through to its output."""
        node = BrowseNode(node_id="browse_1", config={})
        df_in = pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["Alpha", "Beta", "Gamma"],
            "amount": [10.5, 20.0, 35.75]
        })

        outputs = node.execute({"I": df_in})
        self.assertIn("O", outputs)
        df_out = outputs["O"]
        pd.testing.assert_frame_equal(df_in, df_out)

    def test_browse_node_empty_input(self):
        """BrowseNode handles empty input gracefully."""
        node = BrowseNode(node_id="browse_empty", config={})
        outputs = node.execute({})
        self.assertIn("O", outputs)
        self.assertTrue(outputs["O"].empty)

    def test_health_score_and_grade(self):
        """Test health score computation and letter grade assigning."""
        # 1. Pristine clean data -> High health score, Grade A
        clean_df = pd.DataFrame({
            "id": range(1, 101),
            "customer_email": [f"user{i}@example.com" for i in range(1, 101)],
            "revenue": np.random.uniform(10.0, 100.0, size=100)
        })
        profile_clean = compute_dataset_profile(clean_df)
        self.assertGreaterEqual(profile_clean["health_score"], 90)
        self.assertEqual(profile_clean["health_grade"], "A")

        # 2. Dirty dataset with nulls, whitespace, duplicates -> Degraded health score
        dirty_df = pd.DataFrame({
            "id": [1, 1, 2, 3, None, None, None, None, None, None],
            "status": [" Active", "Active ", "ACTIVE", "Pending  ", None, None, "", "  ", "Closed", "Closed"],
            "amount": [10.0, 10.0, 15.0, 12.0, None, 14.0, 99999.0, -99999.0, None, None]
        })
        profile_dirty = compute_dataset_profile(dirty_df)
        self.assertLess(profile_dirty["health_score"], 80)
        self.assertIn(profile_dirty["health_grade"], ["B", "C", "D", "F"])
        self.assertGreater(profile_dirty["health_penalties"]["completeness"], 0)

    def test_tukey_iqr_outlier_detection(self):
        """Test vectorized Tukey IQR outlier fence calculations."""
        # Clean normal values: 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20
        # Outliers: 500, -200
        values = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 500, -200]
        df = pd.DataFrame({"metric": values})

        profile = compute_dataset_profile(df)
        col_map = {c["name"]: c for c in profile["columns"]}
        metric_col = col_map["metric"]
        num_stats = metric_col["numeric_stats"]

        self.assertIsNotNone(num_stats)
        self.assertEqual(num_stats["outlier_count"], 2)
        self.assertGreater(num_stats["outlier_percent"], 0)
        self.assertLess(num_stats["lower_fence"], 10)
        self.assertGreater(num_stats["upper_fence"], 20)

    def test_string_hygiene_and_mixed_casing(self):
        """Test string hygiene diagnostics and mixed-case collision detection."""
        df = pd.DataFrame({
            "category": ["Retail", "retail", "RETAIL", " Wholesale ", "Wholesale\t", "Online\n"]
        })
        profile = compute_dataset_profile(df)
        col_map = {c["name"]: c for c in profile["columns"]}
        cat_col = col_map["category"]
        str_stats = cat_col["string_stats"]

        self.assertIsNotNone(str_stats)
        self.assertGreater(str_stats["leading_whitespace_count"] + str_stats["trailing_whitespace_count"], 0)
        self.assertGreater(str_stats["non_printable_count"], 0)
        self.assertTrue(str_stats["mixed_casing_detected"])

    def test_semantic_pattern_recognition(self):
        """Test automatic inference of semantic data types."""
        df = pd.DataFrame({
            "emails": ["alice@work.com", "bob@corp.org", "charlie@gmail.com", "invalid-email"],
            "ips": ["192.168.1.1", "10.0.0.1", "172.16.254.1", "256.999.0.1"],
            "uuids": ["123e4567-e89b-12d3-a456-426614174000", "e4eaaaf2-d142-11e1-b3e4-080027620cdd", "foo", "bar"],
            "zips": ["90210", "10001", "94105", "ABCDE"]
        })
        profile = compute_dataset_profile(df)
        col_map = {c["name"]: c for c in profile["columns"]}

        self.assertEqual(col_map["emails"]["semantic_type"], "Email")
        self.assertEqual(col_map["ips"]["semantic_type"], "IPv4")
        self.assertEqual(col_map["uuids"]["semantic_type"], "UUID")
        self.assertEqual(col_map["zips"]["semantic_type"], "US ZIP")

    def test_pearson_correlation_matrix(self):
        """Test calculation of correlation matrix for numeric columns."""
        x = np.linspace(1, 100, 100)
        y = 2 * x + 5  # perfectly correlated
        z = -3 * x + 10 # negatively correlated
        df = pd.DataFrame({"x": x, "y": y, "z": z, "str_col": ["a"] * 100})

        profile = compute_dataset_profile(df)
        corr = profile.get("correlations")
        self.assertIsNotNone(corr)
        self.assertIn("x", corr["columns"])
        self.assertIn("y", corr["columns"])
        self.assertIn("z", corr["columns"])
        self.assertNotIn("str_col", corr["columns"])

        # Check matrix value near 1.0 for (x, y)
        self.assertAlmostEqual(corr["matrix"]["x"]["y"], 1.0, places=2)

    def test_standalone_html_report_generation(self):
        """Test generation of the standalone interactive HTML Quality Audit Report."""
        df = pd.DataFrame({
            "Order_ID": [1001, 1002, 1003, 1004],
            "Customer_Email": ["a@corp.com", "b@corp.com", "c@corp.com", "d@corp.com"],
            "Amount": [150.0, 200.5, 99.0, 450.0]
        })
        profile = compute_dataset_profile(df)
        html = generate_html_report(profile, title="Test Audit Report")

        self.assertIsInstance(html, str)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Test Audit Report", html)
        self.assertIn(f"Grade {profile['health_grade']}", html)
        self.assertIn("Order_ID", html)
        self.assertIn("Customer_Email", html)
        self.assertIn("Amount", html)

    def test_api_node_profile_and_export_endpoints(self):
        """Test /api/node-profile/<node_id> and /api/node-profile/<node_id>/export-report."""
        # Build workflow with input_data and browse node
        wf = {
            "name": "Test Browse API Workflow",
            "nodes": [
                {
                    "id": "node_input",
                    "type": "text_input",
                    "name": "Input Data",
                    "config": {
                        "raw_text": "Name,Score\nAlice,95\nBob,82\nCharlie,99\nDavid,75",
                        "delimiter": ","
                    }
                },
                {
                    "id": "node_browse",
                    "type": "browse",
                    "name": "Browse Tool",
                    "config": {}
                }
            ],
            "connections": [
                {
                    "id": "c1",
                    "source": "node_input",
                    "sourceHandle": "O",
                    "target": "node_browse",
                    "targetHandle": "I"
                }
            ]
        }

        # 1. Run workflow via API
        run_res = self.client.post("/api/run", json=wf)
        self.assertEqual(run_res.status_code, 200)

        # 2. Get profiling JSON for node_browse
        profile_res = self.client.get("/api/node-profile/node_browse")
        self.assertEqual(profile_res.status_code, 200)
        pdata = json.loads(profile_res.data)
        self.assertTrue(pdata.get("available"))
        self.assertEqual(pdata["total_rows"], 4)
        col_names = [c["name"] for c in pdata["columns"]]
        self.assertIn("Name", col_names)
        self.assertIn("Score", col_names)
        self.assertIn("health_score", pdata)

        # 3. Export standalone HTML report
        export_res = self.client.get("/api/node-profile/node_browse/export-report")
        self.assertEqual(export_res.status_code, 200)
        self.assertIn("text/html", export_res.content_type)
        self.assertIn("attachment", export_res.headers.get("Content-Disposition", ""))
        self.assertIn("Quality Audit Report", export_res.data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
