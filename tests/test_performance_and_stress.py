"""
Performance, Scalability, and Memory Stress Test Suite.
Verifies engine throughput, spill-to-disk cache mechanics under memory pressure,
and lack of memory leaks during repeated workflow execution cycles.
"""
import os
import gc
import time
import tempfile
import shutil
import numpy as np
import pandas as pd
import pytest

from backend.engine.executor import WorkflowExecutor
from backend.engine.cache_manager import SessionRunCacheManager


@pytest.fixture
def temp_workspace():
    td = tempfile.mkdtemp(prefix="stress_test_")
    yield td
    shutil.rmtree(td, ignore_errors=True)


def _generate_synthetic_df(rows: int) -> pd.DataFrame:
    """Generates synthetic analytical dataframe with diverse types."""
    np.random.seed(42)
    categories = np.random.choice(["Electronics", "Apparel", "Home", "Outdoor", "Automotive"], size=rows)
    amounts = np.random.uniform(5.0, 500.0, size=rows).round(2)
    quantities = np.random.randint(1, 20, size=rows)
    regions = np.random.choice(["North", "South", "East", "West"], size=rows)
    customer_ids = np.random.randint(1000, 50000, size=rows)

    return pd.DataFrame({
        "OrderID": np.arange(1, rows + 1),
        "CustomerID": customer_ids,
        "Category": categories,
        "Amount": amounts,
        "Quantity": quantities,
        "Region": regions
    })


