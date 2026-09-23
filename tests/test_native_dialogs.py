import os
import sys
import json
import unittest
import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app
from backend.engine.workflow_manager import WorkflowManager


class TestNativeDialogsAndTargetPaths(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wf_dir = os.path.join(self.temp_dir, "workflows")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.outside_dir = os.path.join(self.temp_dir, "outside_user_folder")
        os.makedirs(self.wf_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.outside_dir, exist_ok=True)

        self.manager = WorkflowManager(self.wf_dir, self.data_dir, self.temp_dir)
        self.client = app.test_client()
        app.config["TESTING"] = True

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_target_filepath_save_and_load(self):
        wf = {
            "name": "Custom Explorer Flow",
            "nodes": [{"id": "node_1", "type": "InputData", "config": {}, "x": 100, "y": 100}],
            "connections": []
        }
        target_path = os.path.join(self.outside_dir, "custom_flow.json")
        res = self.manager.save_workflow(wf, target_filepath=target_path)
        self.assertTrue(res["success"])
        self.assertTrue(os.path.isfile(target_path))

        # Check file content
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "Custom Explorer Flow")
        self.assertEqual(len(data["nodes"]), 1)

        # Overwrite to trigger backup
        wf["nodes"].append({"id": "node_2", "type": "Select", "config": {}, "x": 200, "y": 100})
        res2 = self.manager.save_workflow(wf, target_filepath=target_path)
        self.assertTrue(res2["success"])
        self.assertIsNotNone(res2["backup_created"])

        # Test load_from_path
        loaded = self.manager.load_from_path(target_path)
        self.assertTrue(loaded["success"])
        self.assertEqual(loaded["name"], "Custom Explorer Flow")
        self.assertEqual(len(loaded["workflow"]["nodes"]), 2)

    def test_api_save_workflow_with_target_filepath(self):
        target_path = os.path.join(self.outside_dir, "api_saved_flow.json")
        payload = {
            "name": "API Flow",
            "target_filepath": target_path,
            "nodes": [{"id": "n1", "type": "Formula", "config": {}, "x": 50, "y": 50}],
            "connections": []
        }
        res = self.client.post("/api/save-workflow", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(os.path.isfile(target_path))

    def test_native_save_dialog_endpoint_mock(self):
        target_path = os.path.join(self.outside_dir, "dialog_saved_flow.json")
        app.config["NATIVE_SAVE_DIALOG_HANDLER"] = lambda default_name: target_path

        payload = {
            "workflow": {
                "name": "Dialog Saved Workflow",
                "nodes": [{"id": "n_d1", "type": "Sort", "config": {}, "x": 10, "y": 10}],
                "connections": []
            }
        }
        res = self.client.post("/api/dialog/save-file", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename"], "dialog_saved_flow.json")
        self.assertTrue(os.path.isfile(target_path))

    def test_native_save_dialog_cancellation(self):
        app.config["NATIVE_SAVE_DIALOG_HANDLER"] = lambda default_name: None

        payload = {
            "workflow": {"name": "Cancelled Flow", "nodes": []}
        }
        res = self.client.post("/api/dialog/save-file", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data["cancelled"])

    def test_native_open_dialog_endpoint_mock(self):
        test_file = os.path.join(self.outside_dir, "sample_open.json")
        with open(test_file, "w", encoding="utf-8") as f:
            json.dump({
                "name": "Sample Open",
                "nodes": [{"id": "n_op", "type": "Filter", "config": {}, "x": 40, "y": 40}],
                "connections": []
            }, f)

        app.config["NATIVE_OPEN_DIALOG_HANDLER"] = lambda: test_file

        res = self.client.post("/api/dialog/open-file")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename"], "sample_open.json")
        self.assertEqual(data["name"], "Sample Open")
        self.assertEqual(len(data["workflow"]["nodes"]), 1)

    def test_native_open_dialog_cancellation(self):
        app.config["NATIVE_OPEN_DIALOG_HANDLER"] = lambda: None

        res = self.client.post("/api/dialog/open-file")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data["cancelled"])

    def test_pick_output_path_endpoint(self):
        target_path = os.path.join(self.outside_dir, "my_custom_report.xlsx")
        app.config["NATIVE_OUTPUT_SAVE_HANDLER"] = lambda default_name, initial_dir, fmt: target_path

        payload = {
            "format": "excel",
            "default_name": "my_custom_report",
            "initial_dir": self.outside_dir
        }
        res = self.client.post("/api/dialog/pick-output-path", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename"], "my_custom_report")
        self.assertEqual(data["full_filename"], "my_custom_report.xlsx")
        self.assertEqual(data["detected_format"], "excel")
        self.assertEqual(data["directory"], self.outside_dir.replace("\\", "/"))

    def test_pick_output_path_cancellation(self):
        app.config["NATIVE_OUTPUT_SAVE_HANDLER"] = lambda default_name, initial_dir, fmt: None

        res = self.client.post("/api/dialog/pick-output-path", json={"format": "csv"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data["cancelled"])

    def test_pick_folder_endpoint(self):
        app.config["NATIVE_FOLDER_DIALOG_HANDLER"] = lambda initial_dir: self.outside_dir

        res = self.client.post("/api/dialog/pick-folder", json={"initial_dir": self.temp_dir})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["path"], self.outside_dir.replace("\\", "/"))

    def test_pick_folder_cancellation(self):
        app.config["NATIVE_FOLDER_HANDLER"] = lambda initial_dir: None
        app.config["NATIVE_FOLDER_DIALOG_HANDLER"] = lambda initial_dir: None

        res = self.client.post("/api/dialog/pick-folder", json={})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data["cancelled"])

    def test_open_in_explorer_endpoint(self):
        opened_paths = []
        app.config["NATIVE_EXPLORER_LAUNCHER"] = lambda p: opened_paths.append(p)

        test_file = os.path.join(self.outside_dir, "test_file.csv")
        with open(test_file, "w") as f:
            f.write("a,b\n1,2\n")

        res = self.client.post("/api/open-in-explorer", json={"path": test_file})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(opened_paths), 1)
        self.assertEqual(opened_paths[0], os.path.normpath(test_file))

    def test_open_in_explorer_missing_path(self):
        res = self.client.post("/api/open-in-explorer", json={})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()

