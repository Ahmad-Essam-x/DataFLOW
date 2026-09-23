"""
Unit and integration tests for:
1. Workflow Save & Open API lifecycle (/api/save-workflow, /api/workflow/<filename>, /api/samples)
2. OutputDataNode execution (CSV, TSV, Excel, JSON, delimiters, append mode, dynamic partitioning)
3. Direct output file downloads (/data/outputs/<filename>) and parameterized exports (/api/export/<node_id>)
"""
import os
import json
import unittest
import pandas as pd
from backend.app import app, WORKFLOWS_DIR, OUTPUT_DIR, DATA_DIR
from backend.engine.executor import WorkflowExecutor
from backend.engine.nodes.io import OutputDataNode, InputDataNode


class TestSaveOpenOutput(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.executor = WorkflowExecutor(context={
            "data_dir": DATA_DIR,
            "output_dir": OUTPUT_DIR,
            "base_dir": os.path.dirname(DATA_DIR)
        })

    def test_save_and_open_workflow_api(self):
        # 1. Save workflow
        wf_payload = {
            "name": "Automated Test Workflow",
            "nodes": [
                {
                    "id": "node_test_input",
                    "type": "input_data",
                    "name": "Input Orders",
                    "x": 100,
                    "y": 100,
                    "config": {
                        "file_path": "orders.csv",
                        "file_type": "csv",
                        "has_header": True
                    }
                },
                {
                    "id": "node_test_output",
                    "type": "output_data",
                    "name": "Output Results",
                    "x": 300,
                    "y": 100,
                    "config": {
                        "filename": "test_saved_output",
                        "format": "csv"
                    }
                }
            ],
            "connections": [
                {
                    "id": "conn_1",
                    "source": "node_test_input",
                    "sourceHandle": "O",
                    "target": "node_test_output",
                    "targetHandle": "I"
                }
            ]
        }

        save_res = self.client.post("/api/save-workflow", json=wf_payload)
        self.assertEqual(save_res.status_code, 200)
        save_data = save_res.get_json()
        self.assertTrue(save_data["success"])
        self.assertEqual(save_data["file"], "automated_test_workflow.json")

        # 2. Check workflow appears in /api/samples
        samples_res = self.client.get("/api/samples")
        self.assertEqual(samples_res.status_code, 200)
        samples_data = samples_res.get_json()
        found = any(w["file"] == "automated_test_workflow.json" for w in samples_data["workflows"])
        self.assertTrue(found, "Saved workflow must appear in samples/saved workflows list")

        # 3. Retrieve saved workflow via /api/workflow/<filename>
        get_res = self.client.get("/api/workflow/automated_test_workflow.json")
        self.assertEqual(get_res.status_code, 200)
        loaded_wf = get_res.get_json()
        self.assertEqual(loaded_wf["name"], "Automated Test Workflow")
        self.assertEqual(len(loaded_wf["nodes"]), 2)
        self.assertEqual(len(loaded_wf["connections"]), 1)

        # 4. Clean up test workflow file
        test_file = os.path.join(WORKFLOWS_DIR, "automated_test_workflow.json")
        if os.path.exists(test_file):
            os.remove(test_file)

    def test_output_data_csv_formats_and_delimiters(self):
        sample_df = pd.DataFrame({
            "region": ["North", "South", "East", "West"],
            "amount": [100.5, 200.0, 150.75, 300.2]
        })

        # Test CSV standard comma
        node_csv = OutputDataNode("out_csv", {
            "filename": "unit_test_out_comma",
            "format": "csv",
            "delimiter": ","
        })
        res_csv = node_csv.execute({"I": sample_df}, context={"output_dir": OUTPUT_DIR})
        out_csv_path = os.path.join(OUTPUT_DIR, "unit_test_out_comma.csv")
        self.assertTrue(os.path.exists(out_csv_path))
        self.assertTrue(any(f["path"] == out_csv_path for f in node_csv.written_files))
        readback_csv = pd.read_csv(out_csv_path)
        self.assertEqual(len(readback_csv), 4)
        self.assertListEqual(list(readback_csv.columns), ["region", "amount"])

        # Test TSV / Tab-delimited
        node_tsv = OutputDataNode("out_tsv", {
            "filename": "unit_test_out_tab",
            "format": "tsv"
        })
        res_tsv = node_tsv.execute({"I": sample_df}, context={"output_dir": OUTPUT_DIR})
        out_tsv_path = os.path.join(OUTPUT_DIR, "unit_test_out_tab.tsv")
        self.assertTrue(os.path.exists(out_tsv_path))
        readback_tsv = pd.read_csv(out_tsv_path, sep="\t")
        self.assertEqual(len(readback_tsv), 4)

        # Test Semicolon delimiter
        node_semi = OutputDataNode("out_semi", {
            "filename": "unit_test_out_semi",
            "format": "csv",
            "delimiter": ";"
        })
        res_semi = node_semi.execute({"I": sample_df}, context={"output_dir": OUTPUT_DIR})
        out_semi_path = os.path.join(OUTPUT_DIR, "unit_test_out_semi.csv")
        self.assertTrue(os.path.exists(out_semi_path))
        readback_semi = pd.read_csv(out_semi_path, sep=";")
        self.assertEqual(len(readback_semi), 4)

        # Test JSON format
        node_json = OutputDataNode("out_json", {
            "filename": "unit_test_out_json",
            "format": "json"
        })
        res_json = node_json.execute({"I": sample_df}, context={"output_dir": OUTPUT_DIR})
        out_json_path = os.path.join(OUTPUT_DIR, "unit_test_out_json.json")
        self.assertTrue(os.path.exists(out_json_path))
        readback_json = pd.read_json(out_json_path)
        self.assertEqual(len(readback_json), 4)

        # Test Excel format
        node_excel = OutputDataNode("out_excel", {
            "filename": "unit_test_out_excel",
            "format": "excel"
        })
        res_excel = node_excel.execute({"I": sample_df}, context={"output_dir": OUTPUT_DIR})
        out_excel_path = os.path.join(OUTPUT_DIR, "unit_test_out_excel.xlsx")
        self.assertTrue(os.path.exists(out_excel_path))
        readback_excel = pd.read_excel(out_excel_path)
        self.assertEqual(len(readback_excel), 4)

        # Clean up files
        for p in [out_csv_path, out_tsv_path, out_semi_path, out_json_path, out_excel_path]:
            if os.path.exists(p):
                os.remove(p)

    def test_output_data_append_mode(self):
        sample_part1 = pd.DataFrame({"id": [1, 2], "name": ["Alpha", "Beta"]})
        sample_part2 = pd.DataFrame({"id": [3, 4], "name": ["Gamma", "Delta"]})

        node = OutputDataNode("out_append", {
            "filename": "unit_test_append",
            "format": "csv",
            "write_mode": "overwrite"
        })
        node.execute({"I": sample_part1}, context={"output_dir": OUTPUT_DIR})

        out_path = os.path.join(OUTPUT_DIR, "unit_test_append.csv")
        self.assertTrue(os.path.exists(out_path))
        self.assertEqual(len(pd.read_csv(out_path)), 2)

        # Now append
        node_append = OutputDataNode("out_append_2", {
            "filename": "unit_test_append",
            "format": "csv",
            "write_mode": "append"
        })
        node_append.execute({"I": sample_part2}, context={"output_dir": OUTPUT_DIR})

        df_combined = pd.read_csv(out_path)
        self.assertEqual(len(df_combined), 4)
        self.assertListEqual(df_combined["name"].tolist(), ["Alpha", "Beta", "Gamma", "Delta"])

        if os.path.exists(out_path):
            os.remove(out_path)

    def test_output_data_dynamic_filename_partition(self):
        # Test partitioning data rows by a column
        df = pd.DataFrame({
            "region": ["North", "South", "North", "East"],
            "val": [10, 20, 30, 40]
        })

        node = OutputDataNode("out_dyn", {
            "filename": "base_sales",
            "format": "csv",
            "take_filename_from_field": True,
            "filename_field": "region",
            "filename_action": "append_suffix"
        })
        res = node.execute({"I": df}, context={"output_dir": OUTPUT_DIR})

        p_north = os.path.join(OUTPUT_DIR, "base_sales_North.csv")
        p_south = os.path.join(OUTPUT_DIR, "base_sales_South.csv")
        p_east = os.path.join(OUTPUT_DIR, "base_sales_East.csv")

        self.assertTrue(os.path.exists(p_north))
        self.assertTrue(os.path.exists(p_south))
        self.assertTrue(os.path.exists(p_east))

        self.assertEqual(len(pd.read_csv(p_north)), 2)
        self.assertEqual(len(pd.read_csv(p_south)), 1)
        self.assertEqual(len(pd.read_csv(p_east)), 1)

        for p in [p_north, p_south, p_east]:
            if os.path.exists(p):
                os.remove(p)

    def test_data_outputs_download_endpoint(self):
        # Create a test file in OUTPUT_DIR
        test_file_path = os.path.join(OUTPUT_DIR, "sample_direct_dl.csv")
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write("a,b\n1,2\n")

        res = self.client.get("/data/outputs/sample_direct_dl.csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"a,b", res.data)
        res.close()

        if os.path.exists(test_file_path):
            os.remove(test_file_path)

    def test_export_endpoint_options(self):
        # Run workflow to populate executor cache
        wf_res = self.client.get("/api/sample-workflow/sales_customer_enrichment.json")
        wf_data = wf_res.get_json()
        self.client.post("/api/run", json=wf_data)

        # Test export CSV with custom filename and delimiter
        exp_csv = self.client.get("/api/export/node_sort_1?port=O&format=csv&filename=my_custom_export&delimiter=;")
        self.assertEqual(exp_csv.status_code, 200)
        self.assertIn("my_custom_export.csv", exp_csv.headers.get("Content-Disposition", ""))
        self.assertIn(b";", exp_csv.data)

        # Test export Excel
        exp_xlsx = self.client.get("/api/export/node_sort_1?port=O&format=excel&filename=my_excel_report")
        self.assertEqual(exp_xlsx.status_code, 200)
        self.assertIn("my_excel_report.xlsx", exp_xlsx.headers.get("Content-Disposition", ""))

        # Test export TSV
        exp_tsv = self.client.get("/api/export/node_sort_1?port=O&format=tsv")
        self.assertEqual(exp_tsv.status_code, 200)
        self.assertIn(b"\t", exp_tsv.data)

        # Test export JSON
        exp_json = self.client.get("/api/export/node_sort_1?port=O&format=json")
        self.assertEqual(exp_json.status_code, 200)
        parsed = json.loads(exp_json.data.decode("utf-8"))
        self.assertIsInstance(parsed, list)
        self.assertGreater(len(parsed), 0)


if __name__ == "__main__":
    unittest.main()
