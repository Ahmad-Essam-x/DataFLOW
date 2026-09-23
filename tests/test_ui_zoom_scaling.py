"""
Tests for UI Display Scaling (Zoom In / Zoom Out / Reset Zoom).
Verifies:
- JavaScript in-app UI zoom scaling controller and keyboard accelerators.
- User settings schema and persistence for UI zoom.
- Menubar settings modal UI scale dropdown.
- Desktop application zoomable window configuration.
"""
import unittest
from backend.app import app


class TestUIZoomScaling(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_app_js_has_ui_zoom_controller_and_shortcuts(self):
        """Ensure static/js/app.js implements window.appUIScale and keyboard accelerators."""
        res = self.client.get("/static/js/app.js")
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn("window.appUIScale", js)
        self.assertIn("UI_ZOOM_LEVELS", js)
        self.assertIn("zoomUIIn", js)
        self.assertIn("zoomUIOut", js)
        self.assertIn("resetUIZoom", js)
        self.assertIn("document.documentElement.style.zoom", js)
        self.assertIn("dataflow_ui_zoom", js)

        # Keyboard shortcuts
        self.assertIn("NumpadAdd", js)
        self.assertIn("NumpadSubtract", js)
        self.assertIn("Numpad0", js)

    def test_user_settings_has_ui_zoom(self):
        """Ensure static/js/user_settings.js includes ui_zoom default, migration, and apply helper."""
        res = self.client.get("/static/js/user_settings.js")
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn("ui_zoom:             1.0", js)
        self.assertIn("'dataflow_ui_zoom':             'ui_zoom'", js)
        self.assertIn("_applyUIScale()", js)

    def test_index_html_has_ui_zoom_setting(self):
        """Ensure index.html includes setting-ui-zoom dropdown in Appearance settings."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('id="setting-ui-zoom"', html)
        self.assertIn("UI Display Scale", html)
        self.assertIn('value="1.0" selected', html)
        self.assertIn('value="1.25"', html)

    def test_menu_bar_js_syncs_ui_zoom(self):
        """Ensure static/js/menu_bar.js loads and saves setting-ui-zoom."""
        res = self.client.get("/static/js/menu_bar.js")
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn("setting-ui-zoom", js)
        self.assertIn("appUIScale.apply", js)

    def test_desktop_app_has_zoomable_flag(self):
        """Ensure desktop_app.py configures zoomable=True on native window."""
        with open("desktop_app.py", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("zoomable=True", content)


if __name__ == "__main__":
    unittest.main()
