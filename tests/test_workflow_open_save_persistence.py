"""
Unit and integration tests for workflow file open and save behaviors:
1. Opening previously saved workflows preserves filename, path, and human-readable name.
2. Saving directly back to the original file (via target_filepath, bare filename, or full path).
3. Workflows saved on disk with generic names ("New Workflow", "untitled_workflow") are normalized.
4. /api/samples and /api/workflow/<filename> return full path and filename metadata.
5. In-place overwrite saves to the original file rather than creating untitled/new workflows.
"""
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


class TestWorkflowOpenSavePersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wf_dir = os.path.join(self.temp_dir, "workflows")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.backups_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.wf_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backups_dir, exist_ok=True)

        self.manager = WorkflowManager(self.wf_dir, self.data_dir, self.temp_dir)
        self.client = app.test_client()
        app.config["TESTING"] = True

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_from_path_resolves_generic_name_to_filestem(self):
        """When opening a workflow whose JSON has 'name': 'New Workflow', load_from_path must derive from filename."""
        wf_file = os.path.join(self.wf_dir, "spotify_analytics.json")
        with open(wf_file, "w", encoding="utf-8") as f:
            json.dump({
                "name": "New Workflow",
                "nodes": [{"id": "n1", "type": "input_data", "config": {}, "x": 100, "y": 100}],
                "connections": []
            }, f)

        res = self.manager.load_from_path(wf_file)
        self.assertTrue(res["success"])
        self.assertEqual(res["filename"], "spotify_analytics.json")
        self.assertEqual(res["name"], "Spotify Analytics")
        self.assertEqual(res["workflow"]["name"], "Spotify Analytics")
        self.assertEqual(res["path"], wf_file.replace("\\", "/"))

    def test_save_workflow_bare_filename_resolves_to_workflows_dir(self):
        """Passing target_filepath as a bare filename ('spotify_analytics.json') must save to workflows_dir."""
        wf_data = {
            "name": "New Workflow",
            "nodes": [{"id": "n1", "type": "filter", "config": {}, "x": 50, "y": 50}],
            "connections": []
        }
        res = self.manager.save_workflow(wf_data, target_filepath="spotify_analytics.json")
        self.assertTrue(res["success"])
        expected_path = os.path.join(self.wf_dir, "spotify_analytics.json")
        self.assertEqual(os.path.abspath(res["path"]), os.path.abspath(expected_path))
        self.assertTrue(os.path.isfile(expected_path))
        self.assertEqual(res["name"], "Spotify Analytics")

    def test_save_workflow_inplace_overwrite_preserves_original_file(self):
        """Subsequent save to target_filepath overwrites the original file and creates a revision backup."""
        orig_path = os.path.join(self.wf_dir, "customer_churn.json")
        v1 = {
            "name": "Customer Churn",
            "nodes": [{"id": "n1", "type": "input_data", "config": {}, "x": 0, "y": 0}],
            "connections": []
        }
        res1 = self.manager.save_workflow(v1, target_filepath=orig_path)
        self.assertTrue(res1["success"])
        self.assertTrue(os.path.isfile(orig_path))
        self.assertIsNone(res1["backup_created"])

        # Edit and save again
        v2 = {
            "name": "Customer Churn",
            "nodes": [
                {"id": "n1", "type": "input_data", "config": {}, "x": 0, "y": 0},
                {"id": "n2", "type": "select", "config": {}, "x": 100, "y": 0}
            ],
            "connections": []
        }
        res2 = self.manager.save_workflow(v2, target_filepath=orig_path)
        self.assertTrue(res2["success"])
        self.assertEqual(os.path.abspath(res2["path"]), os.path.abspath(orig_path))
        self.assertIsNotNone(res2["backup_created"])

        # Verify disk content has 2 nodes
        with open(orig_path, "r", encoding="utf-8") as f:
            saved_content = json.load(f)
        self.assertEqual(len(saved_content["nodes"]), 2)
        self.assertEqual(saved_content["name"], "Customer Churn")

    def test_api_workflow_endpoint_attaches_path_and_resolves_generic_name(self):
        """GET /api/workflow/<filename> attaches _path and _filename and cleans generic names."""
        test_file = "unit_open_test.json"
        from backend.app import WORKFLOWS_DIR
        full_path = os.path.join(WORKFLOWS_DIR, test_file)
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump({
                    "name": "New Workflow",
                    "nodes": [{"id": "n1", "type": "formula", "config": {}, "x": 0, "y": 0}],
                    "connections": []
                }, f)

            res = self.client.get(f"/api/workflow/{test_file}")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["name"], "Unit Open Test")
            self.assertEqual(data["_filename"], test_file)
            self.assertTrue(data["_path"].endswith(test_file))
        finally:
            if os.path.exists(full_path):
                os.remove(full_path)

    def test_api_save_workflow_preserves_target_file(self):
        """POST /api/save-workflow with target_filepath saves in-place to that path."""
        test_file = "saved_target_flow.json"
        from backend.app import WORKFLOWS_DIR
        target = os.path.join(WORKFLOWS_DIR, test_file)
        try:
            payload = {
                "name": "Saved Target Flow",
                "target_filepath": target,
                "nodes": [{"id": "n1", "type": "sort", "config": {}, "x": 10, "y": 10}],
                "connections": []
            }
            res = self.client.post("/api/save-workflow", json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            self.assertTrue(os.path.isfile(target))
            self.assertEqual(data["file"], test_file)
        finally:
            if os.path.exists(target):
                os.remove(target)


if __name__ == "__main__":
    unittest.main()
