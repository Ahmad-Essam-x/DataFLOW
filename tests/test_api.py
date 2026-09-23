"""
Integration tests for Flask REST API endpoints.
"""
import json
import unittest
from backend.app import app


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_tools(self):
        res = self.client.get("/api/tools")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("tools", data)
        self.assertGreater(len(data["tools"]), 5)

    def test_get_samples(self):
        res = self.client.get("/api/samples")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("datasets", data)
        self.assertIn("workflows", data)
        self.assertGreaterEqual(len(data["workflows"]), 2)

    def test_browse_directory(self):
        res = self.client.get("/api/browse")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("current_path", data)
        self.assertIn("folders", data)
        self.assertIn("files", data)

    def test_sample_workflow_and_run(self):
        # 1. Fetch sample workflow
        wf_res = self.client.get("/api/sample-workflow/sales_customer_enrichment.json")
        self.assertEqual(wf_res.status_code, 200)
        wf_data = wf_res.get_json()
        self.assertEqual(wf_data["name"], "Customer Sales Analysis")

        # 2. Run workflow
        run_res = self.client.post("/api/run", json=wf_data)
        self.assertEqual(run_res.status_code, 200)
        run_data = run_res.get_json()
        self.assertTrue(run_data["success"])
        self.assertIn("node_sort_1", run_data["node_results"])

        # 3. Fetch node data
        data_res = self.client.get("/api/node-data/node_sort_1?port=O&page=1&page_size=5")
        self.assertEqual(data_res.status_code, 200)
        records_data = data_res.get_json()
        self.assertTrue(records_data["available"])
        self.assertEqual(len(records_data["records"]), 5)

        # 4. Fetch node profile
        prof_res = self.client.get("/api/node-profile/node_sort_1?port=O")
        self.assertEqual(prof_res.status_code, 200)
        prof_data = prof_res.get_json()
        self.assertTrue(prof_data["available"])
        self.assertGreaterEqual(len(prof_data["columns"]), 2)

        # 5. Test export
        exp_res = self.client.get("/api/export/node_sort_1?port=O&format=csv")
        self.assertEqual(exp_res.status_code, 200)
        self.assertEqual(exp_res.mimetype, "text/csv")

    def test_api_run_error_diagnostic(self):
        wf = {
            "nodes": [
                {
                    "id": "node_in",
                    "type": "input_data",
                    "name": "Input Orders",
                    "config": {"file_path": "dirty_data.csv"}
                },
                {
                    "id": "node_form",
                    "type": "formula",
                    "name": "Bad Formula",
                    "config": {
                        "formulas": [
                            {"output_field": "calc", "expression": "[NonExistentCol] * 2"}
                        ]
                    }
                }
            ],
            "connections": [
                {"source": "node_in", "sourceHandle": "O", "target": "node_form", "targetHandle": "I"}
            ]
        }
        res = self.client.post("/api/run", json=wf)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("diagnostic", data)
        self.assertEqual(data["diagnostic"]["error_code"], "COLUMN_NOT_FOUND")
        self.assertEqual(data["diagnostic"]["node_id"], "node_form")
        self.assertIn("NonExistentCol", data["diagnostic"]["title"])

    def test_api_run_stream(self):
        wf_res = self.client.get("/api/sample-workflow/sales_customer_enrichment.json")
        wf_data = wf_res.get_json()

        res = self.client.post("/api/run-stream", json=wf_data)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.mimetype)

        raw_stream = res.get_data(as_text=True)
        self.assertIn("node_started", raw_stream)
        self.assertIn("node_completed", raw_stream)
        self.assertIn("workflow_completed", raw_stream)


if __name__ == "__main__":
    unittest.main()
