"""
Tests for Superior Excel (.xlsx and .xlsm) Ingestion Engine.
Verifies:
- Calamine acceleration and OpenPyXL fallbacks.
- Native .xlsm macro-enabled workbook ingestion.
- Resilient sheet name matching (case tolerance, whitespace tolerance, default fallback).
- Instant row counting without reading the entire sheet into a full DataFrame twice.
- Graceful recovery when plain-text/CSV files are named with .xlsx extension.
- Upload endpoint and security extension validation.
"""
import os
import io
import shutil
import tempfile
import unittest
import pandas as pd
import openpyxl

from backend.app import app
from backend.engine.nodes.io import InputDataNode
from backend.engine.nodes.base import NodeExecutionError
from backend.engine.security import validate_upload_file
from backend.engine.excel_reader import (
    fast_read_excel,
    get_excel_sheet_names,
    resolve_sheet_name,
    get_excel_row_count,
    is_excel_file,
    HAS_CALAMINE
)


class TestSuperiorExcelIngest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.client = app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_calamine_availability(self):
        """Verify that python-calamine is detected and available."""
        self.assertTrue(HAS_CALAMINE, "python-calamine engine should be installed and active.")

    def test_xlsm_macro_enabled_workbook_ingestion(self):
        """Verify that .xlsm files are properly recognized and parsed."""
        xlsm_path = os.path.join(self.test_dir, "macro_workbook.xlsm")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "MacroData"
        ws.append(["TransactionID", "Amount", "Status"])
        ws.append([1001, 249.99, "Completed"])
        ws.append([1002, 89.50, "Pending"])
        wb.save(xlsm_path)
        wb.close()

        self.assertTrue(is_excel_file(xlsm_path))

        # Test node execution
        node = InputDataNode("node_xlsm", {
            "file_path": xlsm_path,
            "sheet_name": "MacroData"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]

        self.assertEqual(len(df), 2)
        self.assertEqual(list(df.columns), ["TransactionID", "Amount", "Status"])
        self.assertEqual(df["TransactionID"].iloc[0], 1001)

    def test_resilient_sheet_matching_whitespace_and_case(self):
        """Verify tolerance to leading/trailing whitespace and case discrepancies."""
        wb_path = os.path.join(self.test_dir, "space_sheet.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = " Quarterly Sales "  # Intentionally has leading and trailing spaces
        ws.append(["Qtr", "Revenue"])
        ws.append(["Q1", 50000])
        ws.append(["Q2", 75000])
        wb.save(wb_path)
        wb.close()

        sheets = get_excel_sheet_names(wb_path)
        self.assertIn(" Quarterly Sales ", sheets)

        # 1. User config has trimmed sheet name: "Quarterly Sales"
        sheet_key, err = resolve_sheet_name("Quarterly Sales", sheets)
        self.assertIsNone(err)
        self.assertEqual(sheet_key, " Quarterly Sales ")

        # 2. User config has lower-case trimmed sheet name: "quarterly sales"
        sheet_key_lower, err_lower = resolve_sheet_name("quarterly sales", sheets)
        self.assertIsNone(err_lower)
        self.assertEqual(sheet_key_lower, " Quarterly Sales ")

        # Test node execution with "quarterly sales"
        node = InputDataNode("node_fuzzy_sheet", {
            "file_path": wb_path,
            "sheet_name": "quarterly sales"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        df = res["O"]
        self.assertEqual(len(df), 2)
        self.assertEqual(df["Revenue"].iloc[1], 75000)

    def test_default_sheet_fallbacks(self):
        """Verify that 0, '0', '', None, and 'First Sheet (Default)' resolve cleanly."""
        wb_path = os.path.join(self.test_dir, "default_test.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "PrimaryData"
        ws.append(["ColA", "ColB"])
        ws.append([10, 20])
        wb.save(wb_path)
        wb.close()

        sheets = get_excel_sheet_names(wb_path)
        fallback_tokens = [0, "0", "", None, "default", "none", "First Sheet (Default)"]
        for token in fallback_tokens:
            resolved, err = resolve_sheet_name(token, sheets)
            self.assertIsNone(err, f"Token {token!r} caused error: {err}")
            self.assertEqual(resolved, "PrimaryData")

    def test_nonexistent_sheet_error_message(self):
        """Verify that when a sheet does not exist, an informative error listing available sheets is returned."""
        wb_path = os.path.join(self.test_dir, "missing_sheet.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SheetA"
        ws.append(["A"])
        ws.append([1])
        wb.create_sheet("SheetB")
        wb.save(wb_path)
        wb.close()

        sheets = get_excel_sheet_names(wb_path)
        _, err = resolve_sheet_name("SheetZ", sheets)
        self.assertIsNotNone(err)
        self.assertIn("SheetZ", err)
        self.assertIn("SheetA", err)
        self.assertIn("SheetB", err)

        # Node execution should raise NodeExecutionError with informative text
        node = InputDataNode("node_missing", {
            "file_path": wb_path,
            "sheet_name": "NonExistent"
        })
        with self.assertRaises(NodeExecutionError) as ctx:
            node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        self.assertIn("NonExistent", str(ctx.exception))
        self.assertIn("Available sheets", str(ctx.exception))

    def test_instant_row_counting(self):
        """Verify get_excel_row_count is fast and accurate."""
        wb_path = os.path.join(self.test_dir, "row_count.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Numbers"
        ws.append(["Header1", "Header2"])
        for i in range(500):
            ws.append([i, i * 2])
        wb.save(wb_path)
        wb.close()

        count = get_excel_row_count(wb_path, sheet_name="Numbers", has_header=True)
        self.assertEqual(count, 500)

    def test_disguised_csv_with_xlsx_extension(self):
        """Verify that a plain-text CSV named with .xlsx extension is safely recovered."""
        fake_xlsx = os.path.join(self.test_dir, "export_from_legacy_system.xlsx")
        with open(fake_xlsx, "w", encoding="utf-8") as f:
            f.write("CustomerID,Name,Country\n101,John Doe,USA\n102,Jane Smith,UK\n")

        # fast_read_excel should automatically detect text format and parse without crashing
        df = fast_read_excel(fake_xlsx)
        self.assertEqual(len(df), 2)
        self.assertEqual(list(df.columns), ["CustomerID", "Name", "Country"])

        # Node should also read it smoothly
        node = InputDataNode("node_disguised", {
            "file_path": fake_xlsx,
            "file_type": "excel"
        })
        res = node.execute({}, context={"base_dir": self.test_dir, "data_dir": self.test_dir})
        self.assertEqual(len(res["O"]), 2)

    def test_security_extension_allows_xlsm_and_xlsb(self):
        """Verify validate_upload_file accepts .xlsm and .xlsb."""
        valid_xlsm, err_xlsm = validate_upload_file("test.xlsm")
        self.assertTrue(valid_xlsm)
        self.assertIsNone(err_xlsm)

        valid_xlsb, err_xlsb = validate_upload_file("test.xlsb")
        self.assertTrue(valid_xlsb)
        self.assertIsNone(err_xlsb)

    def test_api_upload_xlsm_workflow(self):
        """Verify uploading an .xlsm file through /api/upload returns sheet list and preview."""
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "MainSheet"
        ws1.append(["Col1", "Col2"])
        ws1.append(["ValA", "ValB"])
        ws2 = wb.create_sheet("Secondary")
        ws2.append(["X", "Y"])
        ws2.append([10, 20])

        bio = io.BytesIO()
        wb.save(bio)
        wb.close()
        bio.seek(0)

        response = self.client.post(
            "/api/upload",
            data={"file": (bio, "test_upload.xlsm")},
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["file_type"], "excel")
        self.assertIn("MainSheet", data["sheets"])
        self.assertIn("Secondary", data["sheets"])
        self.assertEqual(data["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
