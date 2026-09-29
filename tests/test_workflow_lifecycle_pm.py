"""
Comprehensive Product Manager Test Suite: Workflow Persistence, Opening,
Tool Registry Fidelity, Auto-Save, and Version History Matrix.
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


class TestWorkflowLifecyclePM(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.wf_dir = os.path.join(self.temp_dir, "workflows")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.backups_dir = os.path.join(self.wf_dir, ".backups")
        self.autosave_dir = os.path.join(self.wf_dir, ".autosave")
        os.makedirs(self.wf_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backups_dir, exist_ok=True)
        os.makedirs(self.autosave_dir, exist_ok=True)

        self.manager = WorkflowManager(self.wf_dir, self.data_dir, self.temp_dir)
        self.client = app.test_client()
        app.config["TESTING"] = True

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Pillar 1 & Bug Fix: Tool Registry & Visual Fidelity Verification
    # -------------------------------------------------------------------------
    def test_tool_registry_metadata_and_ports_fidelity(self):
        """Verify /api/tools provides authentic metadata, icons, and I/O ports for all tools.
        Ensures nodes never need to fall back to the default Formula ('code') glyph or generic I/O.
        """
        res = self.client.get("/api/tools")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("tools", data)
        tools = {t["type"]: t for t in data["tools"]}

        # 1. Join tool ports
        self.assertIn("join", tools)
        join_meta = tools["join"]
        self.assertEqual(join_meta["name"], "Join")
        self.assertEqual(join_meta["inputs"], ["L", "R"], "Join must have Left and Right input ports")
        self.assertEqual(set(join_meta["outputs"]), {"L", "J", "R"}, "Join must have Left, Joined, Right output ports")
        self.assertNotEqual(join_meta["icon"], "code", "Join must not have the formula 'code' icon")

        # 2. Filter tool ports
        self.assertIn("filter", tools)
        filter_meta = tools["filter"]
        self.assertEqual(filter_meta["name"], "Filter")
        self.assertEqual(filter_meta["inputs"], ["I"])
        self.assertEqual(set(filter_meta["outputs"]), {"T", "F"}, "Filter must have True and False output ports")

        # 3. Input Data tool ports
        self.assertIn("input_data", tools)
        input_meta = tools["input_data"]
        self.assertEqual(input_meta["name"], "Input Data")
        self.assertEqual(input_meta["inputs"], [], "Input Data must have no input ports")
        self.assertEqual(input_meta["outputs"], ["O"], "Input Data must have Output port")

        # 4. Output Data tool ports
        self.assertIn("output_data", tools)
        output_meta = tools["output_data"]
        self.assertEqual(output_meta["name"], "Output Data")
        self.assertEqual(output_meta["inputs"], ["I"])
        self.assertEqual(output_meta["outputs"], ["O"])

        # 5. Formula tool
        self.assertIn("formula", tools)
        formula_meta = tools["formula"]
        self.assertEqual(formula_meta["name"], "Formula")
        self.assertEqual(formula_meta["inputs"], ["I"])
        self.assertEqual(formula_meta["outputs"], ["O"])

        # 6. Unique tool ports
        self.assertIn("unique", tools)
        unique_meta = tools["unique"]
        self.assertEqual(unique_meta["name"], "Unique")
        self.assertEqual(set(unique_meta["outputs"]), {"U", "D"}, "Unique must have U and D output ports")

        # 7. Append Fields ports
        self.assertIn("append_fields", tools)
        af_meta = tools["append_fields"]
        self.assertEqual(af_meta["inputs"], ["T", "S"], "Append Fields must have Target and Source inputs")

        # 8. Find & Replace ports
        self.assertIn("find_replace", tools)
        fr_meta = tools["find_replace"]
        self.assertEqual(fr_meta["inputs"], ["F", "R"], "Find & Replace must have Find and Replace inputs")

    def test_workflow_node_hydration_against_registry(self):
        """Simulate loading a complex saved workflow and verifying each node correctly resolves
        its authentic metadata rather than the formula fallback.
        """
        tools_res = self.client.get("/api/tools")
        tools_data = {t["type"]: t for t in tools_res.get_json()["tools"]}

        complex_workflow = {
            "name": "Customer Segmentation & Join Pipeline",
            "nodes": [
                {"id": "n1", "type": "input_data", "name": "Input Orders", "x": 50, "y": 100},
                {"id": "n2", "type": "input_data", "name": "Input Customers", "x": 50, "y": 250},
                {"id": "n3", "type": "filter", "name": "Active Customers", "x": 220, "y": 250},
                {"id": "n4", "type": "join", "name": "Join Orders & Cust", "x": 400, "y": 150},
                {"id": "n5", "type": "select", "name": "Select Fields", "x": 580, "y": 150},
                {"id": "n6", "type": "summarize", "name": "Aggregate Revenue", "x": 750, "y": 150},
                {"id": "n7", "type": "output_data", "name": "Write Parquet", "x": 920, "y": 150}
            ],
            "connections": [
                {"id": "c1", "source": "n1", "sourceHandle": "O", "target": "n4", "targetHandle": "L"},
                {"id": "c2", "source": "n2", "sourceHandle": "O", "target": "n3", "targetHandle": "I"},
                {"id": "c3", "source": "n3", "sourceHandle": "T", "target": "n4", "targetHandle": "R"},
                {"id": "c4", "source": "n4", "sourceHandle": "J", "target": "n5", "targetHandle": "I"},
                {"id": "c5", "source": "n5", "sourceHandle": "O", "target": "n6", "targetHandle": "I"},
                {"id": "c6", "source": "n6", "sourceHandle": "O", "target": "n7", "targetHandle": "I"}
            ]
        }

        # Check that every node type in the workflow maps to its genuine registered metadata
        formula_count = 0
        for node in complex_workflow["nodes"]:
            meta = tools_data.get(node["type"])
            self.assertIsNotNone(meta, f"Tool type {node['type']} must exist in registry")
            if meta["icon"] == "code" and node["type"] != "formula" and node["type"] != "python":
                formula_count += 1

        self.assertEqual(formula_count, 0, "No non-formula tool should have formula 'code' icon when registry is hydrated")

        # Verify multi-port wire validity
        join_meta = tools_data["join"]
        self.assertIn("L", join_meta["inputs"])
        self.assertIn("R", join_meta["inputs"])
        self.assertIn("J", join_meta["outputs"])

        filter_meta = tools_data["filter"]
        self.assertIn("T", filter_meta["outputs"])
        self.assertIn("F", filter_meta["outputs"])

    # -------------------------------------------------------------------------
    # Pillar 2: Saving & Opening Workflow File Persistence
    # -------------------------------------------------------------------------
    def test_save_and_open_in_place_lifecycle(self):
        """Saving an existing workflow preserves file identity, path, and human-readable name."""
        wf_name = "regional_sales_analysis"
        target_path = os.path.join(self.wf_dir, f"{wf_name}.json")

        v1_payload = {
            "name": "Regional Sales Analysis",
            "nodes": [
                {"id": "n1", "type": "input_data", "name": "Sales CSV", "x": 100, "y": 100},
                {"id": "n2", "type": "filter", "name": "Filter Region", "x": 250, "y": 100}
            ],
            "connections": [
                {"id": "c1", "source": "n1", "sourceHandle": "O", "target": "n2", "targetHandle": "I"}
            ]
        }

        # 1. First save to target_filepath
        save_res1 = self.manager.save_workflow(v1_payload, target_filepath=target_path)
        self.assertTrue(save_res1["success"])
        self.assertEqual(os.path.abspath(save_res1["path"]), os.path.abspath(target_path))
        self.assertEqual(save_res1["name"], "Regional Sales Analysis")
        self.assertEqual(save_res1["filename"], f"{wf_name}.json")

        # 2. Open saved workflow
        open_res = self.manager.load_from_path(target_path)
        self.assertTrue(open_res["success"])
        self.assertEqual(open_res["filename"], f"{wf_name}.json")
        self.assertEqual(open_res["name"], "Regional Sales Analysis")
        self.assertEqual(len(open_res["workflow"]["nodes"]), 2)
        self.assertEqual(len(open_res["workflow"]["connections"]), 1)

        # 3. Add node and overwrite in place
        v2_payload = dict(open_res["workflow"])
        v2_payload["nodes"].append({"id": "n3", "type": "formula", "name": "Add Margin", "x": 400, "y": 100})
        v2_payload["connections"].append({"id": "c2", "source": "n2", "sourceHandle": "T", "target": "n3", "targetHandle": "I"})

        save_res2 = self.manager.save_workflow(v2_payload, target_filepath=target_path)
        self.assertTrue(save_res2["success"])
        self.assertEqual(os.path.abspath(save_res2["path"]), os.path.abspath(target_path))
        self.assertIsNotNone(save_res2["backup_created"], "Overwriting existing workflow must create backup snapshot")

        # 4. Re-open and verify updated 3 nodes
        open_res2 = self.manager.load_from_path(target_path)
        self.assertTrue(open_res2["success"])
        self.assertEqual(len(open_res2["workflow"]["nodes"]), 3)
        self.assertEqual(len(open_res2["workflow"]["connections"]), 2)

    def test_save_as_creates_new_file_leaving_original_unmodified(self):
        """Save As to a new filename creates the new file without modifying the original."""
        orig_file = os.path.join(self.wf_dir, "original_model.json")
        orig_data = {
            "name": "Original Model",
            "nodes": [{"id": "n1", "type": "input_data", "name": "Input 1", "x": 50, "y": 50}],
            "connections": []
        }
        self.manager.save_workflow(orig_data, target_filepath=orig_file)

        # Save As new file
        new_file = os.path.join(self.wf_dir, "forked_model.json")
        fork_data = {
            "name": "Forked Model",
            "nodes": [
                {"id": "n1", "type": "input_data", "name": "Input 1", "x": 50, "y": 50},
                {"id": "n2", "type": "select", "name": "Select 1", "x": 200, "y": 50}
            ],
            "connections": []
        }
        save_as_res = self.manager.save_workflow(fork_data, target_filepath=new_file)
        self.assertTrue(save_as_res["success"])
        self.assertEqual(os.path.abspath(save_as_res["path"]), os.path.abspath(new_file))

        # Check original still has 1 node
        orig_check = self.manager.load_from_path(orig_file)
        self.assertEqual(len(orig_check["workflow"]["nodes"]), 1)

        # Check fork has 2 nodes
        fork_check = self.manager.load_from_path(new_file)
        self.assertEqual(len(fork_check["workflow"]["nodes"]), 2)

    # -------------------------------------------------------------------------
    # Pillar 3: Auto-Save & Recovery Lifecycle
    # -------------------------------------------------------------------------
    def test_autosave_save_and_recovery_flow(self):
        """Verify autosave endpoint stores draft with session isolation and recovery finds it."""
        session_id = "test_pm_session_99"
        wf_name = "Autosaved Draft Analysis"

        draft_wf = {
            "name": wf_name,
            "nodes": [
                {"id": "a1", "type": "input_data", "name": "Raw Data", "x": 10, "y": 10},
                {"id": "a2", "type": "formula", "name": "Cleanse Fields", "x": 150, "y": 10}
            ],
            "connections": [
                {"id": "c1", "source": "a1", "sourceHandle": "O", "target": "a2", "targetHandle": "I"}
            ]
        }

        # 1. Post autosave
        res = self.client.post(
            "/api/workflow/autosave",
            json=draft_wf,
            headers={"X-Session-ID": session_id}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # 2. Check recovery discovery via session query
        get_res = self.client.get(
            "/api/workflow/autosave",
            headers={"X-Session-ID": session_id}
        )
        self.assertEqual(get_res.status_code, 200)
        rec_data = get_res.get_json()
        self.assertTrue(rec_data["success"])
        self.assertTrue(rec_data["available"])
        self.assertEqual(rec_data["workflow"]["name"], wf_name)
        self.assertEqual(len(rec_data["workflow"]["nodes"]), 2)

        # 3. Clean up recovery file
        del_res = self.client.delete(
            "/api/workflow/autosave",
            headers={"X-Session-ID": session_id}
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["cleared"])

    # -------------------------------------------------------------------------
    # Pillar 4: Version History & Revisions Matrix
    # -------------------------------------------------------------------------
    def test_version_history_commit_diff_and_revert(self):
        """Test commit checkpoint, revision listing, diffing, and revert to previous revision."""
        wf_file = os.path.join(self.wf_dir, "versioned_pipeline.json")
        v1 = {
            "name": "Versioned Pipeline",
            "nodes": [{"id": "n1", "type": "input_data", "name": "Input 1", "x": 0, "y": 0}],
            "connections": []
        }
        self.manager.save_workflow(v1, target_filepath=wf_file)

        # 1. Create a checkpoint commit
        commit_res = self.manager.commit_checkpoint(
            filename="versioned_pipeline.json",
            wf_data=v1,
            author="Data Engineer PM",
            message="Initial working version with Input tool"
        )
        self.assertTrue(commit_res["success"])
        rev1_filename = commit_res["backup_file"]

        # 2. Modify and commit version 2
        v2 = {
            "name": "Versioned Pipeline",
            "nodes": [
                {"id": "n1", "type": "input_data", "name": "Input 1", "x": 0, "y": 0},
                {"id": "n2", "type": "filter", "name": "Filter High Values", "x": 150, "y": 0}
            ],
            "connections": [
                {"id": "c1", "source": "n1", "sourceHandle": "O", "target": "n2", "targetHandle": "I"}
            ]
        }
        self.manager.save_workflow(v2, target_filepath=wf_file)
        commit_res2 = self.manager.commit_checkpoint(
            filename="versioned_pipeline.json",
            wf_data=v2,
            author="Data Engineer PM",
            message="Added Filter tool for outlier exclusion"
        )
        self.assertTrue(commit_res2["success"])

        # 3. List revisions
        revs = self.manager.get_revisions("versioned_pipeline.json")
        self.assertGreaterEqual(len(revs), 2)

        # 4. Diff between Rev 1 (1 node) and current (2 nodes)
        diff = self.manager.compute_diff(base_wf=v1, target_wf=v2)
        self.assertIn("added_nodes", diff)
        self.assertEqual(len(diff["added_nodes"]), 1)
        self.assertEqual(diff["added_nodes"][0]["name"], "Filter High Values")

        # 5. Revert back to Revision 1
        revert_res = self.manager.revert_revision("versioned_pipeline.json", rev1_filename)
        self.assertTrue(revert_res["success"])
        self.assertEqual(len(revert_res["workflow"]["nodes"]), 1)
        self.assertEqual(revert_res["workflow"]["nodes"][0]["id"], "n1")


if __name__ == "__main__":
    unittest.main()
