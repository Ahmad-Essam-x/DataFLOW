"""
Comprehensive unit and integration tests for DataFLOW Unified I/O Architecture.
Tests format registry, Parquet/JSON/TSV uploads, search-filtered exports, and robust ingestion.
"""
import os
import io
import json
import shutil
import tempfile
import unittest
import pandas as pd

from backend.app import app
import backend.extensions as ext
from backend.engine.io_formats import (
    detect_format,
    read_tabular_file,
    filter_dataframe_by_search,
    export_dataframe_to_stream,
    SUPPORTED_FORMATS
)
from backend.engine.nodes.io import InputDataNode, OutputDataNode, TextInputNode


class TestIOArchitecture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.client = app.test_client()
        app.config["TESTING"] = True

        # Point extensions to temporary directories for testing
        self._orig_data_dir = ext.DATA_DIR
        self._orig_output_dir = ext.OUTPUT_DIR
        self._orig_base_dir = ext.BASE_DIR
        ext.DATA_DIR = self.data_dir
        ext.OUTPUT_DIR = self.output_dir
        ext.BASE_DIR = self.temp_dir

    def tearDown(self):
        ext.DATA_DIR = self._orig_data_dir
        ext.OUTPUT_DIR = self._orig_output_dir
        ext.BASE_DIR = self._orig_base_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. Format Detection & Helper Tests
    # ------------------------------------------------------------------
    def test_detect_format(self):
        self.assertEqual(detect_format("sales.csv"), "csv")
        self.assertEqual(detect_format("data.tsv"), "tsv")
        self.assertEqual(detect_format("export.tab"), "tsv")
        self.assertEqual(detect_format("book.xlsx"), "excel")
        self.assertEqual(detect_format("legacy.xls"), "excel")
        self.assertEqual(detect_format("stream.parquet"), "parquet")
        self.assertEqual(detect_format("archive.pq"), "parquet")
        self.assertEqual(detect_format("records.json"), "json")
        self.assertEqual(detect_format("logs.jsonl"), "json")
        self.assertEqual(detect_format("unknown.xyz"), "csv")

    def test_filter_dataframe_by_search(self):
        df = pd.DataFrame({
            "Name": ["Alice Smith", "Bob Jones", "Charlie Brown"],
            "City": ["Boston", "New York", "Chicago"],
            "Score": [95, 82, 90]
        })
        # Match string in Name
        f_name = filter_dataframe_by_search(df, "alice")
        self.assertEqual(len(f_name), 1)
        self.assertEqual(f_name.iloc[0]["Name"], "Alice Smith")

        # Match string in City
        f_city = filter_dataframe_by_search(df, "york")
        self.assertEqual(len(f_city), 1)
        self.assertEqual(f_city.iloc[0]["City"], "New York")

        # Match numeric value
        f_num = filter_dataframe_by_search(df, "82")
        self.assertEqual(len(f_num), 1)
        self.assertEqual(f_num.iloc[0]["Name"], "Bob Jones")

        # No match
        f_none = filter_dataframe_by_search(df, "nonexistent")
        self.assertEqual(len(f_none), 0)

        # Empty search returns original
        f_empty = filter_dataframe_by_search(df, "")
        self.assertEqual(len(f_empty), 3)

    # ------------------------------------------------------------------
    # 2. Ingestion of Parquet (.pq) & JSON Lines (.jsonl)
    # ------------------------------------------------------------------
    def test_input_data_parquet_pq_extension(self):
        pq_path = os.path.join(self.data_dir, "dataset.pq")
        df_src = pd.DataFrame({"Item": ["Gadget", "Widget"], "Price": [19.99, 29.99]})
        df_src.to_parquet(pq_path, index=False)

        node = InputDataNode("in_pq", {"file_path": pq_path})
        res = node.execute({}, context={"data_dir": self.data_dir, "base_dir": self.temp_dir})
        df_out = res["O"]
        self.assertEqual(len(df_out), 2)
        self.assertListEqual(list(df_out.columns), ["Item", "Price"])

    def test_input_data_json_lines(self):
        jsonl_path = os.path.join(self.data_dir, "stream.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write('{"id": 1, "status": "active"}\n{"id": 2, "status": "pending"}\n')

        node = InputDataNode("in_jsonl", {"file_path": jsonl_path})
        res = node.execute({}, context={"data_dir": self.data_dir, "base_dir": self.temp_dir})
        df_out = res["O"]
        self.assertEqual(len(df_out), 2)
        self.assertIn("status", df_out.columns)

    def test_input_data_tsv_auto_delimiter(self):
        tsv_path = os.path.join(self.data_dir, "tab_data.tsv")
        with open(tsv_path, "w", encoding="utf-8") as f:
            f.write("ColA\tColB\nVal1\tVal2\nVal3\tVal4\n")

        # Even if delimiter is left as default comma, it should auto-detect tab for .tsv
        node = InputDataNode("in_tsv", {"file_path": tsv_path, "delimiter": ","})
        res = node.execute({}, context={"data_dir": self.data_dir, "base_dir": self.temp_dir})
        df_out = res["O"]
        self.assertEqual(len(df_out), 2)
        self.assertEqual(len(df_out.columns), 2)
        self.assertListEqual(list(df_out.columns), ["ColA", "ColB"])

    # ------------------------------------------------------------------
    # 3. Upload Endpoint: Parquet, JSON, TSV
    # ------------------------------------------------------------------
    def test_upload_parquet_file(self):
        df = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)

        data = {"file": (buf, "test_upload.parquet")}
        res = self.client.post("/api/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        json_resp = res.get_json()
        self.assertTrue(json_resp["success"])
        self.assertEqual(json_resp["file_type"], "parquet")
        self.assertEqual(json_resp["row_count"], 3)
        self.assertIn("A", json_resp["columns"])

    def test_upload_json_file(self):
        json_content = json.dumps([{"id": 101, "name": "Alpha"}, {"id": 102, "name": "Beta"}])
        buf = io.BytesIO(json_content.encode("utf-8"))

        data = {"file": (buf, "sample_records.json")}
        res = self.client.post("/api/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        json_resp = res.get_json()
        self.assertTrue(json_resp["success"])
        self.assertEqual(json_resp["file_type"], "json")
        self.assertEqual(json_resp["row_count"], 2)
        self.assertIn("name", json_resp["columns"])

    # ------------------------------------------------------------------
    # 4. Export Endpoint: Parquet & Search Filtering
    # ------------------------------------------------------------------
    def test_export_node_data_parquet(self):
        test_df = pd.DataFrame({"Metric": ["CPU", "RAM"], "Value": [45.2, 78.9]})
        ext.executor.data_cache["test_node_export"] = {"O": test_df}

        res = self.client.get("/api/export/test_node_export?port=O&format=parquet&filename=metrics")
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/octet-stream", res.content_type)
        self.assertIn("metrics.parquet", res.headers.get("Content-Disposition", ""))

        # Verify stream is valid parquet
        stream_bytes = io.BytesIO(res.data)
        read_back_df = pd.read_parquet(stream_bytes)
        self.assertEqual(len(read_back_df), 2)
        self.assertListEqual(list(read_back_df.columns), ["Metric", "Value"])

    def test_export_node_data_with_search_filter(self):
        test_df = pd.DataFrame({
            "Region": ["North", "South", "North", "West"],
            "Revenue": [1000, 2000, 1500, 800]
        })
        ext.executor.data_cache["test_node_search"] = {"O": test_df}

        # Search for "North"
        res = self.client.get("/api/export/test_node_search?port=O&format=csv&search=North&filename=north_data")
        self.assertEqual(res.status_code, 200)
        csv_text = res.data.decode("utf-8")
        lines = [line.strip() for line in csv_text.splitlines() if line.strip()]
        self.assertEqual(len(lines), 3)  # Header + 2 rows
        self.assertIn("North", lines[1])
        self.assertIn("North", lines[2])
        self.assertNotIn("South", csv_text)

    def test_export_node_data_not_cached_returns_404_json(self):
        res = self.client.get("/api/export/unexecuted_node?port=O&format=csv")
        self.assertEqual(res.status_code, 404)
        json_resp = res.get_json()
        self.assertIn("error", json_resp)
        self.assertIn("No cached data found", json_resp["error"])

    # ------------------------------------------------------------------
    # 5. File Schema Endpoint Parity
    # ------------------------------------------------------------------
    def test_file_schema_parquet_and_json(self):
        pq_path = os.path.join(self.data_dir, "schema_test.parquet")
        pd.DataFrame({"X": [1], "Y": [2.5], "Z": ["text"]}).to_parquet(pq_path, index=False)

        res = self.client.get(f"/api/file-schema?file=schema_test.parquet")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["columns"], ["X", "Y", "Z"])


if __name__ == "__main__":
    unittest.main()
