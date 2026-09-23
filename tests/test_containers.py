import os
import unittest
import json
from backend.engine.executor import WorkflowExecutor
from backend.samples.generator import ensure_sample_data

class TestToolContainers(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, 'data')
        self.workflows_dir = os.path.join(self.base_dir, 'workflows')
        ensure_sample_data(self.data_dir, self.workflows_dir)
        self.executor = WorkflowExecutor()

    def test_disabled_container_bypasses_enclosed_nodes(self):
        workflow = {
            'name': 'Disabled Container Test',
            'nodes': [
                {
                    'id': 'node_active_input',
                    'type': 'input_data',
                    'name': 'Active Input',
                    'config': {'file_path': 'customers.csv', 'file_type': 'csv'}
                },
                {
                    'id': 'node_disabled_1',
                    'type': 'select',
                    'name': 'Enclosed Tool 1',
                    'config': {'columns': [{'name': 'CustomerID', 'rename': 'CustID'}]},
                    'container_id': 'container_1'
                },
                {
                    'id': 'node_disabled_2',
                    'type': 'sort',
                    'name': 'Enclosed Tool 2',
                    'config': {'sort_fields': [{'field': 'CustID', 'order': 'asc'}]},
                    'container_id': 'container_1'
                }
            ],
            'connections': [
                {'source': 'node_active_input', 'sourceHandle': 'O', 'target': 'node_disabled_1', 'targetHandle': 'I'},
                {'source': 'node_disabled_1', 'sourceHandle': 'O', 'target': 'node_disabled_2', 'targetHandle': 'I'}
            ],
            'containers': [
                {
                    'id': 'container_1',
                    'title': 'Bypassed Section',
                    'disabled': True,
                    'collapsed': False,
                    'node_ids': ['node_disabled_1', 'node_disabled_2']
                }
            ]
        }

        result = self.executor.run(workflow)
        self.assertTrue(result.success)
        self.assertEqual(result.node_results['node_disabled_1']['status'], 'disabled')
        self.assertEqual(result.node_results['node_disabled_2']['status'], 'disabled')
        self.assertEqual(result.node_results['node_active_input']['status'], 'success')
        bypass_logs = [log for log in result.logs if 'container disabled' in log.get('message', '')]
        self.assertGreaterEqual(len(bypass_logs), 2)

    def test_enabled_container_executes_all_nodes(self):
        workflow = {
            'name': 'Enabled Container Test',
            'nodes': [
                {
                    'id': 'node_input',
                    'type': 'input_data',
                    'name': 'Input Tool',
                    'config': {'file_path': 'customers.csv', 'file_type': 'csv'},
                    'container_id': 'container_1'
                },
                {
                    'id': 'node_sort',
                    'type': 'sort',
                    'name': 'Sort Tool',
                    'config': {'sort_fields': [{'field': 'CustomerID', 'order': 'desc'}]},
                    'container_id': 'container_1'
                }
            ],
            'connections': [
                {'source': 'node_input', 'sourceHandle': 'O', 'target': 'node_sort', 'targetHandle': 'I'}
            ],
            'containers': [
                {
                    'id': 'container_1',
                    'title': 'Active Pipeline',
                    'disabled': False,
                    'collapsed': False,
                    'node_ids': ['node_input', 'node_sort']
                }
            ]
        }

        result = self.executor.run(workflow)
        self.assertTrue(result.success)
        self.assertEqual(result.node_results['node_input']['status'], 'success')
        self.assertEqual(result.node_results['node_sort']['status'], 'success')

    def test_container_properties_serialization(self):
        container_data = {
            'id': 'container_99',
            'title': 'ETL Ingestion Group',
            'x': 120,
            'y': 80,
            'width': 450,
            'height': 300,
            'color': '#16a34a',
            'textColor': '#ffffff',
            'borderStyle': 'dashed',
            'borderWidth': 3,
            'fillOpacity': 20,
            'margin': 30,
            'collapsed': False,
            'disabled': False,
            'node_ids': ['node_1', 'node_2']
        }
        serialized = json.dumps(container_data)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized['id'], 'container_99')
        self.assertEqual(deserialized['title'], 'ETL Ingestion Group')
        self.assertEqual(deserialized['color'], '#16a34a')
        self.assertEqual(deserialized['textColor'], '#ffffff')
        self.assertEqual(deserialized['borderStyle'], 'dashed')
        self.assertEqual(deserialized['borderWidth'], 3)
        self.assertEqual(deserialized['fillOpacity'], 20)
        self.assertEqual(deserialized['margin'], 30)

    def test_autofit_boundary_math(self):
        nodes = [
            {'id': 'n1', 'x': 100, 'y': 100},
            {'id': 'n2', 'x': 300, 'y': 200},
        ]
        margin = 24
        header_height = 34
        min_x = min(n['x'] for n in nodes)
        min_y = min(n['y'] for n in nodes)
        max_x = max(n['x'] + 56 for n in nodes)
        max_y = max(n['y'] + 56 for n in nodes)

        calc_x = max(0, min_x - margin)
        calc_y = max(0, min_y - margin - header_height)
        calc_width = max(160, (max_x - min_x) + margin * 2)
        calc_height = max(70, (max_y - min_y) + margin * 2 + header_height)

        self.assertEqual(calc_x, 76)
        self.assertEqual(calc_y, 42)
        self.assertEqual(calc_width, 304)
        self.assertEqual(calc_height, 238)

        for n in nodes:
            self.assertGreaterEqual(n['x'], calc_x)
            self.assertLessEqual(n['x'] + 56, calc_x + calc_width)
            self.assertGreaterEqual(n['y'], calc_y + header_height)
            self.assertLessEqual(n['y'] + 56, calc_y + calc_height)

    def test_container_drag_moves_enclosed_nodes(self):
        """Verify that dragging a container updates enclosed tools positions by total delta."""
        container_start = {"x": 100, "y": 100}
        enclosed_tools = [
            {"id": "n1", "x": 140, "y": 160},
            {"id": "n2", "x": 220, "y": 200},
        ]
        container_new = {"x": 250, "y": 180}

        total_dx = container_new["x"] - container_start["x"]
        total_dy = container_new["y"] - container_start["y"]

        self.assertEqual(total_dx, 150)
        self.assertEqual(total_dy, 80)

        updated_tools = [
            {"id": t["id"], "x": t["x"] + total_dx, "y": t["y"] + total_dy}
            for t in enclosed_tools
        ]

        # Verify new coordinates
        self.assertEqual(updated_tools[0]["x"], 290)
        self.assertEqual(updated_tools[0]["y"], 240)
        self.assertEqual(updated_tools[1]["x"], 370)
        self.assertEqual(updated_tools[1]["y"], 280)

        # Verify relative distance from container remains constant
        for orig, upd in zip(enclosed_tools, updated_tools):
            rel_orig_x = orig["x"] - container_start["x"]
            rel_orig_y = orig["y"] - container_start["y"]
            rel_upd_x = upd["x"] - container_new["x"]
            rel_upd_y = upd["y"] - container_new["y"]
            self.assertEqual(rel_orig_x, rel_upd_x)
            self.assertEqual(rel_orig_y, rel_upd_y)


if __name__ == '__main__':
    unittest.main()
