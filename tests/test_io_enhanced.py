import unittest
import os
import shutil
import tempfile
import pandas as pd
from backend.engine.nodes.io import InputDataNode, OutputDataNode

class TestIOEnhanced(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_input_data_wildcard_glob(self):
        file1 = os.path.join(self.test_dir, "region_east.csv")
        file2 = os.path.join(self.test_dir, "region_west.csv")

        pd.DataFrame({'ID': [1, 2], 'Sales': [100, 200]}).to_csv(file1, index=False)
        pd.DataFrame({'ID': [3, 4], 'Sales': [300, 400]}).to_csv(file2, index=False)

        pattern = os.path.join(self.test_dir, "region_*.csv")
        node = InputDataNode("node1", {
            "file_path": pattern,
            "output_filename_field": "name_only"
        })
        res = node.execute({})
        df = res["O"]

        self.assertEqual(len(df), 4)
        self.assertIn("FileName", df.columns)
        self.assertEqual(set(df["FileName"].unique()), {"region_east.csv", "region_west.csv"})

    def test_input_data_excel_all_sheets(self):
        excel_path = os.path.join(self.test_dir, "multi_sheet.xlsx")
        with pd.ExcelWriter(excel_path) as writer:
            pd.DataFrame({'Dept': ['HR', 'IT'], 'Budget': [10, 20]}).to_excel(writer, sheet_name='Q1', index=False)
            pd.DataFrame({'Dept': ['Sales', 'Mktg'], 'Budget': [30, 40]}).to_excel(writer, sheet_name='Q2', index=False)

        node = InputDataNode("node2", {
            "file_path": excel_path,
            "file_type": "excel",
            "sheet_name": "*"
        })
        res = node.execute({})
        df = res["O"]

        self.assertEqual(len(df), 4)
        self.assertIn("SheetName", df.columns)
        self.assertEqual(set(df["SheetName"].unique()), {"Q1", "Q2"})

    def test_input_data_json_and_parquet(self):
        json_path = os.path.join(self.test_dir, "sample.json")
        pd.DataFrame({'A': [10, 20], 'B': ['x', 'y']}).to_json(json_path, orient='records')

        node_json = InputDataNode("node_json", {"file_path": json_path, "file_type": "json"})
        res_json = node_json.execute({})
        self.assertEqual(len(res_json["O"]), 2)

        parquet_path = os.path.join(self.test_dir, "sample.parquet")
        pd.DataFrame({'C': [100, 200], 'D': [True, False]}).to_parquet(parquet_path, index=False)

        node_parq = InputDataNode("node_parq", {"file_path": parquet_path, "file_type": "parquet"})
        res_parq = node_parq.execute({})
        self.assertEqual(len(res_parq["O"]), 2)

    def test_input_data_trim_headers_and_bad_lines(self):
        csv_path = os.path.join(self.test_dir, "untrimmed.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("  Name  ,  Age  \nAlice,30\nBob,25\n")

        node = InputDataNode("node_trim", {
            "file_path": csv_path,
            "trim_headers": True,
            "on_bad_lines": "skip"
        })
        res = node.execute({})
        df = res["O"]
        self.assertListEqual(list(df.columns), ["Name", "Age"])

    def test_output_data_write_modes(self):
        out_csv = os.path.join(self.test_dir, "output.csv")
        df1 = pd.DataFrame({'Col1': [1, 2], 'Col2': ['A', 'B']})

        # Mode 1: Overwrite
        node_out1 = OutputDataNode("out1", {
            "file_path": out_csv,
            "format": "csv",
            "write_mode": "overwrite"
        })
        node_out1.execute({"I": df1})

        # Mode 2: Append
        df2 = pd.DataFrame({'Col1': [3, 4], 'Col2': ['C', 'D']})
        node_out2 = OutputDataNode("out2", {
            "file_path": out_csv,
            "format": "csv",
            "write_mode": "append"
        })
        node_out2.execute({"I": df2})

        appended_df = pd.read_csv(out_csv)
        self.assertEqual(len(appended_df), 4)

        # Mode 3: Create New (Fail if exists)
        node_out3 = OutputDataNode("out3", {
            "file_path": out_csv,
            "format": "csv",
            "write_mode": "create_new"
        })
        with self.assertRaises(Exception):
            node_out3.execute({"I": df1})

    def test_output_data_utf8_bom_and_quote_modes(self):
        out_csv = os.path.join(self.test_dir, "output_bom.csv")
        df = pd.DataFrame({'Text': ['Hello "World"', '123'], 'Val': [1, 2]})

        node_out = OutputDataNode("out_bom", {
            "file_path": out_csv,
            "format": "csv",
            "encoding": "utf-8-sig",
            "quote_mode": "all",
            "line_ending": "crlf"
        })
        node_out.execute({"I": df})

        with open(out_csv, "rb") as f:
            raw_bytes = f.read()
            self.assertTrue(raw_bytes.startswith(b'\xef\xbb\xbf'))

    def test_output_data_dynamic_partitioning_and_drop_field(self):
        out_dir = os.path.join(self.test_dir, "partitioned")
        os.makedirs(out_dir, exist_ok=True)
        base_path = os.path.join(out_dir, "report.csv")

        df = pd.DataFrame({
            'Region': ['North', 'North', 'South'],
            'Amount': [100, 200, 300]
        })

        node_out = OutputDataNode("out_part", {
            "file_path": base_path,
            "format": "csv",
            "take_filename_from_field": True,
            "filename_field": "Region",
            "filename_action": "append_suffix",
            "drop_filename_field": True
        })
        node_out.execute({"I": df})

        written = node_out.written_files
        self.assertEqual(len(written), 2)

        file_north = os.path.join(out_dir, "report_North.csv")
        file_south = os.path.join(out_dir, "report_South.csv")
        self.assertTrue(os.path.exists(file_north))
        self.assertTrue(os.path.exists(file_south))

        df_north = pd.read_csv(file_north)
        self.assertEqual(len(df_north), 2)
        self.assertNotIn("Region", df_north.columns)
        self.assertIn("Amount", df_north.columns)

    def test_output_data_custom_output_dir(self):
        custom_dir = os.path.join(self.test_dir, "custom_exports")
        df = pd.DataFrame({'X': [1, 2], 'Y': ['a', 'b']})

        node_out = OutputDataNode("out_custom", {
            "output_dir": custom_dir,
            "filename": "custom_report",
            "format": "csv"
        })
        node_out.execute({"I": df})

        target_file = os.path.join(custom_dir, "custom_report.csv")
        self.assertTrue(os.path.exists(target_file))
        read_back = pd.read_csv(target_file)
        self.assertEqual(len(read_back), 2)

if __name__ == '__main__':
    unittest.main()
