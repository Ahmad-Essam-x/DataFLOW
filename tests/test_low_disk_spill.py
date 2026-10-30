"""When the disk is full the spill cache must keep data in memory (no loss, no crash, no junk files)."""
import errno
import os

import pandas as pd
import pyarrow.feather as feather

from backend.engine import cache_manager
from backend.engine.cache_manager import SpillableRunDataCache


def _df(n=5):
    return pd.DataFrame({"a": range(n), "b": [str(i) for i in range(n)]})


def test_failed_spill_keeps_data_available(tmp_path, monkeypatch):
    cache = SpillableRunDataCache("run_disk_full", cache_root_dir=str(tmp_path), max_in_memory_nodes=1)

    def disk_full(df, path, **kwargs):
        with open(path, "wb") as fh:  # simulate a truncated file left behind by the failed write
            fh.write(b"partial")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(cache_manager.feather, "write_feather", disk_full)

    cache["n1"] = {"O": _df(3)}
    cache["n2"] = {"O": _df(4)}  # evicts n1 -> spill attempt fails

    assert len(cache["n1"]["O"]) == 3          # still readable, not lost
    assert len(cache["n2"]["O"]) == 4
    leftovers = [f for f in os.listdir(cache.cache_dir) if f.endswith(".feather")]
    assert leftovers == []                      # truncated file removed


def test_spill_works_normally_when_disk_is_fine(tmp_path):
    cache = SpillableRunDataCache("run_ok", cache_root_dir=str(tmp_path), max_in_memory_nodes=1)
    cache["n1"] = {"O": _df(3)}
    cache["n2"] = {"O": _df(4)}  # evicts n1 to disk
    assert any(f.endswith(".feather") for f in os.listdir(cache.cache_dir))
    pd.testing.assert_frame_equal(cache["n1"]["O"], _df(3))
