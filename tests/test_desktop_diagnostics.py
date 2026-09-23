"""
Unit tests for Desktop Pre-flight Diagnostics, System Dependency Verification,
Persistent Logging, and Multi-Tier Fallback Cascade.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop.diagnostics import (
    check_os_and_arch,
    check_webview2_runtime,
    check_edge_browser,
    check_default_browser,
    check_loopback_socket,
    check_filesystem_permissions,
    check_system_resources,
    run_system_diagnostics,
    format_diagnostic_report,
    get_launch_log_path,
    setup_persistent_logger,
    show_native_error_dialog,
    WEBVIEW2_DOWNLOAD_URL
)
import desktop_app


class TestDesktopDiagnostics(unittest.TestCase):
    """Test suite for desktop pre-flight diagnostics and dependency verifier."""

    def test_os_and_arch_check(self):
        """Test OS and processor architecture validation."""
        res = check_os_and_arch()
        self.assertIn("status", res)
        self.assertIn("details", res)
        self.assertIn(res["status"], ["PASS", "WARN", "FAIL"])
        self.assertIn("name", res)
        self.assertEqual(res["name"], "Operating System & Architecture")

    def test_webview2_runtime_detected(self):
        """Test WebView2 detection returns valid report."""
        res = check_webview2_runtime()
        self.assertIn("status", res)
        self.assertIn(res["status"], ["PASS", "WARN"])
        if res["status"] == "WARN":
            self.assertIn("fwlink", res.get("remediation", ""))

    def test_webview2_runtime_missing_mock(self):
        """Test WebView2 behavior when registry key is missing."""
        with patch("winreg.OpenKey", side_effect=OSError("Key not found")):
            res = check_webview2_runtime()
            self.assertEqual(res["status"], "WARN")
            self.assertIn(WEBVIEW2_DOWNLOAD_URL, res["remediation"])

    def test_edge_browser_check(self):
        """Test Microsoft Edge executable detection."""
        res = check_edge_browser()
        self.assertIn("status", res)
        self.assertIn(res["status"], ["PASS", "WARN"])
        self.assertEqual(res["name"], "Microsoft Edge Browser (Tier 2 Fallback)")

    def test_edge_browser_missing_mock(self):
        """Test Edge detection fallback when executable not on disk."""
        with patch("os.path.exists", return_value=False), patch("shutil.which", return_value=None):
            res = check_edge_browser()
            self.assertEqual(res["status"], "WARN")

    def test_default_browser_check(self):
        """Test default browser registration detection."""
        res = check_default_browser()
        self.assertIn("status", res)
        self.assertIn(res["status"], ["PASS", "WARN"])
        self.assertEqual(res["name"], "Default Web Browser (Tier 3 Fallback)")

    def test_loopback_socket_operational(self):
        """Test loopback 127.0.0.1 socket binding."""
        res = check_loopback_socket()
        self.assertEqual(res["status"], "PASS")
        self.assertIn("127.0.0.1", res["details"])

    def test_loopback_socket_failure_simulation(self):
        """Test loopback socket failure handling."""
        with patch("socket.socket.bind", side_effect=OSError("Permission denied")):
            res = check_loopback_socket()
            self.assertEqual(res["status"], "FAIL")
            self.assertIn("remediation", res)

    def test_filesystem_permissions(self):
        """Test AppData read/write/delete permission verification."""
        res = check_filesystem_permissions()
        self.assertEqual(res["status"], "PASS")
        self.assertIn("verified", res["details"])

    def test_system_resources_check(self):
        """Test RAM and free disk space check."""
        res = check_system_resources()
        self.assertIn("status", res)
        self.assertIn("details", res)
        self.assertIn("Disk", res["details"])

    def test_run_system_diagnostics_structure(self):
        """Test that run_system_diagnostics aggregates all checks into a valid report."""
        report = run_system_diagnostics()
        self.assertIn("overall_status", report)
        self.assertIn(report["overall_status"], ["PASS", "WARN", "FAIL"])
        self.assertIn("resolved_launch_tier", report)
        self.assertIn("checks", report)
        self.assertGreaterEqual(len(report["checks"]), 6)
        self.assertIn("log_path", report)

    def test_format_diagnostic_report(self):
        """Test ASCII report table rendering."""
        report = run_system_diagnostics()
        formatted = format_diagnostic_report(report)
        self.assertIn("ANTIGRAVITY DATAFLOW", formatted)
        self.assertIn("Overall Status", formatted)
        self.assertIn("Target Launch Engine", formatted)
        self.assertTrue("[PASS]" in formatted or "[WARN]" in formatted or "[FAIL]" in formatted)

    def test_custom_launch_log_path(self):
        """Test resolving custom launch log file path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_log = os.path.join(tmp_dir, "custom_launch.log")
            resolved = get_launch_log_path(custom_log)
            self.assertEqual(resolved, os.path.abspath(custom_log))

    def test_setup_persistent_logger_creates_file(self):
        """Test that setup_persistent_logger creates the target log file and writes to it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "test_launch.log")
            resolved = setup_persistent_logger(log_path)
            self.assertTrue(os.path.exists(resolved))
            # Cleanly close file handler so Windows file lock is released before directory cleanup
            import logging
            from desktop.diagnostics import logger
            for h in list(logger.handlers):
                if isinstance(h, logging.FileHandler):
                    h.close()
                    logger.removeHandler(h)

    def test_show_native_error_dialog_non_blocking_mock(self):
        """Test that native error dialog wrapper executes cleanly without raising."""
        with patch("ctypes.windll.user32.MessageBoxW", return_value=1):
            show_native_error_dialog("Test Title", "Test Message", "C:\\test\\launch.log")

    def test_cli_diagnose_flag(self):
        """Test desktop_app.py --diagnose execution."""
        with patch("sys.argv", ["desktop_app.py", "--diagnose"]):
            code = desktop_app.main()
            self.assertEqual(code, 0)

    def test_cli_check_deps_flag(self):
        """Test desktop_app.py --check-deps execution."""
        with patch("sys.argv", ["desktop_app.py", "--check-deps"]):
            code = desktop_app.main()
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
