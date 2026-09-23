"""
Unit and Integration tests for Production WSGI Server Readiness,
Multi-Session Execution Isolation, Cache Management (LRU/TTL),
and Path Sandboxing / Upload Security.
"""
import os
import io
import time
import json
import unittest
import pandas as pd
from backend.app import app, executor, WORKFLOWS_DIR
from backend.engine.security import (
    validate_safe_path,
    is_safe_path,
    sanitize_file_basename,
    validate_upload_file,
    SecurityError,
    ALLOWED_DATA_EXTENSIONS,
    MAX_UPLOAD_SIZE_BYTES
)
from backend.engine.cache_manager import SessionRunCacheManager, RunCacheEntry


class TestSecurityModule(unittest.TestCase):
    """Tests security sanitization and sandboxing rules."""

    def test_sanitize_file_basename(self):
        # Path traversal sequences
        self.assertEqual(sanitize_file_basename("../../secret.csv"), "secret.csv")
        self.assertEqual(sanitize_file_basename("..\\..\\secret.csv"), "secret.csv")
        self.assertEqual(sanitize_file_basename("subdir/data.xlsx"), "data.xlsx")

        # Dangerous characters and null bytes
        self.assertEqual(sanitize_file_basename("file\x00name*.csv"), "filename.csv")
        self.assertEqual(sanitize_file_basename("", fallback="file.dat"), "file.dat")
        self.assertEqual(sanitize_file_basename("   ", fallback="file.dat"), "file.dat")
        self.assertEqual(sanitize_file_basename("test!@#$%.csv"), "test.csv")

    def test_validate_safe_path(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        safe_file = os.path.join(base_dir, "customers.csv")
        
        # Valid path
        validated = validate_safe_path(safe_file, [base_dir])
        self.assertEqual(os.path.abspath(safe_file), validated)
        self.assertTrue(is_safe_path(safe_file, [base_dir]))

        # Path traversal out of base_dir
        unsafe_file = os.path.join(base_dir, "..", "backend", "app.py")
        self.assertFalse(is_safe_path(unsafe_file, [base_dir]))
        with self.assertRaises(SecurityError):
            validate_safe_path(unsafe_file, [base_dir])

    def test_validate_upload_file(self):
        # Valid extensions
        ok, msg = validate_upload_file("sales.csv", 1024)
        self.assertTrue(ok)
        self.assertIsNone(msg)

        ok, msg = validate_upload_file("report.XLSX", 2048)
        self.assertTrue(ok)

        # Disallowed extensions
        ok, msg = validate_upload_file("malicious.py", 512)
        self.assertFalse(ok)
        self.assertIn("not permitted", msg)

        ok, msg = validate_upload_file("malicious.exe", 512)
        self.assertFalse(ok)

        # File size exceeding max
        ok, msg = validate_upload_file("huge.csv", MAX_UPLOAD_SIZE_BYTES + 100)
        self.assertFalse(ok)
        self.assertIn("exceeds", msg)


class TestSessionRunCacheManager(unittest.TestCase):
    """Tests run/session isolation, LRU eviction, and TTL cleanup."""

    def test_run_isolation(self):
        cm = SessionRunCacheManager(max_runs=10, ttl_seconds=3600)
        
        df1 = pd.DataFrame({"a": [1, 2, 3]})
        df2 = pd.DataFrame({"a": [99, 100]})

        cm.store_run_data("run_1", {"node_1": {"O": df1}}, session_id="sess_A")
        cm.store_run_data("run_2", {"node_1": {"O": df2}}, session_id="sess_B")

        # Query run 1
        entry1 = cm.get_run("run_1", "sess_A")
        self.assertIsNotNone(entry1)
        self.assertEqual(len(entry1.data_cache["node_1"]["O"]), 3)

        # Query run 2
        entry2 = cm.get_run("run_2", "sess_B")
        self.assertIsNotNone(entry2)
        self.assertEqual(len(entry2.data_cache["node_1"]["O"]), 2)

        # Different session querying run_1 falls back or respects session
        entry_wrong_sess = cm.get_run("run_1", "sess_C")
        self.assertIsNone(entry_wrong_sess)

    def test_lru_capacity_eviction(self):
        cm = SessionRunCacheManager(max_runs=3, ttl_seconds=3600)

        for i in range(1, 5):
            cm.store_run_data(f"run_{i}", {"n": {"O": pd.DataFrame({"id": [i]})}}, session_id=f"sess_{i}")

        # Cache size must not exceed 3
        self.assertEqual(cm.size(), 3)

        # Oldest run_1 should have been evicted
        self.assertIsNone(cm.get_run("run_1"))
        # run_2, run_3, run_4 should be present
        self.assertIsNotNone(cm.get_run("run_2"))
        self.assertIsNotNone(cm.get_run("run_3"))
        self.assertIsNotNone(cm.get_run("run_4"))

    def test_ttl_cleanup(self):
        cm = SessionRunCacheManager(max_runs=10, ttl_seconds=1)
        
        cm.store_run_data("run_old", {"n": {"O": pd.DataFrame({"x": [1]})}}, session_id="sess_1")
        # Manually age the entry
        entry = cm.get_run("run_old")
        self.assertIsNotNone(entry)
        entry.created_at = time.time() - 100
        entry.last_accessed = time.time() - 100

        evicted = cm.cleanup_expired()
        self.assertIn("run_old", evicted)
        self.assertEqual(cm.size(), 0)


class TestSecurityEndpoints(unittest.TestCase):
    """Tests security enforcement across HTTP endpoints."""

    def setUp(self):
        self.client = app.test_client()

    def test_upload_rejection_for_bad_extension(self):
        data = {
            "file": (io.BytesIO(b"import os\nprint('exploit')"), "exploit.py")
        }
        res = self.client.post("/api/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        res_json = res.get_json()
        self.assertFalse(res_json["success"])
        self.assertIn("not permitted", res_json["error"])

    def test_upload_allowed_for_csv(self):
        csv_content = b"col1,col2\n1,test\n2,world\n"
        data = {
            "file": (io.BytesIO(csv_content), "secure_test.csv")
        }
        res = self.client.post("/api/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json["success"])
        self.assertIn("secure_test.csv", res_json["original_name"])

    def test_path_traversal_workflow_get(self):
        res = self.client.get("/api/workflow/..%2f..%2fbackend%2fapp.py")
        # Should either be 403 (traversal prohibited) or 404
        self.assertIn(res.status_code, [403, 404])

    def test_save_workflow_sanitizes_filename(self):
        try:
            res = self.client.post("/api/save-workflow", json={
                "name": "../../malicious_name",
                "nodes": []
            })
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            # Traversal components stripped
            self.assertNotIn("..", data["file"])
            self.assertNotIn("/", data["file"])
            self.assertNotIn("\\", data["file"])
        finally:
            mal_path = os.path.join(WORKFLOWS_DIR, "malicious_name.json")
            if os.path.exists(mal_path):
                os.remove(mal_path)

    def test_output_path_traversal_defense(self):
        res = self.client.get("/data/outputs/..%2f..%2fbackend%2fapp.py")
        self.assertIn(res.status_code, [403, 404])

    def test_isolated_execution_runs(self):
        # 1. Fetch sample workflow
        wf_res = self.client.get("/api/sample-workflow/sales_customer_enrichment.json")
        wf_data = wf_res.get_json()

        # 2. Run workflow for Session 1
        res1 = self.client.post("/api/run", json=wf_data, headers={"X-Session-ID": "test_session_1"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        run1_id = data1.get("run_id")
        self.assertIsNotNone(run1_id)

        # 3. Query node data explicitly providing run1_id and test_session_1
        node_res1 = self.client.get(f"/api/node-data/node_sort_1?port=O&run_id={run1_id}&session_id=test_session_1")
        self.assertEqual(node_res1.status_code, 200)
        self.assertTrue(node_res1.get_json()["available"])

        # 4. Query node profile with run1_id
        prof_res1 = self.client.get(f"/api/node-profile/node_sort_1?port=O&run_id={run1_id}&session_id=test_session_1")
        self.assertEqual(prof_res1.status_code, 200)
        self.assertTrue(prof_res1.get_json()["available"])

        # 5. Export with run1_id
        exp_res1 = self.client.get(f"/api/export/node_sort_1?port=O&format=csv&run_id={run1_id}&session_id=test_session_1")
        self.assertEqual(exp_res1.status_code, 200)
        self.assertEqual(exp_res1.mimetype, "text/csv")


if __name__ == "__main__":
    unittest.main()