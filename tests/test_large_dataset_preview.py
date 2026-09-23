"""
Comprehensive tests for High-Performance Large Dataset Preview Architecture.
Tests server-side pagination, sample_mode (page, random, head), safe page_size capping,
wide table detection, memory footprint estimation, and API endpoint integration.
"""
import pytest
import pandas as pd
import numpy as np
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app, executor
from backend.engine.cache_manager import SpillableRunDataCache


@pytest.fixture
def test_client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def large_cache_setup():
    """Sets up a mock node execution with large and wide datasets in executor's cache."""
    # 1. Tall dataset (5,000 rows, 5 columns)
    np.random.seed(42)
    tall_df = pd.DataFrame({
        "ID": np.arange(1, 5001),
        "Category": np.random.choice(["Alpha", "Beta", "Gamma", "Delta"], size=5000),
        "Score": np.random.uniform(10.0, 99.9, size=5000),
        "Notes": ["Long text description " * 15 + f"record #{i}" for i in range(5000)],
        "Flag": np.random.choice([True, False], size=5000)
    })

    # 2. Wide dataset (50 rows, 45 columns)
    wide_data = {f"Col_{i}": np.random.randint(1, 100, size=50) for i in range(45)}
    wide_df = pd.DataFrame(wide_data)

    # 3. Small dataset (10 rows, 3 columns)
    small_df = pd.DataFrame({
        "A": range(10),
        "B": ["x"] * 10,
        "C": [1.1] * 10
    })

    node_id_tall = "node_tall_preview_test"
    node_id_wide = "node_wide_preview_test"
    node_id_small = "node_small_preview_test"

    executor.data_cache[node_id_tall] = {"O": tall_df}
    executor.data_cache[node_id_wide] = {"O": wide_df}
    executor.data_cache[node_id_small] = {"O": small_df}

    yield {
        "tall_id": node_id_tall,
        "wide_id": node_id_wide,
        "small_id": node_id_small,
        "tall_df": tall_df,
        "wide_df": wide_df,
        "small_df": small_df
    }

    # Teardown
    executor.data_cache.pop(node_id_tall, None)
    executor.data_cache.pop(node_id_wide, None)
    executor.data_cache.pop(node_id_small, None)


class TestLargeDatasetPreviewBackend:
    """Tests for executor.get_node_data() enhancements."""

    def test_default_page_mode_slicing(self, large_cache_setup):
        data = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=1,
            page_size=100,
            sample_mode="page"
        )
        assert data["available"] is True
        assert len(data["records"]) == 100
        assert data["records"][0]["ID"] == 1
        assert data["records"][99]["ID"] == 100
        assert data["pagination"]["total_records"] == 5000
        assert data["pagination"]["total_pages"] == 50
        assert data["pagination"]["rendered_records"] == 100
        assert data["is_partial"] is True
        assert data["is_wide_table"] is False
        assert data["sample_mode"] == "page"
        assert "memory_bytes" in data
        assert "memory_formatted" in data
        assert data["memory_bytes"] > 0

    def test_page_navigation(self, large_cache_setup):
        data_p2 = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=2,
            page_size=100,
            sample_mode="page"
        )
        assert data_p2["records"][0]["ID"] == 101
        assert data_p2["records"][99]["ID"] == 200
        assert data_p2["pagination"]["page"] == 2
        assert data_p2["pagination"]["has_prev"] is True
        assert data_p2["pagination"]["has_next"] is True

    def test_random_sample_mode(self, large_cache_setup):
        data = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=1,
            page_size=150,
            sample_mode="random"
        )
        assert data["available"] is True
        assert len(data["records"]) == 150
        assert data["sample_mode"] == "random"
        assert data["is_partial"] is True

        # Check that records are sampled and not strictly 1..150
        ids = [r["ID"] for r in data["records"]]
        assert len(set(ids)) == 150
        assert ids != list(range(1, 151))  # random sampling should not match sequential head

    def test_head_sample_mode(self, large_cache_setup):
        data = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=5,  # page should be ignored in head mode
            page_size=50,
            sample_mode="head"
        )
        assert data["available"] is True
        assert len(data["records"]) == 50
        assert data["records"][0]["ID"] == 1
        assert data["records"][49]["ID"] == 50
        assert data["sample_mode"] == "head"

    def test_page_size_capping_at_1000(self, large_cache_setup):
        """Ensures huge requested page sizes are capped to 1,000 rows to prevent OOM."""
        data = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=1,
            page_size=10000,
            sample_mode="page"
        )
        assert data["available"] is True
        assert len(data["records"]) == 1000
        assert data["pagination"]["page_size"] == 1000

    def test_page_size_minimum_bound(self, large_cache_setup):
        """Ensures invalid/negative page size defaults to at least 1."""
        data = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=1,
            page_size=-50,
            sample_mode="page"
        )
        assert data["pagination"]["page_size"] == 1
        assert len(data["records"]) == 1

    def test_wide_table_detection(self, large_cache_setup):
        # 45 columns > 30 threshold
        data_wide = executor.get_node_data(
            node_id=large_cache_setup["wide_id"],
            port="O"
        )
        assert data_wide["is_wide_table"] is True
        assert len(data_wide["columns"]) == 45

        # 5 columns <= 30 threshold
        data_tall = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O"
        )
        assert data_tall["is_wide_table"] is False

    def test_small_dataset_is_not_partial(self, large_cache_setup):
        data = executor.get_node_data(
            node_id=large_cache_setup["small_id"],
            port="O",
            page=1,
            page_size=100
        )
        assert data["is_partial"] is False
        assert len(data["records"]) == 10
        assert data["pagination"]["total_records"] == 10

    def test_search_filtering_with_large_data(self, large_cache_setup):
        data = executor.get_node_data(
            node_id=large_cache_setup["tall_id"],
            port="O",
            page=1,
            page_size=50,
            search="Alpha"
        )
        assert data["available"] is True
        assert len(data["records"]) <= 50
        for r in data["records"]:
            assert r["Category"] == "Alpha"


class TestLargeDatasetPreviewAPI:
    """Tests for GET /api/node-data/<node_id> route."""

    def test_api_node_data_with_sample_mode_page(self, test_client, large_cache_setup):
        url = f"/api/node-data/{large_cache_setup['tall_id']}?port=O&page=1&page_size=75&sample_mode=page"
        res = test_client.get(url)
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["available"] is True
        assert len(payload["records"]) == 75
        assert payload["sample_mode"] == "page"
        assert payload["is_partial"] is True
        assert payload["is_wide_table"] is False
        assert "memory_formatted" in payload

    def test_api_node_data_with_sample_mode_random(self, test_client, large_cache_setup):
        url = f"/api/node-data/{large_cache_setup['tall_id']}?port=O&page=1&page_size=50&sample_mode=random"
        res = test_client.get(url)
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["available"] is True
        assert len(payload["records"]) == 50
        assert payload["sample_mode"] == "random"

    def test_api_node_data_with_sample_mode_head(self, test_client, large_cache_setup):
        url = f"/api/node-data/{large_cache_setup['tall_id']}?port=O&page=1&page_size=25&sample_mode=head"
        res = test_client.get(url)
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["available"] is True
        assert len(payload["records"]) == 25
        assert payload["sample_mode"] == "head"
        assert payload["records"][0]["ID"] == 1
        assert payload["records"][24]["ID"] == 25

    def test_api_wide_table_metadata(self, test_client, large_cache_setup):
        url = f"/api/node-data/{large_cache_setup['wide_id']}?port=O"
        res = test_client.get(url)
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["is_wide_table"] is True
        assert len(payload["columns"]) == 45
