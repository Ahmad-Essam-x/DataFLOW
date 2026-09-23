"""
Unit tests for SpillableRunDataCache, Arrow/Feather disk-spill caching,
precomputed profiling, execution pruning, and cache purge endpoints.
"""
import os
import shutil
import tempfile
import unittest
import pandas as pd
import numpy as np

from backend.engine.cache_manager import (
    SpillableRunDataCache,
    RunCacheEntry,
    SessionRunCacheManager,
    compute_column_metadata,
    HAS_PYARROW
)
from backend.engine.executor import WorkflowExecutor
from backend.app import app


class TestSpillableRunDataCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_cache_")
        self.cache = SpillableRunDataCache(
            run_id="test_run_1",
            cache_root_dir=self.temp_dir,
            max_in_memory_nodes=2
        )

    def tearDown(self):
        self.cache.destroy()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dict_interface(self):
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["Alpha", "Beta", "Gamma"]})
        self.cache["node_1"] = {"O": df}

        self.assertIn("node_1", self.cache)
        self.assertEqual(len(self.cache), 1)
        self.assertIn("node_1", list(self.cache.keys()))

        retrieved = self.cache["node_1"]["O"]
        self.assertEqual(len(retrieved), 3)
        self.assertListEqual(list(retrieved.columns), ["id", "name"])

    def test_disk_feather_spill_and_lru(self):
        """Verify that when > max_in_memory_nodes are stored, oldest is evicted from RAM but loads from disk."""
        df1 = pd.DataFrame({"val": range(100)})
        df2 = pd.DataFrame({"val": range(200)})
        df3 = pd.DataFrame({"val": range(300)})

        self.cache["n1"] = {"O": df1}
        self.cache["n2"] = {"O": df2}
        self.assertIn("n1", self.cache._memory_lru)
        self.assertIn("n2", self.cache._memory_lru)

        # Adding 3rd node exceeds capacity (2) -> n1 should be evicted from RAM
        self.cache["n3"] = {"O": df3}
        self.assertIn("n3", self.cache._memory_lru)
        self.assertIn("n2", self.cache._memory_lru)
        self.assertNotIn("n1", self.cache._memory_lru)

        # But n1 is still present in cache and on disk
        self.assertIn("n1", self.cache)
        reloaded_n1 = self.cache["n1"]["O"]
        self.assertEqual(len(reloaded_n1), 100)
        # Now n1 is brought back into RAM, and n2 should be evicted
        self.assertIn("n1", self.cache._memory_lru)
        self.assertNotIn("n2", self.cache._memory_lru)

    def test_precomputed_column_metadata(self):
        df = pd.DataFrame({
            "num": [10, 20, np.nan, 40],
            "txt": ["hello", "", "world", None],
            "flag": [True, False, True, True]
        })
        meta = compute_column_metadata(df)
        self.assertEqual(len(meta), 3)

        num_meta = next(m for m in meta if m["name"] == "num")
        self.assertEqual(num_meta["null_count"], 1)
        self.assertIn("histogram", num_meta)
        self.assertGreater(len(num_meta["histogram"]), 0)

        txt_meta = next(m for m in meta if m["name"] == "txt")
        self.assertEqual(txt_meta["blank_count"], 1)
        self.assertEqual(txt_meta["null_count"], 1)

    def test_evict_from_memory(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        self.cache["upstream_node"] = {"O": df}
        self.assertIn("upstream_node", self.cache._memory_lru)

        self.cache.evict_from_memory("upstream_node")
        self.assertNotIn("upstream_node", self.cache._memory_lru)
        self.assertIn("upstream_node", self.cache)

        # Reloading works seamlessly
        reloaded = self.cache.get_dataframe("upstream_node", "O")
        self.assertEqual(len(reloaded), 3)

    def test_lazy_column_metadata(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "", None]})
        self.cache["lazy_node"] = {"O": df}
        # Verify that immediately after setting, column_meta is None in internal meta
        self.assertIsNone(self.cache._meta["lazy_node"]["O"]["column_meta"])

        # Call get_column_metadata and verify it computes lazily
        meta = self.cache.get_column_metadata("lazy_node", "O")
        self.assertIsNotNone(meta)
        self.assertEqual(len(meta), 2)
        # Verify it is now cached in _meta
        self.assertIsNotNone(self.cache._meta["lazy_node"]["O"]["column_meta"])


class TestSessionRunCacheManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_mgr_")
        self.mgr = SessionRunCacheManager(
            max_runs=2,
            ttl_seconds=300,
            cache_root_dir=self.temp_dir,
            max_in_memory_nodes=2
        )

    def tearDown(self):
        self.mgr.purge_all()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_max_runs_eviction(self):
        r1 = self.mgr.create_run(run_id="run_1")
        r1.set_node_outputs("n1", {"O": pd.DataFrame({"x": [1]})})

        r2 = self.mgr.create_run(run_id="run_2")
        r2.set_node_outputs("n1", {"O": pd.DataFrame({"x": [2]})})

        self.assertEqual(len(self.mgr), 2)

        # 3rd run should evict run_1
        r3 = self.mgr.create_run(run_id="run_3")
        r3.set_node_outputs("n1", {"O": pd.DataFrame({"x": [3]})})

        self.assertEqual(len(self.mgr), 2)
        self.assertIsNone(self.mgr.get_run("run_1"))
        self.assertIsNotNone(self.mgr.get_run("run_2"))
        self.assertIsNotNone(self.mgr.get_run("run_3"))

    def test_purge_all(self):
        r1 = self.mgr.create_run(run_id="run_p1")
        r1.set_node_outputs("n1", {"O": pd.DataFrame({"a": range(100)})})
        self.assertGreaterEqual(self.mgr.size(), 1)

        self.mgr.purge_all()
        self.assertEqual(len(self.mgr), 0)
        self.assertIsNone(self.mgr.get_latest_run())


class TestCacheApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_cache_stats(self):
        res = self.client.get("/api/cache/stats")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("runs_count", data)
        self.assertIn("disk_bytes", data)
        self.assertIn("process_memory_mb", data)

    def test_purge_cache_endpoint(self):
        res = self.client.post("/api/cache/purge")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("message", data)
