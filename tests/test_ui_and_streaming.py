"""
Integration tests for UI assets, streaming endpoints, and column quality profiling.
"""
import unittest
import json
from backend.app import app


class TestUIAndStreaming(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_static_files_accessible(self):
        """Ensure all frontend modules and styles are served with HTTP 200."""
        static_files = [
            "/static/css/style.css",
            "/static/js/core/event_bus.js",
            "/static/js/core/history.js",
            "/static/js/palette.js",
            "/static/js/canvas.js",
            "/static/js/config_panel.js",
            "/static/js/results_panel.js",
            "/static/js/overview_minimap.js",
            "/static/js/app.js",
            "/static/js/menu_bar.js",
        ]
        for path in static_files:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f"Static asset {path} failed with {res.status_code}")

    def test_index_html_contains_new_elements(self):
        """Ensure index.html has undo/redo, theme toggle, menubar, splitters, overview minimap, and core scripts."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("btn-undo", html)
        self.assertIn("btn-redo", html)
        self.assertIn("btn-theme-toggle", html)
        self.assertIn("main-menubar", html)
        self.assertIn("menu-wire-probe-status", html)
        self.assertIn("modal-user-settings", html)
        self.assertIn("modal-shortcuts", html)
        self.assertIn("modal-about", html)
        self.assertIn("resizer-top", html)
        self.assertIn("canvas-overview-navigator", html)
        self.assertIn("check-view-overview", html)
        self.assertIn("core/event_bus.js", html)
        self.assertIn("core/history.js", html)
        self.assertIn("overview_minimap.js", html)
        self.assertIn("menu_bar.js", html)

    def test_tools_registry_discovery(self):
        """Ensure tool registry dynamically exposes all 17 nodes across categories."""
        res = self.client.get("/api/tools")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("tools", data)
        self.assertGreaterEqual(len(data["tools"]), 17)
        tool_types = {t["type"] for t in data["tools"]}
        self.assertIn("summarize", tool_types)
        self.assertIn("filter", tool_types)
        self.assertIn("join", tool_types)
        self.assertIn("input_data", tool_types)

    def test_end_to_end_streaming_and_quality_profile(self):
        """Verify full execution stream and column data quality profiling."""
        with open("workflows/sales_customer_enrichment.json", "r", encoding="utf-8") as f:
            wf = json.load(f)

        # 1. Test SSE Stream
        res = self.client.post("/api/run-stream", data=json.dumps(wf), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/event-stream")
        events = []
        for line in res.get_data(as_text=True).split("\n\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        
        event_types = [e.get("event") for e in events]
        self.assertIn("node_started", event_types)
        self.assertIn("node_completed", event_types)
        self.assertIn("workflow_completed", event_types)

        final_event = [e for e in events if e.get("event") == "workflow_completed"][0]
        self.assertTrue(final_event["success"])

        # 2. Test Node Data & Tri-Color Quality Metrics
        first_node_id = wf["nodes"][0]["id"]
        data_res = self.client.get(f"/api/node-data/{first_node_id}?port=O")
        self.assertEqual(data_res.status_code, 200)
        node_data = data_res.get_json()
        self.assertTrue(node_data.get("available"))
        self.assertIn("columns", node_data)
        self.assertGreater(len(node_data["columns"]), 0)

        first_col = node_data["columns"][0]
        self.assertIn("quality", first_col)
        quality = first_col["quality"]
        self.assertIn("ok_pct", quality)
        self.assertIn("null_pct", quality)
        self.assertIn("blank_pct", quality)
        self.assertAlmostEqual(quality["ok_pct"] + quality["null_pct"] + quality["blank_pct"], 100.0, places=0)

    def test_interactive_charts_and_wire_probe_assets(self):
        """Verify HTML, CSS, and JS assets contain all interactive charting and wire probe features."""
        # 1. HTML elements
        res = self.client.get("/")
        html = res.get_data(as_text=True)
        self.assertIn("tab-btn-chart", html)
        self.assertIn("btn-toggle-histograms", html)
        self.assertIn("tab-chart-view", html)
        self.assertIn("chart-viewport", html)
        self.assertIn("chart-type-select", html)
        self.assertIn("btn-chart-export-png", html)
        self.assertIn("btn-chart-export-svg", html)
        self.assertIn("btn-chart-copy-clipboard", html)
        self.assertIn("btn-chart-export-csv", html)

        # 2. CSS classes
        css_res = self.client.get("/static/css/style.css")
        css = css_res.get_data(as_text=True)
        self.assertIn(".col-quality-bar", css)
        self.assertIn(".col-hist-sparkline", css)
        self.assertIn(".chart-builder-container", css)
        self.assertIn(".chart-viewport", css)
        self.assertIn(".chart-tooltip", css)
        self.assertIn(".wire-probe-card", css)
        self.assertIn(".port-record-badge", css)

        # 3. Results Panel JS methods
        rp_res = self.client.get("/static/js/results_panel.js")
        rp_js = rp_res.get_data(as_text=True)
        self.assertIn("initChartTab", rp_js)
        self.assertIn("renderBarChart", rp_js)
        self.assertIn("renderLineChart", rp_js)
        self.assertIn("renderScatterChart", rp_js)
        self.assertIn("renderHistogramChart", rp_js)
        self.assertIn("renderDonutChart", rp_js)
        self.assertIn("exportChartPNG", rp_js)
        self.assertIn("exportChartSVG", rp_js)
        self.assertIn("copyChartToClipboard", rp_js)
        self.assertIn("exportChartCSV", rp_js)
        self.assertIn("openQualityQuickfilter", rp_js)
        self.assertIn("openHistogramQuickfilter", rp_js)

        # 4. Canvas JS wire probes
        canvas_res = self.client.get("/static/js/canvas.js")
        canvas_js = canvas_res.get_data(as_text=True)
        self.assertIn("showWireProbe", canvas_js)
        self.assertIn("hideWireProbe", canvas_js)
        self.assertIn("port-record-badge", canvas_js)

    def test_execution_badge_auto_dismiss_and_wire_probes_relocation(self):
        """Verify the node execution white pill auto-dismiss features and wire probes View menu relocation."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Wire probes moved to View menu and removed from top-right navbar & options menu
        self.assertIn('data-action="view:toggle-wire-probes"', html)
        self.assertIn('id="check-view-wire-probes"', html)
        self.assertNotIn('menubar-probe-pill', html)
        self.assertNotIn('data-action="options:toggle-wire-probes"', html)

        # Execution status badges flyout submenu in View menu
        self.assertIn('id="menu-badge-duration-list"', html)
        self.assertIn('data-action="view:badge-duration:3000"', html)
        self.assertIn('data-action="view:badge-duration:5000"', html)
        self.assertIn('data-action="view:badge-duration:10000"', html)
        self.assertIn('data-action="view:badge-duration:always"', html)
        self.assertIn('data-action="view:badge-duration:off"', html)

        # User Settings Modal duration option
        self.assertIn('id="setting-node-badge-duration"', html)

        # CSS fade-out rule
        css_res = self.client.get("/static/css/style.css")
        css = css_res.get_data(as_text=True)
        self.assertIn(".node-records-pill.fade-out", css)

        # Canvas JS methods
        canvas_res = self.client.get("/static/js/canvas.js")
        canvas_js = canvas_res.get_data(as_text=True)
        self.assertIn("setNodeBadgeDuration", canvas_js)
        self.assertIn("showNodeRecordPill", canvas_js)
        self.assertIn("clearPillTimers", canvas_js)

        # App JS command handlers
        app_res = self.client.get("/static/js/app.js")
        app_js = app_res.get_data(as_text=True)
        self.assertIn("view:toggle-wire-probes", app_js)
        self.assertIn("view:badge-duration:", app_js)


if __name__ == "__main__":
    unittest.main()

