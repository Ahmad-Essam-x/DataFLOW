"""
Unit tests for Desktop Application Packaging, Assets, Shortcuts, and CLI Workflow Loading.
"""
import os
import sys
import json
import unittest
import tempfile
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop.assets import generate_app_icon
from desktop.shortcuts import create_windows_shortcut, install_desktop_shortcuts
from backend.app import app, set_initial_workflow, BASE_DIR, DATA_DIR, WORKFLOWS_DIR


class TestDesktopPackaging(unittest.TestCase):
    """Tests for desktop application packaging utilities and endpoints."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_app_icon_generation(self):
        """Test that generate_app_icon creates valid .ico and .png files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = os.path.join(tmp_dir, "assets")
            static_dir = os.path.join(tmp_dir, "static")
            
            ico_path, png_path = generate_app_icon(out_dir, static_dir)
            
            self.assertTrue(os.path.exists(ico_path), "Icon .ico should exist")
            self.assertTrue(os.path.exists(png_path), "Icon .png should exist")
            self.assertTrue(os.path.exists(os.path.join(static_dir, "icon.png")), "Static icon should exist")

            with Image.open(png_path) as img:
                self.assertEqual(img.size, (256, 256))
                self.assertEqual(img.format, "PNG")

            with Image.open(ico_path) as ico:
                self.assertEqual(ico.format, "ICO")

    def test_app_info_endpoint(self):
        """Test that /api/app-info returns valid desktop metadata."""
        resp = self.client.get("/api/app-info")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertEqual(data.get("app_name"), "Antigravity DataFlow")
        self.assertIn("version", data)
        self.assertIn("data_dir", data)
        self.assertIn("workflows_dir", data)
        self.assertIn("frozen", data)

    def test_initial_workflow_empty(self):
        """Test that /api/initial-workflow returns None when no workflow specified."""
        set_initial_workflow(None)
        resp = self.client.get("/api/initial-workflow")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data.get("workflow"))

    def test_initial_workflow_by_filename(self):
        """Test loading initial workflow by filename."""
        set_initial_workflow("sales_customer_enrichment.json")
        resp = self.client.get("/api/initial-workflow")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertIsNotNone(data.get("workflow"))
        self.assertIn("nodes", data.get("workflow", {}))
        self.assertEqual(data.get("name"), "Customer Sales Analysis")

    def test_initial_workflow_by_name(self):
        """Test loading initial workflow by human-readable name."""
        set_initial_workflow("Customer Sales Analysis")
        resp = self.client.get("/api/initial-workflow")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertIsNotNone(data.get("workflow"))
        self.assertEqual(data.get("name"), "Customer Sales Analysis")

    def test_initial_workflow_by_query_param(self):
        """Test loading initial workflow via ?open= query parameter."""
        set_initial_workflow(None)
        resp = self.client.get("/api/initial-workflow?open=sales_customer_enrichment.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertIsNotNone(data.get("workflow"))
        self.assertEqual(data.get("name"), "Customer Sales Analysis")

    def test_initial_workflow_not_found(self):
        """Test loading non-existent workflow gracefully returns warning."""
        set_initial_workflow("non_existent_random_workflow_987654.json")
        resp = self.client.get("/api/initial-workflow")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertIsNone(data.get("workflow"))
        self.assertIn("warning", data)

    def test_windows_shortcut_creation(self):
        """Test creating a Windows shortcut file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_target = os.path.join(tmp_dir, "dummy_app.exe")
            with open(dummy_target, "w") as f:
                f.write("test")
            
            shortcut_path = os.path.join(tmp_dir, "TestApp.lnk")
            ok, res_path = create_windows_shortcut(dummy_target, shortcut_path)
            
            self.assertTrue(ok, f"Shortcut creation should succeed: {res_path}")
            self.assertTrue(os.path.exists(shortcut_path), "Shortcut .lnk file should exist")

    def test_desktop_shortcuts_installation(self):
        """Test install_desktop_shortcuts execution."""
        res = install_desktop_shortcuts()
        self.assertIn("desktop", res)
        self.assertIn("start_menu", res)
        self.assertTrue(res["desktop"][0])
        self.assertTrue(res["start_menu"][0])


if __name__ == "__main__":
    unittest.main()
