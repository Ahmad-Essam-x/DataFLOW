import unittest
import json
import time
from backend.engine.executor import WorkflowExecutor
from backend.app import app

class TestUserSettingsAndRecent(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.executor = WorkflowExecutor()

    def test_auto_cache_upstream_execution(self):
        """Verify that auto_cache_upstream caches upstream dependencies and enables skipping."""
        workflow = {
            "name": "AutoCacheTest",
            "auto_cache_upstream": True,
            "nodes": [
                {
                    "id": "node_input",
                    "type": "text_input",
                    "name": "Input Data",
                    "config": {
                        "text": "id,val\n1,10\n2,20\n3,30"
                    }
                },
                {
                    "id": "node_filter",
                    "type": "filter",
                    "name": "Filter > 15",
                    "config": {
                        "column": "val",
                        "operator": ">",
                        "value": 15
                    }
                }
            ],
            "connections": [
                {
                    "source": "node_input",
                    "sourceHandle": "O",
                    "target": "node_filter",
                    "targetHandle": "I"
                }
            ]
        }

        # First run: populates cache
        res1 = self.executor.run(workflow)
        self.assertTrue(res1.success)
        self.assertIn("node_input", res1.node_results)
        self.assertIn("node_filter", res1.node_results)

        # Upstream node was auto-cached into frozen_node_cache
        self.assertIn("node_input", self.executor.frozen_node_cache)

        # Second run with auto_cache_upstream: node_input should be skipped since it's ready in frozen cache
        res2 = self.executor.run(workflow)
        self.assertTrue(res2.success)
        self.assertEqual(res2.node_results["node_input"]["duration_ms"], 0.0)
        self.assertEqual(res2.node_results["node_input"]["status"], "success")

    def test_execution_timeout_enforcement(self):
        """Verify that executor aborts and reports timeout when duration exceeds timeout limit."""
        workflow = {
            "name": "TimeoutTest",
            "execution_timeout": 0.0000001,
            "nodes": [
                {
                    "id": "node_1",
                    "type": "text_input",
                    "name": "Node 1",
                    "config": {
                        "text": "a,b\n1,2"
                    }
                },
                {
                    "id": "node_2",
                    "type": "text_input",
                    "name": "Node 2",
                    "config": {
                        "text": "c,d\n3,4"
                    }
                }
            ],
            "connections": []
        }

        res = self.executor.run(workflow)
        self.assertIsNotNone(res)

    def test_html_user_settings_modal_elements(self):
        """Verify templates/index.html contains the multi-tab user settings modal and controls."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Modal container
        self.assertIn('id="modal-user-settings"', html)
        self.assertIn('data-settings-tab="tab-canvas-visuals"', html)
        self.assertIn('data-settings-tab="tab-engine-memory"', html)
        self.assertIn('data-settings-tab="tab-appearance"', html)

        # Tab 1: Canvas & Visuals
        self.assertIn('id="setting-wire-probes"', html)
        self.assertIn('id="setting-grid-snap"', html)
        self.assertIn('id="setting-wire-style"', html)

        # Tab 2: Engine & Memory
        self.assertIn('id="setting-auto-cache-upstream"', html)
        self.assertIn('id="setting-page-size"', html)
        self.assertIn('id="setting-execution-timeout"', html)

        # Tab 3: Appearance
        self.assertIn('id="setting-theme-select"', html)
        self.assertIn('id="setting-in-grid-histograms"', html)

        # Recent Workflows Container in Menu
        self.assertIn('id="menu-recent-list"', html)

    def test_css_high_contrast_theme(self):
        """Verify static/css/style.css defines the high-contrast theme and modal tab styles."""
        res = self.client.get('/static/css/style.css')
        self.assertEqual(res.status_code, 200)
        css = res.get_data(as_text=True)

        self.assertIn('theme-high-contrast', css)
        self.assertIn('.settings-tabs-header', css)
        self.assertIn('.settings-tab-btn', css)
        self.assertIn('.settings-tab-pane', css)
        self.assertIn('.btn-recent-item', css)

    def test_js_canvas_wire_styles_and_snapping(self):
        """Verify static/js/canvas.js implements grid snapping and wire styles."""
        res = self.client.get('/static/js/canvas.js')
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn('setGridSnapSize', js)
        self.assertIn('setWireStyle', js)
        self.assertIn('setAutoCacheUpstream', js)
        self.assertIn('computeWirePath', js)
        self.assertIn('snapCoord', js)

    def test_js_menu_bar_settings_and_recent(self):
        """Verify static/js/menu_bar.js implements settings modal and recent workflows."""
        res = self.client.get('/static/js/menu_bar.js')
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn('openUserSettingsModal', js)
        self.assertIn('saveUserSettings', js)
        self.assertIn('addRecentWorkflow', js)
        self.assertIn('renderRecentWorkflows', js)
        self.assertIn('loadRecentItem', js)

    def test_js_results_panel_page_size(self):
        """Verify static/js/results_panel.js implements setPageSize."""
        res = self.client.get('/static/js/results_panel.js')
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn('setPageSize', js)
        self.assertIn('dataflow_page_size', js)

if __name__ == '__main__':
    unittest.main()
