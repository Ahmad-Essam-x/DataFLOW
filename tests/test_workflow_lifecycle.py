"""
Comprehensive test suite for Workflow Lifecycle, Revision Backups,
Package Bundling (.zip / .yxzp), Security Sandboxing, and Crash Recovery Autosave.
"""
import os
import sys
import io
import json
import zipfile
import shutil
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app import app, WORKFLOWS_DIR, DATA_DIR, BASE_DIR
from backend.engine.workflow_manager import WorkflowManager
from backend.engine.security import SecurityError


class TestWorkflowLifecycle(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.manager = WorkflowManager(
            workflows_dir=WORKFLOWS_DIR,
            data_dir=DATA_DIR,
            base_dir=BASE_DIR
        )

        # Ensure isolated directories
        self.test_wf_name = "unit_lifecycle_test_workflow"
        self.test_wf_file = f"{self.test_wf_name}.json"
        self.test_wf_path = os.path.join(WORKFLOWS_DIR, self.test_wf_file)
        self.cleanup()

    def tearDown(self):
        self.cleanup()

    def cleanup(self):
        # Remove test workflow
        if os.path.exists(self.test_wf_path):
            try:
                os.remove(self.test_wf_path)
            except Exception:
                pass

        # Clean test backups
        backups_dir = os.path.join(WORKFLOWS_DIR, ".backups")
        if os.path.isdir(backups_dir):
            for fn in os.listdir(backups_dir):
                if fn.startswith(self.test_wf_name):
                    try:
                        os.remove(os.path.join(backups_dir, fn))
                    except Exception:
                        pass

        # Clean test autosaves
        autosave_dir = os.path.join(WORKFLOWS_DIR, ".autosave")
        if os.path.isdir(autosave_dir):
            for fn in os.listdir(autosave_dir):
                if "test_session" in fn:
                    try:
                        os.remove(os.path.join(autosave_dir, fn))
                    except Exception:
                        pass

    def test_schema_validation_and_normalization(self):
        """Validates node deduplication, dangling wire pruning, and viewport/metadata injection."""
        raw_payload = {
            "name": "  Dirty Schema Test  ",
            "viewport": {"zoom": "1.25", "panX": 150, "panY": -50},
            "nodes": [
                {"id": "node_1", "type": "input_data", "name": "Input 1", "x": 100, "y": 100},
                {"id": "node_1", "type": "filter", "name": "Filter Duplicate", "x": 200, "y": 100}, # duplicate ID
                {"id": "node_2", "type": "select", "name": "Select Fields", "x": 350, "y": 100}
            ],
            "connections": [
                {"id": "c1", "source": "node_1", "target": "node_2"}, # valid
                {"id": "c2", "source": "node_1", "target": "node_ghost"}, # dangling target!
                {"id": "c3", "source": "node_orphan", "target": "node_2"} # dangling source!
            ]
        }

        norm_wf, warnings = self.manager.validate_and_normalize(raw_payload)

        self.assertEqual(norm_wf["name"], "Dirty Schema Test")
        self.assertIn("metadata", norm_wf)
        self.assertEqual(norm_wf["viewport"]["zoom"], 1.25)
        self.assertEqual(norm_wf["viewport"]["panX"], 150.0)
        self.assertEqual(norm_wf["viewport"]["panY"], -50.0)

        # 3 unique nodes
        node_ids = [n["id"] for n in norm_wf["nodes"]]
        self.assertEqual(len(node_ids), 3)
        self.assertEqual(len(set(node_ids)), 3, "Node IDs must be deduplicated")

        # Dangling connections pruned: only c1 should survive
        self.assertEqual(len(norm_wf["connections"]), 1)
        self.assertEqual(norm_wf["connections"][0]["source"], "node_1")
        self.assertEqual(norm_wf["connections"][0]["target"], "node_2")
        self.assertTrue(any("dangling connection" in w.lower() for w in warnings))

    def test_inplace_save_and_backup_creation(self):
        """Tests that first save writes cleanly, and subsequent overwrite creates timestamped backup."""
        wf_v1 = {
            "name": self.test_wf_name,
            "nodes": [{"id": "n1", "type": "input_data", "config": {"file_path": "orders.csv"}}],
            "connections": []
        }

        # 1. First save via API
        res1 = self.client.post("/api/save-workflow", json=wf_v1)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertTrue(data1["success"])
        self.assertFalse(data1["backup_created"], "First save should not trigger backup")
        self.assertTrue(os.path.isfile(self.test_wf_path))

        # 2. Modify and save v2
        wf_v2 = dict(wf_v1)
        wf_v2["nodes"].append({"id": "n2", "type": "filter", "config": {}})
        res2 = self.client.post("/api/save-workflow", json=wf_v2)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2["success"])
        self.assertTrue(data2["backup_created"], "Overwrite must create a revision backup")

        # 3. Query revisions endpoint
        rev_res = self.client.get(f"/api/workflow/{self.test_wf_file}/revisions")
        self.assertEqual(rev_res.status_code, 200)
        rev_data = rev_res.get_json()
        self.assertTrue(rev_data["success"])
        self.assertGreaterEqual(len(rev_data["revisions"]), 1)

        backup_entry = rev_data["revisions"][0]
        self.assertTrue(backup_entry["backup_file"].startswith(self.test_wf_name))
        self.assertGreater(backup_entry["size_bytes"], 0)

    def test_revert_revision(self):
        """Tests restoring a previous workflow version from a backup snapshot."""
        wf_v1 = {
            "name": self.test_wf_name,
            "nodes": [{"id": "initial_node", "type": "input_data"}],
            "connections": []
        }
        self.client.post("/api/save-workflow", json=wf_v1)

        # Overwrite with v2
        wf_v2 = {
            "name": self.test_wf_name,
            "nodes": [
                {"id": "initial_node", "type": "input_data"},
                {"id": "added_node", "type": "filter"}
            ],
            "connections": []
        }
        self.client.post("/api/save-workflow", json=wf_v2)

        # Get the backup file name
        rev_res = self.client.get(f"/api/workflow/{self.test_wf_file}/revisions")
        backups = rev_res.get_json()["revisions"]
        self.assertGreater(len(backups), 0)
        backup_file = backups[0]["backup_file"]

        # Revert to v1
        revert_res = self.client.post(
            f"/api/workflow/{self.test_wf_file}/revert",
            json={"backup_file": backup_file}
        )
        self.assertEqual(revert_res.status_code, 200)
        revert_data = revert_res.get_json()
        self.assertTrue(revert_data["success"])
        restored_wf = revert_data["workflow"]
        self.assertEqual(len(restored_wf["nodes"]), 1)
        self.assertEqual(restored_wf["nodes"][0]["id"], "initial_node")

    def test_workflow_dependencies_inspection(self):
        """Tests dependency resolution for existing and missing datasets."""
        existing_file = "sales_orders.csv"
        missing_file = "non_existent_dataset_999.csv"

        wf = {
            "name": "Dependency Test",
            "nodes": [
                {
                    "id": "input_1",
                    "type": "input_data",
                    "config": {"file_path": existing_file}
                },
                {
                    "id": "input_2",
                    "type": "input_data",
                    "config": {"file_path": missing_file}
                },
                {
                    "id": "output_1",
                    "type": "output_data",
                    "config": {"filename": "output_test_run", "format": "csv"}
                }
            ]
        }

        dep_res = self.client.post("/api/workflow/dependencies", json=wf)
        self.assertEqual(dep_res.status_code, 200)
        data = dep_res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_dependencies"], 3)
        self.assertEqual(data["missing_count"], 1)

        deps = {d["node_id"]: d for d in data["dependencies"]}
        self.assertTrue(deps["input_1"]["exists"])
        self.assertFalse(deps["input_2"]["exists"])
        self.assertEqual(deps["output_1"]["role"], "output")

    def test_workflow_package_export_and_import(self):
        """Tests exporting workflow + data to a .zip archive and importing it back."""
        # Reference an existing sample dataset in data/
        wf_to_pack = {
            "name": "Packaged Integration Flow",
            "nodes": [
                {
                    "id": "node_in",
                    "type": "input_data",
                    "name": "Input Sales",
                    "config": {"file_path": "sales_orders.csv", "file_type": "csv"}
                }
            ],
            "connections": []
        }

        # 1. Export package
        export_res = self.client.post("/api/workflow/export-package", json=wf_to_pack)
        self.assertEqual(export_res.status_code, 200)
        self.assertEqual(export_res.mimetype, "application/zip")

        zip_bytes = io.BytesIO(export_res.data)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("workflow.json", namelist)
            self.assertIn("manifest.json", namelist)
            self.assertTrue(any(f.startswith("data/") for f in namelist))

        # 2. Import package back
        zip_bytes.seek(0)
        import_res = self.client.post(
            "/api/workflow/import-package",
            data={"file": (zip_bytes, "imported_package.zip")},
            content_type="multipart/form-data"
        )
        self.assertEqual(import_res.status_code, 200)
        import_data = import_res.get_json()
        self.assertTrue(import_data["success"])
        self.assertIn("workflow", import_data)
        self.assertEqual(import_data["workflow"]["name"], "Packaged Integration Flow")
        self.assertGreaterEqual(len(import_data["extracted_files"]), 1)

    def test_workflow_package_zip_slip_security(self):
        """Verifies that zip archives containing path traversal payloads are rejected."""
        malicious_zip = io.BytesIO()
        with zipfile.ZipFile(malicious_zip, "w") as zf:
            zf.writestr("../../evil_exploit.txt", "MALICIOUS CONTENT")
            zf.writestr("workflow.json", json.dumps({"name": "Evil Flow", "nodes": []}))

        malicious_zip.seek(0)
        res = self.client.post(
            "/api/workflow/import-package",
            data={"file": (malicious_zip, "exploit.zip")},
            content_type="multipart/form-data"
        )
        # Must be rejected with 403 or 400
        self.assertIn(res.status_code, [400, 403])
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("forbidden", data["error"].lower())

    def test_autosave_crash_recovery_lifecycle(self):
        """Tests saving, querying, and clearing autosaves for session crash recovery."""
        test_session = "test_session_xyz_123"
        wf_data = {
            "name": "Autosave Recovery Test",
            "nodes": [{"id": "n_rec", "type": "input_data"}],
            "connections": []
        }

        # 1. Post autosave
        save_res = self.client.post(
            "/api/workflow/autosave",
            json=wf_data,
            headers={"X-Session-ID": test_session}
        )
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.get_json()["success"])

        # 2. Get autosave
        get_res = self.client.get(
            "/api/workflow/autosave",
            headers={"X-Session-ID": test_session}
        )
        self.assertEqual(get_res.status_code, 200)
        rec_data = get_res.get_json()
        self.assertTrue(rec_data["success"])
        self.assertTrue(rec_data["available"])
        self.assertEqual(rec_data["workflow"]["name"], "Autosave Recovery Test")

        # 3. Delete autosave
        del_res = self.client.delete(
            "/api/workflow/autosave",
            headers={"X-Session-ID": test_session}
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["cleared"])

        # 4. Verify no longer available
        get_res2 = self.client.get(
            "/api/workflow/autosave",
            headers={"X-Session-ID": test_session}
        )
        self.assertFalse(get_res2.get_json()["available"])

    def test_available_recoveries_discovery_and_clear_all(self):
        """Tests scanning and discovering all orphaned recovery sessions regardless of session ID."""
        session_a = "test_session_recovery_a"
        session_b = "test_session_recovery_b"

        wf_a = {"name": "Crash Flow Alpha", "nodes": [{"id": "n1", "type": "input_data"}], "connections": []}
        wf_b = {"name": "Crash Flow Beta", "nodes": [{"id": "n1", "type": "input_data"}, {"id": "n2", "type": "filter"}], "connections": []}

        # 1. Post two separate autosaves
        self.client.post("/api/workflow/autosave", json=wf_a, headers={"X-Session-ID": session_a})
        self.client.post("/api/workflow/autosave", json=wf_b, headers={"X-Session-ID": session_b})

        # 2. Query available recoveries
        res = self.client.get("/api/workflow/recovery/available")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["count"], 2)

        names = [r["workflow_name"] for r in data["recoveries"]]
        self.assertIn("Crash Flow Alpha", names)
        self.assertIn("Crash Flow Beta", names)

        # 3. Clear all recoveries
        del_all = self.client.post("/api/workflow/recovery/clear-all")
        self.assertEqual(del_all.status_code, 200)
        self.assertTrue(del_all.get_json()["success"])

        # 4. Verify clean
        res_after = self.client.get("/api/workflow/recovery/available")
        self.assertEqual(res_after.get_json()["count"], 0)

    def test_commit_checkpoint_and_version_metadata(self):
        """Tests creating a named checkpoint commit with custom note, author, and semantic tag."""
        wf = {
            "name": self.test_wf_name,
            "nodes": [
                {"id": "n1", "type": "input_data", "config": {"file_path": "data.csv"}},
                {"id": "n2", "type": "filter", "config": {"expression": "[Amount] > 100"}}
            ],
            "connections": [{"id": "c1", "source": "n1", "target": "n2"}]
        }

        # Commit checkpoint
        commit_res = self.client.post(
            f"/api/workflow/{self.test_wf_file}/commit",
            json={
                "workflow": wf,
                "message": "Production release: added amount threshold filter",
                "author": "Alice Engineer",
                "tag": "v1.2.0"
            }
        )
        self.assertEqual(commit_res.status_code, 200)
        commit_data = commit_res.get_json()
        self.assertTrue(commit_data["success"])
        backup_file = commit_data["backup_file"]

        # Fetch revisions list and verify commit metadata
        rev_res = self.client.get(f"/api/workflow/{self.test_wf_file}/revisions")
        self.assertEqual(rev_res.status_code, 200)
        revisions = rev_res.get_json()["revisions"]
        self.assertGreaterEqual(len(revisions), 1)

        target_rev = next((r for r in revisions if r["backup_file"] == backup_file), None)
        self.assertIsNotNone(target_rev)
        self.assertEqual(target_rev["commit_message"], "Production release: added amount threshold filter")
        self.assertEqual(target_rev["author"], "Alice Engineer")
        self.assertEqual(target_rev["tag"], "v1.2.0")

        # Fetch revision full content
        content_res = self.client.get(f"/api/workflow/revision/{backup_file}")
        self.assertEqual(content_res.status_code, 200)
        content_data = content_res.get_json()
        self.assertTrue(content_data["success"])
        self.assertEqual(len(content_data["workflow"]["nodes"]), 2)

    def test_workflow_diff_engine(self):
        """Tests computing structural differences (added, removed, modified tools and wires)."""
        base_wf = {
            "name": "Base Flow",
            "nodes": [
                {"id": "node_1", "type": "input_data", "name": "Input", "config": {"file_path": "a.csv"}},
                {"id": "node_2", "type": "filter", "name": "Filter Old", "config": {"expression": "x > 1"}},
                {"id": "node_3", "type": "select", "name": "Select", "config": {}}
            ],
            "connections": [
                {"id": "c1", "source": "node_1", "source_port": "O", "target": "node_2", "target_port": "I"},
                {"id": "c2", "source": "node_2", "source_port": "O", "target": "node_3", "target_port": "I"}
            ]
        }

        # Target workflow: removed node_3, modified node_2 config & name, added node_4
        target_wf = {
            "name": "Target Flow",
            "nodes": [
                {"id": "node_1", "type": "input_data", "name": "Input", "config": {"file_path": "a.csv"}},
                {"id": "node_2", "type": "filter", "name": "Filter New", "config": {"expression": "x > 100"}},
                {"id": "node_4", "type": "summarize", "name": "Summarize Total", "config": {}}
            ],
            "connections": [
                {"id": "c1", "source": "node_1", "source_port": "O", "target": "node_2", "target_port": "I"},
                {"id": "c3", "source": "node_2", "source_port": "O", "target": "node_4", "target_port": "I"}
            ]
        }

        diff_res = self.client.post("/api/workflow/diff", json={
            "base_workflow": base_wf,
            "target_workflow": target_wf
        })
        self.assertEqual(diff_res.status_code, 200)
        diff_data = diff_res.get_json()
        self.assertTrue(diff_data["success"])
        diff = diff_data["diff"]

        summary = diff["summary"]
        self.assertFalse(summary["is_identical"])
        self.assertEqual(summary["added_nodes_count"], 1)
        self.assertEqual(summary["removed_nodes_count"], 1)
        self.assertEqual(summary["modified_nodes_count"], 1)

        self.assertEqual(diff["added_nodes"][0]["id"], "node_4")
        self.assertEqual(diff["removed_nodes"][0]["id"], "node_3")
        self.assertEqual(diff["modified_nodes"][0]["id"], "node_2")

    def test_recent_workflows_api_and_persistence(self):
        """Tests storing, retrieving, deduplicating, and clearing recent workflow history."""
        # 1. Clear existing recent list
        self.client.delete("/api/workflow/recent")

        # 2. Add recent entries
        entry1 = {"name": "Customer Segmentation", "path": "workflows/customer_segmentation.json", "node_count": 5}
        entry2 = {"name": "Sales Forecast", "path": "workflows/sales_forecast.json", "node_count": 8}

        res1 = self.client.post("/api/workflow/recent", json=entry1)
        self.assertEqual(res1.status_code, 200)
        res2 = self.client.post("/api/workflow/recent", json=entry2)
        self.assertEqual(res2.status_code, 200)

        # 3. Retrieve list
        get_res = self.client.get("/api/workflow/recent")
        self.assertEqual(get_res.status_code, 200)
        recents = get_res.get_json()["recent_workflows"]
        self.assertGreaterEqual(len(recents), 2)
        self.assertEqual(recents[0]["name"], "Sales Forecast")  # Most recently added is first

        # 4. Clear list
        del_res = self.client.delete("/api/workflow/recent")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["cleared"])

        # 5. Verify empty
        get_empty = self.client.get("/api/workflow/recent")
        self.assertEqual(len(get_empty.get_json()["recent_workflows"]), 0)

    def test_dirty_state_tracking_for_exit_guard(self):
        """Verifies that workflow dirty state can be synchronized to the backend for non-blocking exit interception."""
        # 1. Initially set clean
        res1 = self.client.post("/api/app/dirty-state", json={"is_dirty": False, "dirty_tabs_count": 0})
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.get_json()["dirty_state"]["is_dirty"])

        # 2. Query state
        get_res = self.client.get("/api/app/dirty-state")
        self.assertEqual(get_res.status_code, 200)
        self.assertFalse(get_res.get_json()["dirty_state"]["is_dirty"])

        # 3. Mark dirty with 2 tabs
        res2 = self.client.post("/api/app/dirty-state", json={"is_dirty": True, "dirty_tabs_count": 2})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()["dirty_state"]["is_dirty"])
        self.assertEqual(res2.get_json()["dirty_state"]["dirty_tabs_count"], 2)

        # 4. Verify reflected in global state
        from backend.app import _app_dirty_state
        self.assertTrue(_app_dirty_state["is_dirty"])
        self.assertEqual(_app_dirty_state["dirty_tabs_count"], 2)

        # Cleanup
        self.client.post("/api/app/dirty-state", json={"is_dirty": False, "dirty_tabs_count": 0})


if __name__ == "__main__":
    unittest.main()

