"""
Unit and integration test suite for Enterprise Version Control,
Named Checkpoints, DAG/Config Diff Engine, and Rollback Integrity.
"""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app import app, WORKFLOWS_DIR, DATA_DIR, BASE_DIR
from backend.engine.workflow_manager import WorkflowManager


class TestVersionControl(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.manager = WorkflowManager(
            workflows_dir=WORKFLOWS_DIR,
            data_dir=DATA_DIR,
            base_dir=BASE_DIR
        )
        self.test_wf_name = "test_vc_pipeline"
        self.test_wf_file = f"{self.test_wf_name}.json"
        self.test_wf_path = os.path.join(WORKFLOWS_DIR, self.test_wf_file)
        self.cleanup()

    def tearDown(self):
        self.cleanup()

    def cleanup(self):
        if os.path.exists(self.test_wf_path):
            try:
                os.remove(self.test_wf_path)
            except Exception:
                pass

        backups_dir = os.path.join(WORKFLOWS_DIR, ".backups")
        if os.path.isdir(backups_dir):
            for fn in os.listdir(backups_dir):
                if fn.startswith(self.test_wf_name):
                    try:
                        os.remove(os.path.join(backups_dir, fn))
                    except Exception:
                        pass

    def test_checkpoint_commit_lifecycle(self):
        """Verifies creating multiple named checkpoints and querying their enriched metadata."""
        wf_v1 = {
            "name": self.test_wf_name,
            "nodes": [
                {"id": "n1", "type": "input_data", "name": "Raw Ingest", "config": {"file_path": "orders.csv"}},
                {"id": "n2", "type": "select", "name": "Select Columns", "config": {}}
            ],
            "connections": [{"id": "c1", "source": "n1", "source_port": "O", "target": "n2", "target_port": "I"}]
        }

        # 1. Commit Checkpoint 1
        res1 = self.client.post(
            f"/api/workflow/{self.test_wf_file}/commit",
            json={
                "workflow": wf_v1,
                "message": "Initial Ingest & Projection Setup",
                "author": "Lead Architect",
                "tag": "v1.0.0"
            }
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertTrue(data1["success"])
        b1 = data1["backup_file"]

        # 2. Modify and commit Checkpoint 2
        wf_v2 = dict(wf_v1)
        wf_v2["nodes"].append({"id": "n3", "type": "filter", "name": "Filter Invalid", "config": {"expression": "[Status] == 'Active'"}})
        wf_v2["connections"].append({"id": "c2", "source": "n2", "source_port": "O", "target": "n3", "target_port": "I"})

        res2 = self.client.post(
            f"/api/workflow/{self.test_wf_file}/commit",
            json={
                "workflow": wf_v2,
                "message": "Added data sanitization filter",
                "author": "Data Engineer",
                "tag": "v1.1.0"
            }
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        b2 = data2["backup_file"]

        # 3. Retrieve revisions list
        rev_res = self.client.get(f"/api/workflow/{self.test_wf_file}/revisions")
        self.assertEqual(rev_res.status_code, 200)
        revisions = rev_res.get_json()["revisions"]
        self.assertEqual(len(revisions), 2)

        rev_map = {r["backup_file"]: r for r in revisions}
        self.assertIn(b1, rev_map)
        self.assertIn(b2, rev_map)

        self.assertEqual(rev_map[b1]["commit_message"], "Initial Ingest & Projection Setup")
        self.assertEqual(rev_map[b1]["author"], "Lead Architect")
        self.assertEqual(rev_map[b1]["tag"], "v1.0.0")

        self.assertEqual(rev_map[b2]["commit_message"], "Added data sanitization filter")
        self.assertEqual(rev_map[b2]["tag"], "v1.1.0")

    def test_dag_diff_engine_detailed_detection(self):
        """Verifies DAG diff engine correctly identifies node additions, removals, config changes, and wire adjustments."""
        wf_initial = {
            "name": "Diff Test",
            "nodes": [
                {"id": "node_in", "type": "input_data", "name": "Input Orders", "config": {"file_path": "sales.csv"}},
                {"id": "node_flt", "type": "filter", "name": "Active Filter", "config": {"expression": "qty > 10"}},
                {"id": "node_out", "type": "output_data", "name": "Write DB", "config": {"format": "csv"}}
            ],
            "connections": [
                {"id": "w1", "source": "node_in", "source_port": "O", "target": "node_flt", "target_port": "I"},
                {"id": "w2", "source": "node_flt", "source_port": "O", "target": "node_out", "target_port": "I"}
            ]
        }

        # Altered version:
        # - node_flt expression changed
        # - node_out removed
        # - node_sum added
        # - w2 removed, w3 added
        wf_modified = {
            "name": "Diff Test",
            "nodes": [
                {"id": "node_in", "type": "input_data", "name": "Input Orders", "config": {"file_path": "sales.csv"}},
                {"id": "node_flt", "type": "filter", "name": "Active Filter", "config": {"expression": "qty > 50"}},
                {"id": "node_sum", "type": "summarize", "name": "Aggregate Revenue", "config": {}}
            ],
            "connections": [
                {"id": "w1", "source": "node_in", "source_port": "O", "target": "node_flt", "target_port": "I"},
                {"id": "w3", "source": "node_flt", "source_port": "O", "target": "node_sum", "target_port": "I"}
            ]
        }

        res = self.client.post("/api/workflow/diff", json={
            "base_workflow": wf_initial,
            "target_workflow": wf_modified
        })
        self.assertEqual(res.status_code, 200)
        diff = res.get_json()["diff"]

        summary = diff["summary"]
        self.assertFalse(summary["is_identical"])
        self.assertEqual(summary["added_nodes_count"], 1)
        self.assertEqual(summary["removed_nodes_count"], 1)
        self.assertEqual(summary["modified_nodes_count"], 1)
        self.assertEqual(summary["added_connections_count"], 1)
        self.assertEqual(summary["removed_connections_count"], 1)

        self.assertEqual(diff["added_nodes"][0]["id"], "node_sum")
        self.assertEqual(diff["removed_nodes"][0]["id"], "node_out")
        self.assertEqual(diff["modified_nodes"][0]["id"], "node_flt")
        self.assertTrue(any("qty > 50" in c or "expression" in c for c in diff["modified_nodes"][0]["changes"]))

    def test_non_destructive_revert_safety(self):
        """Verifies that reverting a workflow replaces target content while creating a safety rollback snapshot."""
        # 1. Save v1 to disk
        wf_v1 = {"name": self.test_wf_name, "nodes": [{"id": "n1", "type": "input_data"}], "connections": []}
        self.client.post("/api/save-workflow", json=wf_v1)

        # 2. Commit a named checkpoint v1_cp
        cp_res = self.client.post(
            f"/api/workflow/{self.test_wf_file}/commit",
            json={"workflow": wf_v1, "message": "Baseline Snapshot"}
        )
        cp_file = cp_res.get_json()["backup_file"]

        # 3. Overwrite with v2
        wf_v2 = {"name": self.test_wf_name, "nodes": [{"id": "n1", "type": "input_data"}, {"id": "n2", "type": "filter"}], "connections": []}
        self.client.post("/api/save-workflow", json=wf_v2)

        # 4. Revert to cp_file
        revert_res = self.client.post(
            f"/api/workflow/{self.test_wf_file}/revert",
            json={"backup_file": cp_file}
        )
        self.assertEqual(revert_res.status_code, 200)
        revert_data = revert_res.get_json()
        self.assertTrue(revert_data["success"])
        self.assertIsNotNone(revert_data["backup_created"], "Reverting an existing file must create a safety backup")

        # 5. Read back from disk
        with open(self.test_wf_path, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertEqual(len(disk_data["nodes"]), 1)


if __name__ == "__main__":
    unittest.main()
