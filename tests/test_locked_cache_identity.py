"""Persisted locked-node data must only be reused for the same node (type + config), never for a changed one."""
import pandas as pd
import pytest

from backend.engine.executor import WorkflowExecutor


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    pd.DataFrame({"Region": ["North", "South", "North"], "V": [1, 2, 3]}).to_csv(d / "t.csv", index=False)
    return d


def wf(region, locked=True, node_id="flt"):
    return {
        "nodes": [
            {"id": "src", "type": "input_data", "name": "in", "config": {"source_type": "file", "file_path": "t.csv"}},
            {"id": node_id, "type": "filter", "name": "f", "is_cached": locked,
             "config": {"mode": "basic", "conditions": [{"column": "Region", "operator": "==", "value": region}]}},
        ],
        "connections": [{"source": "src", "sourceHandle": "O", "target": node_id, "targetHandle": "T" if False else "I"}],
        "cached_node_ids": [node_id] if locked else [],
    }


def rows(executor, node_id="flt"):
    return len(executor.data_cache[node_id]["T"]) if "T" in executor.data_cache.get(node_id, {}) else len(executor.data_cache[node_id]["O"])


def reused(res, node_id="flt"):
    """True when the executor served this node from the frozen cache (not merely fast)."""
    return any("loaded from frozen cache" in l["message"] and f"({node_id})" in l["message"] for l in res.logs)


def run(data_dir, workflow):
    ex = WorkflowExecutor(context={"data_dir": str(data_dir)})  # fresh process-like executor: only the disk cache is shared
    res = ex.run(workflow)
    assert res.success, res.error
    return ex, res


def test_unchanged_locked_node_is_reused_after_restart(data_dir):
    run(data_dir, wf("North"))
    _, second = run(data_dir, wf("North"))
    assert reused(second)


def test_edited_locked_node_is_recomputed_not_stale(data_dir):
    run(data_dir, wf("North"))
    ex, second = run(data_dir, wf("South"))
    assert not reused(second)
    port = "T" if "T" in ex.data_cache["flt"] else "O"
    assert list(ex.data_cache["flt"][port]["Region"].unique()) == ["South"]


def test_different_workflow_reusing_node_id_does_not_load_old_data(data_dir):
    run(data_dir, wf("North", node_id="n1"))
    other = wf("South", node_id="n1")
    ex, res = run(data_dir, other)
    assert not reused(res, "n1")


def test_legacy_cache_without_sidecar_is_ignored(data_dir):
    ex, _ = run(data_dir, wf("North"))
    cache_dir = data_dir / ".cache"
    for f in cache_dir.glob("*__meta.json"):
        f.unlink()
    _, res = run(data_dir, wf("North"))
    assert not reused(res)


def test_fingerprint_depends_on_type_and_config_only():
    fp = WorkflowExecutor.node_fingerprint
    base = {"id": "a", "type": "filter", "config": {"x": 1}, "x": 10, "y": 20, "name": "n"}
    assert fp(base) == fp({**base, "id": "b", "x": 99, "name": "other"})  # moving/renaming does not invalidate
    assert fp(base) != fp({**base, "config": {"x": 2}})
    assert fp(base) != fp({**base, "type": "sort"})
