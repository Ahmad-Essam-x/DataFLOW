"""
Unit tests for Enhanced Data Profiling (OK / Empty / Null quality metrics, mini-histograms)
and the Interactive Chart Data Aggregation engine.
"""
import os
import sys
import unittest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.engine.executor import WorkflowExecutor
from backend.engine.cache_manager import SessionRunCacheManager
from backend.app import app


class TestProfilingAndCharts(unittest.TestCase):
    """Test suite for data profiling statistics and chart aggregations."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

        self.cache_manager = SessionRunCacheManager(max_runs=10, ttl_seconds=3600)
        self.executor = WorkflowExecutor(context={
            "data_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
            "output_dir": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "outputs"),
            "base_dir": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        }, cache_manager=self.cache_manager)

        # Mock dataset with numeric, string, empty strings, nulls, and dates
        self.test_df = pd.DataFrame({
            "ID": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "Region": ["North", "South", "North", "East", "West", "North", "South", "East", "West", "North"],
            "Sales": [100.0, 250.5, 75.0, np.nan, 300.0, 150.0, 80.0, 420.0, np.nan, 210.0],
            "Comments": ["Good", "", "Great", "   ", None, "OK", "Fine", "", "Excellent", "Fair"],
            "OrderDate": [
                "2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05",
                "2023-01-06", "2023-01-07", "2023-01-08", "2023-01-09", "2023-01-10"
            ]
        })

        self.node_id = "test_node_1"
        self.executor.data_cache[self.node_id] = {"O": self.test_df}

    def test_profiling_quality_metrics(self):
        """Test 3-segment quality bar metrics: OK, Empty, and Null counts and percentages."""
        res = self.executor.get_node_profiling(self.node_id, port="O")
        self.assertTrue(res["available"])
        self.assertEqual(res["total_rows"], 10)

        cols = {c["name"]: c for c in res["columns"]}

        # Comments has:
        # - 1 None (null_count = 1, 10%)
        # - 3 empty/whitespace: "", "   ", "" (empty_count = 3, 30%)
        # - 6 valid: Good, Great, OK, Fine, Excellent, Fair (ok_count = 6, 60%)
        comm = cols["Comments"]
        self.assertEqual(comm["null_count"], 1)
        self.assertEqual(comm["null_percent"], 10.0)
        self.assertEqual(comm["empty_count"], 3)
        self.assertEqual(comm["empty_percent"], 30.0)
        self.assertEqual(comm["ok_count"], 6)
        self.assertEqual(comm["ok_percent"], 60.0)

        # Sales has:
        # - 2 NaN (null_count = 2, 20%)
        # - 0 empty
        # - 8 ok (80%)
        sales = cols["Sales"]
        self.assertEqual(sales["null_count"], 2)
        self.assertEqual(sales["null_percent"], 20.0)
        self.assertEqual(sales["empty_count"], 0)
        self.assertEqual(sales["ok_count"], 8)
        self.assertEqual(sales["ok_percent"], 80.0)

    def test_profiling_histograms(self):
        """Test that numeric and categorical columns have histogram bins generated."""
        res = self.executor.get_node_profiling(self.node_id, port="O")
        cols = {c["name"]: c for c in res["columns"]}

        # Numeric histogram
        sales = cols["Sales"]
        self.assertIn("histogram", sales)
        hist = sales["histogram"]
        self.assertGreater(len(hist), 0)
        total_hist_count = sum(b["count"] for b in hist)
        self.assertEqual(total_hist_count, 8)  # 8 non-null values

        # Categorical distribution
        reg = cols["Region"]
        self.assertIn("histogram", reg)
        self.assertGreater(len(reg["histogram"]), 0)
        # North is most frequent (4 times)
        self.assertEqual(reg["histogram"][0]["value"], "North")
        self.assertEqual(reg["histogram"][0]["count"], 4)

    def test_chart_data_bar_count(self):
        """Test Bar Chart with record count aggregation."""
        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="bar", x_col="Region", agg_func="count"
        )
        self.assertTrue(res["available"])
        self.assertEqual(res["chart_type"], "bar")
        self.assertIn("items", res)

        labels = {item["label"]: item["value"] for item in res["items"]}
        self.assertEqual(labels["North"], 4)
        self.assertEqual(labels["South"], 2)
        self.assertEqual(labels["East"], 2)
        self.assertEqual(labels["West"], 2)

    def test_chart_data_bar_sum(self):
        """Test Bar Chart with Sum aggregation on numeric column."""
        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="bar", x_col="Region", y_col="Sales", agg_func="sum"
        )
        self.assertTrue(res["available"])
        labels = {item["label"]: item["value"] for item in res["items"]}
        # North has: 100 + 75 + 150 + 210 = 535.0
        self.assertEqual(labels["North"], 535.0)

    def test_chart_data_line(self):
        """Test Line Chart series generation with chronological ordering."""
        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="line", x_col="OrderDate", y_col="Sales", agg_func="sum"
        )
        self.assertTrue(res["available"])
        self.assertEqual(res["chart_type"], "line")
        self.assertIn("points", res)
        self.assertGreater(len(res["points"]), 5)

    def test_chart_data_scatter(self):
        """Test Scatter Plot with numeric pairs and correlation."""
        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="scatter", x_col="ID", y_col="Sales"
        )
        self.assertTrue(res["available"])
        self.assertEqual(res["chart_type"], "scatter")
        self.assertIn("points", res)
        self.assertEqual(len(res["points"]), 8)  # 8 valid pairs
        self.assertIn("correlation", res)

    def test_chart_data_histogram(self):
        """Test Histogram binning for continuous numeric column."""
        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="histogram", x_col="Sales", num_bins=5
        )
        self.assertTrue(res["available"])
        self.assertEqual(res["chart_type"], "histogram")
        self.assertIn("series", res)
        self.assertLessEqual(len(res["series"]), 5)
        self.assertEqual(res["min"], 75.0)
        self.assertEqual(res["max"], 420.0)

    def test_chart_data_donut(self):
        """Test Donut Chart categorical shares."""
        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="donut", x_col="Region"
        )
        self.assertTrue(res["available"])
        self.assertEqual(res["chart_type"], "donut")
        self.assertIn("items", res)
        self.assertEqual(len(res["items"]), 4)

    def test_rest_api_node_chart_data(self):
        """Test POST and GET on /api/node-chart-data/<node_id> endpoint."""
        # Attach test_df to app's executor data_cache for API testing
        from backend.app import executor
        executor.data_cache["api_test_node"] = {"O": self.test_df}

        # GET query
        resp_get = self.client.get("/api/node-chart-data/api_test_node?port=O&chart_type=bar&x_col=Region")
        self.assertEqual(resp_get.status_code, 200)
        data_get = resp_get.get_json()
        self.assertTrue(data_get["available"])

        # POST JSON payload
        resp_post = self.client.post("/api/node-chart-data/api_test_node", json={
            "port": "O",
            "chart_type": "donut",
            "x_col": "Region"
        })
        self.assertEqual(resp_post.status_code, 200)
        data_post = resp_post.get_json()
        self.assertTrue(data_post["available"])
        self.assertEqual(data_post["chart_type"], "donut")

    def test_node_data_has_histogram_and_quality(self):
        """Verify get_node_data returns quality and histogram metadata in columns_meta."""
        res = self.executor.get_node_data(self.node_id, port="O", page=1, page_size=10)
        self.assertTrue(res["available"])
        self.assertEqual(len(res["records"]), 10)

        cols = {c["name"]: c for c in res["columns"]}
        self.assertIn("Sales", cols)
        self.assertIn("quality", cols["Sales"])
        self.assertIn("histogram", cols["Sales"])
        self.assertGreater(len(cols["Sales"]["histogram"]), 0)

        # Categorical column also has histogram bins
        self.assertIn("Region", cols)
        self.assertIn("histogram", cols["Region"])
        self.assertGreater(len(cols["Region"]["histogram"]), 0)

    def test_chart_data_session_isolation(self):
        """Verify get_node_chart_data resolves run_id and session_id properly."""
        run_entry = self.cache_manager.create_run(run_id="isolated_run_999", session_id="sess_abc")
        run_entry.data_cache[self.node_id] = {"O": self.test_df}

        res = self.executor.get_node_chart_data(
            self.node_id, port="O", chart_type="bar", x_col="Region", run_id="isolated_run_999"
        )
        self.assertTrue(res["available"])
        self.assertEqual(res["total_rows"], 10)


if __name__ == "__main__":
    unittest.main()