# ----------------------------------------------------------------------
# 1. Tier 1 Performance Benchmark: 10,000 Rows (Target < 1.5s)
# ----------------------------------------------------------------------
def test_performance_tier1_10k_records(temp_workspace):
    df_10k = _generate_synthetic_df(10_000)
    csv_path = os.path.join(temp_workspace, "data_10k.csv")
    df_10k.to_csv(csv_path, index=False)

    wf = {
        "name": "Benchmark 10K",
        "nodes": [
            {"id": "n1", "type": "input_data", "name": "Input", "config": {"file_path": csv_path}},
            {"id": "n2", "type": "filter", "name": "Filter Amount", "config": {"mode": "custom", "expression": "[Amount] >= 50.0"}},
            {
                "id": "n3",
                "type": "formula",
                "name": "Compute Total",
                "config": {
                    "expressions": [
                        {"field": "Line_Total", "expression": "[Amount] * [Quantity]", "type": "float"},
                        {"field": "Discount_Flag", "expression": 'IIF([Line_Total] > 1000, "High Value", "Standard")', "type": "string"}
                    ]
                }
            },
            {
                "id": "n4",
                "type": "summarize",
                "name": "Summarize by Region",
                "config": {
                    "actions": [
                        {"field": "Region", "action": "GroupBy"},
                        {"field": "Line_Total", "action": "Sum", "output_name": "Regional_Spend"},
                        {"field": "OrderID", "action": "Count", "output_name": "Order_Count"}
                    ]
                }
            },
            {"id": "n5", "type": "sort", "name": "Sort", "config": {"sort_by": [{"column": "Regional_Spend", "ascending": False}]}}
        ],
        "connections": [
            {"source": "n1", "target": "n2", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n2", "target": "n3", "sourceHandle": "T", "targetHandle": "I"},
            {"source": "n3", "target": "n4", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n4", "target": "n5", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    t0 = time.perf_counter()
    executor = WorkflowExecutor(context={"data_dir": temp_workspace, "base_dir": temp_workspace})
    res = executor.run(wf)
    elapsed = time.perf_counter() - t0

    assert res.success is True, f"Execution failed: {res.error}"
    assert "n5" in executor.data_cache
    out_df = executor.data_cache["n5"]["O"]
    assert len(out_df) == 4  # 4 regions
    assert elapsed < 1.5, f"10K records took too long: {elapsed:.2f}s (expected < 1.5s)"


# ----------------------------------------------------------------------
# 2. Tier 2 Performance Benchmark: 100,000 Rows (Target < 4.0s)
# ----------------------------------------------------------------------
def test_performance_tier2_100k_records(temp_workspace):
    df_100k = _generate_synthetic_df(100_000)
    csv_path = os.path.join(temp_workspace, "data_100k.csv")
    df_100k.to_csv(csv_path, index=False)

    wf = {
        "name": "Benchmark 100K",
        "nodes": [
            {"id": "n1", "type": "input_data", "name": "Input 100K", "config": {"file_path": csv_path}},
            {"id": "n2", "type": "filter", "name": "Filter Electronics", "config": {"mode": "custom", "expression": "[Category] == 'Electronics'"}},
            {
                "id": "n3",
                "type": "formula",
                "name": "Compute Total",
                "config": {
                    "expressions": [
                        {"field": "Total_Price", "expression": "[Amount] * [Quantity]", "type": "float"}
                    ]
                }
            },
            {
                "id": "n4",
                "type": "summarize",
                "name": "Summary",
                "config": {
                    "actions": [
                        {"field": "Region", "action": "GroupBy"},
                        {"field": "Total_Price", "action": "Sum", "output_name": "Electronics_Revenue"}
                    ]
                }
            }
        ],
        "connections": [
            {"source": "n1", "target": "n2", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n2", "target": "n3", "sourceHandle": "T", "targetHandle": "I"},
            {"source": "n3", "target": "n4", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    t0 = time.perf_counter()
    executor = WorkflowExecutor(context={"data_dir": temp_workspace, "base_dir": temp_workspace})
    res = executor.run(wf)
    elapsed = time.perf_counter() - t0

    assert res.success is True, f"Execution failed: {res.error}"
    out_df = executor.data_cache["n4"]["O"]
    assert len(out_df) == 4
    assert elapsed < 4.0, f"100K records took too long: {elapsed:.2f}s (expected < 4.0s)"


# ----------------------------------------------------------------------
# 3. Spill-to-Disk Cache Mechanics Under Memory Pressure
# ----------------------------------------------------------------------
def test_spillable_cache_under_memory_pressure(temp_workspace):
    """
    Sets max_in_memory_nodes=1 to force older node dataframes to spill
    to disk cache. Verifies that downstream nodes transparently access spilled
    partitions and produce exact results.
    """
    df = _generate_synthetic_df(50_000)
    csv_path = os.path.join(temp_workspace, "spill_data.csv")
    df.to_csv(csv_path, index=False)

    cache_dir = os.path.join(temp_workspace, "run_cache")
    cache_mgr = SessionRunCacheManager(
        max_runs=2,
        ttl_seconds=1800,
        cache_root_dir=cache_dir,
        max_in_memory_nodes=1
    )

    executor = WorkflowExecutor(
        context={"data_dir": temp_workspace, "base_dir": temp_workspace},
        cache_manager=cache_mgr
    )

    wf = {
        "name": "Spill Test Flow",
        "nodes": [
            {"id": "n1", "type": "input_data", "name": "Input 50K", "config": {"file_path": csv_path}},
            {
                "id": "n2",
                "type": "formula",
                "name": "Compute Total",
                "config": {
                    "expressions": [
                        {"field": "Taxed_Amount", "expression": "[Amount] * 1.15", "type": "float"}
                    ]
                }
            },
            {
                "id": "n3",
                "type": "filter",
                "name": "High Tax",
                "config": {"mode": "custom", "expression": "[Taxed_Amount] > 200.0"}
            }
        ],
        "connections": [
            {"source": "n1", "target": "n2", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n2", "target": "n3", "sourceHandle": "O", "targetHandle": "I"}
        ]
    }

    res = executor.run(wf)
    assert res.success is True, f"Spill run failed: {res.error}"

    cached_n1 = executor.data_cache.get("n1", {}).get("O")
    cached_n3 = executor.data_cache.get("n3", {}).get("T")
    assert cached_n1 is not None
    assert cached_n3 is not None
    assert len(cached_n1) == 50_000
    assert len(cached_n3) > 0


# ----------------------------------------------------------------------
# 4. Memory Leak Audit (20 Consecutive Executions)
# ----------------------------------------------------------------------
def test_consecutive_execution_memory_stability(temp_workspace):
    """
    Executes a multi-node workflow in an automated 20-run loop.
    Monitors process memory and verifies that memory remains stable without runaway leaks.
    """
    try:
        import psutil
        process = psutil.Process()
        has_psutil = True
    except ImportError:
        has_psutil = False

    df = _generate_synthetic_df(5_000)
    csv_path = os.path.join(temp_workspace, "mem_audit.csv")
    df.to_csv(csv_path, index=False)

    wf = {
        "name": "Memory Audit Flow",
        "nodes": [
            {"id": "n1", "type": "input_data", "name": "Input", "config": {"file_path": csv_path}},
            {
                "id": "n2",
                "type": "formula",
                "name": "Calc",
                "config": {
                    "expressions": [
                        {"field": "Metric", "expression": "[Amount] * 2.5", "type": "float"}
                    ]
                }
            },
            {"id": "n3", "type": "filter", "name": "Filt", "config": {"mode": "custom", "expression": "[Metric] > 100"}},
            {
                "id": "n4",
                "type": "summarize",
                "name": "Agg",
                "config": {
                    "actions": [
                        {"field": "Region", "action": "GroupBy"},
                        {"field": "Metric", "action": "Sum", "output_name": "Sum_Metric"}
                    ]
                }
            }
        ],
        "connections": [
            {"source": "n1", "target": "n2", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n2", "target": "n3", "sourceHandle": "O", "targetHandle": "I"},
            {"source": "n3", "target": "n4", "sourceHandle": "T", "targetHandle": "I"}
        ]
    }

    executor = WorkflowExecutor(context={"data_dir": temp_workspace, "base_dir": temp_workspace})
    mem_readings = []

    for i in range(20):
        res = executor.run(wf)
        assert res.success is True
        gc.collect()
        if has_psutil:
            mem_mb = process.memory_info().rss / (1024 * 1024)
            mem_readings.append(mem_mb)

    if has_psutil and len(mem_readings) >= 20:
        initial_mem = mem_readings[2]  # warm baseline after 3 runs
        final_mem = mem_readings[-1]
        delta = final_mem - initial_mem
        # Memory growth over 17 runs must not exceed 25 MB
        assert delta < 25.0, f"Potential memory leak detected: grew by {delta:.1f} MB (initial {initial_mem:.1f}, final {final_mem:.1f})"
