import unittest
import json
import os
import shutil
from backend.engine.executor import WorkflowExecutor
from backend.app import app

class TestCanvasFeatures(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.executor = WorkflowExecutor()

    def test_disabled_container_execution_bypass(self):
        """Verify that nodes inside a disabled container are bypassed during execution."""
        workflow = {
            "nodes": [
                {
                    "id": "node_active_text",
                    "type": "text_input",
                    "name": "Active Text Input",
                    "config": {
                        "text": "id,name,val\n1,Alpha,10\n2,Beta,20"
                    }
                },
                {
                    "id": "node_disabled_filter",
                    "type": "filter",
                    "name": "Disabled Filter",
                    "container_id": "container_1",
                    "config": {
                        "column": "val",
                        "operator": ">",
                        "value": 15
                    }
                }
            ],
            "connections": [
                {
                    "source": "node_active_text",
                    "sourceHandle": "O",
                    "target": "node_disabled_filter",
                    "targetHandle": "I"
                }
            ],
            "containers": [
                {
                    "id": "container_1",
                    "title": "Experimental Tools Container",
                    "disabled": True,
                    "collapsed": False,
                    "nodeIds": ["node_disabled_filter"]
                }
            ],
            "comments": [
                {
                    "id": "comment_1",
                    "text": "# Notes\nThis is a documentation note."
                }
            ]
        }

        result = self.executor.run(workflow)
        node_results = result.node_results

        self.assertIn("node_active_text", node_results)
        self.assertEqual(node_results["node_active_text"]["status"], "success")

        # Disabled node should be flagged as disabled and bypassed
        self.assertIn("node_disabled_filter", node_results)
        self.assertEqual(node_results["node_disabled_filter"]["status"], "disabled")

        # Logs should record bypass notice
        bypass_logs = [l["message"] for l in result.logs if "bypassed" in l.get("message", "").lower()]
        self.assertTrue(len(bypass_logs) > 0)

    def test_workflow_save_and_open_with_containers_and_comments(self):
        """Verify save and load round-trip for containers and comment notes."""
        payload = {
            "name": "test_canvas_save_workflow",
            "nodes": [
                {
                    "id": "n1",
                    "type": "text_input",
                    "name": "Input 1",
                    "x": 100,
                    "y": 120,
                    "config": {"text": "a,b\n1,2"}
                }
            ],
            "connections": [],
            "containers": [
                {
                    "id": "cont_1",
                    "title": "Data Prep Group",
                    "color": "#0284c7",
                    "x": 80,
                    "y": 80,
                    "width": 300,
                    "height": 200,
                    "collapsed": False,
                    "disabled": False,
                    "nodeIds": ["n1"]
                }
            ],
            "comments": [
                {
                    "id": "note_1",
                    "text": "## Business Logic\n- Step 1\n- Step 2",
                    "color": "#fef08a",
                    "textColor": "#1e293b",
                    "fontSize": 13,
                    "x": 420,
                    "y": 80,
                    "width": 240,
                    "height": 160
                }
            ]
        }

        # Save workflow
        save_resp = self.client.post('/api/save-workflow', json=payload)
        self.assertEqual(save_resp.status_code, 200)
        save_data = save_resp.get_json()
        self.assertTrue(save_data.get("success"))
        filename = save_data.get("file")

        # Open workflow
        open_resp = self.client.get(f'/api/workflow/{filename}')
        self.assertEqual(open_resp.status_code, 200)
        wf = open_resp.get_json()

        self.assertEqual(len(wf.get("nodes", [])), 1)
        self.assertEqual(len(wf.get("containers", [])), 1)
        self.assertEqual(len(wf.get("comments", [])), 1)

        loaded_c = wf["containers"][0]
        self.assertEqual(loaded_c["id"], "cont_1")
        self.assertEqual(loaded_c["title"], "Data Prep Group")
        self.assertEqual(loaded_c["width"], 300)

        loaded_note = wf["comments"][0]
        self.assertEqual(loaded_note["id"], "note_1")
        self.assertIn("Business Logic", loaded_note["text"])

        # Clean up saved file
        wf_path = os.path.join(os.path.dirname(__file__), '..', 'workflows', filename)
        if os.path.exists(wf_path):
            os.remove(wf_path)

if __name__ == '__main__':
    unittest.main()
