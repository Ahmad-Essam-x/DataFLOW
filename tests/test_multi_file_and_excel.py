"""
Tests for Multi-File Wildcard Ingestion, Excel Multi-Sheet Handling,
File Metadata Appending, and /api/excel-sheets Endpoint.
"""
import os
import shutil
import tempfile
import unittest
import json
import pandas as pd

from backend.app import app
from backend.engine.nodes.io import InputDataNode
from backend.engine.nodes.base import NodeExecutionError


class TestMultiFileAndExcel(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.client = app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_wildcard_csv_stacking(self):
        """Stack multiple CSV files matching a wildcard pattern."""
        f1 = os.path.join(self.test_dir, "sales_2024_01.csv")
        f2 = os.path.join(self.test_dir, "sales_2024_02.csv")
        f3 = os.path.join(self.test_dir, "sales_2024_03.csv")

        pd.DataFrame({"OrderID": [101, 102], "Amount": [150.0, 200.0]}).to_csv(f1, index=False)
        pd.DataFrame({"OrderID": [103, 104], "Amount": [300.0, 450.0]}).to_csv(f2, index=False)
        pd.DataFrame({"OrderID": [105], "Amount": [90.0]}).to_csv(f3, index=False)

        pattern = os.path.join(self.test_dir, "sales_2024_*.csv")
        node = InputDataNode("node_wildcard", {
            "file_path": pattern
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 5)
        self.assertEqual(list(df["OrderID"]), [101, 102, 103, 104, 105])

    def test_wildcard_excel_stacking(self):
        """Stack multiple Excel files matching a wildcard pattern."""
        f1 = os.path.join(self.test_dir, "inv_warehouse_a.xlsx")
        f2 = os.path.join(self.test_dir, "inv_warehouse_b.xlsx")

        pd.DataFrame({"SKU": ["A1", "A2"], "Qty": [50, 75]}).to_excel(f1, index=False)
        pd.DataFrame({"SKU": ["B1", "B2"], "Qty": [30, 40]}).to_excel(f2, index=False)

        pattern = os.path.join(self.test_dir, "inv_warehouse_*.xlsx")
        node = InputDataNode("node_excel_wildcard", {
            "file_path": pattern,
            "file_type": "excel"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 4)
        self.assertEqual(set(df["SKU"]), {"A1", "A2", "B1", "B2"})

    def test_excel_specific_sheet_by_name(self):
        """Extract a specific Excel sheet by sheet name."""
        excel_path = os.path.join(self.test_dir, "financials.xlsx")
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            pd.DataFrame({"Metric": ["Rev"], "Val": [1000]}).to_excel(writer, sheet_name="Summary", index=False)
            pd.DataFrame({"Department": ["Eng", "Sales"], "Cost": [200, 300]}).to_excel(writer, sheet_name="Detail", index=False)

        node = InputDataNode("node_sheet_name", {
            "file_path": excel_path,
            "file_type": "excel",
            "sheet_name": "Detail"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 2)
        self.assertIn("Department", df.columns)
        self.assertIn("Cost", df.columns)
        self.assertNotIn("Metric", df.columns)

    def test_excel_specific_sheet_by_index(self):
        """Extract a specific Excel sheet by zero-based integer index."""
        excel_path = os.path.join(self.test_dir, "financials_idx.xlsx")
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            pd.DataFrame({"P1": [1]}).to_excel(writer, sheet_name="First", index=False)
            pd.DataFrame({"P2": [2, 3]}).to_excel(writer, sheet_name="Second", index=False)

        node = InputDataNode("node_sheet_idx", {
            "file_path": excel_path,
            "file_type": "excel",
            "sheet_name": 1
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 2)
        self.assertIn("P2", df.columns)

    def test_excel_read_all_sheets_union(self):
        """Union all sheets in an Excel workbook with SheetName column."""
        excel_path = os.path.join(self.test_dir, "regional_reports.xlsx")
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            pd.DataFrame({"Rep": ["Alice"], "Sales": [500]}).to_excel(writer, sheet_name="North", index=False)
            pd.DataFrame({"Rep": ["Bob", "Charlie"], "Sales": [400, 600]}).to_excel(writer, sheet_name="South", index=False)
            pd.DataFrame({"Rep": ["Dana"], "Sales": [700]}).to_excel(writer, sheet_name="West", index=False)

        node = InputDataNode("node_all_sheets", {
            "file_path": excel_path,
            "file_type": "excel",
            "read_all_sheets": True
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 4)
        self.assertIn("SheetName", df.columns)
        self.assertEqual(set(df["SheetName"].unique()), {"North", "South", "West"})

    def test_output_file_name_mode_filename_only(self):
        """Verify FileName metadata column is injected with basename."""
        f1 = os.path.join(self.test_dir, "north_data.csv")
        pd.DataFrame({"ID": [1]}).to_csv(f1, index=False)

        node = InputDataNode("node_meta_fn", {
            "file_path": f1,
            "output_file_name_mode": "filename_only"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertIn("FileName", df.columns)
        self.assertNotIn("FilePath", df.columns)
        self.assertEqual(df["FileName"].iloc[0], "north_data.csv")

    def test_output_file_name_mode_full_path(self):
        """Verify FilePath metadata column is injected with absolute path."""
        f1 = os.path.join(self.test_dir, "south_data.csv")
        pd.DataFrame({"ID": [2]}).to_csv(f1, index=False)

        node = InputDataNode("node_meta_fp", {
            "file_path": f1,
            "output_file_name_mode": "full_path"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertIn("FilePath", df.columns)
        self.assertNotIn("FileName", df.columns)
        self.assertEqual(df["FilePath"].iloc[0], os.path.abspath(f1))

    def test_output_file_name_mode_both(self):
        """Verify both FileName and FilePath are injected when mode is both."""
        f1 = os.path.join(self.test_dir, "east_data.csv")
        pd.DataFrame({"ID": [3]}).to_csv(f1, index=False)

        node = InputDataNode("node_meta_both", {
            "file_path": f1,
            "output_file_name_mode": "both"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertIn("FileName", df.columns)
        self.assertIn("FilePath", df.columns)
        self.assertEqual(df["FileName"].iloc[0], "east_data.csv")
        self.assertEqual(df["FilePath"].iloc[0], os.path.abspath(f1))

    def test_edge_case_empty_glob(self):
        """Raise NodeExecutionError when no files match the glob pattern."""
        pattern = os.path.join(self.test_dir, "no_such_files_*.csv")
        node = InputDataNode("node_empty_glob", {
            "file_path": pattern
        })
        with self.assertRaises(NodeExecutionError) as ctx:
            node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        self.assertIn("No file(s) found matching", str(ctx.exception))

    def test_edge_case_mismatched_columns(self):
        """Stack files with mismatched columns without error, filling NaNs."""
        f1 = os.path.join(self.test_dir, "schema1.csv")
        f2 = os.path.join(self.test_dir, "schema2.csv")

        pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}).to_csv(f1, index=False)
        pd.DataFrame({"A": [3], "C": [99.5]}).to_csv(f2, index=False)

        node = InputDataNode("node_schema_mismatch", {
            "file_path": os.path.join(self.test_dir, "schema*.csv")
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 3)
        self.assertEqual(set(df.columns), {"A", "B", "C"})
        self.assertTrue(pd.isna(df.loc[df["A"] == 3, "B"].iloc[0]))
        self.assertTrue(pd.isna(df.loc[df["A"] == 1, "C"].iloc[0]))

    def test_edge_case_nonexistent_sheet(self):
        """Raise NodeExecutionError when requested sheet does not exist."""
        excel_path = os.path.join(self.test_dir, "single_sheet.xlsx")
        pd.DataFrame({"X": [10]}).to_excel(excel_path, sheet_name="RealSheet", index=False)

        node = InputDataNode("node_bad_sheet", {
            "file_path": excel_path,
            "file_type": "excel",
            "sheet_name": "GhostSheet"
        })
        with self.assertRaises(NodeExecutionError) as ctx:
            node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        self.assertIn("Sheet 'GhostSheet' not found", str(ctx.exception))

    def test_api_excel_sheets_endpoint(self):
        """Verify GET /api/excel-sheets returns sheet list quickly without loading dataset."""
        from backend.app import DATA_DIR
        excel_path = os.path.join(DATA_DIR, "test_api_workbook.xlsx")
        try:
            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="Overview", index=False)
                pd.DataFrame({"y": [2]}).to_excel(writer, sheet_name="Transactions", index=False)
                pd.DataFrame({"z": [3]}).to_excel(writer, sheet_name="Audit", index=False)

            res = self.client.get("/api/excel-sheets?file=test_api_workbook.xlsx")
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("sheets"), ["Overview", "Transactions", "Audit"])
        finally:
            if os.path.exists(excel_path):
                try:
                    os.remove(excel_path)
                except Exception:
                    pass

    def test_api_excel_sheets_security(self):
        """Ensure /api/excel-sheets rejects path traversal outside workspace."""
        traversal = "../../secret/passwords.xlsx"
        res = self.client.get(f"/api/excel-sheets?file={traversal}")
        self.assertIn(res.status_code, [400, 403, 404])


if __name__ == "__main__":
    unittest.main()
