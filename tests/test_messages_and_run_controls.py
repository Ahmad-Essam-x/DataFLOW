"""
Unit and integration tests for execution messages retention,
meaningful tool naming (fixing 'undefined' tool names),
and the Run/Stop dual control toolbar buttons.
"""
import unittest
import json
from backend.app import app
from backend.engine.executor import WorkflowExecutor


class TestMessagesAndRunControls(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_backend_node_events_contain_valid_node_names(self):
        """Ensure WorkflowExecutor observer callbacks emit valid node_name and name (never 'undefined' or empty)."""
        wf_data = {
            "nodes": [
                {
                    "id": "node_input_1",
                    "type": "text_input",
                    "name": "Customer Data Source",
                    "config": {
                        "text": "id,name,score\n1,Alice,85\n2,Bob,40\n3,Charlie,95"
                    }
                },
                {
                    "id": "node_filter_1",
                    "type": "filter",
                    "name": "Filter High Scorers",
                    "config": {
                        "mode": "basic",
                        "column": "score",
                        "operator": ">",
                        "value": "50"
                    }
                }
            ],
            "connections": [
                {
                    "source": "node_input_1",
                    "sourceHandle": "O",
                    "target": "node_filter_1",
                    "targetHandle": "I"
                }
            ]
        }

        events_captured = []

        def observer(event):
            events_captured.append(event)

        executor = WorkflowExecutor()
        result = executor.run(wf_data, observer_cb=observer)

        self.assertTrue(result.success)
        self.assertGreaterEqual(len(events_captured), 4)

        started_events = [e for e in events_captured if e.get("event") == "node_started"]
        completed_events = [e for e in events_captured if e.get("event") == "node_completed"]

        self.assertEqual(len(started_events), 2)
        self.assertEqual(len(completed_events), 2)

        # Verify node_input_1 has its custom name
        input_started = next(p for p in started_events if p["node_id"] == "node_input_1")
        self.assertEqual(input_started["node_name"], "Customer Data Source")
        self.assertEqual(input_started["name"], "Customer Data Source")
        self.assertEqual(input_started["node_type"], "text_input")

        # Verify node_filter_1 has its custom name
        filter_completed = next(p for p in completed_events if p["node_id"] == "node_filter_1")
        self.assertEqual(filter_completed["node_name"], "Filter High Scorers")
        self.assertEqual(filter_completed["name"], "Filter High Scorers")
        self.assertEqual(filter_completed["node_type"], "filter")

    def test_backend_node_fallback_names_when_custom_name_missing(self):
        """Ensure nodes without explicit 'name' fallback cleanly to their type or id (never 'undefined')."""
        wf_data = {
            "nodes": [
                {
                    "id": "unnamed_node_1",
                    "type": "text_input",
                    "config": {
                        "text": "x,y\n1,2"
                    }
                }
            ],
            "connections": []
        }

        events_captured = []

        def observer(event):
            events_captured.append(event)

        executor = WorkflowExecutor()
        result = executor.run(wf_data, observer_cb=observer)

        self.assertTrue(result.success)
        started_events = [e for e in events_captured if e.get("event") == "node_started"]
        self.assertTrue(len(started_events) > 0)
        started = started_events[0]
        self.assertIn(started["node_name"], ["text_input", "unnamed_node_1"])
        self.assertNotEqual(started["node_name"], "undefined")
        self.assertNotEqual(started["node_name"], "")

    def test_run_stream_sse_emits_node_names(self):
        """Verify the /api/run-stream SSE endpoint delivers valid node_name in streaming chunks."""
        payload = {
            "nodes": [
                {
                    "id": "node_sse_1",
                    "type": "text_input",
                    "name": "SSE Test Input",
                    "config": {"text": "a,b\n1,2"}
                }
            ],
            "connections": []
        }

        res = self.client.post(
            "/api/run-stream",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)

        chunks = res.get_data(as_text=True).split("\n\n")
        events = []
        for c in chunks:
            c = c.strip()
            if c.startswith("data:"):
                events.append(json.loads(c[5:].strip()))

        node_started = [e for e in events if e.get("event") == "node_started"]
        node_completed = [e for e in events if e.get("event") == "node_completed"]

        self.assertTrue(len(node_started) > 0)
        self.assertEqual(node_started[0]["node_name"], "SSE Test Input")
        self.assertNotEqual(node_started[0]["node_name"], "undefined")

        self.assertTrue(len(node_completed) > 0)
        self.assertEqual(node_completed[0]["node_name"], "SSE Test Input")
        self.assertNotEqual(node_completed[0]["node_name"], "undefined")

    def test_frontend_index_html_elements(self):
        """Verify index.html has Run and Stop controls, messages toolbar with filter pills, copy and clear buttons."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Run & Stop dual control group
        self.assertIn("run-stop-control-group", html)
        self.assertIn('id="btn-run"', html)
        self.assertIn('id="btn-stop"', html)
        self.assertIn("btn-stop-workflow", html)
        self.assertIn("disabled", html)

        # Messages toolbar & filters
        self.assertIn("messages-toolbar", html)
        self.assertIn('data-msg-filter="all"', html)
        self.assertIn('data-msg-filter="error"', html)
        self.assertIn('data-msg-filter="warning"', html)
        self.assertIn('data-msg-filter="info"', html)
        self.assertIn('id="btn-copy-messages"', html)
        self.assertIn('id="btn-clear-messages"', html)

    def test_frontend_css_rules(self):
        """Verify style.css has styles for Run/Stop states, messages toolbar, filter pills, and run blocks."""
        res = self.client.get("/static/css/style.css")
        self.assertEqual(res.status_code, 200)
        css = res.get_data(as_text=True)

        # Controls styles
        self.assertIn(".run-stop-control-group", css)
        self.assertIn(".btn-run-workflow", css)
        self.assertIn(".btn-stop-workflow", css)
        self.assertIn(".btn-stop-active", css)
        self.assertIn(".is-stopping", css)
        self.assertIn(".spinner-sm", css)

        # Messages toolbar & run blocks
        self.assertIn(".messages-toolbar", css)
        self.assertIn(".btn-filter-pill", css)
        self.assertIn(".run-block", css)
        self.assertIn(".run-header", css)
        self.assertIn(".run-header-success", css)
        self.assertIn(".run-header-error", css)
        self.assertIn(".run-header-cancelled", css)
        self.assertIn(".run-badge", css)

    def test_frontend_results_panel_implementation(self):
        """Verify results_panel.js has run-block architecture, log persistence, and filter methods."""
        res = self.client.get("/static/js/results_panel.js")
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn("startRun", js)
        self.assertIn("finalizeRun", js)
        self.assertIn("appendLog", js)
        self.assertIn("clearMessagesLog", js)
        self.assertIn("copyMessagesLog", js)
        self.assertIn("filterMessages", js)
        self.assertIn("run-block", js)
        self.assertIn("run-badge", js)

        # Ensure clear() does not wipe messagesLog
        clear_func_idx = js.find("clear()")
        self.assertNotEqual(clear_func_idx, -1)
        clear_func_body = js[clear_func_idx:clear_func_idx + 600]
        self.assertNotIn("this.messagesLog.innerHTML", clear_func_body)

    def test_frontend_app_js_implementation(self):
        """Verify app.js defines getToolDisplayName, stopWorkflow, dual button handling, and Escape key."""
        res = self.client.get("/static/js/app.js")
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn("getToolDisplayName", js)
        self.assertIn("stopWorkflow", js)
        self.assertIn("btn-stop-active", js)
        self.assertIn("is-stopping", js)
        self.assertIn("finalizeRun", js)
        self.assertIn("workflow:stop", js)
        self.assertIn("Escape", js)


if __name__ == "__main__":
    unittest.main()
